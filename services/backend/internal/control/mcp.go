package control

import (
	"agentworkspace/backend/internal/contracts"
	"crypto/sha256"
	"encoding/hex"
	"github.com/gin-gonic/gin"
	"gorm.io/gorm"
	"time"
)

func (s *Service) Discover(c *gin.Context) {
	input, ok := body(c, "RevisionWrite")
	if !ok {
		return
	}
	id := c.Param("id")
	connection, e := get(s.DB.WithContext(c.Request.Context()), "mcp_connections", id)
	if e != nil {
		fail(c, e)
		return
	}
	if num(input, "revision") != num(connection, "revision") {
		fail(c, conflict())
		return
	}
	if !flag(connection, "enabled") {
		fail(c, invalid("请先启用连接"))
		return
	}
	var result object
	probeErr := s.runtime(c.Request.Context(), "/internal/mcp/discover", object{"endpoint": connection["endpoint"], "credential_ref": connection["credential_ref"]}, &result)
	if probeErr == nil {
		probeErr = contracts.Validate("DiscoverResult", result)
	}
	e = s.DB.WithContext(c.Request.Context()).Transaction(func(tx *gorm.DB) error {
		if e := lock(tx); e != nil {
			return e
		}
		latest, e := get(tx, "mcp_connections", id)
		if e != nil {
			return e
		}
		if num(latest, "revision") != num(input, "revision") {
			return conflict()
		}
		connection = latest
		connection["revision"] = num(connection, "revision") + 1
		connection["last_probe_at"] = time.Now().UTC().Format(time.RFC3339Nano)
		connection["probe_error"] = ""
		connection["probe_status"] = "success"
		if probeErr != nil {
			connection["probe_status"] = "failed"
			connection["probe_error"] = "MCP_UNAVAILABLE"
		} else {
			oldTools, e := list(tx, "mcp_tools")
			if e != nil {
				return e
			}
			seen := map[string]bool{}
			for _, raw := range result["tools"].([]any) {
				t := raw.(map[string]any)
				name := str(t, "remote_name")
				tid := toolID(id, name)
				if seen[tid] {
					return invalid("工具名称冲突")
				}
				seen[tid] = true
				hash := sha256.Sum256(encode(t["input_schema"]))
				schemaHash := hex.EncodeToString(hash[:])
				revision := int64(1)
				enabled := false
				old, e := get(tx, "mcp_tools", tid)
				if e != nil && e != gorm.ErrRecordNotFound {
					return e
				}
				if e == nil {
					if str(old, "remote_name") != name {
						return invalid("工具命名冲突")
					}
					revision = num(old, "revision")
					enabled = flag(old, "enabled")
					if str(old, "schema_hash") != schemaHash || str(old, "description") != str(t, "description") || !flag(old, "available") || flag(old, "trusted_read_only") != flag(t, "trusted_read_only") {
						revision++
						enabled = false
					}
				}
				readOnly := flag(t, "trusted_read_only") && trusted(str(connection, "endpoint"), str(connection, "credential_ref"), name)
				if !readOnly {
					enabled = false
				}
				v := object{"namespaced_tool_id": tid, "connection_id": id, "remote_name": name, "description": t["description"], "input_schema": t["input_schema"], "schema_hash": schemaHash, "revision": revision, "enabled": enabled, "available": true, "trusted_read_only": readOnly}
				if e = put(tx, "mcp_tools", v); e != nil {
					return e
				}
			}
			for _, t := range oldTools {
				if str(t, "connection_id") == id && !seen[str(t, "namespaced_tool_id")] {
					t["enabled"] = false
					t["available"] = false
					t["revision"] = num(t, "revision") + 1
					if e = put(tx, "mcp_tools", t); e != nil {
						return e
					}
				}
			}
		}
		if e = put(tx, "mcp_connections", connection); e != nil {
			return e
		}
		return audit(tx, c, "mcp.discover", id, object{"revision": connection["revision"], "probe_status": connection["probe_status"]})
	})
	if e != nil {
		fail(c, e)
		return
	}
	c.JSON(200, connection)
}
func (s *Service) Tools(c *gin.Context) {
	tx := s.DB.WithContext(c.Request.Context())
	if _, e := get(tx, "mcp_connections", c.Param("id")); e != nil {
		fail(c, e)
		return
	}
	items, e := list(tx, "mcp_tools")
	if e != nil {
		fail(c, e)
		return
	}
	out := []object{}
	for _, v := range items {
		if str(v, "connection_id") == c.Param("id") {
			out = append(out, v)
		}
	}
	c.JSON(200, gin.H{"items": out})
}
func (s *Service) SetTool(c *gin.Context) {
	v, ok := body(c, "EnablementWrite")
	if !ok {
		return
	}
	var tool object
	e := s.DB.WithContext(c.Request.Context()).Transaction(func(tx *gorm.DB) error {
		if e := lock(tx); e != nil {
			return e
		}
		conn, e := get(tx, "mcp_connections", c.Param("id"))
		if e != nil {
			return e
		}
		tool, e = get(tx, "mcp_tools", c.Param("tool_id"))
		if e != nil {
			return e
		}
		if str(tool, "connection_id") != str(conn, "id") {
			return gorm.ErrRecordNotFound
		}
		if num(v, "revision") != num(tool, "revision") {
			return conflict()
		}
		if flag(v, "enabled") && (!flag(conn, "enabled") || str(conn, "probe_status") != "success" || !flag(tool, "available") || !flag(tool, "trusted_read_only") || !trusted(str(conn, "endpoint"), str(conn, "credential_ref"), str(tool, "remote_name"))) {
			return fault{403, "TOOL_DENIED", "工具未通过发现或部署只读准入"}
		}
		tool["enabled"] = flag(v, "enabled")
		tool["revision"] = num(tool, "revision") + 1
		if e = put(tx, "mcp_tools", tool); e != nil {
			return e
		}
		return audit(tx, c, "mcp.tool_enablement", str(tool, "namespaced_tool_id"), object{"enabled": tool["enabled"], "revision": tool["revision"]})
	})
	if e != nil {
		fail(c, e)
		return
	}
	c.JSON(200, tool)
}
func enabledTools(tx *gorm.DB) ([]object, []object, error) {
	tools, e := list(tx, "mcp_tools")
	if e != nil {
		return nil, nil, e
	}
	connections, e := list(tx, "mcp_connections")
	if e != nil {
		return nil, nil, e
	}
	available := map[string]object{}
	for _, c := range connections {
		if flag(c, "enabled") && str(c, "probe_status") == "success" && allowed("mcp", str(c, "endpoint"), str(c, "credential_ref")) {
			available[str(c, "id")] = c
		}
	}
	out := []object{}
	used := map[string]bool{}
	conns := []object{}
	for _, t := range tools {
		c := available[str(t, "connection_id")]
		if c != nil && flag(t, "enabled") && flag(t, "available") && flag(t, "trusted_read_only") && trusted(str(c, "endpoint"), str(c, "credential_ref"), str(t, "remote_name")) {
			out = append(out, t)
			if !used[str(c, "id")] {
				conns = append(conns, c)
				used[str(c, "id")] = true
			}
		}
	}
	return out, conns, nil
}
func (s *Service) CatalogTools(c *gin.Context) {
	v, _, e := enabledTools(s.DB.WithContext(c.Request.Context()))
	if e != nil {
		fail(c, e)
		return
	}
	c.JSON(200, gin.H{"items": v})
}
