package control

import (
	"agentworkspace/backend/internal/contracts"
	"agentworkspace/backend/internal/platform"
	"context"
	"errors"
	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
	"golang.org/x/crypto/bcrypt"
	"gorm.io/gorm"
	"strings"
	"time"
)

type User struct {
	ID           string `gorm:"column:id;primaryKey"`
	Username     string
	PasswordHash string
	Role         string
	Enabled      bool
	Revision     int64 `gorm:"default:1"`
}

func (User) TableName() string { return "backend.users" }
func (u User) Public() contracts.User {
	return contracts.User{Id: u.ID, Username: u.Username, Role: u.Role, Enabled: u.Enabled, Revision: u.Revision}
}

type Service struct {
	DB     *gorm.DB
	Config platform.Config
}
type Claims struct{ jwt.RegisteredClaims }

func (s *Service) Login(c *gin.Context) {
	input, err := contracts.DecodeLogin(c.Request.Body)
	if err != nil {
		platform.Error(c, 400, "INVALID_ARGUMENT", "用户名或密码格式无效")
		return
	}
	var u User
	err = s.DB.WithContext(c.Request.Context()).Where("username = ?", input.Username).Take(&u).Error
	if err != nil && !errors.Is(err, gorm.ErrRecordNotFound) {
		platform.Error(c, 503, "DEPENDENCY_UNAVAILABLE", "数据库暂不可用")
		return
	}
	hash := u.PasswordHash
	if err != nil {
		hash = "$2a$10$7EqJtq98hPqEX7fNZaFWoO5uEykEHeYVQfS8GfVksVv8pS9M6oV6u"
	}
	valid := bcrypt.CompareHashAndPassword([]byte(hash), []byte(input.Password)) == nil
	if err != nil || !valid || !u.Enabled {
		platform.Error(c, 401, "UNAUTHENTICATED", "账号或密码错误，或账号已禁用")
		return
	}
	now := time.Now().UTC()
	expiry := now.Add(time.Duration(s.Config.TokenHours) * time.Hour)
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, Claims{jwt.RegisteredClaims{Subject: u.ID, Issuer: "agent-workspace", Audience: jwt.ClaimStrings{"workspace-web"}, IssuedAt: jwt.NewNumericDate(now), ExpiresAt: jwt.NewNumericDate(expiry), ID: uuid.NewString()}})
	signed, err := token.SignedString([]byte(s.Config.JWTSecret))
	if err != nil {
		platform.Error(c, 500, "INTERNAL_ERROR", "无法签发令牌")
		return
	}
	c.JSON(200, contracts.Token{AccessToken: signed, TokenType: "Bearer", ExpiresAt: expiry.Format(time.RFC3339), User: u.Public()})
}
func (s *Service) Authenticate() gin.HandlerFunc {
	return func(c *gin.Context) {
		h := c.GetHeader("Authorization")
		if !strings.HasPrefix(h, "Bearer ") {
			platform.Error(c, 401, "UNAUTHENTICATED", "请先登录")
			return
		}
		claims := &Claims{}
		token, err := jwt.ParseWithClaims(strings.TrimPrefix(h, "Bearer "), claims, func(t *jwt.Token) (any, error) { return []byte(s.Config.JWTSecret), nil }, jwt.WithValidMethods([]string{"HS256"}), jwt.WithIssuer("agent-workspace"), jwt.WithAudience("workspace-web"), jwt.WithExpirationRequired())
		if err != nil || !token.Valid {
			platform.Error(c, 401, "UNAUTHENTICATED", "登录已失效")
			return
		}
		var u User
		err = s.DB.WithContext(c.Request.Context()).Where("id = ?", claims.Subject).Take(&u).Error
		if err != nil && !errors.Is(err, gorm.ErrRecordNotFound) {
			platform.Error(c, 503, "DEPENDENCY_UNAVAILABLE", "数据库暂不可用")
			return
		}
		if err != nil || !u.Enabled {
			platform.Error(c, 401, "UNAUTHENTICATED", "登录已失效")
			return
		}
		c.Set("user", u)
		c.Set("identity", contracts.Context{TenantId: s.Config.Tenant, ProjectId: s.Config.Project, UserId: u.ID, RequestId: c.GetString("request_id")})
		c.Next()
	}
}
func Admin() gin.HandlerFunc {
	return func(c *gin.Context) {
		if c.MustGet("user").(User).Role != "admin" {
			platform.Error(c, 403, "FORBIDDEN", "需要管理员权限")
			return
		}
		c.Next()
	}
}
func (s *Service) Me(c *gin.Context) { c.JSON(200, c.MustGet("user").(User).Public()) }
func (s *Service) Users(c *gin.Context) {
	var users []User
	if err := s.DB.WithContext(c.Request.Context()).Order("username").Limit(100).Find(&users).Error; err != nil {
		platform.Error(c, 503, "DEPENDENCY_UNAVAILABLE", "无法读取用户")
		return
	}
	result := make([]contracts.User, 0, len(users))
	for _, u := range users {
		result = append(result, u.Public())
	}
	c.JSON(200, gin.H{"items": result})
}

// Capabilities is consumed by agententry; control owns the authoritative configuration.
type Capabilities interface {
	Snapshot(ctx context.Context, identity contracts.Context, request contracts.Submit) (contracts.Snapshot, error)
}
