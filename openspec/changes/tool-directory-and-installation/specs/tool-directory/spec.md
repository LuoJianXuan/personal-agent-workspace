# Tool Directory and Installation

## ADDED Requirements

### Requirement: Unified actual capability catalog

- WHEN a user opens Tools, the UI SHALL offer Skill and MCP tabs with search and personal filters.
- The catalog SHALL display only backend-published entries; prototype-only entries SHALL NOT be seeded.
- Platform MCPs SHALL indicate platform ownership and SHALL NOT request a personal Token.

### Requirement: Explicit installation and authorization

- WHEN a personal Token is submitted, the existing discovery operation SHALL run without model or business tool execution.
- The UI SHALL display the discovered permission scope and require explicit confirmation before reporting successful installation.
- Query-only and current-compatible-capabilities options SHALL remain available; write approvals SHALL remain enforced by the existing execution boundary.
- Failed, expired or conflicting operations SHALL NOT be reported as successful.

### Requirement: Reusable management and conversation entry

- The directory and chat drawer SHALL share the same installation and management implementation.
- Installing or cancelling from the chat drawer SHALL preserve the draft and SHALL NOT send it.
- Use actions SHALL fill a draft and choose the requested capability; only an explicit Send starts a run.
- Uninstall SHALL use existing credential removal and revocation; it SHALL NOT claim service-side revocation or cancellation of already-issued requests.

### Requirement: Presentation metadata does not change execution authority

- Administrators MAY edit names, descriptions, categories, supported icon identifiers and HTTPS Token help links.
- Omitted presentation data in an existing write request SHALL preserve the current presentation.
- Endpoints, credentials, risk policy, tool admission and authorization truth SHALL remain in their existing boundaries.
- Public directory DTOs SHALL NOT include personal Tokens, platform credential references or internal service endpoints.

### Requirement: Backward navigation compatibility

- Old skill and capability routes SHALL redirect to the corresponding tool tab.
- Models, network and sandbox availability SHALL remain discoverable under Settings, with capability diagnostics collapsed by default.
