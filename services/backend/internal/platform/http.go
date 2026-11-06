package platform

import (
	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
)

func Error(c *gin.Context, status int, code, message string) {
	c.AbortWithStatusJSON(status, gin.H{"code": code, "message": message, "request_id": c.GetString("request_id")})
}
func RequestID() gin.HandlerFunc {
	return func(c *gin.Context) {
		id := uuid.NewString()
		c.Set("request_id", id)
		c.Header("X-Request-ID", id)
		c.Header("Cache-Control", "no-store")
		c.Next()
	}
}

// ConnectionKey makes the actual HTTP/1 connection available for bounded SSE writes.
type ConnectionKey struct{}
