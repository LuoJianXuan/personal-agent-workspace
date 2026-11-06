package agententry

import (
	"agentworkspace/backend/internal/contracts"
	"agentworkspace/backend/internal/control"
	"agentworkspace/backend/internal/platform"
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"gorm.io/gorm"
	"io"
	"net"
	"net/http"
	"os"
	"strconv"
	"sync"
	"time"
)

type Service struct {
	DB            *gorm.DB
	Control       *control.Service
	Client        *HTTPClient
	mu            sync.Mutex
	subscriptions map[string]int
	total         int
}
type submission struct {
	RunID        string
	ThreadID     string
	OwnerID      string
	RequestHash  string
	StartPayload json.RawMessage
	Status       string
	Active       bool
	FinalText    string
	ErrorCode    string
	TraceURL     string

	CancelRequested bool
	CreatedAt       time.Time
}

func (submission) TableName() string { return "backend.run_submissions" }
func New(db *gorm.DB, c *control.Service) *Service {
	return &Service{DB: db, Control: c, Client: NewClient(c.Config.RuntimeURL, c.Config.BToR), subscriptions: map[string]int{}}
}
func identity(c *gin.Context) contracts.Context       { return c.MustGet("identity").(contracts.Context) }
func failure(c *gin.Context, status int, code string) { platform.Error(c, status, code, code) }
func validID(id string) bool                          { _, e := uuid.Parse(id); return e == nil }
func (s *Service) owned(c *gin.Context, id string) bool {
	if !validID(id) {
		failure(c, 404, "NOT_FOUND")
		return false
	}
	var n int64
	e := s.DB.Table("backend.threads").Where("id=? AND owner_id=?", id, identity(c).UserId).Count(&n).Error
	if e != nil {
		failure(c, 503, "DEPENDENCY_UNAVAILABLE")
		return false
	}
	if n != 1 {
		failure(c, 404, "NOT_FOUND")
		return false
	}
	return true
}
func decode(c *gin.Context, name string) (map[string]any, bool) {
	v, e := contracts.Decode(name, c.Request.Body)
	if e != nil {
		failure(c, 400, "INVALID_ARGUMENT")
		return nil, false
	}
	return v, true
}
func (s *Service) Threads(c *gin.Context) {
	if c.Request.Method == "GET" {
		var rows []contracts.Thread
		e := s.DB.Raw("SELECT id,title,to_char(created_at AT TIME ZONE 'UTC','YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') AS created_at FROM backend.threads WHERE owner_id=? ORDER BY created_at DESC LIMIT 200", identity(c).UserId).Scan(&rows).Error
		if e != nil {
			failure(c, 503, "DEPENDENCY_UNAVAILABLE")
			return
		}
		if rows == nil {
			rows = []contracts.Thread{}
		}
		c.JSON(200, contracts.ThreadList{Items: rows})
		return
	}
	v, ok := decode(c, "ThreadWrite")
	if !ok {
		return
	}
	ctx := identity(c)
	if c.Request.Method == "PATCH" {
		if !s.owned(c, c.Param("id")) {
			return
		}
		if e := s.DB.Exec("UPDATE backend.threads SET title=? WHERE id=?", v["title"], c.Param("id")).Error; e != nil {
			failure(c, 503, "DEPENDENCY_UNAVAILABLE")
			return
		}
		c.JSON(200, gin.H{"id": c.Param("id")})
		return
	}
	id := uuid.NewString()
	if e := s.DB.Exec("INSERT INTO backend.threads(id,owner_id,tenant_id,project_id,title) VALUES(?,?,?,?,?)", id, ctx.UserId, ctx.TenantId, ctx.ProjectId, v["title"]).Error; e != nil {
		failure(c, 503, "DEPENDENCY_UNAVAILABLE")
		return
	}
	c.JSON(201, gin.H{"id": id, "title": v["title"], "created_at": time.Now().UTC().Format(time.RFC3339Nano)})
}
func (s *Service) Messages(c *gin.Context) {
	if !s.owned(c, c.Param("id")) {
		return
	}
	var rows []contracts.Message
	e := s.DB.Raw("SELECT id,run_id,role,text,to_char(created_at AT TIME ZONE 'UTC','YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') AS created_at FROM backend.messages WHERE thread_id=? ORDER BY created_at,id", c.Param("id")).Scan(&rows).Error
	if e != nil {
		failure(c, 503, "DEPENDENCY_UNAVAILABLE")
		return
	}
	if rows == nil {
		rows = []contracts.Message{}
	}
	c.JSON(200, contracts.MessageList{Items: rows})
}
func public(row submission, unavailable bool) contracts.Submission {
	mode := "real"
	var start contracts.Start
	if json.Unmarshal(row.StartPayload, &start) == nil {
		mode = start.Mode
	}
	var trace *string
	if row.TraceURL != "" {
		trace = &row.TraceURL
	}
	return contracts.Submission{RunId: row.RunID, ThreadId: row.ThreadID, Status: row.Status, Mode: mode, RuntimeUnavailable: unavailable, FinalText: row.FinalText, ErrorCode: row.ErrorCode, CancelRequested: &row.CancelRequested, TraceUrl: trace}
}
func (s *Service) Submit(c *gin.Context) {
	tid := c.Param("id")
	if !s.owned(c, tid) {
		return
	}
	v, ok := decode(c, "Submit")
	if !ok {
		return
	}
	key := c.GetHeader("Idempotency-Key")
	if len(key) < 8 || len(key) > 128 {
		failure(c, 400, "INVALID_IDEMPOTENCY_KEY")
		return
	}
	raw, _ := json.Marshal(gin.H{"thread_id": tid, "submit": v})
	h := sha256.Sum256(raw)
	hash := hex.EncodeToString(h[:])
	ctx := identity(c)
	var prior submission
	e := s.DB.Where("owner_id=? AND idempotency_key=?", ctx.UserId, key).Take(&prior).Error
	if e == nil {
		if prior.RequestHash != hash {
			failure(c, 409, "IDEMPOTENCY_CONFLICT")
		} else {
			c.JSON(202, public(prior, false))
		}
		return
	}
	if e != gorm.ErrRecordNotFound {
		failure(c, 503, "DEPENDENCY_UNAVAILABLE")
		return
	}
	var req contracts.Submit
	raw, _ = json.Marshal(v)
	_ = json.Unmarshal(raw, &req)
	if req.Scenario != nil && (req.FileIds == nil || len(*req.FileIds) != 1) {
		failure(c, 400, "SCENARIO_REQUIRES_ONE_FILE")
		return
	}
	snap, e := s.Control.Snapshot(c.Request.Context(), ctx, req)
	if e != nil {
		control.WriteFailure(c, e)
		return
	}
	row := submission{RunID: uuid.NewString(), ThreadID: tid, OwnerID: ctx.UserId, RequestHash: hash, Status: "PENDING", Active: true}
	code := ""
	e = s.DB.Transaction(func(tx *gorm.DB) error {
		if e := tx.Exec("SELECT pg_advisory_xact_lock(210003)").Error; e != nil {
			return e
		}
		var old submission
		e := tx.Where("owner_id=? AND idempotency_key=?", ctx.UserId, key).Take(&old).Error
		if e == nil {
			if old.RequestHash != hash {
				code = "IDEMPOTENCY_CONFLICT"
				return fmt.Errorf("conflict")
			}
			row = old
			return nil
		}
		if e != gorm.ErrRecordNotFound {
			return e
		}
		var busy int64
		if e := tx.Model(&submission{}).Where("thread_id=? AND active=true", tid).Count(&busy).Error; e != nil {
			return e
		}
		if busy > 0 {
			code = "THREAD_BUSY"
			return fmt.Errorf("busy")
		}
		history := []contracts.HistoryMessage{}
		if e := tx.Raw("SELECT m.run_id,m.role,m.text AS content FROM backend.messages m JOIN backend.run_submissions r ON r.run_id=m.run_id WHERE m.thread_id=? AND r.status='SUCCEEDED' ORDER BY m.created_at,m.id", tid).Scan(&history).Error; e != nil {
			return e
		}
		if len(history) > 40 {
			history = history[len(history)-40:]
		}
		mode := os.Getenv("MODEL_MODE")
		if mode != "mock" {
			mode = "real"
		}
		start := contracts.Start{RunId: row.RunID, ThreadId: tid, Context: ctx, Input: req.Input, History: history, EffectiveCapabilities: snap, FileRefs: snap.FileRefs, Mode: mode, RequestHash: hash, Scenario: req.Scenario}
		row.StartPayload, _ = json.Marshal(start)
		if e := tx.Exec("INSERT INTO backend.run_submissions(run_id,thread_id,owner_id,idempotency_key,request_hash,snapshot_id,start_payload) VALUES(?,?,?,?,?,?,?::jsonb)", row.RunID, tid, ctx.UserId, key, hash, snap.SnapshotId, string(row.StartPayload)).Error; e != nil {
			return e
		}
		if e := tx.Exec("INSERT INTO backend.messages(id,thread_id,run_id,role,text) VALUES(?,?,?,'user',?)", uuid.NewString(), tid, row.RunID, req.Input).Error; e != nil {
			return e
		}
		return tx.Exec("INSERT INTO backend.dispatch_commands(command_id,run_id) VALUES(?,?)", uuid.NewString(), row.RunID).Error
	})
	if e != nil {
		if code != "" {
			failure(c, 409, code)
		} else {
			failure(c, 503, "DEPENDENCY_UNAVAILABLE")
		}
		return
	}
	c.JSON(202, public(row, false))
}
func (c *HTTPClient) call(ctx context.Context, method, path string, body []byte) (int, []byte, error) {
	r, e := http.NewRequestWithContext(ctx, method, c.BaseURL+path, bytes.NewReader(body))
	if e != nil {
		return 0, nil, e
	}
	r.Header.Set("Authorization", "Bearer "+c.Token)
	r.Header.Set("Content-Type", "application/json")
	res, e := c.RPC.Do(r)
	if e != nil {
		return 0, nil, e
	}
	defer res.Body.Close()
	b, e := io.ReadAll(io.LimitReader(res.Body, 2<<20))
	return res.StatusCode, b, e
}
func (c *HTTPClient) Start(ctx context.Context, start contracts.Start) (contracts.Run, error) {
	raw, _ := json.Marshal(start)
	status, b, e := c.call(ctx, "POST", "/internal/runs", raw)
	var r contracts.Run
	if e != nil || status != 200 && status != 202 {
		return r, fmt.Errorf("runtime unavailable")
	}
	e = json.Unmarshal(b, &r)
	return r, e
}
func terminal(status string) bool {
	return status == "SUCCEEDED" || status == "FAILED" || status == "CANCELLED" || status == "INTERRUPTED"
}
func (s *Service) syncRun(ctx context.Context, row *submission) bool {
	status, b, e := s.Client.call(ctx, "GET", "/internal/runs/"+row.RunID, nil)
	if e != nil || status != 200 {
		return false
	}
	var result contracts.Submission
	if json.Unmarshal(b, &result) != nil {
		return false
	}
	if result.RunId != row.RunID {
		return false
	}
	e = s.DB.Transaction(func(tx *gorm.DB) error {
		trace := ""
		if result.TraceUrl != nil {
			trace = *result.TraceUrl
		}
		if e := tx.Exec("UPDATE backend.run_submissions SET status=?,final_text=?,error_code=?,trace_url=?,active=? WHERE run_id=? AND active=true", result.Status, result.FinalText, result.ErrorCode, trace, !terminal(result.Status), row.RunID).Error; e != nil {
			return e
		}
		if result.Status == "SUCCEEDED" {
			return tx.Exec("INSERT INTO backend.messages(id,thread_id,run_id,role,text) VALUES(?,?,?,'assistant',?) ON CONFLICT(run_id,role) DO NOTHING", uuid.NewString(), row.ThreadID, row.RunID, result.FinalText).Error
		}
		return nil
	})
	if e != nil {
		return false
	}
	row.Status = result.Status
	row.FinalText = result.FinalText
	row.ErrorCode = result.ErrorCode
	if result.TraceUrl != nil {
		row.TraceURL = *result.TraceUrl
	}
	return true
}
func (s *Service) Worker(ctx context.Context) {
	ticker := time.NewTicker(time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			s.processCommands(ctx)
			var pending []submission
			if s.DB.Raw("SELECT r.* FROM backend.run_submissions r JOIN backend.dispatch_commands d ON d.run_id=r.run_id WHERE r.active AND NOT d.accepted AND d.next_attempt<=now() ORDER BY r.created_at LIMIT 16").Scan(&pending).Error == nil {
				for _, row := range pending {
					status, _, e := s.Client.call(ctx, "POST", "/internal/runs", row.StartPayload)
					accepted := e == nil && (status == 200 || status == 202)
					_ = s.DB.Exec("UPDATE backend.dispatch_commands SET attempts=attempts+1,accepted=?,next_attempt=now()+interval '3 seconds' WHERE run_id=?", accepted, row.RunID).Error
					if e == nil && (status == 400 || status == 403 || status == 409) {
						_ = s.DB.Exec("UPDATE backend.run_submissions SET status='FAILED',error_code='START_REJECTED',active=false WHERE run_id=? AND status='PENDING'", row.RunID).Error
					}
				}
			}
			var active []submission
			if s.DB.Where("active=true").Order("created_at").Limit(64).Find(&active).Error == nil {
				for i := range active {
					s.syncRun(ctx, &active[i])
				}
			}
		}
	}
}
func (s *Service) get(c *gin.Context) (submission, bool) {
	var row submission
	if !validID(c.Param("id")) {
		failure(c, 404, "NOT_FOUND")
		return row, false
	}
	e := s.DB.Where("run_id=? AND owner_id=?", c.Param("id"), identity(c).UserId).Take(&row).Error
	if e != nil {
		failure(c, 404, "NOT_FOUND")
		return row, false
	}
	return row, true
}
func (s *Service) Run(c *gin.Context) {
	row, ok := s.get(c)
	if !ok {
		return
	}
	available := true
	if row.Active {
		available = s.syncRun(c.Request.Context(), &row)
	}
	c.JSON(200, public(row, !available))
}
func (s *Service) AdminRuns(c *gin.Context) {
	var rows []submission
	q := s.DB.Order("created_at DESC").Limit(100)
	if c.Param("id") != "" {
		if !validID(c.Param("id")) {
			failure(c, 404, "NOT_FOUND")
			return
		}
		q = q.Where("run_id=?", c.Param("id"))
	}
	if q.Find(&rows).Error != nil {
		failure(c, 503, "DEPENDENCY_UNAVAILABLE")
		return
	}
	out := []gin.H{}
	for _, r := range rows {
		var start contracts.Start
		_ = json.Unmarshal(r.StartPayload, &start)
		out = append(out, gin.H{"run_id": r.RunID, "thread_id": r.ThreadID, "owner_id": r.OwnerID, "model": start.EffectiveCapabilities.Model.Name, "created_at": r.CreatedAt.UTC().Format(time.RFC3339Nano), "status": r.Status, "mode": public(r, false).Mode, "error_code": r.ErrorCode})
	}
	c.JSON(200, gin.H{"items": out})
}
func (s *Service) Events(c *gin.Context) {
	row, ok := s.get(c)
	if !ok {
		return
	}
	seq, e := strconv.ParseInt(c.DefaultQuery("after_seq", "0"), 10, 64)
	if e != nil || seq < 0 {
		failure(c, 400, "INVALID_ARGUMENT")
		return
	}
	status, b, e := s.Client.call(c.Request.Context(), "GET", fmt.Sprintf("/internal/runs/%s/events?after_seq=%d", row.RunID, seq), nil)
	if e != nil {
		failure(c, 503, "RUNTIME_UNAVAILABLE")
		return
	}
	c.Data(status, "application/json", b)
}
func (s *Service) Stream(c *gin.Context) {
	row, ok := s.get(c)
	if !ok {
		return
	}
	seq, e := strconv.ParseInt(c.DefaultQuery("after_seq", "0"), 10, 64)
	if e != nil || seq < 0 {
		failure(c, 400, "INVALID_ARGUMENT")
		return
	}
	user := identity(c).UserId
	s.mu.Lock()
	if s.total >= 32 || s.subscriptions[user] >= 4 {
		s.mu.Unlock()
		c.Header("Retry-After", "3")
		failure(c, 429, "RESOURCE_EXHAUSTED")
		return
	}
	s.total++
	s.subscriptions[user]++
	s.mu.Unlock()
	defer func() { s.mu.Lock(); s.total--; s.subscriptions[user]--; s.mu.Unlock() }()
	r, _ := http.NewRequestWithContext(c.Request.Context(), "GET", fmt.Sprintf("%s/internal/runs/%s/stream?after_seq=%d", s.Client.BaseURL, row.RunID, seq), nil)
	r.Header.Set("Authorization", "Bearer "+s.Client.Token)
	res, e := s.Client.Stream.Do(r)
	if e != nil {
		failure(c, 503, "RUNTIME_UNAVAILABLE")
		return
	}
	defer res.Body.Close()
	if res.StatusCode != 200 {
		b, _ := io.ReadAll(io.LimitReader(res.Body, 8192))
		c.Data(res.StatusCode, "application/json", b)
		return
	}
	c.Header("Content-Type", "text/event-stream")
	c.Header("Cache-Control", "no-cache")
	c.Header("X-Accel-Buffering", "no")
	c.Status(200)
	c.Writer.Flush()
	connection, _ := c.Request.Context().Value(platform.ConnectionKey{}).(net.Conn)
	if connection != nil {
		defer connection.SetWriteDeadline(time.Time{})
	}
	buf := make([]byte, 8192)
	for {
		n, e := res.Body.Read(buf)
		if n > 0 {
			if connection != nil {
				_ = connection.SetWriteDeadline(time.Now().Add(10 * time.Second))
			}
			if _, w := c.Writer.Write(buf[:n]); w != nil {
				return
			}
			c.Writer.Flush()
		}
		if e != nil {
			return
		}
	}
}
