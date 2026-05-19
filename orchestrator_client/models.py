"""Typed dataclasses for orchestrator API response models.

All models are plain ``@dataclass`` — no runtime Pydantic dependency.
Upstream applications can use ``dataclasses.asdict()`` for serialization
or access attributes directly.
"""

from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


@dataclass
class Pagination:
    current_page: int
    per_page: int
    total_items: int
    total_pages: int
    has_next: bool
    has_prev: bool


# ---------------------------------------------------------------------------
# Task summaries and detail
# ---------------------------------------------------------------------------


@dataclass
class TaskSummary:
    id: str
    status: str
    workflow_id: str
    iteration: int
    max_iterations: int
    goal_prompt: str
    result: str
    result_localized: str | None
    approval_reason: str
    ticket_id: str | None
    available_tools: list[str] | None
    insight: str | None
    insight_localized: str | None
    created_at: str
    updated_at: str
    pending_translations_for_locales: list[str] | None = None


@dataclass
class TaskOptions:
    """Per-task feature toggles set at creation time.

    All flags default to ``False`` (feature enabled).  ``None`` for
    the ``options`` field on :class:`TaskDetail` means the task was
    created before the feature was introduced (all features active).
    """

    disable_summaries: bool = False
    disable_translation: bool = False


@dataclass
class TaskDetail(TaskSummary):
    """Full task status including fields returned by ``GET /task/status``."""

    subtask_ids: list[str] = field(default_factory=list)
    workflow_data: dict[str, Any] | None = None
    options: dict[str, Any] | None = None


@dataclass
class TaskListResult:
    tasks: list[TaskSummary]
    pagination: Pagination


@dataclass
class TaskCreateResponse:
    task_id: str
    status: str


@dataclass
class TaskCancelResponse:
    task_id: str
    killed: bool
    via: str
    message: str
    holder_id: str | None = None
    reason: str | None = None


@dataclass
class TaskDeleteResult:
    deleted_tasks: list[str]
    failed_tasks: list[str]
    total_deleted: int
    total_failed: int


# ---------------------------------------------------------------------------
# Conversation / Messages
# ---------------------------------------------------------------------------


@dataclass
class AttachmentMeta:
    id: str
    filename: str
    mime_type: str
    size: int
    width: int | None = None
    height: int | None = None
    token_count: int | None = None


@dataclass
class ToolCall:
    id: str
    type: str
    function: dict[str, Any]


@dataclass
class Message:
    id: int
    role: str
    content: str
    created_at: str
    kind: str | None = None
    name: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    reasoning: str | None = None
    reasoning_summary: str | None = None
    tool_call_summary: str | None = None
    tool_output_summary: str | None = None
    summary_source: str | None = None
    archived: bool = False
    archived_reason: str | None = None
    attachments: list[AttachmentMeta] = field(default_factory=list)


@dataclass
class ConversationResult:
    task_id: str
    conversation: list[Message]


@dataclass
class ArchivedContent:
    id: int
    content: str
    archived: bool
    archived_reason: str | None
    created_at: str


@dataclass
class MessageTranslation:
    locale: str
    kind: str
    translated_text: str
    is_fallback: bool = False
    created_at: str | None = None


@dataclass
class MessageTranslationsResult:
    message_id: int
    translations: list[MessageTranslation] = field(default_factory=list)


@dataclass
class MessageTranslationReadyEvent:
    task_id: str
    message_id: int
    locale: str
    message_index: int
    translated_content: str | None = None
    translated_reasoning: str | None = None
    translated_reasoning_summary: str | None = None
    translated_tool_call_summary: str | None = None
    translation_failed: bool = False
    event_type: str = "message_translation_ready"


# ---------------------------------------------------------------------------
# Compaction / Journal
# ---------------------------------------------------------------------------


@dataclass
class CompactionEvent:
    id: int
    task_id: str
    triggered_at: str
    trigger_reason: str
    pre_token_count: int
    post_token_count: int
    cleared_tool_count: int
    messages_archived: int
    boundary_message_id: int | None
    consecutive_failures_at_start: int
    duration_ms: int
    workflow_id: str
    compactor_model_id: str


@dataclass
class TaskJournal:
    task_id: str
    exists: bool
    content: str | None
    updated_at: str | None
    version: int | None
    sections_over_budget: dict[str, int] | None


# ---------------------------------------------------------------------------
# Attachments (upload response)
# ---------------------------------------------------------------------------


@dataclass
class AttachmentUploadResponse:
    id: str
    filename: str
    mime_type: str
    size: int
    width: int | None
    height: int | None
    token_count: int | None


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@dataclass
class ToolInfo:
    name: str
    description: str
    server: str


@dataclass
class ToolsListResult:
    tools: list[ToolInfo]
    total_tools: int
    servers: list[str]


# ---------------------------------------------------------------------------
# Error Events
# ---------------------------------------------------------------------------


@dataclass
class ErrorEvent:
    id: str
    created_at: str
    severity: str
    source: str
    task_id: str | None
    workflow_id: str | None
    error_code: str | None
    exception_type: str | None
    message: str
    holder_id: str | None
    request_id: str | None


@dataclass
class ErrorEventDetail(ErrorEvent):
    traceback: str | None
    context: dict[str, Any] | None


@dataclass
class ErrorStatsResult:
    total: int
    by_severity: dict[str, int]
    by_source: dict[str, int]
    by_workflow_id: dict[str, int]
    by_exception_type: dict[str, int]
    top_task_ids: list[dict[str, Any]]
    top_holder_ids: list[dict[str, Any]]


@dataclass
class ErrorCountResult:
    count: int


@dataclass
class ErrorPurgeResult:
    deleted: int


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class SystemStatusSettings:
    agent_model_id: str | None
    orchestrator_model_id: str | None
    compactor_model_id: str | None
    journal_model_id: str | None
    summary_model_id: str | None
    translate_model_id: str | None
    max_concurrent_tasks_per_replica: int | None
    subagents_enabled: bool | None
    localization_targets: list[dict[str, str]] | None


@dataclass
class SystemStatus:
    is_configured: bool
    missing_fields: list[str]
    settings: SystemStatusSettings
    version: int


@dataclass
class LLMBackendInfo:
    host: str
    models: list[str]


@dataclass
class MCPServerInfo:
    base_url: str
    name: str
    description: str
    tools: list[str]


@dataclass
class TaskHandlerReplica:
    holder_id: str
    max_concurrent_tasks_per_replica: int
    currently_running_tasks: int
    running_task_ids: list[str]
    lease_ttl_seconds: float
    started_at: str
    last_heartbeat_at: str


@dataclass
class TaskHandlerCluster:
    max_concurrent_tasks_per_replica: int
    currently_running_tasks: int
    running_task_ids: list[str]
    replicas_alive: int
    queued_tasks: int
    active_tasks: int
    total_tasks: int


@dataclass
class TaskHandlerStatus:
    cluster: TaskHandlerCluster
    replicas: list[TaskHandlerReplica]


@dataclass
class TaskHandlerStatusLocal:
    running: bool
    max_concurrent_tasks: int
    currently_running_tasks: int
    running_task_ids: list[str]
    holder_id: str
    total_tasks: int
    queued_tasks: int
    active_tasks: int


@dataclass
class SummaryWorkerStatus:
    running: bool
    uptime_seconds: float
    max_concurrent_summaries: int
    processed_count: int
    queued_count: int
    pending_count: int
    queue_size: int
    error_count: int
    model_id: str
    translate_model_id: str
    is_leader: bool


@dataclass
class TokenWorkerStatus:
    running: bool
    uptime_seconds: float
    processed_count: int
    queue_size: int
    error_count: int
    encoding: str


@dataclass
class SlotInfo:
    id: str
    ip: str
    status: str
    task_id: str | None
    last_activity: str | None
    idle_seconds: int | None


@dataclass
class SlotsStatus:
    enabled: bool
    total_slots: int
    available_slots: int
    slot_tools: list[str]
    acquire_timeout_seconds: int
    slots: list[SlotInfo]


@dataclass
class ConfigurationStatus:
    agent_model: str | None
    orchestrator_model: str | None
    summary_model: str | None
    translate_model: str | None
    llm_backends_count: int
    mcp_servers_count: int
    total_tasks: int
    queued_tasks: int
    active_tasks: int
    pending_approval_tasks: int
    subagents_enabled: bool
    localization_targets: list[dict[str, str]]


# ---------------------------------------------------------------------------
# Health / Metrics
# ---------------------------------------------------------------------------


@dataclass
class HealthStatus:
    status: str
    message: str
    version: str


@dataclass
class ComponentHealth:
    connected: bool | None
    running: bool | None
    latency_ms: float | None


@dataclass
class HealthDetail(HealthStatus):
    components: dict[str, ComponentHealth]


@dataclass
class ReadinessCheck:
    ok: bool
    detail: str | None


@dataclass
class ReadinessResult:
    ready: bool
    reason: str | None
    is_startup_complete: bool
    is_shutting_down: bool
    checks: dict[str, ReadinessCheck]


@dataclass
class LockStatus:
    name: str
    is_leader: bool
    is_running: bool
    ttl_seconds: float
    token: str | None


@dataclass
class LeaderStatus:
    holder_id: str
    locks: list[LockStatus]


@dataclass
class MetricSnapshot:
    uptime_seconds: float | None
    active_tasks: int | None
    open_tasks: int | None
    llm_generated_tokens: int | None
    llm_avg_response_time_sec: float | None
    llm_requests_per_minute: float | None
    avg_task_solution_time_sec: float | None


# ---------------------------------------------------------------------------
# Auth / WebSocket status
# ---------------------------------------------------------------------------


@dataclass
class AuthConfig:
    keycloak_enabled: bool
    keycloak_url: str | None
    keycloak_realm: str | None
    keycloak_client_id: str | None


@dataclass
class WebSocketClientInfo:
    client_id: str
    connected_at: str


@dataclass
class WebSocketStatus:
    connected_clients: int
    clients: list[WebSocketClientInfo]
    event_listener_healthy: bool
    last_event_time: str | None = None


# ---------------------------------------------------------------------------
# Workflow-specific interaction responses
# ---------------------------------------------------------------------------


@dataclass
class SuccessResponse:
    message: str


@dataclass
class MioContext:
    task_id: str
    model_id: str
    current_tokens: int
    context_limit: int
    usage_percentage: float
    total_messages: int
    active_messages: int
    archived_messages: int
    messages_without_token_count: int


@dataclass
class MatrixConversationResult:
    task_id: str
    conversation: list[Message]


@dataclass
class VSATaskCreateResponse(TaskCreateResponse):
    pass


# ---------------------------------------------------------------------------
# Debug
# ---------------------------------------------------------------------------


@dataclass
class WorkflowStates:
    valid_states: dict[str, list[str]]
    processable_states: dict[str, list[str]]
    waiting_states: dict[str, list[str]]
    stopped_states: dict[str, list[str]]
    intermediate_states: dict[str, list[str]]


# ---------------------------------------------------------------------------
# New models
# ---------------------------------------------------------------------------


@dataclass
class SubagentsStatus:
    subagents_enabled: bool


@dataclass
class MioMemoryItem:
    id: str
    title: str
    content: str
    tags: list[str]
    created_at: str
    updated_at: str
    task_id: str | None = None
    linked_task_id: str | None = None


@dataclass
class MioMemoriesResult:
    memories: list[MioMemoryItem]
    total: int


@dataclass
class ToolCatalogEntry:
    name: str
    description: str
    provenance_kind: str
    category: str
    tags: list[str]
    dangerous: bool
    has_fragment: bool
    provenance_server: str | None = None
    workflow_ids: list[str] | None = None


@dataclass
class ToolCatalogResult:
    tools: list[ToolCatalogEntry]
    total_tools: int
    providers: list[str]


@dataclass
class MCPRefreshResult:
    results: dict[str, Any]
    total_refreshed: int


@dataclass
class CatalogValidationIssue:
    tool_name: str
    issue_type: str
    detail: str


@dataclass
class CatalogValidationResult:
    issues: list[CatalogValidationIssue]
    total_issues: int


@dataclass
class ReloadServicesResult:
    timestamp: str
    llm_backends: dict[str, Any]
    mcp_servers: dict[str, Any]
    slot_manager: dict[str, Any]
    next_scheduled_reload: str | None = None


@dataclass
class ReloadStatus:
    enabled: bool
    interval_hours: float | None
    last_reload: str | None = None
    next_scheduled_reload: str | None = None


@dataclass
class MessageDeleteMultipleResult:
    deleted_ids: list[int]
    failed_ids: list[int]
    total_deleted: int
    total_failed: int
