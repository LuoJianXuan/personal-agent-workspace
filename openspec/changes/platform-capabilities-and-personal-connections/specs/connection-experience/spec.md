# Connection and Skill Experience

## ADDED Requirements

### Requirement: Users see platform and personal readiness

- **WHEN** a user opens capability settings
- **THEN** platform-provided capabilities, personal connections and Skills SHALL have clear readiness states
- **AND** a missing personal account SHALL show a connection action
- **AND** service failures SHALL show recovery actions rather than only internal IDs or stack traces.

### Requirement: Connecting requires explicit scope confirmation

- **WHEN** a user submits a Token for validation
- **THEN** the UI SHALL explain its destination and local storage before submission
- **AND** validation SHALL only initialize and discover tools
- **WHEN** the catalog is available
- **THEN** the UI SHALL summarize personal-data access, actions requiring confirmation and unsupported items
- **AND** users SHALL confirm the catalog before it becomes usable by the Agent.

### Requirement: Connection changes do not submit chat messages

- **WHEN** a connection dialog is completed, cancelled or fails
- **THEN** the original chat draft SHALL be preserved
- **AND** connecting SHALL NOT itself send a model request or execute a business tool.

### Requirement: Skills resolve dependencies in user context

- **WHEN** an administrator publishes a Skill requiring platform tools and a personal provider
- **THEN** it SHALL reference stable capability/connector identifiers, not a user's credential or connection ID
- **AND** Backend SHALL resolve those dependencies for the current user.

#### Scenario: Required connection missing

- **WHEN** a selected Skill requires an unconnected personal provider
- **THEN** submission SHALL return a structured missing-dependency response with a connection action
- **AND** no provider/model execution SHALL be started for that rejected submission.

#### Scenario: Optional connection missing

- **WHEN** only an optional dependency is missing
- **THEN** the task MAY proceed with an explicit description of the omitted capability
- **AND** the assistant SHALL NOT claim that missing personal data was consulted.

### Requirement: MCP use does not require an optional branded Skill

- **WHEN** a user has an authorized personal MCP connection
- **THEN** normal conversation SHALL be able to invoke its available tools without installing a corresponding branded Skill.

### Requirement: User-facing verification covers the actual conversation

- **WHEN** the change is accepted for release
- **THEN** evidence SHALL include the browser connection flow and a real DeepSeek conversation using a real read-only McDonald's activity tool
- **AND** API-only checks, a time-only tool call, a Mock model or a trace URL without ingested observations SHALL NOT substitute for that evidence.
