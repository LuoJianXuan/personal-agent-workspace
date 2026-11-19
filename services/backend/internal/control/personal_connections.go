package control

import (
	"agentworkspace/backend/internal/contracts"
	"agentworkspace/backend/internal/credentials"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"net/http"
	"os"
	"slices"
	"sort"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"gorm.io/gorm"
)

const personalTable = "backend.personal_connections"
const probeTable = "backend.personal_probes"
const secretTable = "backend.personal_credentials"

type personalConnectionRow struct {
	ID, OwnerID, ConnectorID, Status           string
	Revision, CredentialVersion, GrantRevision int64
	Catalog, Grants                            json.RawMessage
}

type personalSecretRow struct {
	KeyID      string
	Ciphertext []byte
}

type personalProbeRow struct {
	ID, ConnectionID, OwnerID    string
	KeyID                        string
	Ciphertext                   []byte
	CredentialVersion            int64
	ReplacesCredential, Received bool
	Catalog                      json.RawMessage
	ExpiresAt                    time.Time
}

type personalTool struct {
	Name        string
	Description string
	InputSchema json.RawMessage
	Fingerprint string
	Policy      string
	Unsupported bool
}

func personalDefinitions() ([]policyEntry, error) {
	p, err := policy()
	if err != nil {
		return nil, err
	}
	defs := []policyEntry{}
	for _, entry := range p["mcp"] {
		if entry.PersonalConnector != "" {
			defs = append(defs, entry)
		}
	}
	return defs, nil
}

func personalDefinition(id string) (policyEntry, error) {
	defs, err := personalDefinitions()
	if err != nil {
		return policyEntry{}, err
	}
	for _, def := range defs {
		if def.PersonalConnector == id {
			return def, nil
		}
	}
	return policyEntry{}, gorm.ErrRecordNotFound
}

func connectionKeyring() (*credentials.Keyring, error) {
	if os.Getenv("PERSONAL_CONNECTIONS_ENABLED") != "true" {
		return nil, connectionError("CONNECTION_SECRET_UNAVAILABLE", "个人连接尚未启用")
	}
	keys, err := credentials.Configured()
	if err != nil {
		return nil, connectionError("CONNECTION_SECRET_UNAVAILABLE", "个人连接的凭据存储暂不可用")
	}
	return keys, nil
}

func connectionError(code, message string) error { return fault{409, code, message} }

func personalOwner(c *gin.Context) string { return c.MustGet("user").(User).ID }

func connectionAAD(row personalConnectionRow, version int64, def policyEntry) []byte {
	return encode([]any{row.ID, row.OwnerID, row.ConnectorID, version, def.Endpoint, def.CredentialRef})
}

func fingerprint(value any) string {
	sum := sha256.Sum256(encode(value))
	return hex.EncodeToString(sum[:])
}

func personalRisk(def policyEntry, name string) string {
	switch {
	case slices.Contains(def.BlockedTools, name):
		return "blocked"
	case slices.Contains(def.ReadOnlyTools, name):
		return "read"
	case slices.Contains(def.ApprovalRequiredTools, name):
		return "confirm"
	default:
		return "unknown"
	}
}

func personalCatalog(raw json.RawMessage, def policyEntry) ([]personalTool, error) {
	items := []personalTool{}
	if err := json.Unmarshal(raw, &items); err != nil {
		return nil, err
	}
	for i := range items {
		item := &items[i]
		risk := personalRisk(def, item.Name)
		if item.Unsupported {
			risk = "blocked"
		}
		if item.Policy != risk {
			item.Policy = risk
			item.Fingerprint = fingerprint([]string{item.Fingerprint, risk})
		}
	}
	return items, nil
}

func (row personalConnectionRow) authorized(def policyEntry) ([]personalTool, error) {
	if row.Status != "ready" {
		return []personalTool{}, nil
	}
	items, err := personalCatalog(row.Catalog, def)
	if err != nil {
		return nil, err
	}
	var grants map[string]string
	if err := json.Unmarshal(row.Grants, &grants); err != nil {
		return nil, err
	}
	return slices.DeleteFunc(items, func(t personalTool) bool {
		return t.Policy == "blocked" || grants[t.Name] != t.Fingerprint
	}), nil
}

func personalRow(tx *gorm.DB, owner, connector string) (personalConnectionRow, error) {
	var row personalConnectionRow
	err := tx.Table(personalTable).Where("owner_id=? AND connector_id=?", owner, connector).Take(&row).Error
	return row, err
}

func candidate(tx *gorm.DB, row personalConnectionRow) (personalProbeRow, error) {
	var probe personalProbeRow
	err := tx.Table(probeTable).Where("connection_id=? AND owner_id=? AND expires_at>now()", row.ID, row.OwnerID).Take(&probe).Error
	return probe, err
}

func personalView(tx *gorm.DB, owner string, def policyEntry) (object, error) {
	view := object{"connector_id": def.PersonalConnector, "name": def.ConnectorName, "status": "disconnected", "revision": 0, "catalog_hash": "", "pending": false, "tools": []object{}}
	view["presentation"] = def.Presentation
	if _, err := connectionKeyring(); err != nil {
		view["status"] = "unconfigured"
		return view, nil
	}
	row, err := personalRow(tx, owner, def.PersonalConnector)
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return view, nil
	}
	if err != nil {
		return nil, err
	}
	view["connection_id"], view["status"], view["revision"] = row.ID, row.Status, row.Revision
	probe, err := candidate(tx, row)
	if err != nil && !errors.Is(err, gorm.ErrRecordNotFound) {
		return nil, err
	}
	raw := row.Catalog
	if len(probe.Catalog) > 0 {
		view["pending"] = true
		if row.Status == "disconnected" {
			view["status"] = "pending"
		}
		raw = probe.Catalog
	}
	items, err := personalCatalog(raw, def)
	if err != nil {
		return nil, err
	}
	if len(probe.Catalog) > 0 {
		view["catalog_hash"] = fingerprint(items)
	}
	active, err := row.authorized(def)
	if err != nil {
		return nil, err
	}
	tools := make([]object, 0, len(items))
	for _, tool := range items {
		granted := slices.ContainsFunc(active, func(v personalTool) bool { return v.Fingerprint == tool.Fingerprint })
		preview := object{"name": tool.Name, "policy": tool.Policy, "granted": granted}
		if tool.Unsupported {
			preview["reason"] = "UNSUPPORTED_SCHEMA"
		} else if tool.Policy == "blocked" {
			preview["reason"] = "PLATFORM_BLOCKED"
		}
		tools = append(tools, preview)
	}
	view["tools"] = tools
	return view, nil
}

func (s *Service) PersonalConnections(c *gin.Context) {
	if os.Getenv("PERSONAL_CONNECTIONS_ENABLED") != "true" {
		c.JSON(http.StatusOK, object{"items": []object{}})
		return
	}
	defs, err := personalDefinitions()
	if err != nil {
		fail(c, err)
		return
	}
	items := make([]object, 0, len(defs))
	tx := s.DB.WithContext(c.Request.Context())
	for _, def := range defs {
		def, err := publication(tx, def)
		if err != nil {
			fail(c, err)
			return
		}
		if !def.Published {
			continue
		}
		item, err := personalView(tx, personalOwner(c), def)
		if err != nil {
			fail(c, err)
			return
		}
		items = append(items, item)
	}
	c.JSON(http.StatusOK, object{"items": items})
}

func (s *Service) PersonalConnection(c *gin.Context) {
	def, err := personalDefinition(c.Param("connector"))
	if err != nil {
		fail(c, err)
		return
	}
	s.writeConnection(c, def)
}

func (s *Service) CleanupPersonalProbes(ctx context.Context) {
	ticker := time.NewTicker(5 * time.Minute)
	defer ticker.Stop()
	for {
		// Expiration is enforced by each lookup; here we remove the ciphertext.
		_ = s.DB.WithContext(ctx).Exec("DELETE FROM " + probeTable + " WHERE expires_at<=now()").Error
		select {
		case <-ticker.C:
		case <-ctx.Done():
			return
		}
	}
}

func (s *Service) writeConnection(c *gin.Context, def policyEntry) {
	tx := s.DB.WithContext(c.Request.Context())
	// All mutation responses use the same presentation/defaults as the catalog,
	// including discard/revoke, which are also allowed after unpublishing.
	effective, err := publication(tx, def)
	if err != nil {
		fail(c, err)
		return
	}
	view, err := personalView(tx, personalOwner(c), effective)
	if err != nil {
		fail(c, err)
		return
	}
	c.Header("Cache-Control", "no-store")
	c.JSON(http.StatusOK, view)
}

func openActive(tx *gorm.DB, keys *credentials.Keyring, row personalConnectionRow, def policyEntry) (string, error) {
	var secret personalSecretRow
	err := tx.Table(secretTable).Where("connection_id=? AND owner_id=?", row.ID, row.OwnerID).Take(&secret).Error
	if err == nil {
		if plain, err := keys.Open(secret.KeyID, secret.Ciphertext, connectionAAD(row, row.CredentialVersion, def)); err == nil {
			return plain, nil
		}
	}
	return "", connectionError("CONNECTION_SECRET_UNAVAILABLE", "凭据不可用，请更换 Token")
}

func (s *Service) ProbePersonalConnection(c *gin.Context) {
	input, ok := body(c, "PersonalProbeWrite")
	if !ok {
		return
	}
	keys, err := connectionKeyring()
	if err != nil {
		fail(c, err)
		return
	}
	def, err := personalDefinition(c.Param("connector"))
	if err != nil {
		fail(c, err)
		return
	}
	owner := personalOwner(c)
	var row personalConnectionRow
	var probe personalProbeRow
	db := s.DB.WithContext(c.Request.Context())
	err = db.Transaction(func(tx *gorm.DB) error {
		if err := lock(tx); err != nil {
			return err
		}
		var err error
		def, err = publishedDefinition(tx, def.PersonalConnector)
		if err != nil {
			return err
		}
		token := str(input, "token")
		row, err = personalRow(tx, owner, def.PersonalConnector)
		if errors.Is(err, gorm.ErrRecordNotFound) && num(input, "revision") == 0 && token != "" {
			row = personalConnectionRow{ID: uuid.NewString(), OwnerID: owner, ConnectorID: def.PersonalConnector}
			err = tx.Exec("INSERT INTO "+personalTable+"(id,owner_id,connector_id) VALUES(?,?,?)", row.ID, row.OwnerID, row.ConnectorID).Error
		}
		if err != nil {
			return err
		}
		if row.Revision != num(input, "revision") {
			return conflict()
		}
		var recent int64
		if err := tx.Raw("SELECT count(*) FROM backend.admin_audits WHERE actor_id=? AND action='connection.probe' AND created_at > now()-interval '1 minute'", owner).Scan(&recent).Error; err != nil {
			return err
		}
		if recent >= 6 {
			return fault{429, "MCP_RATE_LIMIT", "连接测试过于频繁，请稍后再试"}
		}
		probe = personalProbeRow{ID: uuid.NewString(), ConnectionID: row.ID, OwnerID: row.OwnerID,
			CredentialVersion: row.CredentialVersion, ReplacesCredential: token != ""}
		if token == "" {
			if token, err = openActive(tx, keys, row, def); err != nil {
				return err
			}
		} else {
			probe.CredentialVersion++
		}
		probe.KeyID, probe.Ciphertext, err = keys.Seal(token, connectionAAD(row, probe.CredentialVersion, def))
		if err != nil {
			return err
		}
		if err := tx.Exec("DELETE FROM "+probeTable+" WHERE connection_id=?", row.ID).Error; err != nil {
			return err
		}
		if err := tx.Exec("INSERT INTO "+probeTable+"(id,connection_id,owner_id,key_id,ciphertext,credential_version,replaces_credential) VALUES(?,?,?,?,?,?,?)",
			probe.ID, row.ID, row.OwnerID, probe.KeyID, probe.Ciphertext, probe.CredentialVersion, probe.ReplacesCredential).Error; err != nil {
			return err
		}
		if err := tx.Exec("UPDATE "+personalTable+" SET revision=revision+1 WHERE id=?", row.ID).Error; err != nil {
			return err
		}
		return audit(tx, c, "connection.probe", row.ID, object{"replacement": probe.ReplacesCredential})
	})
	if err != nil {
		fail(c, err)
		return
	}
	var result object
	err = s.runtime(c.Request.Context(), "/internal/mcp/personal-discover", object{"operation_id": probe.ID}, &result)
	if err == nil {
		err = contracts.Validate("DiscoverResult", result)
	}
	if err != nil {
		var rf fault
		s.DB.Transaction(func(tx *gorm.DB) error {
			if err := lock(tx); err != nil {
				return err
			}
			deletion := tx.Exec("DELETE FROM "+probeTable+" WHERE id=?", probe.ID)
			if deletion.Error != nil {
				return deletion.Error
			}
			if deletion.RowsAffected == 1 && !probe.ReplacesCredential && errors.As(err, &rf) && rf.code == "CONNECTION_AUTH_REQUIRED" {
				return tx.Exec("UPDATE "+personalTable+" SET status='auth_required',revision=revision+1 WHERE id=? AND credential_version=?", row.ID, row.CredentialVersion).Error
			}
			return nil
		})
		if errors.As(err, &rf) {
			fail(c, rf)
		} else {
			fail(c, connectionError("CONNECTION_UNAVAILABLE", "无法发现服务工具，请检查连接后重试"))
		}
		return
	}
	items := make([]personalTool, 0)
	for _, entry := range result["tools"].([]any) {
		tool := entry.(map[string]any)
		name := str(tool, "remote_name")
		risk := personalRisk(def, name)
		unsupported := flag(tool, "unsupported_schema")
		if unsupported {
			risk = "blocked"
		}
		items = append(items, personalTool{Name: name, Description: str(tool, "description"), InputSchema: encode(tool["input_schema"]),
			Fingerprint: fingerprint([]any{def.Endpoint, def.CredentialRef, risk, tool}), Policy: risk, Unsupported: unsupported})
	}
	sort.Slice(items, func(i, j int) bool { return items[i].Name < items[j].Name })
	err = db.Transaction(func(tx *gorm.DB) error {
		if err := lock(tx); err != nil {
			return err
		}
		published, err := publishedDefinition(tx, def.PersonalConnector)
		if err != nil || published.PublicationRevision != def.PublicationRevision {
			return conflict()
		}
		result := tx.Exec("UPDATE "+probeTable+" SET catalog=?::jsonb WHERE id=? AND expires_at>now()", string(encode(items)), probe.ID)
		if result.Error != nil {
			return result.Error
		}
		if result.RowsAffected != 1 {
			return conflict()
		}
		// A refresh immediately removes stale grants from the effective catalog.
		// Replacement credentials stay staged until explicit user consent.
		if !probe.ReplacesCredential {
			// Delete changed grants permanently. A removed tool returning with the
			// same fingerprint must still wait for fresh consent.
			if err := tx.Exec(`UPDATE backend.personal_connections SET catalog=?::jsonb,
				grants=COALESCE((SELECT jsonb_object_agg(t->>'Name',t->>'Fingerprint')
					FROM jsonb_array_elements(?::jsonb) t
					WHERE grants->>(t->>'Name')=t->>'Fingerprint'), '{}'::jsonb)
				WHERE id=?`, string(encode(items)), string(encode(items)), row.ID).Error; err != nil {
				return err
			}
		}
		return nil
	})
	if err != nil {
		fail(c, err)
		return
	}
	s.writeConnection(c, def)
}

func (s *Service) GrantPersonalConnection(c *gin.Context) {
	input, ok := body(c, "PersonalGrantWrite")
	if !ok {
		return
	}
	if _, err := connectionKeyring(); err != nil {
		fail(c, err)
		return
	}
	def, err := personalDefinition(c.Param("connector"))
	if err != nil {
		fail(c, err)
		return
	}
	err = s.DB.WithContext(c.Request.Context()).Transaction(func(tx *gorm.DB) error {
		if err := lock(tx); err != nil {
			return err
		}
		published, err := publishedDefinition(tx, def.PersonalConnector)
		if err != nil {
			return err
		}
		def = published
		row, err := personalRow(tx, personalOwner(c), def.PersonalConnector)
		if err != nil {
			return err
		}
		if row.Revision != num(input, "revision") {
			return conflict()
		}
		probe, err := candidate(tx, row)
		if err != nil || len(probe.Catalog) == 0 {
			return connectionError("CONNECTION_CATALOG_CHANGED", "请重新验证连接，再确认授权")
		}
		items, err := personalCatalog(probe.Catalog, def)
		if err != nil || fingerprint(items) != str(input, "catalog_hash") {
			return connectionError("CONNECTION_CATALOG_CHANGED", "工具清单已变化，请重新确认")
		}
		grants := map[string]string{}
		for _, tool := range items {
			if tool.Policy == "read" || (tool.Policy != "blocked" && str(input, "mode") == "full") {
				grants[tool.Name] = tool.Fingerprint
			}
		}
		if len(grants) == 0 {
			return connectionError("CONNECTION_GRANT_REQUIRED", "当前权限范围内没有可用工具")
		}
		if err := tx.Exec(`INSERT INTO backend.personal_credentials(connection_id,owner_id,key_id,ciphertext)
			VALUES(?,?,?,?) ON CONFLICT(connection_id) DO UPDATE SET key_id=EXCLUDED.key_id,ciphertext=EXCLUDED.ciphertext`,
			row.ID, row.OwnerID, probe.KeyID, probe.Ciphertext).Error; err != nil {
			return err
		}
		if err := tx.Exec(`UPDATE backend.personal_connections SET catalog=?::jsonb,grants=?::jsonb,
			status='ready',revision=revision+1,grant_revision=grant_revision+1,credential_version=? WHERE id=?`,
			string(encode(items)), string(encode(grants)), probe.CredentialVersion, row.ID).Error; err != nil {
			return err
		}
		if err := tx.Exec("DELETE FROM "+probeTable+" WHERE id=?", probe.ID).Error; err != nil {
			return err
		}
		return audit(tx, c, "connection.grant", row.ID, object{"mode": input["mode"], "catalog_hash": input["catalog_hash"], "grant_revision": row.GrantRevision + 1})
	})
	if err != nil {
		fail(c, err)
		return
	}
	s.writeConnection(c, def)
}

func (s *Service) RevokePersonalConnection(c *gin.Context) { s.closePersonal(c, true) }
func (s *Service) DiscardPersonalProbe(c *gin.Context)     { s.closePersonal(c, false) }

func (s *Service) closePersonal(c *gin.Context, revoke bool) {
	input, ok := body(c, "RevisionWrite")
	if !ok {
		return
	}
	def, err := personalDefinition(c.Param("connector"))
	if err != nil {
		fail(c, err)
		return
	}
	err = s.DB.WithContext(c.Request.Context()).Transaction(func(tx *gorm.DB) error {
		if err := lock(tx); err != nil {
			return err
		}
		row, err := personalRow(tx, personalOwner(c), def.PersonalConnector)
		if err != nil {
			return err
		}
		if row.Revision != num(input, "revision") {
			return conflict()
		}
		if err := tx.Exec("DELETE FROM "+probeTable+" WHERE connection_id=?", row.ID).Error; err != nil {
			return err
		}
		if !revoke {
			return tx.Exec("UPDATE "+personalTable+" SET revision=revision+1 WHERE id=?", row.ID).Error
		}
		if err := tx.Exec("DELETE FROM "+secretTable+" WHERE connection_id=?", row.ID).Error; err != nil {
			return err
		}
		if err := tx.Exec(`UPDATE backend.personal_connections SET status='disconnected', catalog='[]', grants='{}',
			revision=revision+1,grant_revision=grant_revision+1 WHERE id=?`, row.ID).Error; err != nil {
			return err
		}
		return audit(tx, c, "connection.revoke", row.ID, object{"grant_revision": row.GrantRevision + 1})
	})
	if err != nil {
		fail(c, err)
		return
	}
	s.writeConnection(c, def)
}

func personalToolDisplay(def policyEntry, name string) string {
	labels := map[string]string{"campaign-calendar": "查询活动日历", "now-time-info": "查询当前时间", "create-order": "创建订单", "query-meals": "查询菜单"}
	label := labels[name]
	if label == "" {
		label = strings.ReplaceAll(name, "-", " ")
	}
	return def.ConnectorName + " · " + label
}

func (t personalTool) snapshot(row personalConnectionRow, def policyEntry) object {
	mode := "write"
	if t.Policy == "read" {
		mode = "read"
	}
	return object{"namespaced_tool_id": toolID(row.ID, t.Name), "connection_id": row.ID, "remote_name": t.Name,
		"description": t.Description, "display_name": personalToolDisplay(def, t.Name), "input_schema": t.InputSchema, "fingerprint": t.Fingerprint,
		"schema_hash": fingerprint(t.InputSchema), "revision": row.GrantRevision, "access_mode": mode, "requires_approval": mode == "write"}
}

func personalCapabilities(tx *gorm.DB, owner string) ([]object, []object, error) {
	tools, connections := []object{}, []object{}
	if _, err := connectionKeyring(); err != nil {
		return tools, connections, nil
	}
	var rows []personalConnectionRow
	if err := tx.Table(personalTable).Where("owner_id=? AND status='ready'", owner).Order("id").Find(&rows).Error; err != nil {
		return nil, nil, err
	}
	for _, row := range rows {
		def, err := publishedDefinition(tx, row.ConnectorID)
		if errors.Is(err, gorm.ErrRecordNotFound) {
			continue
		}
		if err != nil {
			return nil, nil, err
		}
		items, err := row.authorized(def)
		if err != nil {
			return nil, nil, err
		}
		if len(items) == 0 {
			continue
		}
		connections = append(connections, object{"id": row.ID, "endpoint": def.Endpoint, "credential_ref": def.CredentialRef,
			"connector_id": row.ConnectorID, "credential_version": row.CredentialVersion, "grant_revision": row.GrantRevision,
			"connector_revision": def.PublicationRevision,
			"revision":           row.GrantRevision, "max_calls_per_minute": def.MaxCallsPerMinute})
		for _, t := range items {
			tools = append(tools, t.snapshot(row, def))
		}
	}
	return tools, connections, nil
}
