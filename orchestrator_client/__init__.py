"""orchestrator-client — async Python client for the DAMIT AIOps Orchestrator.

Provides a complete wrapper for the orchestrator's REST API and
Socket.IO realtime events, with typed responses, automatic retry,
and configurable auth.

Main components:

* :class:`OrchestratorClient` — full REST API surface
* :class:`RealtimeClient` — Socket.IO event subscription layer
* Typed exception hierarchy (:class:`OrchestratorError` and subclasses)
* Typed response models (dataclasses for all response shapes)
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("orchestrator-client")
except PackageNotFoundError:
    __version__ = "0.0.0.dev"

from orchestrator_client.client import OrchestratorClient
from orchestrator_client.config import OrchestratorConfig, load_config
from orchestrator_client.exceptions import (
    OrchestratorAPIError,
    OrchestratorAuthError,
    OrchestratorConfigError,
    OrchestratorConnectionError,
    OrchestratorError,
    OrchestratorNotFoundError,
)
from orchestrator_client.models import (
    ArchivedContent,
    AttachmentMeta,
    # Attachments
    AttachmentUploadResponse,
    # Auth / WebSocket
    AuthConfig,
    # Compaction / Journal
    CompactionEvent,
    ConfigurationStatus,
    ConversationResult,
    ErrorCountResult,
    # Error events
    ErrorEvent,
    ErrorEventDetail,
    ErrorPurgeResult,
    ErrorStatsResult,
    HealthDetail,
    # Health / Metrics
    HealthStatus,
    LeaderStatus,
    MatrixConversationResult,
    # Conversation
    Message,
    MetricSnapshot,
    MioContext,
    Pagination,
    ReadinessResult,
    SlotsStatus,
    # Workflow-specific
    SuccessResponse,
    SummaryWorkerStatus,
    # Configuration
    SystemStatus,
    SystemStatusSettings,
    TaskCancelResponse,
    TaskCreateResponse,
    TaskDeleteResult,
    TaskDetail,
    TaskHandlerStatus,
    TaskHandlerStatusLocal,
    TaskJournal,
    TaskListResult,
    # Core task models
    TaskSummary,
    TokenWorkerStatus,
    ToolCall,
    # Tools
    ToolInfo,
    ToolsListResult,
    VSATaskCreateResponse,
    WebSocketStatus,
    WorkflowStates,
)
from orchestrator_client.socketio import RealtimeClient

__all__ = [
    # Client classes
    "OrchestratorClient",
    "RealtimeClient",
    # Config
    "OrchestratorConfig",
    "load_config",
    # Exceptions
    "OrchestratorError",
    "OrchestratorConnectionError",
    "OrchestratorAuthError",
    "OrchestratorNotFoundError",
    "OrchestratorAPIError",
    "OrchestratorConfigError",
    # Task models
    "TaskSummary",
    "TaskDetail",
    "TaskListResult",
    "TaskCreateResponse",
    "TaskCancelResponse",
    "TaskDeleteResult",
    "Pagination",
    # Conversation
    "Message",
    "ConversationResult",
    "AttachmentMeta",
    "ToolCall",
    "ArchivedContent",
    # Compaction / Journal
    "CompactionEvent",
    "TaskJournal",
    # Attachments
    "AttachmentUploadResponse",
    # Tools
    "ToolInfo",
    "ToolsListResult",
    # Error events
    "ErrorEvent",
    "ErrorEventDetail",
    "ErrorStatsResult",
    "ErrorCountResult",
    "ErrorPurgeResult",
    # Configuration
    "SystemStatus",
    "SystemStatusSettings",
    "ConfigurationStatus",
    "TaskHandlerStatus",
    "TaskHandlerStatusLocal",
    "SummaryWorkerStatus",
    "TokenWorkerStatus",
    "SlotsStatus",
    # Health / Metrics
    "HealthStatus",
    "HealthDetail",
    "ReadinessResult",
    "LeaderStatus",
    "MetricSnapshot",
    # Auth / WebSocket
    "AuthConfig",
    "WebSocketStatus",
    # Workflow-specific
    "SuccessResponse",
    "MioContext",
    "MatrixConversationResult",
    "VSATaskCreateResponse",
    "WorkflowStates",
]
