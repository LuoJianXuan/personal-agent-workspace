package agententry

import (
	"agentworkspace/backend/internal/contracts"
	"agentworkspace/backend/internal/workspace"
	"encoding/json"
	"errors"
	"github.com/gin-gonic/gin"
	"gorm.io/gorm"
	"io"
	"net/http"
	"strings"
)

func binaryMedia(media string) bool {
	return media == "application/pdf" || strings.HasPrefix(media, "application/vnd.openxmlformats-officedocument.")
}
func (s *Service) phaseWorkspace() *workspace.Service { return &workspace.Service{DB: s.DB} }
func (s *Service) InternalBlob(c *gin.Context) {
	// The original file authorization path remains the only Runtime entry.
	s.InternalFile(c)
}
func (s *Service) ParsedFile(c *gin.Context) {
	row, ok := s.ownedFile(c)
	if !ok {
		return
	}
	var count int64
	if s.DB.Table("backend.parsed_documents").Where("file_id=?", row.ID).Count(&count).Error != nil {
		failure(c, 503, "DEPENDENCY_UNAVAILABLE")
		return
	}
	if count == 0 {
		file := filePublic(row)
		c.JSON(200, contracts.ParsedDocument{FileId: file.Id, Sha256: file.Sha256, ParserRevision: "phase1-2", Status: "not_extracted", Error: "", Warnings: []string{}, Chunks: []contracts.DocumentChunk{}, Columns: []string{}})
		return
	}
	s.parsedResponse(c, row.ID)
}
func (s *Service) parsedResponse(c *gin.Context, id string) {
	var row struct{ Data json.RawMessage }
	if s.DB.Table("backend.parsed_documents").Where("file_id=?", id).Take(&row).Error != nil {
		failure(c, 404, "NOT_FOUND")
		return
	}
	c.Data(200, "application/json", row.Data)
}
func (s *Service) saveParsed(row fileRow, document contracts.ParsedDocument) (contracts.ParsedDocument, error) {
	var result contracts.ParsedDocument
	raw, _ := json.Marshal(document)
	if contracts.Validate("ParsedDocument", mapValue(raw)) != nil || document.FileId != row.ID {
		return result, errors.New("INVALID_ARGUMENT")
	}
	if document.Status != "ready" && document.Status != "unsupported" {
		return result, errors.New("PARSE_FAILED")
	}
	file := filePublic(row)
	if document.Sha256 != file.Sha256 || document.ParserRevision != "phase1-2" {
		return result, errors.New("FILE_CHANGED")
	}
	err := s.DB.Transaction(func(tx *gorm.DB) error {
		if err := tx.Exec("SELECT pg_advisory_xact_lock(hashtextextended(?,0))", "document:"+row.ID).Error; err != nil {
			return err
		}
		var current fileRow
		if err := tx.Where("id=?", row.ID).Take(&current).Error; err != nil {
			return err
		}
		if filePublic(current).Sha256 != document.Sha256 {
			return errors.New("FILE_CHANGED")
		}
		var existing struct{ Data json.RawMessage }
		if err := tx.Table("backend.parsed_documents").Where("file_id=? AND sha256=? AND parser_revision=?", row.ID, document.Sha256, document.ParserRevision).Take(&existing).Error; err == nil {
			return json.Unmarshal(existing.Data, &result)
		} else if err != gorm.ErrRecordNotFound {
			return err
		}
		if err := tx.Exec("INSERT INTO backend.parsed_documents(file_id,data,sha256,parser_revision,status,updated_at) VALUES(?,?::jsonb,?,?,?,now()) ON CONFLICT(file_id) DO UPDATE SET data=excluded.data,sha256=excluded.sha256,parser_revision=excluded.parser_revision,status=excluded.status,updated_at=now()", row.ID, string(raw), document.Sha256, document.ParserRevision, document.Status).Error; err != nil {
			return err
		}
		if err := tx.Exec("UPDATE backend.files SET data=jsonb_set(jsonb_set(data,'{parse_status}',to_jsonb(?::text)),'{parse_error}',to_jsonb(?::text)) WHERE id=?", document.Status, document.Error, row.ID).Error; err != nil {
			return err
		}
		if err := tx.Exec("UPDATE backend.document_jobs SET status='retired',lease_id=NULL,lease_until=NULL WHERE file_id=? AND status IN ('queued','processing')", row.ID).Error; err != nil {
			return err
		}
		result = document
		return nil
	})
	return result, err
}
func (s *Service) ExtractFile(c *gin.Context) {
	row, ok := s.ownedFile(c)
	if !ok {
		return
	}
	if !binaryMedia(filePublic(row).MediaType) {
		failure(c, 400, "PARSE_UNSUPPORTED")
		return
	}
	var cached struct{ Data json.RawMessage }
	if s.DB.Table("backend.parsed_documents").Where("file_id=? AND sha256=? AND parser_revision='phase1-2' AND status IN ('ready','unsupported')", row.ID, filePublic(row).Sha256).Take(&cached).Error == nil {
		c.Data(200, "application/json", cached.Data)
		return
	}
	data, err := readStored(row)
	if err != nil {
		failure(c, 503, safeFileError(err))
		return
	}
	file := filePublic(row)
	document, err := s.Client.ExtractDocument(c.Request.Context(), contracts.DocumentExtractMetadata{FileId: file.Id, Sha256: file.Sha256, MediaType: file.MediaType}, data)
	if err != nil {
		failure(c, 503, "DOCUMENT_EXTRACT_UNAVAILABLE")
		return
	}
	if document.Status == "failed" {
		failure(c, 422, document.Error)
		return
	}
	document, err = s.saveParsed(row, document)
	if err != nil {
		failure(c, 409, safeDocumentError(err))
		return
	}
	c.JSON(200, document)
}
func safeDocumentError(err error) string {
	for _, code := range []string{"INVALID_ARGUMENT", "PARSE_FAILED", "FILE_CHANGED"} {
		if err.Error() == code {
			return code
		}
	}
	return "DOCUMENT_CACHE_FAILED"
}
func (s *Service) InternalParsed(c *gin.Context) {
	row, ok := s.authorizedInternalFile(c)
	if !ok {
		return
	}
	v, ok := decode(c, "ParsedDocument")
	if !ok {
		return
	}
	var document contracts.ParsedDocument
	_ = json.Unmarshal(encodeJSON(v), &document)
	saved, err := s.saveParsed(row, document)
	if err != nil {
		failure(c, 409, safeDocumentError(err))
		return
	}
	c.JSON(200, saved)
}
func (s *Service) WorkFiles(c *gin.Context) {
	var req *contracts.WorkFileWrite
	run := c.Query("run_id")
	logical := c.Query("path")
	if c.Request.Method == "PUT" {
		v, ok := decode(c, "WorkFileWrite")
		if !ok {
			return
		}
		req = &contracts.WorkFileWrite{}
		_ = json.Unmarshal(encodeJSON(v), req)
		run = req.RunId
		logical = req.Path
	}
	var start contracts.Start
	e := s.DB.Transaction(func(tx *gorm.DB) error { var err error; start, err = s.Control.CheckExecution(tx, run); return err })
	if e != nil {
		failure(c, 404, "NOT_FOUND")
		return
	}
	if logical == "" && req == nil {
		var rows []struct{ Data json.RawMessage }
		s.DB.Table("backend.work_files").Where("owner_id=? AND thread_id=?", start.Context.UserId, start.ThreadId).Limit(100).Find(&rows)
		out := []contracts.WorkFile{}
		for _, row := range rows {
			var f contracts.WorkFile
			_ = json.Unmarshal(row.Data, &f)
			out = append(out, f)
		}
		c.JSON(200, gin.H{"items": out})
		return
	}
	file, e := s.phaseWorkspace().WorkFile(start.Context.UserId, start.ThreadId, logical, req)
	if e != nil {
		failure(c, 409, "WORKFILE_CONFLICT")
		return
	}
	c.JSON(200, file)
}
func (s *Service) FileVersions(c *gin.Context) {
	row, ok := s.ownedFile(c)
	if !ok {
		return
	}
	out := []contracts.File{filePublic(row)}
	seen := map[string]bool{row.ID: true}
	for len(out) < 30 {
		parent := out[len(out)-1].ParentFileId
		if parent == nil || seen[*parent] {
			break
		}
		seen[*parent] = true
		var previous fileRow
		if s.DB.Where("id=? AND owner_id=?", *parent, identity(c).UserId).Take(&previous).Error != nil {
			break
		}
		out = append(out, filePublic(previous))
	}
	c.JSON(200, contracts.FileList{Items: out, HasMore: false})
}
func (s *Service) bindParent(file contracts.File, parent *string, run string) (contracts.File, error) {
	if parent == nil {
		return file, nil
	}
	var start contracts.Start
	e := s.DB.Transaction(func(tx *gorm.DB) error { var err error; start, err = s.Control.CheckExecution(tx, run); return err })
	if e != nil {
		return file, e
	}
	allowed := false
	for _, ref := range start.FileRefs {
		if ref.Id == *parent {
			allowed = true
		}
	}
	if !allowed {
		return file, errors.New("FILE_NOT_AUTHORIZED")
	}
	var row fileRow
	if e = s.DB.Where("id=? AND owner_id=?", *parent, file.OwnerId).Take(&row).Error; e != nil {
		return file, e
	}
	if file.ParentFileId != nil {
		if *file.ParentFileId != *parent {
			return file, errors.New("ARTIFACT_CONFLICT")
		}
		return file, nil
	}
	file.ParentFileId = parent
	v := int64(2)
	previous := filePublic(row)
	if previous.Version != nil {
		v = *previous.Version + 1
	}
	file.Version = &v
	return file, s.DB.Model(&fileRow{}).Where("id=?", file.Id).Update("data", encodeJSON(file)).Error
}
func (s *Service) InternalBinaryArtifact(c *gin.Context) {
	var raw any
	if json.Unmarshal([]byte(c.GetHeader("X-Artifact-Metadata")), &raw) != nil || contracts.Validate("BinaryArtifactMetadata", raw) != nil {
		failure(c, 400, "INVALID_ARGUMENT")
		return
	}
	var req contracts.BinaryArtifactMetadata
	_ = json.Unmarshal(encodeJSON(raw), &req)
	var start contracts.Start
	e := s.DB.Transaction(func(tx *gorm.DB) error {
		if req.ArtifactKey == "export.docx" && req.MediaType == "application/vnd.openxmlformats-officedocument.wordprocessingml.document" && req.ParentFileId == nil {
			var row submission
			if err := tx.Where("run_id=? AND status='SUCCEEDED'", req.RunId).Take(&row).Error; err != nil {
				return err
			}
			return json.Unmarshal(row.StartPayload, &start)
		}
		var err error
		start, err = s.Control.CheckExecution(tx, req.RunId)
		return err
	})
	if e != nil {
		failure(c, 409, "RUN_NOT_AUTHORIZED")
		return
	}
	if req.ParentFileId != nil {
		found := false
		for _, f := range start.FileRefs {
			if f.Id == *req.ParentFileId {
				found = true
			}
		}
		if !found {
			failure(c, 404, "NOT_FOUND")
			return
		}
	}
	c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, maxFileBytes)
	data, e := io.ReadAll(c.Request.Body)
	if e != nil {
		failure(c, 413, "FILE_TOO_LARGE")
		return
	}
	if req.MediaType == "application/json" {
		var chart contracts.Chart
		if json.Unmarshal(data, &chart) != nil {
			failure(c, 400, "INVALID_CHART")
			return
		}
		found := false
		for _, f := range start.FileRefs {
			if f.Id == chart.FileId {
				found = true
			}
		}
		if !found {
			failure(c, 400, "INVALID_CHART_SOURCE")
			return
		}
	}
	f, e := s.storeFile(start.Context.UserId, &req.RunId, &req.ArtifactKey, req.Name, req.MediaType, data)
	if e == nil {
		f, e = s.bindParent(f, req.ParentFileId, req.RunId)
	}
	if e == nil && binaryMedia(f.MediaType) {
		state := "not_extracted"
		f.ParseStatus = &state
		e = s.DB.Model(&fileRow{}).Where("id=?", f.Id).Update("data", encodeJSON(f)).Error
	}
	if e != nil {
		failure(c, 409, safeFileError(e))
		return
	}
	c.JSON(200, f)
}
func (s *Service) Sources(c *gin.Context) {
	r, ok := s.get(c)
	if !ok {
		return
	}
	status, b, e := s.Client.call(c.Request.Context(), "GET", "/internal/runs/"+r.RunID+"/sources", nil)
	if e != nil {
		failure(c, 503, "RUNTIME_UNAVAILABLE")
		return
	}
	c.Data(status, "application/json", b)
}
func (s *Service) NetworkStatus(c *gin.Context) {
	status, b, e := s.Client.call(c.Request.Context(), "GET", "/internal/capabilities/network", nil)
	if e != nil {
		failure(c, 503, "RUNTIME_UNAVAILABLE")
		return
	}
	c.Data(status, "application/json", b)
}
