# Capability Ownership

## ADDED Requirements

### Requirement: Platform and personal capabilities coexist

- **WHEN** an administrator publishes a platform model, search service, public MCP or Skill
- **THEN** authorized users SHALL use it without entering the platform credential
- **AND** platform configuration SHALL NOT imply shared ownership of user files, tool results or personal connections.

### Requirement: Personal connection ownership is authoritative

- **WHEN** a user creates a personal connection
- **THEN** Backend SHALL derive the owner from authenticated identity and persist scope and owner with database constraints
- **AND** credentials, discovery results and grants SHALL belong to that connection
- **AND** client-supplied owner/source/endpoint overrides SHALL be rejected.

#### Scenario: Cross-user access

- **GIVEN** users A and B each have a connection to the same provider
- **WHEN** A requests B's connection, operation or tools, or attempts execution with B's connection ID
- **THEN** public access SHALL return 404 and internal authorization SHALL deny execution
- **AND** no provider request SHALL be made using B's credential.

### Requirement: Public credential input is write-only

- **WHEN** a user provides or replaces a Token
- **THEN** it SHALL be encrypted by Backend with connection/owner-bound authenticated encryption
- **AND** public responses SHALL expose only configuration status and safe metadata
- **AND** the credential SHALL NOT appear in URLs, browser persistent storage, logs, snapshots, events, checkpoints, model context or traces.

### Requirement: Internal credential material is purpose-bound

- **WHEN** Runtime requests execution credentials
- **THEN** Backend SHALL authenticate the service and validate its own Run submission, snapshot, current ownership, connection/grant/credential versions and required approval
- **AND** bind issuance to execution ID, tool, target and canonical argument hash
- **AND** discovery-only authorization SHALL permit initialization/listing, not business tool calls.

### Requirement: Personal secrets survive controlled restarts

- **WHEN** Backend or Runtime is recreated with the same durable configuration
- **THEN** connected accounts SHALL remain usable without re-entering Tokens
- **AND** a missing/invalid master key SHALL fail personal credential access explicitly, without disabling otherwise configured platform capabilities.

## MODIFIED Requirements

### Requirement: Credential references support platform and user sources

- **WHEN** a platform connection executes
- **THEN** the existing deployment credential reference MAY be used
- **WHEN** a personal connection executes
- **THEN** only that user's connection credential SHALL be resolved transiently
- **AND** no missing personal credential SHALL fall back to a platform or another user's account.

### Requirement: Legacy personal accounts do not become shared accounts

- **WHEN** old deployment-scoped McDonald's records are migrated
- **THEN** they SHALL be excluded from ordinary-user discovery and new snapshots until explicitly connected to a known user through the new flow
- **AND** migration SHALL NOT guess the owner or copy the Token to all users
- **AND** disabling the new feature SHALL NOT re-expose the legacy shared personal account.
