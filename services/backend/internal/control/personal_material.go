package control

import (
	"agentworkspace/backend/internal/contracts"
	"encoding/json"
	"net/http"

	"github.com/gin-gonic/gin"
	"gorm.io/gorm"
)

func (s *Service) PersonalDiscoveryMaterial(c *gin.Context) {
	input, ok := body(c, "PersonalDiscovery")
	if !ok {
		return
	}
	keys, err := connectionKeyring()
	if err != nil {
		fail(c, err)
		return
	}
	var result contracts.PersonalSecretMaterial
	err = s.DB.WithContext(c.Request.Context()).Transaction(func(tx *gorm.DB) error {
		if err := lock(tx); err != nil {
			return err
		}
		var probe personalProbeRow
		if err := tx.Table(probeTable).Where("id=? AND received=false AND expires_at>now()", str(input, "operation_id")).Take(&probe).Error; err != nil {
			return err
		}
		var row personalConnectionRow
		if err := tx.Table(personalTable).Where("id=? AND owner_id=? AND EXISTS (SELECT 1 FROM backend.users WHERE id=? AND enabled=true)", probe.ConnectionID, probe.OwnerID, probe.OwnerID).Take(&row).Error; err != nil {
			return err
		}
		def, err := publishedDefinition(tx, row.ConnectorID)
		if err != nil {
			return err
		}
		token, err := keys.Open(probe.KeyID, probe.Ciphertext, connectionAAD(row, probe.CredentialVersion, def))
		if err != nil {
			return connectionError("CONNECTION_SECRET_UNAVAILABLE", "连接凭据不可用")
		}
		if err := tx.Exec("UPDATE "+probeTable+" SET received=true WHERE id=?", probe.ID).Error; err != nil {
			return err
		}
		result = contracts.PersonalSecretMaterial{Endpoint: def.Endpoint, CredentialRef: def.CredentialRef, Token: token}
		return nil
	})
	if err != nil {
		fail(c, err)
		return
	}
	c.Header("Cache-Control", "no-store")
	c.JSON(http.StatusOK, result)
}

func checkPersonalSnapshot(tx *gorm.DB, owner string, conn contracts.Mcp) (personalConnectionRow, map[string]personalTool, bool) {
	var row personalConnectionRow
	if conn.ConnectorId == nil || conn.GrantRevision == nil || conn.CredentialVersion == nil {
		return row, nil, false
	}
	if _, err := connectionKeyring(); err != nil {
		return row, nil, false
	}
	def, err := publishedDefinition(tx, *conn.ConnectorId)
	if err != nil || def.Endpoint != conn.Endpoint || def.CredentialRef != conn.CredentialRef || def.MaxCallsPerMinute != conn.MaxCallsPerMinute {
		return row, nil, false
	}
	if conn.ConnectorRevision == nil || def.PublicationRevision != *conn.ConnectorRevision {
		return row, nil, false
	}
	row, err = personalRow(tx, owner, def.PersonalConnector)
	if err != nil || row.ID != conn.Id || row.Status != "ready" || row.GrantRevision != *conn.GrantRevision || row.CredentialVersion != *conn.CredentialVersion || row.GrantRevision != conn.Revision {
		return row, nil, false
	}
	items, err := row.authorized(def)
	if err != nil {
		return row, nil, false
	}
	available := map[string]personalTool{}
	for _, item := range items {
		available[toolID(row.ID, item.Name)] = item
	}
	return row, available, true
}

func matchesPersonalTool(tool contracts.Tool, available map[string]personalTool) bool {
	item, ok := available[tool.NamespacedToolId]
	if !ok || tool.Fingerprint == nil || item.Fingerprint != *tool.Fingerprint || item.Name != tool.RemoteName {
		return false
	}
	if item.Policy == "read" {
		return tool.AccessMode == "read" && !tool.RequiresApproval
	}
	return tool.AccessMode == "write" && tool.RequiresApproval
}

func (s *Service) PersonalExecutionMaterial(c *gin.Context) {
	input, ok := body(c, "PersonalExecutionMaterial")
	if !ok {
		return
	}
	keys, err := connectionKeyring()
	if err != nil {
		fail(c, err)
		return
	}
	runID, eid, toolID, hash := str(input, "run_id"), str(input, "execution_id"), str(input, "tool_id"), str(input, "args_hash")
	var result contracts.PersonalSecretMaterial
	err = s.DB.WithContext(c.Request.Context()).Transaction(func(tx *gorm.DB) error {
		if err := lock(tx); err != nil {
			return err
		}
		if flag(input, "auth_failed") {
			return tx.Exec(`UPDATE backend.personal_connections c SET status='auth_required', revision=revision+1
				FROM backend.personal_execution_access a WHERE a.execution_id=? AND a.run_id=? AND a.tool_id=? AND a.args_hash=?
				AND c.id=a.connection_id AND c.owner_id=a.owner_id AND c.credential_version=a.credential_version AND c.status='ready'`, eid, runID, toolID, hash).Error
		}
		start, err := s.CheckExecution(tx, runID)
		if err != nil {
			return connectionError("CAPABILITY_CHANGED", "本轮授权已变化，请重新发起对话")
		}
		snap := start.EffectiveCapabilities
		for _, tool := range snap.Tools {
			if tool.NamespacedToolId != toolID {
				continue
			}
			for _, conn := range snap.McpConnections {
				if conn.Id != tool.ConnectionId || conn.ConnectorId == nil {
					continue
				}
				row, available, allowed := checkPersonalSnapshot(tx, start.Context.UserId, conn)
				if !allowed || !matchesPersonalTool(tool, available) {
					break
				}
				if tool.RequiresApproval {
					var decision struct{ Proposal json.RawMessage }
					if str(input, "decision_id") == "" ||
						tx.Table("backend.approval_decisions").Where("decision_id=? AND owner_id=? AND run_id=? AND decision='approve'", str(input, "decision_id"), row.OwnerID, runID).Take(&decision).Error != nil {
						return connectionError("APPROVAL_REQUIRED", "请先确认操作")
					}
					var proposal contracts.Approval
					if json.Unmarshal(decision.Proposal, &proposal) != nil || proposal.ExecutionId != eid || proposal.ArgsHash != hash ||
						proposal.NamespacedToolId != toolID || proposal.SnapshotId != snap.SnapshotId || proposal.CapabilityRevision != tool.Revision {
						return connectionError("APPROVAL_CONFLICT", "操作内容已变化，请重新确认")
					}
				}
				def, err := personalDefinition(*conn.ConnectorId)
				if err != nil {
					return err
				}
				token, err := openActive(tx, keys, row, def)
				if err != nil {
					return err
				}
				access := tx.Exec(`INSERT INTO backend.personal_execution_access(execution_id,run_id,owner_id,connection_id,tool_id,args_hash,credential_version)
					VALUES (?,?,?,?,?,?,?) ON CONFLICT (execution_id) DO NOTHING`, eid, runID, row.OwnerID, row.ID, toolID, hash, row.CredentialVersion)
				if access.Error != nil {
					return access.Error
				}
				if access.RowsAffected != 1 {
					return connectionError("OUTCOME_UNKNOWN", "该工具调用已分配凭据，请检查执行结果")
				}
				result = contracts.PersonalSecretMaterial{Endpoint: conn.Endpoint, CredentialRef: conn.CredentialRef, Token: token}
				return nil
			}
		}
		return connectionError("CONNECTION_REVOKED", "个人连接已不可用")
	})
	if err != nil {
		fail(c, err)
		return
	}
	c.Header("Cache-Control", "no-store")
	if flag(input, "auth_failed") {
		c.Status(http.StatusNoContent)
		return
	}
	c.JSON(http.StatusOK, result)
}
