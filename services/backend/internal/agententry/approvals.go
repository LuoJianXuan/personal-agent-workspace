package agententry

import (
	"agentworkspace/backend/internal/contracts"
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"gorm.io/gorm"
	"net/http"
	"os"
	"time"
)

func encodeJSON(v any) []byte       { b, _ := json.Marshal(v); return b }
func controlLock(tx *gorm.DB) error { return tx.Exec("SELECT pg_advisory_xact_lock(210002)").Error }
func (s *Service) Approvals(c *gin.Context) {
	r, ok := s.get(c)
	if !ok {
		return
	}
	status, b, e := s.Client.call(c.Request.Context(), "GET", "/internal/runs/"+r.RunID+"/approvals", nil)
	if e != nil {
		failure(c, 503, "RUNTIME_UNAVAILABLE")
		return
	}
	c.Data(status, "application/json", b)
}
func (s *Service) proposal(ctx context.Context, id string) (contracts.Approval, error) {
	var p contracts.Approval
	status, b, e := s.Client.call(ctx, "GET", "/internal/approvals/"+id, nil)
	if e != nil || status != 200 {
		return p, errors.New("PROPOSAL_UNAVAILABLE")
	}
	var v any
	if json.Unmarshal(b, &v) != nil || contracts.Validate("Approval", v) != nil {
		return p, errors.New("INVALID_PROPOSAL")
	}
	e = json.Unmarshal(b, &p)
	return p, e
}
func decisionJSON(row decisionRow) contracts.DecisionRecord {
	var proposal contracts.Approval
	_ = json.Unmarshal(row.Proposal, &proposal)
	return contracts.DecisionRecord{DecisionId: row.DecisionID, ApprovalId: row.ApprovalID, RunId: row.RunID, OwnerId: row.OwnerID, Decision: row.Decision, Proposal: proposal, CreatedAt: row.CreatedAt.UTC().Format(time.RFC3339Nano)}
}

type decisionRow struct {
	DecisionID, ApprovalID, RunID, OwnerID, Decision string
	Proposal                                         json.RawMessage
	CreatedAt                                        time.Time
}

func (decisionRow) TableName() string { return "backend.approval_decisions" }
func (s *Service) Decision(c *gin.Context) {
	id := c.Param("id")
	if !validID(id) {
		failure(c, 404, "NOT_FOUND")
		return
	}
	v, ok := decode(c, "Decision")
	if !ok {
		return
	}
	choice := v["decision"].(string)
	owner := identity(c).UserId
	var old decisionRow
	e := s.DB.Where("approval_id=? AND owner_id=?", id, owner).Take(&old).Error
	if e == nil {
		if old.Decision != choice {
			failure(c, 409, "APPROVAL_CONFLICT")
		} else {
			c.JSON(200, decisionJSON(old))
		}
		return
	}
	p, e := s.proposal(c.Request.Context(), id)
	if e != nil {
		failure(c, 503, "RUNTIME_UNAVAILABLE")
		return
	}
	if p.OwnerId != owner || p.ApprovalId != id {
		failure(c, 404, "NOT_FOUND")
		return
	}
	expires, e := time.Parse(time.RFC3339Nano, p.ExpiresAt)
	if e != nil || !time.Now().Before(expires) {
		failure(c, 409, "APPROVAL_EXPIRED")
		return
	}
	if p.Status != "PENDING" {
		failure(c, 409, "APPROVAL_CONFLICT")
		return
	}
	row := decisionRow{DecisionID: uuid.NewString(), ApprovalID: id, RunID: p.RunId, OwnerID: owner, Decision: choice, Proposal: encodeJSON(p), CreatedAt: time.Now().UTC()}
	code := ""
	e = s.DB.Transaction(func(tx *gorm.DB) error {
		if e := controlLock(tx); e != nil {
			return e
		}
		var prior decisionRow
		e := tx.Where("approval_id=?", id).Take(&prior).Error
		if e == nil {
			if prior.OwnerID != owner || prior.Decision != choice {
				code = "APPROVAL_CONFLICT"
				return errors.New(code)
			}
			row = prior
			return nil
		}
		if e != gorm.ErrRecordNotFound {
			return e
		}
		start, e := s.Control.CheckExecution(tx, p.RunId)
		if e != nil {
			code = "CAPABILITY_CHANGED"
			return e
		}
		if start.Context.UserId != owner || start.EffectiveCapabilities.SnapshotId != p.SnapshotId {
			code = "APPROVAL_CONFLICT"
			return errors.New(code)
		}
		if !time.Now().Before(expires) {
			code = "APPROVAL_EXPIRED"
			return errors.New(code)
		}
		if e := tx.Create(&row).Error; e != nil {
			return e
		}
		if e := tx.Exec("INSERT INTO backend.run_commands(command_id,run_id,kind,payload) VALUES(?,?,'resume',?::jsonb)", row.DecisionID, row.RunID, string(encodeJSON(contracts.Resume{DecisionId: row.DecisionID}))).Error; e != nil {
			return e
		}
		return s.auditAction(tx, owner, "approval."+choice, id, identity(c).RequestId)
	})
	if e != nil {
		if code == "" {
			code = "DEPENDENCY_UNAVAILABLE"
		}
		failure(c, 409, code)
		return
	}
	c.JSON(200, decisionJSON(row))
}
func (s *Service) auditAction(tx *gorm.DB, actor, action, objectID, requestID string) error {
	return tx.Exec("INSERT INTO backend.admin_audits(id,actor_id,action,object_id,request_id,safe_changes) VALUES(?,?,?,?,?,?::jsonb)", uuid.NewString(), actor, action, objectID, requestID, `{}`).Error
}
func (s *Service) Resume(c *gin.Context) {
	r, ok := s.get(c)
	if !ok {
		return
	}
	var d decisionRow
	if e := s.DB.Where("run_id=? AND owner_id=?", r.RunID, identity(c).UserId).Order("created_at DESC").Take(&d).Error; e != nil {
		failure(c, 409, "RUN_NOT_RESUMABLE")
		return
	}
	if !r.Active {
		failure(c, 409, "RUN_NOT_RESUMABLE")
		return
	}
	if e := s.DB.Exec("UPDATE backend.run_commands SET delivered=false,next_attempt=now() WHERE command_id=?", d.DecisionID).Error; e != nil {
		failure(c, 503, "DEPENDENCY_UNAVAILABLE")
		return
	}
	c.JSON(202, gin.H{"run_id": r.RunID, "decision_id": d.DecisionID})
}
func (s *Service) Cancel(c *gin.Context) {
	r, ok := s.get(c)
	if !ok {
		return
	}
	command := uuid.NewSHA1(uuid.MustParse(r.RunID), []byte("cancel")).String()
	e := s.DB.Transaction(func(tx *gorm.DB) error {
		if e := controlLock(tx); e != nil {
			return e
		}
		if e := tx.Exec("UPDATE backend.run_submissions SET cancel_requested=true WHERE run_id=? AND active=true", r.RunID).Error; e != nil {
			return e
		}
		return tx.Exec("INSERT INTO backend.run_commands(command_id,run_id,kind,payload) VALUES(?,?,'cancel',?::jsonb) ON CONFLICT(command_id) DO NOTHING", command, r.RunID, string(encodeJSON(contracts.Cancel{CommandId: command}))).Error
	})
	if e != nil {
		failure(c, 503, "DEPENDENCY_UNAVAILABLE")
		return
	}
	c.JSON(202, gin.H{"run_id": r.RunID, "cancel_requested": r.Active})
}
func (s *Service) processCommands(ctx context.Context) {
	var rows []struct {
		CommandID, RunID, Kind string
		Payload                json.RawMessage
	}
	if s.DB.Raw("SELECT * FROM backend.run_commands WHERE NOT delivered AND next_attempt<=now() ORDER BY kind, next_attempt LIMIT 16").Scan(&rows).Error != nil {
		return
	}
	for _, r := range rows {
		if os.Getenv("ENABLE_FAULTS") == "true" && os.Getenv("FAULT_PAUSE_RESUME_DELIVERY") == "true" && r.Kind == "resume" {
			continue
		}
		status, _, e := s.Client.call(ctx, "POST", "/internal/runs/"+r.RunID+"/"+r.Kind, r.Payload)
		done := e == nil && (status == 200 || status == 202 || status == 409)
		_ = s.DB.Exec("UPDATE backend.run_commands SET delivered=?,next_attempt=now()+interval '3 seconds' WHERE command_id=?", done, r.CommandID).Error
	}
}
func (s *Service) InternalSubmission(c *gin.Context) {
	if !validID(c.Param("id")) {
		failure(c, 404, "NOT_FOUND")
		return
	}
	var r struct {
		RunID, OwnerID, Status  string
		Active, CancelRequested bool
	}
	if e := s.DB.Table("backend.run_submissions").Where("run_id=?", c.Param("id")).Take(&r).Error; e != nil {
		failure(c, 404, "NOT_FOUND")
		return
	}
	c.JSON(200, gin.H{"run_id": r.RunID, "owner_id": r.OwnerID, "status": r.Status, "active": r.Active, "cancel_requested": r.CancelRequested})
}
func (s *Service) InternalDecision(c *gin.Context) {
	if !validID(c.Param("id")) {
		failure(c, 404, "NOT_FOUND")
		return
	}
	var row decisionRow
	if e := s.DB.Where("decision_id=?", c.Param("id")).Take(&row).Error; e != nil {
		failure(c, 404, "NOT_FOUND")
		return
	}
	c.JSON(200, decisionJSON(row))
}
func canonicalArgs(v any) (string, string, error) {
	buf := new(bytes.Buffer)
	encoder := json.NewEncoder(buf)
	encoder.SetEscapeHTML(false)
	if e := encoder.Encode(v); e != nil {
		return "", "", e
	}
	raw := bytes.TrimSuffix(buf.Bytes(), []byte("\n"))
	hash := sha256.Sum256(raw)
	return string(raw), hex.EncodeToString(hash[:]), nil
}
func (s *Service) Ticket(c *gin.Context) {
	v, ok := decode(c, "TicketWrite")
	if !ok {
		return
	}
	var req contracts.TicketWrite
	_ = json.Unmarshal(encodeJSON(v), &req)
	var result json.RawMessage
	code := ""
	created := false
	e := s.DB.Transaction(func(tx *gorm.DB) error {
		if e := controlLock(tx); e != nil {
			return e
		}
		var cached struct {
			RequestHash string
			Result      json.RawMessage
		}
		e := tx.Table("backend.demo_write_results").Where("execution_id=?", req.ExecutionId).Take(&cached).Error
		if e == nil {
			if cached.RequestHash != req.ArgsHash {
				code = "APPROVAL_CONFLICT"
				return errors.New(code)
			}
			result = cached.Result
			return nil
		}
		if e != gorm.ErrRecordNotFound {
			return e
		}
		start, e := s.Control.CheckExecution(tx, req.RunId)
		if e != nil {
			code = "CAPABILITY_CHANGED_OR_CANCELLED"
			return e
		}
		var d decisionRow
		if e := tx.Where("decision_id=? AND run_id=? AND owner_id=? AND decision='approve'", req.DecisionId, req.RunId, start.Context.UserId).Take(&d).Error; e != nil {
			code = "APPROVAL_REQUIRED"
			return e
		}
		var p contracts.Approval
		if json.Unmarshal(d.Proposal, &p) != nil {
			return errors.New("bad proposal")
		}
		expires, e := time.Parse(time.RFC3339Nano, p.ExpiresAt)
		if e != nil || !time.Now().Before(expires) {
			code = "APPROVAL_EXPIRED"
			return errors.New(code)
		}
		if p.ExecutionId != req.ExecutionId || p.ArgsHash != req.ArgsHash || p.CanonicalArgs != req.CanonicalArgs || p.SnapshotId != start.EffectiveCapabilities.SnapshotId || p.NamespacedToolId != "builtin_create_demo_ticket" {
			code = "APPROVAL_CONFLICT"
			return errors.New(code)
		}
		authorized := false
		if start.EffectiveCapabilities.BuiltinTools != nil {
			for _, t := range *start.EffectiveCapabilities.BuiltinTools {
				if t.NamespacedToolId == p.NamespacedToolId && t.Revision == p.CapabilityRevision {
					authorized = true
				}
			}
		}
		if !authorized {
			code = "TOOL_DENIED"
			return errors.New(code)
		}
		var args map[string]any
		if json.Unmarshal([]byte(req.CanonicalArgs), &args) != nil || contracts.Validate("TicketArgs", args) != nil {
			code = "INVALID_ARGUMENT"
			return errors.New(code)
		}
		canonical, hash, e := canonicalArgs(args)
		if e != nil || canonical != req.CanonicalArgs || hash != req.ArgsHash {
			code = "APPROVAL_CONFLICT"
			return errors.New(code)
		}
		var prior struct {
			ArgsHash string
			Result   json.RawMessage
		}
		e = tx.Table("backend.demo_tickets").Where("run_id=?", req.RunId).Take(&prior).Error
		if e == nil {
			if prior.ArgsHash != hash {
				code = "TICKET_CONFLICT"
				return errors.New(code)
			}
			result = prior.Result
		} else if e == gorm.ErrRecordNotFound {
			ticket := contracts.TicketResult{TicketId: uuid.NewString(), RunId: req.RunId, ExecutionId: req.ExecutionId, OrderId: args["order_id"].(string), Title: args["title"].(string), Description: args["description"].(string), Synthetic: true, CreatedAt: time.Now().UTC().Format(time.RFC3339Nano)}
			result = encodeJSON(ticket)
			if e := tx.Exec("INSERT INTO backend.demo_tickets(id,run_id,execution_id,args_hash,result) VALUES(?,?,?,?,?::jsonb)", ticket.TicketId, req.RunId, req.ExecutionId, hash, string(result)).Error; e != nil {
				return e
			}
			created = true
		} else {
			return e
		}
		if e := tx.Exec("INSERT INTO backend.demo_write_results(execution_id,run_id,request_hash,result) VALUES(?,?,?,?::jsonb)", req.ExecutionId, req.RunId, hash, string(result)).Error; e != nil {
			return e
		}
		return s.auditAction(tx, start.Context.UserId, "ticket.create", req.ExecutionId, start.Context.RequestId)
	})
	if e != nil {
		if code == "" {
			code = "DEPENDENCY_UNAVAILABLE"
		}
		failure(c, 409, code)
		return
	}
	// Controlled fault only on the first committed write; retry/query returns the original result.
	if created && os.Getenv("ENABLE_FAULTS") == "true" && os.Getenv("FAULT_TICKET_RESPONSE_LOST") == "true" {
		failure(c, 503, "INJECTED_RESPONSE_LOSS")
		return
	}
	c.Data(200, "application/json", result)
}
func (s *Service) TicketByExecution(c *gin.Context) {
	if !validID(c.Param("id")) {
		failure(c, 404, "NOT_FOUND")
		return
	}
	if os.Getenv("ENABLE_FAULTS") == "true" && os.Getenv("FAULT_TICKET_QUERY_UNAVAILABLE") == "true" {
		failure(c, 503, "INJECTED_QUERY_FAILURE")
		return
	}
	var row struct{ Result json.RawMessage }
	if e := s.DB.Table("backend.demo_write_results").Where("execution_id=?", c.Param("id")).Take(&row).Error; e != nil {
		failure(c, 404, "NOT_FOUND")
		return
	}
	c.Data(http.StatusOK, "application/json", row.Result)
}
