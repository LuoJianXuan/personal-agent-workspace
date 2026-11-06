# 001 — Ownership and contract discipline
Backend owns identity, configuration, thread, submission intent, approval decisions and files. Runtime owns Run lifecycle, proposal/checkpoint, tool execution and canonical events. A submission tracks PENDING_DISPATCH → ACCEPTED or DISPATCH_FAILED; ACCEPTED does not mean a Run succeeded. Run facts are fetched from Runtime, never duplicated as control-plane truth.

Only Backend writes approval decisions after checking current proposal, owner, expiry and revisions. Runtime validates the stored decision before resuming the same graph_thread_id = run_id. Approved does not mean executed. Backend owns disk bytes and metadata; Runtime accesses scoped APIs, never the file volume.

Capabilities flow: authenticated identity → control authorization/configuration → immutable non-secret snapshot → agententry dispatch → Runtime. The request body cannot override public identity. Every tool/model invocation revalidates revisions; unavailable validation fails closed.

`schemas/jsonschema/contracts.json` is authoritative. `scripts/generate-contracts.py` emits Go structs, Python TypedDicts and TypeScript interfaces plus schema copies. These DTOs do not themselves validate: shared schema validators enforce closed objects, UUID/date-time formats and required fields. Unknown fields fail; arbitrary keys are permitted only within a tool's input_schema (which is itself JSON Schema). Future endpoints must validate before using their DTO. Public login already uses this boundary.

Three idempotency layers: user+Idempotency-Key binds normalized submission request; Runtime run_id binds request_hash; business execution_id binds canonical_args/args_hash and original result. A thread has one active submission via transactional lock + partial unique index. One Run has one pending approval; multiple tool calls execute in order. Constraints arrive with S03/S04 tables, not premature D1 business tables.

See ../plan-v2/CONTRACTS.md for failure windows, event cursor, capacity and error semantics. No implementation of those later-day flows is claimed by D1 contracts.
