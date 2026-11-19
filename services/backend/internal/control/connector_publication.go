package control

import (
	"agentworkspace/backend/internal/contracts"
	"encoding/json"
	"errors"
	"net/http"
	"net/url"
	"strings"

	"github.com/gin-gonic/gin"
	"gorm.io/gorm"
)

type publicationRow struct {
	Presentation json.RawMessage
	Name         string
	Enabled      bool
	Revision     int64
}

func publication(tx *gorm.DB, entry policyEntry) (policyEntry, error) {
	entry.Published = true
	if entry.Presentation.Icon == "" {
		entry.Presentation.Icon = "plug"
	}
	var row publicationRow
	err := tx.Table("backend.connector_publication").Where("connector_id=?", entry.PersonalConnector).Take(&row).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return entry, nil
	}
	if err != nil {
		return entry, err
	}
	entry.ConnectorName, entry.Published, entry.PublicationRevision = row.Name, row.Enabled, row.Revision
	if len(row.Presentation) > 2 {
		if err := json.Unmarshal(row.Presentation, &entry.Presentation); err != nil {
			return entry, err
		}
	}
	return entry, nil
}

func publishedDefinition(tx *gorm.DB, id string) (policyEntry, error) {
	entry, err := personalDefinition(id)
	if err != nil {
		return entry, err
	}
	entry, err = publication(tx, entry)
	if err == nil && !entry.Published {
		err = gorm.ErrRecordNotFound
	}
	return entry, err
}

func settings(entry policyEntry) contracts.ConnectorSettings {
	return contracts.ConnectorSettings{ConnectorId: entry.PersonalConnector, Name: entry.ConnectorName,
		Endpoint: entry.Endpoint, Enabled: entry.Published, Revision: entry.PublicationRevision, Presentation: &entry.Presentation}
}

func (s *Service) ConnectorSettings(c *gin.Context) {
	defs, err := personalDefinitions()
	if err != nil {
		fail(c, err)
		return
	}
	items := make([]contracts.ConnectorSettings, 0, len(defs))
	for _, def := range defs {
		def, err := publication(s.DB.WithContext(c.Request.Context()), def)
		if err != nil {
			fail(c, err)
			return
		}
		items = append(items, settings(def))
	}
	c.JSON(http.StatusOK, contracts.ConnectorSettingsList{Items: items})
}

func (s *Service) UpdateConnectorSettings(c *gin.Context) {
	input, ok := body(c, "ConnectorSettingsWrite")
	if !ok {
		return
	}
	def, err := personalDefinition(c.Param("connector"))
	if err != nil {
		fail(c, err)
		return
	}
	name := strings.TrimSpace(str(input, "name"))
	if name == "" {
		fail(c, invalid("请输入连接器名称"))
		return
	}
	err = s.DB.WithContext(c.Request.Context()).Transaction(func(tx *gorm.DB) error {
		if err := lock(tx); err != nil {
			return err
		}
		current, err := publication(tx, def)
		if err != nil {
			return err
		}
		if current.PublicationRevision != num(input, "revision") {
			return conflict()
		}
		def.PublicationRevision = current.PublicationRevision + 1
		def.Presentation = current.Presentation
		if raw, ok := input["presentation"]; ok {
			if err := json.Unmarshal(encode(raw), &def.Presentation); err != nil {
				return err
			}
			if link := def.Presentation.TokenHelpUrl; link != "" {
				u, err := url.Parse(link)
				if err != nil || u.Scheme != "https" || u.Hostname() == "" || u.User != nil {
					return invalid("Token 获取链接必须是有效的 HTTPS 地址，且不能包含凭据")
				}
			}
		}
		def.ConnectorName, def.Published = name, flag(input, "enabled")
		if err := tx.Exec(`INSERT INTO backend.connector_publication(connector_id,name,enabled,revision,presentation)
			VALUES(?,?,?,?,?::jsonb) ON CONFLICT(connector_id) DO UPDATE SET name=EXCLUDED.name,enabled=EXCLUDED.enabled,revision=EXCLUDED.revision,presentation=EXCLUDED.presentation`,
			def.PersonalConnector, name, def.Published, def.PublicationRevision, string(encode(def.Presentation))).Error; err != nil {
			return err
		}
		if !def.Published {
			if err := tx.Exec("DELETE FROM "+probeTable+" WHERE connection_id IN (SELECT id FROM "+personalTable+" WHERE connector_id=?)", def.PersonalConnector).Error; err != nil {
				return err
			}
		}
		return audit(tx, c, "connector.publication", def.PersonalConnector, object{"enabled": def.Published, "revision": def.PublicationRevision})
	})
	if err != nil {
		fail(c, err)
		return
	}
	c.JSON(http.StatusOK, settings(def))
}
