package control

import (
	"agentworkspace/backend/internal/contracts"
	"github.com/gin-gonic/gin"
)

// CatalogMcpServices exposes only platform service labels and admitted tools.
// Personal credentials and internal connection configuration stay out of this projection.
func (s *Service) CatalogMcpServices(c *gin.Context) {
	tx := s.DB.WithContext(c.Request.Context())
	connections, err := list(tx, "mcp_connections")
	if err != nil {
		fail(c, err)
		return
	}
	tools, _, err := enabledTools(tx)
	if err != nil {
		fail(c, err)
		return
	}
	items := []contracts.PlatformMcpService{}
	for _, connection := range connections {
		if !flag(connection, "enabled") {
			continue
		}
		// Personal connector definitions are represented by /catalog/connectors only.
		if !allowed("mcp", str(connection, "endpoint"), str(connection, "credential_ref")) {
			continue
		}
		item := contracts.PlatformMcpService{Id: str(connection, "id"), Name: str(connection, "name"),
			Availability: "unavailable", Reason: "管理员尚未完成工具发现与授权", Tools: []contracts.PlatformMcpTool{}}
		for _, tool := range tools {
			if str(tool, "connection_id") == item.Id {
				item.Tools = append(item.Tools, contracts.PlatformMcpTool{Name: str(tool, "remote_name"),
					Description: str(tool, "description"), RequiresApproval: flag(tool, "requires_approval")})
			}
		}
		if len(item.Tools) > 0 {
			item.Availability, item.Reason = "configured", ""
		}
		if str(connection, "probe_status") == "failed" {
			item.Reason = "最近一次工具发现失败，请联系管理员重新发现"
		}
		items = append(items, item)
	}
	c.JSON(200, contracts.PlatformMcpServiceList{Items: items})
}
