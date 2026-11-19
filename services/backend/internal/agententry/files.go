package agententry

import (
	"agentworkspace/backend/internal/blobstore"
	"agentworkspace/backend/internal/contracts"
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/csv"
	"encoding/hex"
	"encoding/json"
	"errors"
	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"gorm.io/gorm"
	"io"
	"mime"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"
)

const maxFileBytes = 5 * 1024 * 1024

func fileRoot() string { return os.Getenv("FILE_ROOT") }

type fileRow struct {
	ID, OwnerID     string
	RunID           *string
	ArtifactKey     *string
	Data            json.RawMessage
	StorageKey      string
	StorageProvider string
	Status          string
	CreatedAt       time.Time
}

func (fileRow) TableName() string { return "backend.files" }
func filePublic(f fileRow) contracts.File {
	var v contracts.File
	_ = json.Unmarshal(f.Data, &v)
	return v
}
func inspectMaterial(data []byte, media string) ([]string, error) {
	if len(data) > maxFileBytes {
		return nil, errors.New("FILE_TOO_LARGE")
	}
	if binaryMedia(media) {
		if media == "application/pdf" && bytes.HasPrefix(data, []byte("%PDF-")) {
			return []string{}, nil
		}
		if media != "application/pdf" && bytes.HasPrefix(data, []byte("PK\x03\x04")) {
			return []string{}, nil
		}
		return nil, errors.New("UNSUPPORTED_FILE_ENCODING")
	}
	if !utf8.Valid(data) || bytes.IndexByte(data, 0) >= 0 {
		return nil, errors.New("UNSUPPORTED_FILE_ENCODING")
	}
	text := strings.TrimPrefix(string(data), "\ufeff")
	if media != "text/csv" {
		if utf8.RuneCountInString(text) > 50000 {
			return nil, errors.New("TEXT_TOO_LARGE")
		}
		return []string{}, nil
	}
	reader := csv.NewReader(strings.NewReader(text))
	reader.FieldsPerRecord = -1
	header, e := reader.Read()
	if e != nil || len(header) == 0 || len(header) > 30 {
		return nil, errors.New("INVALID_CSV")
	}
	names := map[string]bool{}
	for _, h := range header {
		if h == "" || names[h] {
			return nil, errors.New("INVALID_CSV_HEADER")
		}
		names[h] = true
	}
	for n := 0; ; n++ {
		record, e := reader.Read()
		if e == io.EOF {
			break
		}
		if e != nil || len(record) != len(header) {
			return nil, errors.New("INVALID_CSV")
		}
		if n >= 10000 {
			return nil, errors.New("CSV_ROW_LIMIT")
		}
	}
	return header, nil
}
func (s *Service) storeFile(owner string, run *string, key *string, name, media string, data []byte, parent, execution *string) (contracts.File, error) {
	var result contracts.File
	if key != nil && media == "text/csv" {
		reader := csv.NewReader(bytes.NewReader(data))
		reader.FieldsPerRecord = -1
		var out bytes.Buffer
		writer := csv.NewWriter(&out)
		for {
			record, e := reader.Read()
			if e == io.EOF {
				break
			}
			if e != nil {
				return result, errors.New("INVALID_CSV")
			}
			for i, value := range record {
				if strings.HasPrefix(value, "=") || strings.HasPrefix(value, "+") || strings.HasPrefix(value, "-") || strings.HasPrefix(value, "@") || strings.HasPrefix(value, "\t") || strings.HasPrefix(value, "\r") {
					if _, e := strconv.ParseFloat(value, 64); e != nil {
						record[i] = "'" + value
					}
				}
			}
			if e = writer.Write(record); e != nil {
				return result, e
			}
		}
		writer.Flush()
		if e := writer.Error(); e != nil {
			return result, e
		}
		data = out.Bytes()
	}

	if media == "application/json" {
		var v any
		if json.Unmarshal(data, &v) != nil || contracts.Validate("Chart", v) != nil {
			return result, errors.New("INVALID_CHART")
		}
	} else {
		if _, e := inspectMaterial(data, media); e != nil {
			return result, e
		}
	}
	hash := sha256.Sum256(data)
	digest := hex.EncodeToString(hash[:])
	id := uuid.NewString()
	if run != nil && key != nil {
		id = uuid.NewSHA1(uuid.MustParse(*run), []byte(*key)).String()
	}

	source := "upload"
	if key != nil {
		source = "generated"
	}
	result = contracts.File{Id: id, OwnerId: owner, RunId: run, Name: name, MediaType: media, Size: int64(len(data)), Sha256: digest, Source: source, Status: "PENDING", CreatedAt: time.Now().UTC().Format(time.RFC3339Nano)}
	if s.Blobs == nil {
		return result, blobstore.ErrUnavailable
	}
	provider := s.Blobs.Default
	store, err := s.Blobs.For(provider)
	if err != nil {
		return result, err
	}
	storage := "users/" + owner + "/uploads/" + id + "/content"
	if key != nil {
		storage = "users/" + owner + "/revisions/" + id + "/content"
	}
	// Durable intent precedes object I/O. A process crash after Put cannot leave
	// an untracked orphan; the cleaner waits and rechecks committed references.
	if e := s.DB.Exec("INSERT INTO backend.blob_cleanup(storage_provider,storage_key) VALUES(?,?) ON CONFLICT DO NOTHING", provider, storage).Error; e != nil {
		return result, e
	}
	e := s.DB.Transaction(func(tx *gorm.DB) error {
		if e := tx.Exec("SELECT pg_advisory_xact_lock(210004)").Error; e != nil {
			return e
		}
		var prior fileRow
		if e := tx.Where("id=?", id).Take(&prior).Error; e == nil {
			v := filePublic(prior)
			if v.OwnerId != owner || v.Sha256 != digest || v.MediaType != media || !samePointer(v.ParentFileId, parent) || !samePointer(v.SourceExecutionId, execution) {
				return errors.New("ARTIFACT_CONFLICT")
			}
			if _, e := s.readStored(prior); e != nil {
				return e
			}
			result = v
			return nil
		} else if e != gorm.ErrRecordNotFound {
			return e
		}
		if key != nil {
			if e := s.prepareRevision(tx, &result, parent, execution); e != nil {
				return e
			}
		}
		row := fileRow{ID: id, OwnerID: owner, RunID: run, ArtifactKey: key, Data: encodeJSON(result), StorageKey: storage, StorageProvider: provider, Status: "PENDING", CreatedAt: time.Now().UTC()}
		if e := tx.Create(&row).Error; e != nil {
			return e
		}
		if key != nil {
			var parentRevision *string
			if parent != nil {
				var pf fileRow
				if e := tx.Where("id=?", *parent).Take(&pf).Error; e != nil {
					return e
				}
				parentRevision = filePublic(pf).RevisionId
			}
			if e := tx.Exec("INSERT INTO backend.artifact_revisions(id,artifact_id,version,parent_revision_id,file_id,source_thread_id,source_run_id,source_execution_id,status) VALUES(?,?,?,?,?,?,?,?,'PENDING')", *result.RevisionId, *result.ArtifactId, *result.Version, parentRevision, id, result.SourceThreadId, run, execution).Error; e != nil {
				return e
			}
		}
		ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
		defer cancel()
		meta := blobstore.Metadata{Size: result.Size, SHA256: digest, MediaType: media}
		if e := store.Put(ctx, storage, data, meta); e != nil {
			return e
		}
		if e := store.Head(ctx, storage, meta); e != nil {
			return e
		}
		if os.Getenv("ENABLE_FAULTS") == "true" && os.Getenv("FAULT_ARTIFACT_METADATA") == "true" && key != nil {
			return errors.New("ARTIFACT_STORAGE_FAILED")
		}
		result.Status = "READY"
		if e := tx.Model(&fileRow{}).Where("id=?", id).Updates(map[string]any{"data": encodeJSON(result), "status": "READY"}).Error; e != nil {
			return e
		}
		if key != nil {
			if e := tx.Exec("UPDATE backend.artifact_revisions SET status='READY' WHERE id=?", *result.RevisionId).Error; e != nil {
				return e
			}
			if e := tx.Exec("UPDATE backend.artifacts SET current_revision_id=? WHERE id=?", *result.RevisionId, *result.ArtifactId).Error; e != nil {
				return e
			}
		}
		return nil
	})
	if e == nil {
		_ = s.DB.Exec("DELETE FROM backend.blob_cleanup WHERE storage_provider=? AND storage_key=?", provider, storage).Error
	}
	return result, e
}
func samePointer(a, b *string) bool {
	if a == nil || b == nil {
		return a == nil && b == nil
	}
	return *a == *b
}
func (s *Service) readStored(row fileRow) ([]byte, error) {
	if !validID(row.ID) || row.Status != "" && row.Status != "READY" {
		return nil, errors.New("ARTIFACT_NOT_READY")
	}
	if s.Blobs == nil {
		return nil, blobstore.ErrUnavailable
	}
	store, e := s.Blobs.For(row.StorageProvider)
	if e != nil {
		return nil, e
	}
	v := filePublic(row)
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	return store.Get(ctx, row.StorageKey, blobstore.Metadata{Size: v.Size, SHA256: v.Sha256, MediaType: v.MediaType})
}
func (s *Service) ownedFile(c *gin.Context) (fileRow, bool) {
	var row fileRow
	if !validID(c.Param("id")) {
		failure(c, 404, "NOT_FOUND")
		return row, false
	}
	if e := s.DB.Where("id=? AND owner_id=? AND data->>'status'='READY'", c.Param("id"), identity(c).UserId).Take(&row).Error; e != nil {
		failure(c, 404, "NOT_FOUND")
		return row, false
	}
	return row, true
}
func (s *Service) Upload(c *gin.Context) {
	c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, maxFileBytes+65536)
	if e := c.Request.ParseMultipartForm(maxFileBytes + 65536); e != nil {
		failure(c, 413, "FILE_TOO_LARGE_OR_INVALID")
		return
	}
	defer c.Request.MultipartForm.RemoveAll()
	if len(c.Request.MultipartForm.File["file"]) != 1 {
		failure(c, 400, "INVALID_ARGUMENT")
		return
	}
	part := c.Request.MultipartForm.File["file"][0]
	name := filepath.Base(strings.ReplaceAll(part.Filename, "\\", "/"))
	if name == "." || name == "" || utf8.RuneCountInString(name) > 120 {
		failure(c, 400, "INVALID_FILE_NAME")
		return
	}
	media := map[string]string{".txt": "text/plain", ".md": "text/markdown", ".csv": "text/csv", ".pdf": "application/pdf", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}[strings.ToLower(filepath.Ext(name))]
	if media == "" {
		failure(c, 400, "UNSUPPORTED_FILE")
		return
	}
	f, e := part.Open()
	if e != nil {
		failure(c, 400, "INVALID_ARGUMENT")
		return
	}
	defer f.Close()
	data, e := io.ReadAll(io.LimitReader(f, maxFileBytes+1))
	if e != nil {
		failure(c, 400, "INVALID_ARGUMENT")
		return
	}
	v, e := s.storeFile(identity(c).UserId, nil, nil, name, media, data, nil, nil)
	if e != nil {
		status := 400
		if errors.Is(e, blobstore.ErrUnavailable) || safeFileError(e) == "FILE_STORAGE_UNAVAILABLE" {
			status = 503
		}
		failure(c, status, safeFileError(e))
		return
	}
	if binaryMedia(media) {
		status := "not_extracted"
		v.ParseStatus = &status
		if e = s.DB.Model(&fileRow{}).Where("id=?", v.Id).Update("data", encodeJSON(v)).Error; e != nil {
			failure(c, 503, "DEPENDENCY_UNAVAILABLE")
			return
		}
	}
	c.JSON(201, v)
}
func safeFileError(e error) string {
	for _, v := range []string{"FILE_TOO_LARGE", "UNSUPPORTED_FILE_ENCODING", "TEXT_TOO_LARGE", "INVALID_CSV", "INVALID_CSV_HEADER", "CSV_ROW_LIMIT", "INVALID_CHART", "ARTIFACT_CONFLICT", "ARTIFACT_STORAGE_FAILED", "FILE_MISSING", "FILE_INTEGRITY_ERROR", "STORAGE_UNAVAILABLE", "ARTIFACT_NOT_READY", "FILE_NOT_AUTHORIZED", "ARTIFACT_REVISION_CONFLICT"} {
		if e.Error() == v {
			return v
		}
	}
	return "FILE_STORAGE_UNAVAILABLE"
}
func (s *Service) Files(c *gin.Context) {
	offset, e := strconv.Atoi(c.DefaultQuery("offset", "0"))
	if e != nil || offset < 0 {
		failure(c, 400, "INVALID_ARGUMENT")
		return
	}
	source := c.Query("source")
	if source != "" && source != "upload" && source != "generated" {
		failure(c, 400, "INVALID_ARGUMENT")
		return
	}
	q := s.DB.Where("owner_id=? AND status='READY'", identity(c).UserId)
	// A logical artifact appears once in the library; historical versions stay
	// addressable by File ID and through the explicit version endpoint.
	q = q.Where("(data->>'artifact_id' IS NULL OR EXISTS (SELECT 1 FROM backend.artifacts a WHERE a.id::text=backend.files.data->>'artifact_id' AND a.current_revision_id::text=backend.files.data->>'revision_id'))")
	if source != "" {
		q = q.Where("data->>'source'=?", source)
	}
	if term := c.Query("q"); term != "" {
		q = q.Where("data->>'name' ILIKE ?", "%"+term+"%")
	}
	var rows []fileRow
	if q.Order("created_at DESC,id").Offset(offset).Limit(51).Find(&rows).Error != nil {
		failure(c, 503, "DEPENDENCY_UNAVAILABLE")
		return
	}
	more := len(rows) > 50
	if more {
		rows = rows[:50]
	}
	out := []contracts.File{}
	for _, f := range rows {
		out = append(out, filePublic(f))
	}
	c.JSON(200, contracts.FileList{Items: out, HasMore: more})
}
func (s *Service) File(c *gin.Context) {
	row, ok := s.ownedFile(c)
	if ok {
		c.JSON(200, filePublic(row))
	}
}
func (s *Service) FileContent(c *gin.Context) {
	row, ok := s.ownedFile(c)
	if !ok {
		return
	}
	s.serveContent(c, row, false)
}
func (s *Service) serveContent(c *gin.Context, row fileRow, internal bool) {
	data, e := s.readStored(row)
	if e != nil {
		failure(c, 503, safeFileError(e))
		return
	}
	meta := filePublic(row)
	if binaryMedia(meta.MediaType) {
		var parsed struct{ Data json.RawMessage }
		if s.DB.Table("backend.parsed_documents").Where("file_id=?", row.ID).Take(&parsed).Error != nil {
			failure(c, 409, "NOT_READY")
			return
		}
		var doc contracts.ParsedDocument
		_ = json.Unmarshal(parsed.Data, &doc)
		if doc.Status != "ready" {
			failure(c, 409, "PARSE_"+strings.ToUpper(doc.Status))
			return
		}
		var text strings.Builder
		for _, chunk := range doc.Chunks {
			if text.Len() > 150000 {
				break
			}
			text.WriteString("[" + chunk.Locator + "]\n" + chunk.Text + "\n\n")
		}
		c.JSON(200, contracts.FileContent{File: meta, Text: text.String(), Columns: doc.Columns})
		return
	}
	columns := []string{}
	if meta.MediaType == "text/csv" {
		columns, e = inspectMaterial(data, meta.MediaType)
		if e != nil {
			failure(c, 400, safeFileError(e))
			return
		}
	}
	text := strings.TrimPrefix(string(data), "\ufeff")
	if !internal && c.Query("columns_only") == "1" {
		text = ""
	}
	if !internal && utf8.RuneCountInString(text) > 50000 {
		failure(c, 413, "PREVIEW_TOO_LARGE")
		return
	}
	c.JSON(200, contracts.FileContent{File: meta, Text: text, Columns: columns})
}
func (s *Service) DownloadLocation(c *gin.Context) {
	row, ok := s.ownedFile(c)
	if !ok {
		return
	}
	v := filePublic(row)
	store, e := s.Blobs.For(row.StorageProvider)
	if e != nil {
		failure(c, 503, safeFileError(e))
		return
	}
	if row.StorageProvider == "s3" {
		ctx, cancel := context.WithTimeout(c.Request.Context(), 10*time.Second)
		defer cancel()
		if e = store.Head(ctx, row.StorageKey, blobstore.Metadata{Size: v.Size, SHA256: v.Sha256, MediaType: v.MediaType}); e != nil {
			failure(c, 503, safeFileError(e))
			return
		}
		u, expires, e := store.PresignGet(ctx, row.StorageKey, v.Name, v.MediaType)
		if e != nil {
			failure(c, 503, safeFileError(e))
			return
		}
		c.Header("Cache-Control", "no-store")
		c.Header("Referrer-Policy", "no-referrer")
		c.JSON(200, contracts.DownloadLocation{Url: u, ExpiresAt: expires.Format(time.RFC3339), Mode: "presigned"})
		return
	}
	c.Header("Cache-Control", "no-store")
	c.JSON(200, contracts.DownloadLocation{Url: "/api/files/" + v.Id + "/download", ExpiresAt: time.Now().UTC().Add(10 * time.Minute).Format(time.RFC3339), Mode: "stream"})
}
func (s *Service) Download(c *gin.Context) {
	row, ok := s.ownedFile(c)
	if !ok {
		return
	}
	if row.StorageProvider == "s3" {
		v := filePublic(row)
		store, e := s.Blobs.For("s3")
		if e != nil {
			failure(c, 503, safeFileError(e))
			return
		}
		ctx, cancel := context.WithTimeout(c.Request.Context(), 10*time.Second)
		defer cancel()
		if e = store.Head(ctx, row.StorageKey, blobstore.Metadata{Size: v.Size, SHA256: v.Sha256, MediaType: v.MediaType}); e != nil {
			failure(c, 503, safeFileError(e))
			return
		}
		u, _, e := store.PresignGet(ctx, row.StorageKey, v.Name, v.MediaType)
		if e != nil {
			failure(c, 503, safeFileError(e))
			return
		}
		c.Header("Cache-Control", "no-store")
		c.Header("Referrer-Policy", "no-referrer")
		c.Redirect(302, u)
		return
	}
	data, e := s.readStored(row)
	if e != nil {
		failure(c, 503, safeFileError(e))
		return
	}
	c.Header("X-Content-Type-Options", "nosniff")
	c.Header("Content-Disposition", mime.FormatMediaType("attachment", map[string]string{"filename": filePublic(row).Name}))
	c.DataFromReader(200, int64(len(data)), filePublic(row).MediaType, bytes.NewReader(data), nil)
}
func (s *Service) authorizedInternalFile(c *gin.Context) (fileRow, bool) {
	run := c.Query("run_id")
	if !validID(run) || !validID(c.Param("id")) {
		failure(c, 404, "NOT_FOUND")
		return fileRow{}, false
	}
	var row fileRow
	e := s.DB.Transaction(func(tx *gorm.DB) error {
		if e := controlLock(tx); e != nil {
			return e
		}
		start, e := s.Control.CheckExecution(tx, run)
		if e != nil {
			return e
		}
		allowed := false
		for _, f := range start.FileRefs {
			if f.Id == c.Param("id") {
				allowed = true
			}
		}
		if !allowed {
			return gorm.ErrRecordNotFound
		}
		return tx.Where("id=? AND owner_id=? AND data->>'status'='READY'", c.Param("id"), start.Context.UserId).Take(&row).Error
	})
	if e != nil {
		failure(c, 404, "NOT_FOUND")
		return fileRow{}, false
	}
	return row, true
}
func (s *Service) InternalFile(c *gin.Context) {
	row, ok := s.authorizedInternalFile(c)
	if !ok {
		return
	}
	if strings.HasSuffix(c.Request.URL.Path, "/blob") {
		data, e := s.readStored(row)
		if e != nil {
			failure(c, 503, safeFileError(e))
			return
		}
		c.Data(200, filePublic(row).MediaType, data)
		return
	}
	if strings.HasSuffix(c.Request.URL.Path, "/parsed") {
		s.parsedResponse(c, row.ID)
		return
	}
	if c.Query("metadata_only") == "1" {
		c.JSON(200, contracts.FileContent{File: filePublic(row), Text: "", Columns: []string{}})
		return
	}
	s.serveContent(c, row, true)
}
func (s *Service) InternalArtifact(c *gin.Context) {
	v, ok := decode(c, "ArtifactWrite")
	if !ok {
		return
	}
	var req contracts.ArtifactWrite
	_ = json.Unmarshal(encodeJSON(v), &req)
	var r submission
	if s.DB.Where("run_id=?", req.RunId).Take(&r).Error != nil {
		failure(c, 404, "NOT_FOUND")
		return
	}
	var start contracts.Start
	_ = json.Unmarshal(r.StartPayload, &start)
	if req.MediaType == "text/markdown" && req.ArtifactKey == "report.md" {
		if r.Status != "SUCCEEDED" {
			failure(c, 409, "RUN_NOT_COMPLETED")
			return
		}
	} else {
		if e := s.Control.CheckRun(c.Request.Context(), r.RunID); e != nil {
			failure(c, 409, "RUN_NOT_AUTHORIZED")
			return
		}
	}
	if req.MediaType == "application/json" {
		var chart contracts.Chart
		if json.Unmarshal([]byte(req.Content), &chart) != nil {
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
	if e := verifyCandidate([]byte(req.Content), req.Sha256, req.Size); e != nil {
		failure(c, 400, safeFileError(e))
		return
	}
	file, e := s.storeFile(r.OwnerID, &r.RunID, &req.ArtifactKey, req.Name, req.MediaType, []byte(req.Content), req.ParentFileId, req.ExecutionId)
	if e != nil {
		failure(c, 503, safeFileError(e))
		return
	}
	c.JSON(200, file)
}
func (s *Service) Artifacts(c *gin.Context) {
	r, ok := s.get(c)
	if !ok {
		return
	}
	if c.Request.Method == "POST" {
		if r.Active {
			s.syncRun(c.Request.Context(), &r)
		}
		if r.Status != "SUCCEEDED" {
			failure(c, 409, "RUN_NOT_COMPLETED")
			return
		}
		format := c.DefaultQuery("format", "markdown")
		if format != "markdown" && format != "docx" {
			failure(c, 400, "INVALID_ARGUMENT")
			return
		}
		status, b, e := s.Client.call(c.Request.Context(), "POST", "/internal/runs/"+r.RunID+"/artifacts?format="+format, nil)
		if e != nil {
			failure(c, 503, "ARTIFACT_UNAVAILABLE")
			return
		}
		c.Data(status, "application/json", b)
		return
	}
	var rows []fileRow
	if s.DB.Where("run_id=? AND owner_id=? AND data->>'source'='generated'", r.RunID, r.OwnerID).Order("created_at").Find(&rows).Error != nil {
		failure(c, 503, "DEPENDENCY_UNAVAILABLE")
		return
	}
	out := []contracts.File{}
	for _, f := range rows {
		out = append(out, filePublic(f))
	}
	c.JSON(200, contracts.FileList{Items: out, HasMore: false})
}

// Managed temporary/orphan files older than an hour can only originate from this service.
func (s *Service) CleanupFiles() {
	root := fileRoot()
	if root == "" {
		return
	}
	entries, e := os.ReadDir(root)
	if e != nil {
		return
	}
	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}
		name := entry.Name()
		if !strings.HasPrefix(name, "tmp-") && !strings.HasPrefix(name, "obj-") {
			continue
		}
		info, e := entry.Info()
		if e != nil || time.Since(info.ModTime()) < time.Hour {
			continue
		}
		var n int64
		if s.DB.Model(&fileRow{}).Where("storage_key=?", name).Count(&n).Error == nil && n == 0 {
			_ = os.Remove(filepath.Join(root, name))
		}
	}
}
