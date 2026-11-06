package control

import (
	"agentworkspace/backend/internal/contracts"
	"context"
	_ "embed"
	"encoding/json"
	"fmt"
	"gorm.io/gorm"
	"reflect"
)

//go:embed builtin-tools.json
var builtinJSON []byte

func BuiltinTools() []contracts.BuiltinTool {
	var tools []contracts.BuiltinTool
	_ = json.Unmarshal(builtinJSON, &tools)
	return tools
}
func (s *Service) checkSnapshot(tx *gorm.DB, snap contracts.Snapshot) string {
	var user User
	if tx.Where("id=? AND enabled=true", snap.Context.UserId).Take(&user).Error != nil {
		return "USER_DISABLED"
	}
	check := func(kind, id string, revision int64) bool {
		v, e := get(tx, kind, id)
		return e == nil && flag(v, "enabled") && num(v, "revision") == revision
	}
	if !check("models", snap.Model.Id, snap.Model.Revision) || !allowed("models", snap.Model.BaseUrl, snap.Model.CredentialRef) {
		return "CAPABILITY_CHANGED"
	}
	for _, v := range snap.Skills {
		if !check("skills", v.Id, v.Revision) {
			return "CAPABILITY_CHANGED"
		}
	}
	for _, v := range snap.McpConnections {
		if !check("mcp_connections", v.Id, v.Revision) || !allowed("mcp", v.Endpoint, v.CredentialRef) {
			return "CAPABILITY_CHANGED"
		}
		conn, e := get(tx, "mcp_connections", v.Id)
		if e != nil || str(conn, "probe_status") != "success" {
			return "CAPABILITY_CHANGED"
		}
	}
	for _, v := range snap.Tools {
		if !check("mcp_tools", v.NamespacedToolId, v.Revision) {
			return "CAPABILITY_CHANGED"
		}
		tool, e := get(tx, "mcp_tools", v.NamespacedToolId)
		if e != nil {
			return "CAPABILITY_CHANGED"
		}
		conn, e := get(tx, "mcp_connections", v.ConnectionId)
		if e != nil || !flag(tool, "available") || str(tool, "schema_hash") != v.SchemaHash || !trusted(str(conn, "endpoint"), str(conn, "credential_ref"), v.RemoteName) {
			return "CAPABILITY_CHANGED"
		}
	}
	if snap.BuiltinTools != nil {
		known := map[string]contracts.BuiltinTool{}
		for _, v := range BuiltinTools() {
			known[v.NamespacedToolId] = v
		}
		for _, v := range *snap.BuiltinTools {
			var expected, actual any
			_ = json.Unmarshal(encode(known[v.NamespacedToolId]), &expected)
			_ = json.Unmarshal(encode(v), &actual)
			if !reflect.DeepEqual(expected, actual) {
				return "CAPABILITY_CHANGED"
			}
		}
	}
	for _, f := range snap.FileRefs {
		var n int64
		if tx.Raw("SELECT count(*) FROM backend.files WHERE id=? AND owner_id=? AND data->>'status'='READY' AND data->>'sha256'=?", f.Id, snap.Context.UserId, f.Sha256).Scan(&n).Error != nil || n != 1 {
			return "CAPABILITY_CHANGED"
		}
	}
	return ""
}

// CheckExecution must run inside the caller's transaction after taking control lock 210002.
// This serializes writes against configuration changes, decisions and cancellation.
func (s *Service) CheckExecution(tx *gorm.DB, run string) (contracts.Start, error) {
	var row struct {
		StartPayload    json.RawMessage
		Active          bool
		CancelRequested bool
	}
	var start contracts.Start
	if e := tx.Table("backend.run_submissions").Where("run_id=?", run).Take(&row).Error; e != nil {
		return start, e
	}
	if !row.Active || row.CancelRequested {
		return start, fmt.Errorf("RUN_CANCELLED")
	}
	if e := json.Unmarshal(row.StartPayload, &start); e != nil {
		return start, e
	}
	if reason := s.checkSnapshot(tx, start.EffectiveCapabilities); reason != "" {
		return start, fmt.Errorf("%s", reason)
	}
	return start, nil
}
func (s *Service) CheckRun(ctx context.Context, run string) error {
	return s.DB.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		if e := lock(tx); e != nil {
			return e
		}
		_, e := s.CheckExecution(tx, run)
		return e
	})
}
