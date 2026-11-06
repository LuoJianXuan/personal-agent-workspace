package workspace

import (
	"agentworkspace/backend/internal/contracts"
	"context"
	"gorm.io/gorm"
)

type Thread struct {
	ID        string `gorm:"column:id;primaryKey"`
	OwnerID   string
	TenantID  string
	ProjectID string
	Title     string
}

func (Thread) TableName() string { return "backend.threads" }

type Service struct{ DB *gorm.DB }

// OwnedThread intentionally returns the same not-found result for missing and foreign IDs.
func (s *Service) OwnedThread(ctx context.Context, identity contracts.Context, id string) (Thread, error) {
	var t Thread
	err := s.DB.WithContext(ctx).Where("id = ? AND owner_id = ? AND tenant_id = ? AND project_id = ?", id, identity.UserId, identity.TenantId, identity.ProjectId).Take(&t).Error
	return t, err
}

// Application is the business boundary for the S03 entry orchestrator.
type Application interface {
	OwnedThread(context.Context, contracts.Context, string) (Thread, error)
}
