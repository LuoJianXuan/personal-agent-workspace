package main

import (
	"agentworkspace/backend/internal/agententry"
	"agentworkspace/backend/internal/control"
	"agentworkspace/backend/internal/platform"
	"context"
	"crypto/subtle"
	"fmt"
	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"golang.org/x/crypto/bcrypt"
	"gorm.io/gorm"
	"gorm.io/gorm/clause"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"
)

func main() {
	cfg := platform.Load()
	db, err := platform.Open(cfg.DSN)
	if err != nil {
		log.Fatal("database connection failed")
	}
	sqlDB, err := db.DB()
	if err != nil {
		log.Fatal("database pool failed")
	}
	defer sqlDB.Close()
	sqlDB.SetMaxOpenConns(10)
	sqlDB.SetMaxIdleConns(5)
	if len(os.Args) > 1 {
		switch os.Args[1] {
		case "migrate":
			err = platform.Migrate(db)
		case "seed":
			err = seed(db)
		default:
			log.Fatal("usage: server [migrate|seed]")
		}
		if err != nil {
			log.Fatal("migration/seed failed; verify database and environment configuration")
		}
		return
	}
	gin.SetMode(gin.ReleaseMode)
	r := gin.New()
	r.Use(gin.Recovery(), platform.RequestID())
	s := control.Service{DB: db, Config: cfg}
	r.GET("/health", func(c *gin.Context) { c.JSON(200, gin.H{"status": "alive"}) })
	r.GET("/ready", func(c *gin.Context) {
		ctx, cancel := context.WithTimeout(c.Request.Context(), 3*time.Second)
		defer cancel()
		if platform.Ready(ctx, db) != nil {
			platform.Error(c, 503, "NOT_READY", "数据库或迁移未就绪")
			return
		}
		c.JSON(200, gin.H{"status": "ready"})
	})
	r.POST("/api/auth/login", s.Login)
	api := r.Group("/api", s.Authenticate())
	api.GET("/auth/me", s.Me)
	admin := api.Group("/admin", control.Admin())
	admin.GET("/users", s.Users)
	admin.POST("/users", s.CreateUser)
	admin.PATCH("/users/:id", s.UpdateUser)
	admin.GET("/deployment", s.Deployment)
	admin.GET("/audits", s.Audits)
	for _, resource := range []struct{ path, kind, schema string }{{"models", "models", "ModelWrite"}, {"skills", "skills", "SkillWrite"}, {"mcp-connections", "mcp_connections", "McpWrite"}} {
		admin.GET("/"+resource.path, s.ListResources(resource.kind))
		admin.POST("/"+resource.path, s.SaveResource(resource.kind, resource.schema))
		admin.PATCH("/"+resource.path+"/:id", s.SaveResource(resource.kind, resource.schema))
	}
	admin.POST("/models/:id/validate", s.ValidateModel)
	admin.POST("/mcp-connections/:id/discover", s.Discover)
	admin.GET("/mcp-connections/:id/tools", s.Tools)
	admin.PATCH("/mcp-connections/:id/tools/:tool_id", s.SetTool)
	api.GET("/catalog/models", s.CatalogModels)
	api.GET("/catalog/skills", s.CatalogSkills)
	api.GET("/catalog/tools", s.CatalogTools)
	api.PUT("/me/skills/:id/enablement", s.Preference)
	api.POST("/capabilities/resolve", s.Resolve)

	runs := agententry.New(db, &s)
	go runs.CleanupFiles()
	workerContext, stopWorker := context.WithCancel(context.Background())
	defer stopWorker()
	go runs.Worker(workerContext)
	api.GET("/files", runs.Files)
	api.POST("/files", runs.Upload)
	api.GET("/files/:id", runs.File)
	api.GET("/files/:id/content", runs.FileContent)
	api.GET("/files/:id/download", runs.Download)
	api.GET("/files/:id/parsed", runs.ParsedFile)
	api.POST("/files/:id/extract", runs.ExtractFile)
	api.GET("/files/:id/versions", runs.FileVersions)
	api.GET("/runs/:id/sources", runs.Sources)
	api.GET("/capabilities/network", runs.NetworkStatus)
	api.GET("/runs/:id/artifacts", runs.Artifacts)
	api.POST("/runs/:id/artifacts", runs.Artifacts)
	api.GET("/scenes", func(c *gin.Context) {
		c.JSON(200, gin.H{"items": []gin.H{{"id": "data-analysis", "name": "CSV 数据分析"}}})
	})
	api.GET("/threads", runs.Threads)
	api.POST("/threads", runs.Threads)
	api.PATCH("/threads/:id", runs.Threads)
	api.GET("/threads/:id/messages", runs.Messages)
	api.POST("/threads/:id/runs", runs.Submit)
	api.GET("/runs/:id", runs.Run)
	api.GET("/runs/:id/events", runs.Events)
	api.GET("/runs/:id/stream", runs.Stream)
	api.GET("/runs/:id/approvals", runs.Approvals)
	api.POST("/approvals/:id/decision", runs.Decision)
	api.POST("/runs/:id/resume", runs.Resume)
	api.POST("/runs/:id/cancel", runs.Cancel)
	admin.GET("/runs", runs.AdminRuns)
	admin.GET("/runs/:id", runs.AdminRuns)
	internal := r.Group("/internal", func(c *gin.Context) {
		expected := "Bearer " + cfg.RToB
		if subtle.ConstantTimeCompare([]byte(c.GetHeader("Authorization")), []byte(expected)) != 1 {
			platform.Error(c, 401, "UNAUTHENTICATED", "invalid service credential")
			return
		}
		c.Next()
	})
	internal.POST("/capabilities/validate", s.ValidateCapabilities)
	internal.GET("/submissions/:id", runs.InternalSubmission)
	internal.GET("/approval-decisions/:id", runs.InternalDecision)
	internal.POST("/demo-tickets", runs.Ticket)
	internal.GET("/demo-tickets/by-execution/:id", runs.TicketByExecution)
	internal.GET("/files/:id/content", runs.InternalFile)
	internal.GET("/files/:id/blob", runs.InternalBlob)
	internal.GET("/files/:id/parsed", runs.InternalFile)
	internal.PUT("/files/:id/parsed", runs.InternalParsed)
	internal.GET("/work-files", runs.WorkFiles)
	internal.PUT("/work-files", runs.WorkFiles)
	internal.POST("/artifacts", runs.InternalArtifact)
	internal.POST("/artifacts/blob", runs.InternalBinaryArtifact)
	internal.GET("/health", func(c *gin.Context) { c.JSON(200, gin.H{"status": "alive"}) })
	r.NoRoute(func(c *gin.Context) { platform.Error(c, 404, "NOT_FOUND", "接口不存在或尚未开放") })
	server := &http.Server{ConnContext: func(ctx context.Context, conn net.Conn) context.Context {
		return context.WithValue(ctx, platform.ConnectionKey{}, conn)
	}, Addr: ":8080", Handler: r, ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 15 * time.Second, IdleTimeout: 60 * time.Second, MaxHeaderBytes: 1 << 20}
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	go func() {
		<-quit
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		_ = server.Shutdown(ctx)
	}()
	log.Print("backend listening on :8080")
	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatal("HTTP server failed")
	}
}
func seed(db *gorm.DB) error {
	type account struct{ name, password, role string }
	accounts := []account{}
	for _, a := range []struct{ prefix, role string }{{"ADMIN", "admin"}, {"USER_A", "user"}, {"USER_B", "user"}} {
		name := platform.Required("SEED_" + a.prefix + "_USERNAME")
		pw := platform.Required("SEED_" + a.prefix + "_PASSWORD")
		if len(pw) < 12 || len(pw) > 72 {
			return fmt.Errorf("seed passwords must be 12..72 bytes")
		}
		accounts = append(accounts, account{name, pw, a.role})
	}
	if accounts[0].name == accounts[1].name || accounts[0].name == accounts[2].name || accounts[1].name == accounts[2].name {
		return fmt.Errorf("seed usernames must be distinct")
	}
	return db.Transaction(func(tx *gorm.DB) error {
		for _, a := range accounts {
			hash, err := bcrypt.GenerateFromPassword([]byte(a.password), 12)
			if err != nil {
				return err
			}
			u := control.User{ID: uuid.NewString(), Username: a.name, PasswordHash: string(hash), Role: a.role, Enabled: true}
			if err := tx.Clauses(clause.OnConflict{Columns: []clause.Column{{Name: "username"}}, DoNothing: true}).Create(&u).Error; err != nil {
				return err
			}
		}
		return nil
	})
}
