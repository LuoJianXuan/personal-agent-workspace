// Generated. Validate external data with shared JSON Schema.
export interface Context {
  tenant_id: string;
  project_id: string;
  user_id: string;
  request_id: string;
}
export interface Login {
  username: string;
  password: string;
}
export interface User {
  id: string;
  username: string;
  role: "admin" | "user";
  enabled: boolean;
  revision: number;
}
export interface Token {
  access_token: string;
  token_type: "Bearer";
  expires_at: string;
  user: User;
}
export interface Error {
  code: string;
  message: string;
  request_id: string;
  details?: string;
}
export interface Model {
  id: string;
  name: string;
  provider: string;
  protocol: "openai_chat_completions";
  protocol_options: ProtocolOptions;
  provider_model_name: string;
  base_url: string;
  credential_ref: string;
  context_limit: number;
  max_output_tokens: number;
  capabilities: ModelCapabilities;
  revision: number;
}
export interface Skill {
  id: string;
  name: string;
  content: string;
  revision: number;
}
export interface Tool {
  namespaced_tool_id: string;
  connection_id: string;
  input_schema: Record<string, unknown>;
  schema_hash: string;
  revision: number;
  remote_name: string;
  description: string;
}
export interface Mcp {
  id: string;
  endpoint: string;
  credential_ref: string;
  revision: number;
}
export interface FileRef {
  id: string;
  sha256: string;
}
export interface Snapshot {
  snapshot_id: string;
  created_at: string;
  context: Context;
  model: Model;
  skills: Array<Skill>;
  tools: Array<Tool>;
  mcp_connections: Array<Mcp>;
  file_refs: Array<FileRef>;
  builtin_tools?: Array<BuiltinTool>;
  network_enabled?: boolean;
}
export interface HistoryMessage {
  role: "user" | "assistant";
  content: string;
  run_id: string;
}
export interface Start {
  run_id: string;
  thread_id: string;
  context: Context;
  input: string;
  history: Array<HistoryMessage>;
  effective_capabilities: Snapshot;
  file_refs: Array<FileRef>;
  mode: "real" | "mock";
  request_hash: string;
  scenario?: Scenario;
}
export interface Scenario {
  dimension: string;
  measure: string;
  aggregation: "sum" | "count" | "avg";
  chart_type: "bar" | "line";
  unit?: string;
}
export interface Submit {
  input: string;
  model_id?: string;
  skill_ids?: Array<string>;
  file_ids?: Array<string>;
  scenario?: Scenario;
  network_enabled?: boolean;
}
export interface Submission {
  run_id: string;
  thread_id: string;
  status: string;
  mode: "real" | "mock";
  runtime_unavailable: boolean;
  error_code: string;
  final_text: string;
  cancel_requested?: boolean;
  trace_url?: string;
}
export interface Run {
  run_id: string;
  thread_id: string;
  status: "QUEUED" | "RUNNING" | "WAITING_APPROVAL" | "SUCCEEDED" | "FAILED" | "CANCELLED" | "INTERRUPTED";
  mode: "real" | "mock";
}
export interface MessageStarted {
  message_id: string;
}
export interface MessageDelta {
  message_id: string;
  chunk_index: number;
  text: string;
}
export interface MessageCompleted {
  message_id: string;
  text: string;
  is_final: boolean;
}
export interface Progress {
  status: string;
  object_id?: string;
  code?: string;
}
export interface Event {
  event_id: string;
  run_id: string;
  thread_id: string;
  seq: number;
  type: "run.started" | "tool.requested" | "tool.started" | "tool.completed" | "tool.failed" | "approval.required" | "approval.resolved" | "message.started" | "message.delta" | "message.completed" | "run.completed" | "run.failed" | "run.cancelled" | "run.interrupted" | "artifact.ready" | "source.ready" | "task.updated" | "context.compacted";
  created_at: string;
  payload: MessageStarted | MessageDelta | MessageCompleted | Progress | Approval | ToolResult | File | SourceRecord | TaskUpdate | ContextUpdate;
}
export interface EventPage {
  items: Array<Event>;
  next_seq: number;
  has_more: boolean;
}
export interface Approval {
  approval_id: string;
  run_id: string;
  execution_id: string;
  tool_call_id: string;
  namespaced_tool_id: string;
  canonical_args: string;
  args_hash: string;
  capability_revision: number;
  expires_at: string;
  status: "PENDING" | "APPROVED" | "REJECTED" | "EXPIRED" | "CANCELLED";
  snapshot_id: string;
  owner_id: string;
}
export interface Decision {
  decision: "approve" | "reject";
}
export interface Resume {
  decision_id: string;
}
export interface Cancel {
  command_id: string;
}
export interface ToolResult {
  execution_id: string;
  tool_call_id: string;
  status: "REQUESTED" | "WAITING_APPROVAL" | "RUNNING" | "SUCCEEDED" | "FAILED" | "DENIED" | "CANCELLED" | "UNKNOWN";
  text: string;
  file_refs: Array<FileRef>;
}
export interface File {
  id: string;
  owner_id: string;
  run_id?: string;
  name: string;
  media_type: "text/plain" | "text/markdown" | "text/csv" | "application/json" | "application/pdf" | "application/vnd.openxmlformats-officedocument.wordprocessingml.document" | "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
  size: number;
  sha256: string;
  source: "upload" | "generated";
  status: "PENDING" | "READY" | "FAILED";
  created_at: string;
  parse_status?: "not_extracted" | "queued" | "processing" | "ready" | "failed" | "unsupported";
  parse_error?: string;
  parent_file_id?: string;
  version?: number;
}
export interface ChartPoint {
  label: string;
  value: number;
}
export interface Chart {
  type: "bar" | "line";
  file_id: string;
  dimension: string;
  measure: string;
  aggregation: "sum" | "count" | "avg";
  row_count: number;
  unit?: string;
  points: Array<ChartPoint>;
}
export interface ThinkingOptions {
  type: "disabled";
}
export interface ProtocolOptions {
  thinking?: ThinkingOptions;
}
export interface ModelCapabilities {
  streaming: boolean;
  tool_calling: boolean;
}
export interface ModelWrite {
  name: string;
  provider: string;
  protocol: "openai_chat_completions";
  protocol_options: ProtocolOptions;
  provider_model_name: string;
  base_url: string;
  credential_ref: string;
  context_limit: number;
  max_output_tokens: number;
  capabilities: ModelCapabilities;
  enabled: boolean;
  is_default: boolean;
  revision: number;
}
export interface ModelConfig {
  id: string;
  name: string;
  provider: string;
  protocol: "openai_chat_completions";
  protocol_options: ProtocolOptions;
  provider_model_name: string;
  base_url: string;
  credential_ref: string;
  context_limit: number;
  max_output_tokens: number;
  capabilities: ModelCapabilities;
  revision: number;
  enabled: boolean;
  is_default: boolean;
  credential_configured: boolean;
  availability: string;
  chat_status: "unverified";
  stream_status: "unverified";
  tool_loop_status: "unverified";
}
export interface ModelCatalog {
  id: string;
  name: string;
  provider: string;
  capabilities: ModelCapabilities;
  is_default: boolean;
  available: boolean;
  availability: string;
  revision: number;
}
export interface SkillWrite {
  name: string;
  description: string;
  category: string;
  content: string;
  enabled: boolean;
  revision: number;
}
export interface SkillConfig {
  id: string;
  name: string;
  description: string;
  category: string;
  content: string;
  enabled: boolean;
  revision: number;
  personal_enabled: boolean;
}
export interface McpWrite {
  name: string;
  endpoint: string;
  credential_ref: string;
  enabled: boolean;
  revision: number;
}
export interface McpConfig {
  id: string;
  name: string;
  endpoint: string;
  credential_ref: string;
  enabled: boolean;
  revision: number;
  probe_status: "unverified" | "success" | "failed";
  last_probe_at: string;
  probe_error: string;
}
export interface EnablementWrite {
  enabled: boolean;
  revision: number;
}
export interface PreferenceWrite {
  enabled: boolean;
}
export interface UserCreate {
  username: string;
  password: string;
}
export interface McpToolConfig {
  namespaced_tool_id: string;
  connection_id: string;
  input_schema: Record<string, unknown>;
  schema_hash: string;
  revision: number;
  remote_name: string;
  description: string;
  enabled: boolean;
  available: boolean;
  trusted_read_only: boolean;
}
export interface DiscoverRequest {
  endpoint: string;
  credential_ref: string;
}
export interface DiscoveredTool {
  remote_name: string;
  description: string;
  input_schema: Record<string, unknown>;
  trusted_read_only: boolean;
}
export interface DiscoverResult {
  tools: Array<DiscoveredTool>;
}
export interface ResolveRequest {
  model_id?: string;
  skill_ids?: Array<string>;
  require_tools: boolean;
  require_streaming: boolean;
  network_enabled?: boolean;
}
export interface CapabilityValidation {
  snapshot_id: string;
  context: Context;
  run_id?: string;
}
export interface CapabilityDecision {
  allow: boolean;
  reason: string;
}
export interface CapabilityPreview {
  snapshot_id: string;
  model_id: string;
  skill_ids: Array<string>;
  tool_ids: Array<string>;
}
export interface Audit {
  id: string;
  actor_id: string;
  action: string;
  object_id: string;
  request_id: string;
  created_at: string;
  safe_changes: Record<string, unknown>;
}
export interface PolicyTarget {
  endpoint: string;
  credential_ref: string;
  credential_configured: boolean;
}
export interface DeploymentCatalog {
  models: Array<PolicyTarget>;
  mcp: Array<PolicyTarget>;
}
export interface ModelConfigList {
  items: Array<ModelConfig>;
}
export interface ModelCatalogList {
  items: Array<ModelCatalog>;
}
export interface SkillConfigList {
  items: Array<SkillConfig>;
}
export interface McpConfigList {
  items: Array<McpConfig>;
}
export interface McpToolConfigList {
  items: Array<McpToolConfig>;
}
export interface UserList {
  items: Array<User>;
}
export interface AuditList {
  items: Array<Audit>;
}
export interface RevisionWrite {
  revision: number;
}
export interface ThreadWrite {
  title: string;
}
export interface Thread {
  id: string;
  title: string;
  created_at: string;
}
export interface Message {
  id: string;
  run_id: string;
  role: "user" | "assistant";
  text: string;
  created_at: string;
}
export interface ThreadList {
  items: Array<Thread>;
}
export interface MessageList {
  items: Array<Message>;
}
export interface SubmissionList {
  items: Array<Submission>;
}
export interface ApprovalList {
  items: Array<Approval>;
}
export interface DecisionRecord {
  decision_id: string;
  approval_id: string;
  run_id: string;
  owner_id: string;
  decision: "approve" | "reject";
  proposal: Approval;
  created_at: string;
}
export interface BuiltinTool {
  namespaced_tool_id: string;
  description: string;
  input_schema: Record<string, unknown>;
  revision: number;
}
export interface TicketArgs {
  order_id: string;
  title: string;
  description: string;
}
export interface TicketWrite {
  run_id: string;
  execution_id: string;
  decision_id: string;
  canonical_args: string;
  args_hash: string;
}
export interface TicketResult {
  ticket_id: string;
  run_id: string;
  execution_id: string;
  order_id: string;
  title: string;
  description: string;
  synthetic: boolean;
  created_at: string;
}
export interface ArtifactWrite {
  run_id: string;
  artifact_key: string;
  name: string;
  media_type: "text/markdown" | "text/csv" | "application/json";
  content: string;
  parent_file_id?: string;
}
export interface FileList {
  items: Array<File>;
  has_more: boolean;
}
export interface FileContent {
  file: File;
  text: string;
  columns: Array<string>;
}
export interface AdminRun {
  run_id: string;
  thread_id: string;
  owner_id: string;
  model: string;
  status: string;
  mode: string;
  error_code: string;
  created_at: string;
}
export interface DocumentChunk {
  id: string;
  page?: number;
  text: string;
  locator: string;
}
export interface ParsedDocument {
  file_id: string;
  sha256: string;
  parser_revision: string;
  status: "not_extracted" | "queued" | "processing" | "ready" | "failed" | "unsupported";
  error: string;
  warnings: Array<string>;
  chunks: Array<DocumentChunk>;
  columns: Array<string>;
}
export interface SourceRecord {
  source_id: string;
  kind: "web" | "file";
  title: string;
  url?: string;
  file_id?: string;
  sha256: string;
  locator: string;
  excerpt: string;
  read_status: "search_only" | "read" | "truncated";
  retrieved_at: string;
}
export interface SourceList {
  items: Array<SourceRecord>;
}
export interface TaskItem {
  id: string;
  title: string;
  status: "pending" | "in_progress" | "completed" | "failed" | "skipped";
}
export interface TaskUpdate {
  tasks: Array<TaskItem>;
}
export interface ContextUpdate {
  message_count: number;
  estimated_tokens: number;
  summary_version: number;
}
export interface WorkFileWrite {
  run_id: string;
  path: string;
  content: string;
  expected_revision: number;
}
export interface WorkFile {
  path: string;
  content: string;
  revision: number;
  sha256: string;
}
export interface DocumentTask {
  job_id: string;
  file_id: string;
  sha256: string;
  media_type: string;
  lease_id: string;
}
export interface DocumentResult {
  job_id: string;
  lease_id: string;
  document: ParsedDocument;
}
export interface DocumentExtractMetadata {
  file_id: string;
  sha256: string;
  media_type: "application/pdf" | "application/vnd.openxmlformats-officedocument.wordprocessingml.document" | "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
}
export interface BinaryArtifactMetadata {
  run_id: string;
  artifact_key: string;
  name: string;
  media_type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" | "text/csv" | "application/json" | "text/markdown";
  parent_file_id?: string;
}
