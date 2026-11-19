package control

import (
	"agentworkspace/backend/internal/contracts"
	"context"
	"encoding/json"
	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"gorm.io/gorm"
	"time"
)

func pick(v object, keys ...string) object {
	out := object{}
	for _, k := range keys {
		if value, ok := v[k]; ok {
			out[k] = value
		}
	}
	return out
}
func (s *Service) resolve(ctx context.Context, identity contracts.Context, input object) (contracts.Snapshot, error) {
	var snapshot contracts.Snapshot
	status, statusErr := s.deployment(ctx)
	environment := object{}
	if statusErr == nil {
		probeContext, cancel := context.WithTimeout(ctx, time.Second)
		_ = s.runtime(probeContext, "/internal/capabilities/network", nil, &environment)
		cancel()
	}
	e := s.DB.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		if e := lock(tx); e != nil {
			return e
		}
		var u User
		if e := tx.Where("id=? AND enabled=true", identity.UserId).Take(&u).Error; e != nil {
			return e
		}
		if identity.TenantId != s.Config.Tenant || identity.ProjectId != s.Config.Project {
			return fault{403, "FORBIDDEN", "工作区上下文无效"}
		}
		models, e := list(tx, "models")
		if e != nil {
			return e
		}
		var model object
		for _, v := range models {
			if (str(input, "model_id") != "" && str(v, "id") == str(input, "model_id")) || (str(input, "model_id") == "" && flag(v, "is_default")) {
				model = v
				break
			}
		}
		if model == nil || !flag(model, "enabled") || (availability(model, status, statusErr) != "ready_unverified" && !(statusErr != nil && flag(input, "defer_runtime_check"))) || !allowed("models", str(model, "base_url"), str(model, "credential_ref")) {
			return unavailable()
		}
		caps := model["capabilities"].(map[string]any)
		if (flag(input, "require_tools") && !flag(caps, "tool_calling")) || (flag(input, "require_streaming") && !flag(caps, "streaming")) {
			return unavailable()
		}
		skills, e := list(tx, "skills")
		if e != nil {
			return e
		}
		selected := map[string]bool{}
		if ids, explicit := input["skill_ids"]; explicit {
			for _, id := range ids.([]any) {
				selected[id.(string)] = true
			}
		} else {
			for _, v := range skills {
				yes, e := personal(tx, identity.UserId, str(v, "id"))
				if e != nil {
					return e
				}
				if yes {
					selected[str(v, "id")] = true
				}
			}
		}
		if len(selected) > 3 {
			return invalid("每轮最多选择 3 个技能，请明确选择")
		}
		userTools, userConnections, e := personalCapabilities(tx, identity.UserId)
		if e != nil {
			return e
		}
		if ids, explicit := input["connector_ids"].([]any); explicit {
			selectedIDs := map[string]bool{}
			for _, value := range ids {
				selectedIDs[value.(string)] = true
			}
			selectedConnections := map[string]bool{}
			filtered := []object{}
			for _, connection := range userConnections {
				id := str(connection, "connector_id")
				if selectedIDs[id] {
					filtered = append(filtered, connection)
					selectedConnections[str(connection, "id")] = true
					delete(selectedIDs, id)
				}
			}
			if len(selectedIDs) != 0 {
				return connectionError("CONNECTION_REQUIRED", "选中的个人连接不可用，请检查连接状态")
			}
			userConnections = filtered
			filtered = []object{}
			for _, tool := range userTools {
				if selectedConnections[str(tool, "connection_id")] {
					filtered = append(filtered, tool)
				}
			}
			userTools = filtered
		}
		outSkills := []object{}
		for _, v := range skills {
			if selected[str(v, "id")] {
				if !flag(v, "enabled") {
					return fault{409, "CAPABILITY_CHANGED", "选中的技能已禁用"}
				}
				skill := pick(v, "id", "name", "content", "revision")
				var dependencies []contracts.SkillDependency
				if raw, ok := v["dependencies"]; ok {
					if err := json.Unmarshal(encode(raw), &dependencies); err != nil {
						return err
					}
				}
				for _, dep := range dependencies {
					if flag(caps, "tool_calling") && dependencyReady(dep, userConnections, environment, flag(input, "network_enabled")) {
						continue
					}
					if dep.Required {
						if dep.Kind == "connector" {
							def, _ := personalDefinition(dep.CapabilityId)
							return connectionError("SKILL_DEPENDENCY_MISSING", "技能需要连接："+def.ConnectorName)
						}
						return connectionError("SKILL_DEPENDENCY_MISSING", "技能所需工具不可用："+dep.CapabilityId)
					}
					missing, _ := skill["missing_optional_dependencies"].([]contracts.SkillDependency)
					skill["missing_optional_dependencies"] = append(missing, dep)
				}
				outSkills = append(outSkills, skill)
				delete(selected, str(v, "id"))
			}
		}
		if len(selected) > 0 {
			return fault{404, "NOT_FOUND", "选中的技能不可见"}
		}
		tools, connections, e := enabledTools(tx)
		if e != nil {
			return e
		}
		outTools := []object{}
		outConnections := []object{}
		if flag(caps, "tool_calling") {
			for _, v := range tools {
				outTools = append(outTools, pick(v, "namespaced_tool_id", "connection_id", "remote_name", "description", "input_schema", "schema_hash", "revision", "access_mode", "requires_approval"))
			}
			for _, v := range connections {
				connection := pick(v, "id", "endpoint", "credential_ref", "revision")
				connection["max_calls_per_minute"] = mcpLimit(str(v, "endpoint"), str(v, "credential_ref"))
				outConnections = append(outConnections, connection)
			}
			outTools = append(outTools, userTools...)
			outConnections = append(outConnections, userConnections...)
			if len(outTools) > 100 {
				return connectionError("CONNECTION_TOOL_LIMIT", "当前授权的工具过多，请减少本轮选择的连接")
			}
		}
		refs := []object{}
		if ids, ok := input["file_ids"].([]any); ok {
			for _, id := range ids {
				var f record
				if e := tx.Table("backend.files").Where("id=? AND owner_id=? AND data->>'status'='READY'", id, identity.UserId).Take(&f).Error; e != nil {
					return e
				}
				var data object
				if e := json.Unmarshal(f.Data, &data); e != nil {
					return e
				}
				refs = append(refs, pick(data, "id", "sha256"))
			}
		}
		builtins := []contracts.BuiltinTool{}
		if flag(caps, "tool_calling") {
			builtins = BuiltinTools()
		}
		payload := object{"snapshot_id": uuid.NewString(), "created_at": time.Now().UTC().Format(time.RFC3339Nano), "context": identity, "model": pick(model, "id", "name", "provider", "protocol", "protocol_options", "provider_model_name", "base_url", "credential_ref", "context_limit", "max_output_tokens", "capabilities", "revision"), "skills": outSkills, "tools": outTools, "mcp_connections": outConnections, "file_refs": refs, "builtin_tools": builtins}
		raw := encode(payload)
		payload["network_enabled"] = flag(input, "network_enabled")
		raw = encode(payload)
		var value any
		_ = json.Unmarshal(raw, &value)
		if e = contracts.Validate("Snapshot", value); e != nil {
			return e
		}
		if e = json.Unmarshal(raw, &snapshot); e != nil {
			return e
		}
		return tx.Exec("INSERT INTO backend.capability_snapshots(id,owner_id,data) VALUES(?,?,?::jsonb)", snapshot.SnapshotId, identity.UserId, string(raw)).Error
	})
	return snapshot, e
}

func dependencyReady(dep contracts.SkillDependency, connections []object, environment object, network bool) bool {
	if dep.Kind == "connector" {
		for _, connection := range connections {
			if str(connection, "connector_id") == dep.CapabilityId {
				return true
			}
		}
		return false
	}
	switch dep.CapabilityId {
	case "builtin_web_search":
		return network && flag(environment, "search_available")
	case "builtin_fetch_page":
		return network && flag(environment, "fetch_available")
	case "builtin_python":
		return flag(environment, "compute_available")
	}
	for _, tool := range BuiltinTools() {
		if tool.NamespacedToolId == dep.CapabilityId {
			return true
		}
	}
	return false
}

// Snapshot is the control-plane application boundary for the Day 3 entry orchestrator.
func (s *Service) Snapshot(ctx context.Context, identity contracts.Context, request contracts.Submit) (contracts.Snapshot, error) {
	var input object
	_ = json.Unmarshal(encode(request), &input)
	input["require_tools"] = false
	input["require_streaming"] = true
	input["defer_runtime_check"] = true
	return s.resolve(ctx, identity, input)
}
func (s *Service) Resolve(c *gin.Context) {
	v, ok := body(c, "ResolveRequest")
	if !ok {
		return
	}
	snapshot, e := s.resolve(c.Request.Context(), c.MustGet("identity").(contracts.Context), v)
	if e != nil {
		fail(c, e)
		return
	}
	skills := []string{}
	tools := []string{}
	for _, v := range snapshot.Skills {
		skills = append(skills, v.Id)
	}
	for _, v := range snapshot.Tools {
		tools = append(tools, v.NamespacedToolId)
	}
	c.JSON(200, contracts.CapabilityPreview{SnapshotId: snapshot.SnapshotId, ModelId: snapshot.Model.Id, SkillIds: skills, ToolIds: tools})
}
func (s *Service) ValidateCapabilities(c *gin.Context) {
	input, ok := body(c, "CapabilityValidation")
	if !ok {
		return
	}
	var req contracts.CapabilityValidation
	_ = json.Unmarshal(encode(input), &req)
	reason := ""
	e := s.DB.WithContext(c.Request.Context()).Transaction(func(tx *gorm.DB) error {
		if e := lock(tx); e != nil {
			return e
		}
		var row record
		if e := tx.Table("backend.capability_snapshots").Where("id=? AND owner_id=?", req.SnapshotId, req.Context.UserId).Take(&row).Error; e != nil {
			return e
		}
		var snap contracts.Snapshot
		if e := json.Unmarshal(row.Data, &snap); e != nil {
			return e
		}
		if snap.Context.TenantId != req.Context.TenantId || snap.Context.ProjectId != req.Context.ProjectId || req.Context.TenantId != s.Config.Tenant || req.Context.ProjectId != s.Config.Project {
			return gorm.ErrRecordNotFound
		}
		if req.RunId != nil {
			var n int64
			if e := tx.Raw("SELECT count(*) FROM backend.run_submissions WHERE run_id=? AND snapshot_id=? AND owner_id=? AND active=true AND cancel_requested=false", *req.RunId, req.SnapshotId, req.Context.UserId).Scan(&n).Error; e != nil {
				return e
			}
			if n != 1 {
				reason = "RUN_NOT_AUTHORIZED"
				return nil
			}
		}
		reason = s.checkSnapshot(tx, snap)
		return nil
	})
	if e != nil {
		fail(c, e)
		return
	}
	c.JSON(200, contracts.CapabilityDecision{Allow: reason == "", Reason: reason})
}
