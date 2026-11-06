# Generated. Validate with shared JSON Schema before using DTOs.
from __future__ import annotations
from typing import Any, Literal, TypedDict, NotRequired
class Context(TypedDict):
    tenant_id: str
    project_id: str
    user_id: str
    request_id: str

class Login(TypedDict):
    username: str
    password: str

class User(TypedDict):
    id: str
    username: str
    role: Literal["admin", "user"]
    enabled: bool
    revision: int

class Token(TypedDict):
    access_token: str
    token_type: Literal["Bearer"]
    expires_at: str
    user: User

class Error(TypedDict):
    code: str
    message: str
    request_id: str
    details: NotRequired[str]

class Model(TypedDict):
    id: str
    name: str
    provider: str
    protocol: Literal["openai_chat_completions"]
    protocol_options: ProtocolOptions
    provider_model_name: str
    base_url: str
    credential_ref: str
    context_limit: int
    max_output_tokens: int
    capabilities: ModelCapabilities
    revision: int

class Skill(TypedDict):
    id: str
    name: str
    content: str
    revision: int

class Tool(TypedDict):
    namespaced_tool_id: str
    connection_id: str
    input_schema: dict[str, Any]
    schema_hash: str
    revision: int
    remote_name: str
    description: str

class Mcp(TypedDict):
    id: str
    endpoint: str
    credential_ref: str
    revision: int

class FileRef(TypedDict):
    id: str
    sha256: str

class Snapshot(TypedDict):
    snapshot_id: str
    created_at: str
    context: Context
    model: Model
    skills: list[Skill]
    tools: list[Tool]
    mcp_connections: list[Mcp]
    file_refs: list[FileRef]
    builtin_tools: NotRequired[list[BuiltinTool]]
    network_enabled: NotRequired[bool]

class HistoryMessage(TypedDict):
    role: Literal["user", "assistant"]
    content: str
    run_id: str

class Start(TypedDict):
    run_id: str
    thread_id: str
    context: Context
    input: str
    history: list[HistoryMessage]
    effective_capabilities: Snapshot
    file_refs: list[FileRef]
    mode: Literal["real", "mock"]
    request_hash: str
    scenario: NotRequired[Scenario]

class Scenario(TypedDict):
    dimension: str
    measure: str
    aggregation: Literal["sum", "count", "avg"]
    chart_type: Literal["bar", "line"]
    unit: NotRequired[str]

class Submit(TypedDict):
    input: str
    model_id: NotRequired[str]
    skill_ids: NotRequired[list[str]]
    file_ids: NotRequired[list[str]]
    scenario: NotRequired[Scenario]
    network_enabled: NotRequired[bool]

class Submission(TypedDict):
    run_id: str
    thread_id: str
    status: str
    mode: Literal["real", "mock"]
    runtime_unavailable: bool
    error_code: str
    final_text: str
    cancel_requested: NotRequired[bool]
    trace_url: NotRequired[str]

class Run(TypedDict):
    run_id: str
    thread_id: str
    status: Literal["QUEUED", "RUNNING", "WAITING_APPROVAL", "SUCCEEDED", "FAILED", "CANCELLED", "INTERRUPTED"]
    mode: Literal["real", "mock"]

class MessageStarted(TypedDict):
    message_id: str

class MessageDelta(TypedDict):
    message_id: str
    chunk_index: int
    text: str

class MessageCompleted(TypedDict):
    message_id: str
    text: str
    is_final: bool

class Progress(TypedDict):
    status: str
    object_id: NotRequired[str]
    code: NotRequired[str]

class Event(TypedDict):
    event_id: str
    run_id: str
    thread_id: str
    seq: int
    type: Literal["run.started", "tool.requested", "tool.started", "tool.completed", "tool.failed", "approval.required", "approval.resolved", "message.started", "message.delta", "message.completed", "run.completed", "run.failed", "run.cancelled", "run.interrupted", "artifact.ready", "source.ready", "task.updated", "context.compacted"]
    created_at: str
    payload: Any

class EventPage(TypedDict):
    items: list[Event]
    next_seq: int
    has_more: bool

class Approval(TypedDict):
    approval_id: str
    run_id: str
    execution_id: str
    tool_call_id: str
    namespaced_tool_id: str
    canonical_args: str
    args_hash: str
    capability_revision: int
    expires_at: str
    status: Literal["PENDING", "APPROVED", "REJECTED", "EXPIRED", "CANCELLED"]
    snapshot_id: str
    owner_id: str

class Decision(TypedDict):
    decision: Literal["approve", "reject"]

class Resume(TypedDict):
    decision_id: str

class Cancel(TypedDict):
    command_id: str

class ToolResult(TypedDict):
    execution_id: str
    tool_call_id: str
    status: Literal["REQUESTED", "WAITING_APPROVAL", "RUNNING", "SUCCEEDED", "FAILED", "DENIED", "CANCELLED", "UNKNOWN"]
    text: str
    file_refs: list[FileRef]

class File(TypedDict):
    id: str
    owner_id: str
    run_id: NotRequired[str]
    name: str
    media_type: Literal["text/plain", "text/markdown", "text/csv", "application/json", "application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"]
    size: int
    sha256: str
    source: Literal["upload", "generated"]
    status: Literal["PENDING", "READY", "FAILED"]
    created_at: str
    parse_status: NotRequired[Literal["not_extracted", "queued", "processing", "ready", "failed", "unsupported"]]
    parse_error: NotRequired[str]
    parent_file_id: NotRequired[str]
    version: NotRequired[int]

class ChartPoint(TypedDict):
    label: str
    value: float

class Chart(TypedDict):
    type: Literal["bar", "line"]
    file_id: str
    dimension: str
    measure: str
    aggregation: Literal["sum", "count", "avg"]
    row_count: int
    unit: NotRequired[str]
    points: list[ChartPoint]

class ThinkingOptions(TypedDict):
    type: Literal["disabled"]

class ProtocolOptions(TypedDict):
    thinking: NotRequired[ThinkingOptions]

class ModelCapabilities(TypedDict):
    streaming: bool
    tool_calling: bool

class ModelWrite(TypedDict):
    name: str
    provider: str
    protocol: Literal["openai_chat_completions"]
    protocol_options: ProtocolOptions
    provider_model_name: str
    base_url: str
    credential_ref: str
    context_limit: int
    max_output_tokens: int
    capabilities: ModelCapabilities
    enabled: bool
    is_default: bool
    revision: int

class ModelConfig(TypedDict):
    id: str
    name: str
    provider: str
    protocol: Literal["openai_chat_completions"]
    protocol_options: ProtocolOptions
    provider_model_name: str
    base_url: str
    credential_ref: str
    context_limit: int
    max_output_tokens: int
    capabilities: ModelCapabilities
    revision: int
    enabled: bool
    is_default: bool
    credential_configured: bool
    availability: str
    chat_status: Literal["unverified"]
    stream_status: Literal["unverified"]
    tool_loop_status: Literal["unverified"]

class ModelCatalog(TypedDict):
    id: str
    name: str
    provider: str
    capabilities: ModelCapabilities
    is_default: bool
    available: bool
    availability: str
    revision: int

class SkillWrite(TypedDict):
    name: str
    description: str
    category: str
    content: str
    enabled: bool
    revision: int

class SkillConfig(TypedDict):
    id: str
    name: str
    description: str
    category: str
    content: str
    enabled: bool
    revision: int
    personal_enabled: bool

class McpWrite(TypedDict):
    name: str
    endpoint: str
    credential_ref: str
    enabled: bool
    revision: int

class McpConfig(TypedDict):
    id: str
    name: str
    endpoint: str
    credential_ref: str
    enabled: bool
    revision: int
    probe_status: Literal["unverified", "success", "failed"]
    last_probe_at: str
    probe_error: str

class EnablementWrite(TypedDict):
    enabled: bool
    revision: int

class PreferenceWrite(TypedDict):
    enabled: bool

class UserCreate(TypedDict):
    username: str
    password: str

class McpToolConfig(TypedDict):
    namespaced_tool_id: str
    connection_id: str
    input_schema: dict[str, Any]
    schema_hash: str
    revision: int
    remote_name: str
    description: str
    enabled: bool
    available: bool
    trusted_read_only: bool

class DiscoverRequest(TypedDict):
    endpoint: str
    credential_ref: str

class DiscoveredTool(TypedDict):
    remote_name: str
    description: str
    input_schema: dict[str, Any]
    trusted_read_only: bool

class DiscoverResult(TypedDict):
    tools: list[DiscoveredTool]

class ResolveRequest(TypedDict):
    model_id: NotRequired[str]
    skill_ids: NotRequired[list[str]]
    require_tools: bool
    require_streaming: bool
    network_enabled: NotRequired[bool]

class CapabilityValidation(TypedDict):
    snapshot_id: str
    context: Context
    run_id: NotRequired[str]

class CapabilityDecision(TypedDict):
    allow: bool
    reason: str

class CapabilityPreview(TypedDict):
    snapshot_id: str
    model_id: str
    skill_ids: list[str]
    tool_ids: list[str]

class Audit(TypedDict):
    id: str
    actor_id: str
    action: str
    object_id: str
    request_id: str
    created_at: str
    safe_changes: dict[str, Any]

class PolicyTarget(TypedDict):
    endpoint: str
    credential_ref: str
    credential_configured: bool

class DeploymentCatalog(TypedDict):
    models: list[PolicyTarget]
    mcp: list[PolicyTarget]

class ModelConfigList(TypedDict):
    items: list[ModelConfig]

class ModelCatalogList(TypedDict):
    items: list[ModelCatalog]

class SkillConfigList(TypedDict):
    items: list[SkillConfig]

class McpConfigList(TypedDict):
    items: list[McpConfig]

class McpToolConfigList(TypedDict):
    items: list[McpToolConfig]

class UserList(TypedDict):
    items: list[User]

class AuditList(TypedDict):
    items: list[Audit]

class RevisionWrite(TypedDict):
    revision: int

class ThreadWrite(TypedDict):
    title: str

class Thread(TypedDict):
    id: str
    title: str
    created_at: str

class Message(TypedDict):
    id: str
    run_id: str
    role: Literal["user", "assistant"]
    text: str
    created_at: str

class ThreadList(TypedDict):
    items: list[Thread]

class MessageList(TypedDict):
    items: list[Message]

class SubmissionList(TypedDict):
    items: list[Submission]

class ApprovalList(TypedDict):
    items: list[Approval]

class DecisionRecord(TypedDict):
    decision_id: str
    approval_id: str
    run_id: str
    owner_id: str
    decision: Literal["approve", "reject"]
    proposal: Approval
    created_at: str

class BuiltinTool(TypedDict):
    namespaced_tool_id: str
    description: str
    input_schema: dict[str, Any]
    revision: int

class TicketArgs(TypedDict):
    order_id: str
    title: str
    description: str

class TicketWrite(TypedDict):
    run_id: str
    execution_id: str
    decision_id: str
    canonical_args: str
    args_hash: str

class TicketResult(TypedDict):
    ticket_id: str
    run_id: str
    execution_id: str
    order_id: str
    title: str
    description: str
    synthetic: bool
    created_at: str

class ArtifactWrite(TypedDict):
    run_id: str
    artifact_key: str
    name: str
    media_type: Literal["text/markdown", "text/csv", "application/json"]
    content: str
    parent_file_id: NotRequired[str]

class FileList(TypedDict):
    items: list[File]
    has_more: bool

class FileContent(TypedDict):
    file: File
    text: str
    columns: list[str]

class AdminRun(TypedDict):
    run_id: str
    thread_id: str
    owner_id: str
    model: str
    status: str
    mode: str
    error_code: str
    created_at: str

class DocumentChunk(TypedDict):
    id: str
    page: NotRequired[int]
    text: str
    locator: str

class ParsedDocument(TypedDict):
    file_id: str
    sha256: str
    parser_revision: str
    status: Literal["not_extracted", "queued", "processing", "ready", "failed", "unsupported"]
    error: str
    warnings: list[str]
    chunks: list[DocumentChunk]
    columns: list[str]

class SourceRecord(TypedDict):
    source_id: str
    kind: Literal["web", "file"]
    title: str
    url: NotRequired[str]
    file_id: NotRequired[str]
    sha256: str
    locator: str
    excerpt: str
    read_status: Literal["search_only", "read", "truncated"]
    retrieved_at: str

class SourceList(TypedDict):
    items: list[SourceRecord]

class TaskItem(TypedDict):
    id: str
    title: str
    status: Literal["pending", "in_progress", "completed", "failed", "skipped"]

class TaskUpdate(TypedDict):
    tasks: list[TaskItem]

class ContextUpdate(TypedDict):
    message_count: int
    estimated_tokens: int
    summary_version: int

class WorkFileWrite(TypedDict):
    run_id: str
    path: str
    content: str
    expected_revision: int

class WorkFile(TypedDict):
    path: str
    content: str
    revision: int
    sha256: str

class DocumentTask(TypedDict):
    job_id: str
    file_id: str
    sha256: str
    media_type: str
    lease_id: str

class DocumentResult(TypedDict):
    job_id: str
    lease_id: str
    document: ParsedDocument

class DocumentExtractMetadata(TypedDict):
    file_id: str
    sha256: str
    media_type: Literal["application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"]

class BinaryArtifactMetadata(TypedDict):
    run_id: str
    artifact_key: str
    name: str
    media_type: Literal["application/vnd.openxmlformats-officedocument.wordprocessingml.document", "text/csv", "application/json", "text/markdown"]
    parent_file_id: NotRequired[str]
