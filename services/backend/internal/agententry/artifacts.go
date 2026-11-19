package agententry

import (
	"agentworkspace/backend/internal/contracts"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"gorm.io/gorm"
	"time"
)

type artifactRow struct {
	ID, OwnerID, Title string
	CurrentRevisionID  *string
	CreatedAt          time.Time
}

func (artifactRow) TableName() string { return "backend.artifacts" }

type revisionRow struct {
	ID, ArtifactID                                 string
	Version                                        int64
	ParentRevisionID                               *string
	FileID                                         string
	SourceThreadID, SourceRunID, SourceExecutionID *string
	Status                                         string
	CreatedAt                                      time.Time
}

func (revisionRow) TableName() string { return "backend.artifact_revisions" }
func (s *Service) prepareRevision(tx *gorm.DB, f *contracts.File, parent, execution *string) error {
	if f.RunId == nil {
		return errors.New("RUN_NOT_AUTHORIZED")
	}
	var run submission
	if e := tx.Raw("SELECT * FROM backend.run_submissions WHERE run_id=? AND owner_id=? FOR UPDATE", *f.RunId, f.OwnerId).Scan(&run).Error; e != nil {
		return e
	}
	if run.RunID == "" {
		return errors.New("RUN_NOT_AUTHORIZED")
	}
	if run.CancelRequested {
		return errors.New("RUN_NOT_AUTHORIZED")
	}
	f.SourceThreadId = &run.ThreadID
	f.SourceExecutionId = execution
	f.ParentFileId = parent
	aid := f.Id
	rid := f.Id
	version := int64(1)
	if parent != nil {
		var start contracts.Start
		if e := jsonDecode(run.StartPayload, &start); e != nil {
			return e
		}
		allowed := false
		for _, ref := range start.FileRefs {
			if ref.Id == *parent {
				allowed = true
			}
		}
		if !allowed {
			return errors.New("FILE_NOT_AUTHORIZED")
		}
		var previous fileRow
		if e := tx.Where("id=? AND owner_id=? AND status='READY'", *parent, f.OwnerId).Take(&previous).Error; e != nil {
			return e
		}
		pf := filePublic(previous)
		if pf.ArtifactId != nil && pf.MediaType == f.MediaType {
			aid = *pf.ArtifactId
			var ar artifactRow
			if e := tx.Where("id=? AND owner_id=?", aid, f.OwnerId).Take(&ar).Error; e != nil {
				return e
			}
			// A branch from a historical revision is allowed. A competing child produced
			// after this Run began is rejected instead of silently winning the race.
			if ar.CurrentRevisionID != nil {
				var latest revisionRow
				if e := tx.Where("id=?", *ar.CurrentRevisionID).Take(&latest).Error; e != nil {
					return e
				}
				if latest.CreatedAt.After(run.CreatedAt) && !samePointer(ar.CurrentRevisionID, pf.RevisionId) {
					return errors.New("ARTIFACT_REVISION_CONFLICT")
				}
			}
			if e := tx.Model(&revisionRow{}).Where("artifact_id=?", aid).Select("COALESCE(max(version),0)+1").Scan(&version).Error; e != nil {
				return e
			}
		}
	}
	if aid == f.Id {
		if e := tx.Create(&artifactRow{ID: aid, OwnerID: f.OwnerId, Title: f.Name, CreatedAt: time.Now().UTC()}).Error; e != nil {
			return e
		}
	}
	f.ArtifactId = &aid
	f.RevisionId = &rid
	f.Version = &version
	return nil
}
func jsonDecode(data []byte, v any) error { return json.Unmarshal(data, v) }
func verifyCandidate(data []byte, sha *string, size *int64) error {
	if size != nil && int64(len(data)) != *size {
		return errors.New("FILE_INTEGRITY_ERROR")
	}
	if sha != nil {
		h := sha256.Sum256(data)
		if hex.EncodeToString(h[:]) != *sha {
			return errors.New("FILE_INTEGRITY_ERROR")
		}
	}
	return nil
}
func (s *Service) revisionList(owner, artifactID string) (contracts.ArtifactRevisionList, error) {
	var out contracts.ArtifactRevisionList
	var ar artifactRow
	if e := s.DB.Where("id=? AND owner_id=?", artifactID, owner).Take(&ar).Error; e != nil {
		return out, e
	}
	out.Artifact = contracts.Artifact{Id: ar.ID, OwnerId: ar.OwnerID, Title: ar.Title, CurrentRevisionId: ar.CurrentRevisionID, CreatedAt: ar.CreatedAt.UTC().Format(time.RFC3339Nano)}
	out.Items = []contracts.ArtifactRevision{}
	var rows []revisionRow
	if e := s.DB.Where("artifact_id=? AND status='READY'", ar.ID).Order("version DESC").Limit(101).Find(&rows).Error; e != nil {
		return out, e
	}
	out.HasMore = len(rows) > 100
	if out.HasMore {
		rows = rows[:100]
	}
	for _, r := range rows {
		var f fileRow
		if e := s.DB.Where("id=? AND owner_id=? AND status='READY'", r.FileID, owner).Take(&f).Error; e != nil {
			return out, e
		}
		out.Items = append(out.Items, contracts.ArtifactRevision{Id: r.ID, ArtifactId: r.ArtifactID, Version: r.Version, ParentRevisionId: r.ParentRevisionID, File: filePublic(f), SourceThreadId: r.SourceThreadID, SourceRunId: r.SourceRunID, SourceExecutionId: r.SourceExecutionID, Status: r.Status, CreatedAt: r.CreatedAt.UTC().Format(time.RFC3339Nano)})
	}
	return out, nil
}
func (s *Service) ArtifactRevisions(c *gin.Context) {
	if _, e := uuid.Parse(c.Param("id")); e != nil {
		failure(c, 404, "NOT_FOUND")
		return
	}
	out, e := s.revisionList(identity(c).UserId, c.Param("id"))
	if e != nil {
		failure(c, 404, "NOT_FOUND")
		return
	}
	c.JSON(200, out)
}
func (s *Service) FileVersions(c *gin.Context) {
	row, ok := s.ownedFile(c)
	if !ok {
		return
	}
	file := filePublic(row)
	if file.ArtifactId == nil {
		c.JSON(200, contracts.FileList{Items: []contracts.File{file}, HasMore: false})
		return
	}
	out, e := s.revisionList(identity(c).UserId, *file.ArtifactId)
	if e != nil {
		failure(c, 503, "DEPENDENCY_UNAVAILABLE")
		return
	}
	files := []contracts.File{}
	for _, r := range out.Items {
		files = append(files, r.File)
	}
	c.JSON(200, contracts.FileList{Items: files, HasMore: out.HasMore})
}
