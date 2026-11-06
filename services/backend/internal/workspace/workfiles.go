package workspace

import (
	"agentworkspace/backend/internal/contracts"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"gorm.io/gorm"
	"path"
	"strings"
)

func (s *Service) WorkFile(owner, thread, logical string, write *contracts.WorkFileWrite) (contracts.WorkFile, error) {
	var result contracts.WorkFile
	clean := path.Clean(logical)
	if clean != logical || strings.Contains(logical, "\\") || (!strings.HasPrefix(clean, "/work/") && !strings.HasPrefix(clean, "/outputs/") && !strings.HasPrefix(clean, "/large_tool_results/") && !strings.HasPrefix(clean, "/conversation_history/")) {
		return result, errors.New("WORKFILE_PATH_DENIED")
	}
	err := s.DB.Transaction(func(tx *gorm.DB) error {
		if e := tx.Exec("SELECT pg_advisory_xact_lock(hashtextextended(?,0))", owner+thread+clean).Error; e != nil {
			return e
		}
		var row struct {
			Data     json.RawMessage
			Revision int64
		}
		e := tx.Table("backend.work_files").Where("owner_id=? AND thread_id=? AND path=?", owner, thread, clean).Take(&row).Error
		if e != nil && e != gorm.ErrRecordNotFound {
			return e
		}
		if write == nil {
			if e != nil {
				return e
			}
			return json.Unmarshal(row.Data, &result)
		}
		if e == gorm.ErrRecordNotFound {
			var count int64
			if err := tx.Table("backend.work_files").Where("owner_id=? AND thread_id=?", owner, thread).Count(&count).Error; err != nil {
				return err
			}
			if count >= 100 {
				return errors.New("WORKFILE_LIMIT")
			}
		}
		if write.ExpectedRevision != row.Revision {
			return errors.New("WORKFILE_CONFLICT")
		}
		sum := sha256.Sum256([]byte(write.Content))
		result = contracts.WorkFile{Path: clean, Content: write.Content, Revision: row.Revision + 1, Sha256: hex.EncodeToString(sum[:])}
		raw, _ := json.Marshal(result)
		if e = tx.Exec("INSERT INTO backend.work_files(owner_id,thread_id,path,revision,data) VALUES(?,?,?,?,?::jsonb) ON CONFLICT(owner_id,thread_id,path) DO UPDATE SET revision=excluded.revision,data=excluded.data,updated_at=now()", owner, thread, clean, result.Revision, string(raw)).Error; e != nil {
			return e
		}
		if err := tx.Exec("INSERT INTO backend.work_file_versions(owner_id,thread_id,path,revision,data) VALUES(?,?,?,?,?::jsonb)", owner, thread, clean, result.Revision, string(raw)).Error; err != nil {
			return err
		}
		return tx.Exec("DELETE FROM backend.work_file_versions WHERE owner_id=? AND thread_id=? AND path=? AND revision<?", owner, thread, clean, result.Revision-19).Error
	})
	return result, err
}
