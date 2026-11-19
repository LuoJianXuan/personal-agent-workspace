package agententry

import (
	"context"
	"gorm.io/gorm"
	"time"
)

// Only keys explicitly recorded by a durable publication intent are considered.
// Never list or sweep a shared bucket, and never delete a referenced object.
func (s *Service) CleanupBlobs(ctx context.Context) {
	timer := time.NewTicker(15 * time.Minute)
	defer timer.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-timer.C:
		}
		if s.Blobs == nil {
			continue
		}
		_ = s.DB.Transaction(func(tx *gorm.DB) error {
			if e := tx.Exec("SELECT pg_advisory_xact_lock(210004)").Error; e != nil {
				return e
			}
			var rows []struct{ StorageProvider, StorageKey string }
			if e := tx.Table("backend.blob_cleanup").Where("created_at < now()-interval '1 hour'").Limit(50).Find(&rows).Error; e != nil {
				return e
			}
			for _, row := range rows {
				var n int64
				if e := tx.Model(&fileRow{}).Where("storage_provider=? AND storage_key=?", row.StorageProvider, row.StorageKey).Count(&n).Error; e != nil {
					return e
				}
				if n == 0 {
					store, e := s.Blobs.For(row.StorageProvider)
					if e != nil {
						continue
					}
					deleteCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
					e = store.Delete(deleteCtx, row.StorageKey)
					cancel()
					if e != nil {
						continue
					}
				}
				if e := tx.Exec("DELETE FROM backend.blob_cleanup WHERE storage_provider=? AND storage_key=?", row.StorageProvider, row.StorageKey).Error; e != nil {
					return e
				}
			}
			return nil
		})
	}
}
