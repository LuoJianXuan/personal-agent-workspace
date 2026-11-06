package platform

import (
	"context"
	_ "embed"
	"fmt"
	"gorm.io/driver/postgres"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"
)

//go:embed migrations/001_foundation.sql
var migration string

//go:embed migrations/002_control.sql
var controlMigration string

//go:embed migrations/003_runs.sql
var runsMigration string

//go:embed migrations/004_delivery.sql
var deliveryMigration string

//go:embed migrations/005_phase1.sql
var phase1Migration string

//go:embed migrations/006_personal_agent.sql
var personalAgentMigration string

func Open(dsn string) (*gorm.DB, error) {
	return gorm.Open(postgres.Open(dsn), &gorm.Config{Logger: logger.Default.LogMode(logger.Silent)})
}
func Migrate(db *gorm.DB) error {
	return db.Transaction(func(tx *gorm.DB) error {
		if err := tx.Exec("SELECT pg_advisory_xact_lock(210001)").Error; err != nil {
			return err
		}
		var exists bool
		if err := tx.Raw("SELECT to_regclass('backend.schema_migrations') IS NOT NULL").Scan(&exists).Error; err != nil {
			return err
		}
		if !exists {
			if err := tx.Exec(migration).Error; err != nil {
				return err
			}
		}
		var count int64
		if err := tx.Raw("SELECT count(*) FROM backend.schema_migrations WHERE version=2").Scan(&count).Error; err != nil {
			return err
		}
		if count == 0 {
			if err := tx.Exec(controlMigration).Error; err != nil {
				return err
			}
		}
		if err := tx.Raw("SELECT count(*) FROM backend.schema_migrations WHERE version=3").Scan(&count).Error; err != nil {
			return err
		}
		if count == 0 {
			if err := tx.Exec(runsMigration).Error; err != nil {
				return err
			}
		}
		if err := tx.Raw("SELECT count(*) FROM backend.schema_migrations WHERE version=4").Scan(&count).Error; err != nil {
			return err
		}
		if count == 0 {
			if err := tx.Exec(deliveryMigration).Error; err != nil {
				return err
			}
		}
		if err := tx.Raw("SELECT count(*) FROM backend.schema_migrations WHERE version=5").Scan(&count).Error; err != nil {
			return err
		}
		if count == 0 {
			if err := tx.Exec(phase1Migration).Error; err != nil {
				return err
			}
		}
		if err := tx.Raw("SELECT count(*) FROM backend.schema_migrations WHERE version=6").Scan(&count).Error; err != nil {
			return err
		}
		if count == 0 {
			return tx.Exec(personalAgentMigration).Error
		}
		return nil
	})
}
func Ready(ctx context.Context, db *gorm.DB) error {
	var n int
	err := db.WithContext(ctx).Raw("SELECT count(*) FROM backend.schema_migrations WHERE version IN (1,2,3,4,5,6)").Scan(&n).Error
	if err != nil || n != 6 {
		return fmt.Errorf("database or migration unavailable")
	}
	return nil
}
