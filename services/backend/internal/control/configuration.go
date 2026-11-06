package control

import (
	"agentworkspace/backend/internal/contracts"
	"agentworkspace/backend/internal/platform"
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgconn"
	"golang.org/x/crypto/bcrypt"
	"gorm.io/gorm"
	"io"
	"net/http"
	"os"
	"strings"
	"time"
)

type object = map[string]any

func str(v object, k string) string { s, _ := v[k].(string); return s }
func flag(v object, k string) bool  { b, _ := v[k].(bool); return b }
func num(v object, k string) int64 {
	switch n := v[k].(type) {
	case float64:
		return int64(n)
	case int64:
		return n
	case int:
		return int64(n)
	}
	return 0
}
func encode(v any) []byte   { b, _ := json.Marshal(v); return b }
func clone(v object) object { var out object; _ = json.Unmarshal(encode(v), &out); return out }

type fault struct {
	status        int
	code, message string
}

func (f fault) Error() string  { return f.code }
func invalid(msg string) error { return fault{400, "INVALID_ARGUMENT", msg} }
func conflict() error          { return fault{409, "CONFIG_CONFLICT", "配置已改变，请刷新后重试"} }
func unavailable() error {
	return fault{409, "MODEL_UNAVAILABLE", "模型、凭据或本轮所需能力不可用"}
}
func fail(c *gin.Context, err error) {
	var f fault
	if errors.As(err, &f) {
		platform.Error(c, f.status, f.code, f.message)
		return
	}
	if errors.Is(err, gorm.ErrRecordNotFound) {
		platform.Error(c, 404, "NOT_FOUND", "资源不存在或不可见")
		return
	}
	platform.Error(c, 503, "DEPENDENCY_UNAVAILABLE", "服务暂不可用，请稍后重试")
}

// WriteFailure preserves safe control-plane error details across the entry boundary.
func WriteFailure(c *gin.Context, err error) { fail(c, err) }
func body(c *gin.Context, name string) (object, bool) {
	v, e := contracts.Decode(name, c.Request.Body)
	if e != nil {
		platform.Error(c, 400, "INVALID_ARGUMENT", "配置格式无效、缺少字段或含不支持的选项")
		return nil, false
	}
	return v, true
}
func lock(tx *gorm.DB) error { return tx.Exec("SELECT pg_advisory_xact_lock(210002)").Error }

type record struct {
	ID   string
	Data json.RawMessage
}

func table(kind string) string {
	switch kind {
	case "models", "skills", "mcp_connections", "mcp_tools":
		return "backend." + kind
	}
	panic("invalid resource table")
}
func get(tx *gorm.DB, kind, id string) (object, error) {
	if kind != "mcp_tools" {
		if _, e := uuid.Parse(id); e != nil {
			return nil, gorm.ErrRecordNotFound
		}
	}
	var row record
	if e := tx.Table(table(kind)).Where("id = ?", id).Take(&row).Error; e != nil {
		return nil, e
	}
	var v object
	e := json.Unmarshal(row.Data, &v)
	return v, e
}
func list(tx *gorm.DB, kind string) ([]object, error) {
	var rows []record
	if e := tx.Table(table(kind)).Order("id").Find(&rows).Error; e != nil {
		return nil, e
	}
	result := []object{}
	for _, row := range rows {
		var v object
		if e := json.Unmarshal(row.Data, &v); e != nil {
			return nil, e
		}
		result = append(result, v)
	}
	return result, nil
}
func put(tx *gorm.DB, kind string, v object) error {
	id := str(v, "id")
	if kind == "mcp_tools" {
		id = str(v, "namespaced_tool_id")
		return tx.Exec("INSERT INTO backend.mcp_tools(id,connection_id,data) VALUES(?,?,?::jsonb) ON CONFLICT(id) DO UPDATE SET data=EXCLUDED.data", id, str(v, "connection_id"), string(encode(v))).Error
	}
	return tx.Exec("INSERT INTO "+table(kind)+"(id,data) VALUES(?,?::jsonb) ON CONFLICT(id) DO UPDATE SET data=EXCLUDED.data", id, string(encode(v))).Error
}
func audit(tx *gorm.DB, c *gin.Context, action, id string, changes object) error {
	return tx.Exec("INSERT INTO backend.admin_audits(id,actor_id,action,object_id,request_id,safe_changes) VALUES(?,?,?,?,?,?::jsonb)", uuid.NewString(), c.MustGet("user").(User).ID, action, id, c.GetString("request_id"), string(encode(changes))).Error
}

type policyEntry struct {
	Endpoint      string   `json:"endpoint"`
	CredentialRef string   `json:"credential_ref"`
	ReadOnlyTools []string `json:"read_only_tools"`
}

func policy() (map[string][]policyEntry, error) {
	raw, e := os.ReadFile(os.Getenv("ACCESS_POLICY_PATH"))
	if e != nil {
		return nil, e
	}
	var p map[string][]policyEntry
	e = json.Unmarshal(raw, &p)
	return p, e
}
func allowed(kind, endpoint, credential string) bool {
	p, e := policy()
	if e != nil {
		return false
	}
	for _, v := range p[kind] {
		if v.Endpoint == endpoint && v.CredentialRef == credential {
			return true
		}
	}
	return false
}
func trusted(endpoint, credential, name string) bool {
	p, e := policy()
	if e != nil {
		return false
	}
	for _, v := range p["mcp"] {
		if v.Endpoint == endpoint && v.CredentialRef == credential {
			for _, n := range v.ReadOnlyTools {
				if n == name {
					return true
				}
			}
		}
	}
	return false
}
func (s *Service) runtime(ctx context.Context, path string, input any, output any) error {
	var data io.Reader
	if input != nil {
		data = bytes.NewReader(encode(input))
	}
	method := "GET"
	if input != nil {
		method = "POST"
	}
	req, e := http.NewRequestWithContext(ctx, method, s.Config.RuntimeURL+path, data)
	if e != nil {
		return e
	}
	req.Header.Set("Authorization", "Bearer "+s.Config.BToR)
	req.Header.Set("Content-Type", "application/json")
	client := http.Client{Timeout: 9 * time.Second, CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse }}
	res, e := client.Do(req)
	if e != nil {
		return e
	}
	defer res.Body.Close()
	if res.StatusCode != 200 {
		return fmt.Errorf("runtime unavailable")
	}
	raw, e := io.ReadAll(io.LimitReader(res.Body, 262145))
	if e != nil || len(raw) > 262144 {
		return fmt.Errorf("invalid upstream response")
	}
	return json.Unmarshal(raw, output)
}
func (s *Service) deployment(ctx context.Context) (contracts.DeploymentCatalog, error) {
	var status contracts.DeploymentCatalog
	e := s.runtime(ctx, "/internal/configuration/status", nil, &status)
	if e == nil {
		var v any
		_ = json.Unmarshal(encode(status), &v)
		e = contracts.Validate("DeploymentCatalog", v)
	}
	return status, e
}
func availability(v object, status contracts.DeploymentCatalog, err error) string {
	if !flag(v, "enabled") {
		return "disabled"
	}
	if err != nil {
		return "runtime_unavailable"
	}
	for _, t := range status.Models {
		if t.Endpoint == str(v, "base_url") && t.CredentialRef == str(v, "credential_ref") {
			if t.CredentialConfigured {
				return "ready_unverified"
			}
			return "credential_missing"
		}
	}
	return "target_denied"
}
func decorateModel(v object, status contracts.DeploymentCatalog, e error) object {
	v = clone(v)
	v["availability"] = availability(v, status, e)
	v["credential_configured"] = false
	for _, t := range status.Models {
		if t.Endpoint == str(v, "base_url") && t.CredentialRef == str(v, "credential_ref") {
			v["credential_configured"] = t.CredentialConfigured
		}
	}
	for _, k := range []string{"chat_status", "stream_status", "tool_loop_status"} {
		v[k] = "unverified"
	}
	return v
}
func (s *Service) Deployment(c *gin.Context) {
	v, e := s.deployment(c.Request.Context())
	if e != nil {
		fail(c, e)
		return
	}
	c.JSON(200, v)
}
func (s *Service) ListResources(kind string) gin.HandlerFunc {
	return func(c *gin.Context) {
		items, e := list(s.DB.WithContext(c.Request.Context()), kind)
		if e != nil {
			fail(c, e)
			return
		}
		if kind == "models" {
			status, err := s.deployment(c.Request.Context())
			for i, v := range items {
				items[i] = decorateModel(v, status, err)
			}
		}
		if kind == "skills" {
			for _, v := range items {
				v["personal_enabled"] = false
			}
		}
		c.JSON(200, gin.H{"items": items})
	}
}
func (s *Service) SaveResource(kind, schema string) gin.HandlerFunc {
	return func(c *gin.Context) {
		v, ok := body(c, schema)
		if !ok {
			return
		}
		id := c.Param("id")
		create := id == ""
		if create {
			id = uuid.NewString()
			if num(v, "revision") != 0 {
				fail(c, invalid("新增配置的 revision 必须为 0"))
				return
			}
		}
		if kind == "models" {
			if !allowed("models", str(v, "base_url"), str(v, "credential_ref")) {
				fail(c, invalid("地址与凭据组合不在部署准入清单"))
				return
			}
			if num(v, "max_output_tokens") >= num(v, "context_limit") {
				fail(c, invalid("输出上限必须小于上下文上限"))
				return
			}
			if flag(v, "is_default") && !flag(v, "enabled") {
				fail(c, invalid("默认模型必须启用"))
				return
			}
		}
		if kind == "mcp_connections" && !allowed("mcp", str(v, "endpoint"), str(v, "credential_ref")) {
			fail(c, invalid("MCP 地址与凭据组合未被部署允许"))
			return
		}
		e := s.DB.WithContext(c.Request.Context()).Transaction(func(tx *gorm.DB) error {
			if e := lock(tx); e != nil {
				return e
			}
			if !create {
				old, e := get(tx, kind, id)
				if e != nil {
					return e
				}
				if num(old, "revision") != num(v, "revision") {
					return conflict()
				}
			}
			v["id"] = id
			v["revision"] = num(v, "revision") + 1
			if kind == "models" && flag(v, "is_default") {
				all, e := list(tx, kind)
				if e != nil {
					return e
				}
				for _, old := range all {
					if str(old, "id") != id && flag(old, "is_default") {
						old["is_default"] = false
						old["revision"] = num(old, "revision") + 1
						if e = put(tx, kind, old); e != nil {
							return e
						}
						if e = audit(tx, c, "model.default_cleared", str(old, "id"), object{"revision": old["revision"]}); e != nil {
							return e
						}
					}
				}
			}
			if kind == "mcp_connections" {
				v["probe_status"] = "unverified"
				v["last_probe_at"] = ""
				v["probe_error"] = ""
				tools, e := list(tx, "mcp_tools")
				if e != nil {
					return e
				}
				for _, t := range tools {
					if str(t, "connection_id") == id {
						t["enabled"] = false
						t["available"] = false
						t["revision"] = num(t, "revision") + 1
						if e = put(tx, "mcp_tools", t); e != nil {
							return e
						}
					}
				}
			}
			if e := put(tx, kind, v); e != nil {
				return e
			}
			return audit(tx, c, kind+".save", id, object{"revision": v["revision"], "enabled": v["enabled"]})
		})
		if e != nil {
			fail(c, e)
			return
		}
		if kind == "models" {
			status, e := s.deployment(c.Request.Context())
			v = decorateModel(v, status, e)
		}
		if kind == "skills" {
			v["personal_enabled"] = false
		}
		c.JSON(200, v)
	}
}
func (s *Service) ValidateModel(c *gin.Context) {
	v, e := get(s.DB.WithContext(c.Request.Context()), "models", c.Param("id"))
	if e != nil {
		fail(c, e)
		return
	}
	status, e := s.deployment(c.Request.Context())
	c.JSON(200, decorateModel(v, status, e))
}
func (s *Service) CatalogModels(c *gin.Context) {
	items, e := list(s.DB.WithContext(c.Request.Context()), "models")
	if e != nil {
		fail(c, e)
		return
	}
	status, err := s.deployment(c.Request.Context())
	out := []object{}
	for _, v := range items {
		if !flag(v, "enabled") {
			continue
		}
		state := availability(v, status, err)
		out = append(out, object{"id": v["id"], "name": v["name"], "provider": v["provider"], "capabilities": v["capabilities"], "revision": v["revision"], "is_default": v["is_default"], "available": state == "ready_unverified", "availability": state})
	}
	c.JSON(200, gin.H{"items": out})
}
func personal(tx *gorm.DB, user, id string) (bool, error) {
	var values []bool
	e := tx.Raw("SELECT enabled FROM backend.user_skill_preferences WHERE user_id=? AND skill_id=?", user, id).Scan(&values).Error
	return len(values) > 0 && values[0], e
}
func (s *Service) CatalogSkills(c *gin.Context) {
	tx := s.DB.WithContext(c.Request.Context())
	items, e := list(tx, "skills")
	if e != nil {
		fail(c, e)
		return
	}
	out := []object{}
	for _, v := range items {
		if flag(v, "enabled") {
			v["personal_enabled"], e = personal(tx, c.MustGet("user").(User).ID, str(v, "id"))
			if e != nil {
				fail(c, e)
				return
			}
			out = append(out, v)
		}
	}
	c.JSON(200, gin.H{"items": out})
}
func (s *Service) Preference(c *gin.Context) {
	v, ok := body(c, "PreferenceWrite")
	if !ok {
		return
	}
	var skill object
	e := s.DB.WithContext(c.Request.Context()).Transaction(func(tx *gorm.DB) error {
		if e := lock(tx); e != nil {
			return e
		}
		var e error
		skill, e = get(tx, "skills", c.Param("id"))
		if e != nil {
			return e
		}
		if !flag(skill, "enabled") {
			return fault{409, "CAPABILITY_CHANGED", "技能已被管理员禁用"}
		}
		return tx.Exec("INSERT INTO backend.user_skill_preferences(user_id,skill_id,enabled) VALUES(?,?,?) ON CONFLICT(user_id,skill_id) DO UPDATE SET enabled=EXCLUDED.enabled", c.MustGet("user").(User).ID, c.Param("id"), flag(v, "enabled")).Error
	})
	if e != nil {
		fail(c, e)
		return
	}
	skill["personal_enabled"] = flag(v, "enabled")
	c.JSON(200, skill)
}
func (s *Service) CreateUser(c *gin.Context) {
	v, ok := body(c, "UserCreate")
	if !ok {
		return
	}
	if len(str(v, "password")) > 72 {
		fail(c, invalid("密码不能超过 72 字节"))
		return
	}
	hash, e := bcrypt.GenerateFromPassword([]byte(str(v, "password")), 12)
	if e != nil {
		fail(c, e)
		return
	}
	u := User{ID: uuid.NewString(), Username: str(v, "username"), PasswordHash: string(hash), Role: "user", Enabled: true, Revision: 1}
	e = s.DB.WithContext(c.Request.Context()).Transaction(func(tx *gorm.DB) error {
		if e := lock(tx); e != nil {
			return e
		}
		if e := tx.Create(&u).Error; e != nil {
			return e
		}
		return audit(tx, c, "user.create", u.ID, object{"role": "user", "enabled": true})
	})
	if e != nil {
		var pg *pgconn.PgError
		if errors.As(e, &pg) && pg.Code == "23505" {
			e = fault{409, "CONFIG_CONFLICT", "账号已存在"}
		}
		fail(c, e)
		return
	}
	c.JSON(200, u.Public())
}
func (s *Service) UpdateUser(c *gin.Context) {
	v, ok := body(c, "EnablementWrite")
	if !ok {
		return
	}
	if _, e := uuid.Parse(c.Param("id")); e != nil {
		fail(c, gorm.ErrRecordNotFound)
		return
	}
	var u User
	e := s.DB.WithContext(c.Request.Context()).Transaction(func(tx *gorm.DB) error {
		if e := lock(tx); e != nil {
			return e
		}
		if e := tx.Where("id=?", c.Param("id")).Take(&u).Error; e != nil {
			return e
		}
		if u.Revision != num(v, "revision") {
			return conflict()
		}
		if u.Role == "admin" && !flag(v, "enabled") {
			return fault{403, "FORBIDDEN", "首版管理员不可禁用"}
		}
		u.Enabled = flag(v, "enabled")
		u.Revision++
		if e := tx.Save(&u).Error; e != nil {
			return e
		}
		return audit(tx, c, "user.enablement", u.ID, object{"enabled": u.Enabled, "revision": u.Revision})
	})
	if e != nil {
		fail(c, e)
		return
	}
	c.JSON(200, u.Public())
}
func (s *Service) Audits(c *gin.Context) {
	type row struct {
		ID, ActorID, Action, ObjectID, RequestID string
		SafeChanges                              json.RawMessage
		CreatedAt                                time.Time
	}
	rows := []row{}
	q := s.DB.WithContext(c.Request.Context()).Table("backend.admin_audits")
	if id := c.Query("object_id"); id != "" {
		q = q.Where("object_id=?", id)
	}
	if since := c.Query("since"); since != "" {
		at, e := time.Parse(time.RFC3339, since)
		if e != nil {
			fail(c, invalid("since 必须是带时区时间"))
			return
		}
		q = q.Where("created_at>=?", at)
	}
	if e := q.Order("created_at DESC").Limit(200).Find(&rows).Error; e != nil {
		fail(c, e)
		return
	}
	items := []object{}
	for _, v := range rows {
		items = append(items, object{"id": v.ID, "actor_id": v.ActorID, "action": v.Action, "object_id": v.ObjectID, "request_id": v.RequestID, "safe_changes": v.SafeChanges, "created_at": v.CreatedAt.UTC().Format(time.RFC3339Nano)})
	}
	c.JSON(200, gin.H{"items": items})
}
func toolID(connection, name string) string {
	sum := sha256.Sum256([]byte(name))
	return "mcp_" + strings.ReplaceAll(connection, "-", "") + "_" + hex.EncodeToString(sum[:12])
}
