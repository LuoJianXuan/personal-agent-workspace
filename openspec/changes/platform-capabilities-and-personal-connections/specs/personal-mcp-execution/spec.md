# Personal MCP Execution

## MODIFIED Requirements

### Requirement: Personal connections authorize a catalog in one operation

- **WHEN** a user confirms the current discovered catalog and permission mode
- **THEN** Backend SHALL record a versioned grant and expose compatible, granted, non-prohibited tools
- **AND** the user SHALL NOT be required to enable each tool separately
- **AND** readiness SHALL NOT claim unsupported tools are executable.

### Requirement: Invocation policy is independent from service hints

- **WHEN** a granted tool has a trusted read policy
- **THEN** it MAY execute without per-call approval within the connection's authorized data scope
- **WHEN** a granted tool writes data or its risk remains unknown
- **THEN** it SHALL require argument-bound per-call approval
- **AND** remote annotations or tool name prefixes SHALL NOT independently upgrade it to direct execution.

### Requirement: Explicitly unsafe or incompatible tools remain unavailable

- **WHEN** a tool violates platform restrictions, has unsupported schema, duplicates a name in one catalog or exceeds protocol bounds
- **THEN** execution SHALL be denied with a stable reason
- **AND** user consent SHALL NOT override target security or protocol validation.

## ADDED Requirements

### Requirement: Catalog changes require incremental consent

- **WHEN** tools are added or their effective description/schema/policy fingerprint changes
- **THEN** changed items SHALL remain pending until the user accepts the revised catalog
- **AND** unchanged granted tools SHALL remain available
- **AND** removed tools SHALL become non-executable immediately.

### Requirement: Approvals bind account and capability identity

- **WHEN** a user approves a tool proposal
- **THEN** approval SHALL bind run, execution, tool, canonical args/hash, snapshot, connection, credential version and grant revision
- **AND** cancellation, rejection, expiration, credential replacement or revoked permissions SHALL prevent stale proposals from executing.

### Requirement: Revocation prevents future dispatch

- **WHEN** a connection is disconnected or disabled
- **THEN** subsequent material resolution and dispatch SHALL fail
- **AND** in-flight requests SHALL be cancelled where possible
- **AND** the UI SHALL NOT promise to undo remote actions already submitted
- **AND** unknown remote outcomes SHALL NOT be retried automatically.

### Requirement: Runtime preserves the existing tool boundary

- **WHEN** any personal MCP tool executes
- **THEN** it SHALL pass through the existing Tool Gateway, parameter validation, lifecycle, rate limits and canonical events
- **AND** secrets SHALL be resolved after authorization and outside LangChain callback/state objects
- **AND** a worker SHALL receive only its required credential and minimal process environment.

### Requirement: Tool output cannot echo credentials into observations

- **WHEN** a provider returns a credential in catalog text, output or errors
- **THEN** the raw secret SHALL be removed or the result rejected before persistence, model input or callbacks
- **AND** Langfuse outages SHALL NOT block an otherwise valid tool call
- **AND** disabled observability SHALL be reported accurately in acceptance evidence.
