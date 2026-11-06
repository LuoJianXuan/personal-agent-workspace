package platform

import (
	"fmt"
	"os"
	"strconv"
)

type Config struct {
	DSN, JWTSecret, BToR, RToB, RuntimeURL, Tenant, Project string
	TokenHours                                              int
}

func Required(key string) string {
	v := os.Getenv(key)
	if v == "" {
		panic(fmt.Sprintf("missing required configuration: %s", key))
	}
	return v
}
func Load() Config {
	c := Config{DSN: Required("BACKEND_DATABASE_URL"), JWTSecret: Required("JWT_SECRET"), BToR: Required("BACKEND_TO_RUNTIME_TOKEN"), RToB: Required("RUNTIME_TO_BACKEND_TOKEN"), RuntimeURL: Required("RUNTIME_URL"), Tenant: Required("TENANT_ID"), Project: Required("PROJECT_ID"), TokenHours: 8}
	if len(c.JWTSecret) < 32 || len(c.BToR) < 32 || len(c.RToB) < 32 {
		panic("JWT and service secrets must be at least 32 bytes")
	}
	if c.BToR == c.RToB || c.JWTSecret == c.BToR || c.JWTSecret == c.RToB {
		panic("authentication secrets must be distinct")
	}
	if v := os.Getenv("TOKEN_TTL_HOURS"); v != "" {
		n, e := strconv.Atoi(v)
		if e != nil || n < 1 || n > 24 {
			panic("TOKEN_TTL_HOURS must be 1..24")
		}
		c.TokenHours = n
	}
	return c
}
