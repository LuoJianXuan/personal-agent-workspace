# Governed MCP

## Requirements

### MCP discovery is default-deny

- **WHEN** Runtime discovers tools from an allowlisted endpoint
- **THEN** Backend SHALL classify each tool from deployment policy and persist the server read-only hint separately
- **AND** an unlisted tool SHALL remain blocked and disabled

### MCP writes require argument-bound approval

- **WHEN** an enabled MCP write tool is selected by the Agent
- **THEN** the run SHALL pause before remote execution
- **AND** approval SHALL bind run, execution, tool, canonical arguments, hash, capability revision and snapshot
- **AND** rejection, expiry, cancellation or capability revocation SHALL prevent execution

### Remote execution is bounded

- **WHEN** Tool Gateway dispatches an MCP call
- **THEN** it SHALL re-check exact target, tool classification and approval requirement
- **AND** enforce timeout, cancellation, result-size, run-call and per-connection rate limits
- **AND** uncertain remote outcomes SHALL not be retried automatically

### Secrets remain deployment-only

- **WHEN** a credentialed MCP is configured or executed
- **THEN** APIs, snapshots, events, traces and evidence SHALL contain only credential references, never the credential value

### UI presents one tool operation once

- **WHEN** requested, started and terminal events share an execution ID
- **THEN** the conversation SHALL render one operation card with the latest status and terminal result
