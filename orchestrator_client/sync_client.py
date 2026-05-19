"""Orchestrator — synchronous wrapper around OrchestratorAsync.

Manages a dedicated asyncio event loop internally so every method is a
plain sync call — no ``await`` needed. Perfect for scripts, REPL sessions,
CLI tools, and any code that doesn't want to enter the async world.

Usage::

    from orchestrator_client import Orchestrator

    client = Orchestrator(
        base_url="http://localhost:8080",
        api_key="...",
    )
    tasks = client.list_tasks(workflow_id="proactive")
    for t in tasks.tasks:
        print(t.id, t.status)
    client.close()

Or use the context manager::

    with Orchestrator() as client:
        status = client.get_task_status("task-abc123")
        print(status.status)

**Note**: Cannot be used from within an active asyncio event loop
(e.g. inside an ``async def``). For async contexts, use
:class:`OrchestratorAsync` directly.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any

from orchestrator_client.client import OrchestratorAsync as _OrchestratorAsync
from orchestrator_client.models import (
    ArchivedContent,
    AttachmentUploadResponse,
    AuthConfig,
    CompactionEvent,
    ConfigurationStatus,
    ConversationResult,
    ErrorCountResult,
    ErrorEventDetail,
    ErrorPurgeResult,
    ErrorStatsResult,
    HealthDetail,
    HealthStatus,
    LeaderStatus,
    MatrixConversationResult,
    MessageTranslationsResult,
    MetricSnapshot,
    MioContext,
    ReadinessResult,
    SlotsStatus,
    SuccessResponse,
    SummaryWorkerStatus,
    SystemStatus,
    TaskCreateResponse,
    TaskDeleteResult,
    TaskDetail,
    TaskHandlerStatus,
    TaskHandlerStatusLocal,
    TaskJournal,
    TaskListResult,
    TaskSummary,
    TokenWorkerStatus,
    ToolsListResult,
    VSATaskCreateResponse,
    WebSocketStatus,
    WorkflowStates,
)

logger = logging.getLogger(__name__)


class Orchestrator:
    """Synchronous client for the Orchestrator REST API.

    Wraps :class:`OrchestratorAsync` with an internal event loop.
    Every method blocks until the result is ready.

    Args:
        base_url:     Base URL of the orchestrator API.
        api_key:      Optional bearer token.
        timeout:      Default per-request timeout in seconds.
        max_retries:  Max retry attempts on transient failures.
        verify_ssl:   Whether to verify SSL certificates. Set to ``False`` for
                      self-signed certificates (default ``True``).
        http_client:  Optional pre-configured ``httpx.AsyncClient``.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        api_key: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        verify_ssl: bool = True,
        http_client: Any = None,
    ):
        self._loop = asyncio.new_event_loop()
        self._async_client = _OrchestratorAsync(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            max_retries=max_retries,
            verify_ssl=verify_ssl,
            http_client=http_client,
        )
        self._loop.run_until_complete(self._async_client.__aenter__())

    def close(self) -> None:
        """Close the underlying HTTP session and event loop."""
        try:
            self._loop.run_until_complete(self._async_client.__aexit__(None, None, None))
        finally:
            self._loop.close()

    def __enter__(self) -> "Orchestrator":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _run(self, coro: Any) -> Any:
        """Schedule and run a coroutine on the internal event loop."""
        return self._loop.run_until_complete(coro)

    # ==================================================================
    # 1. Task Management
    # ==================================================================

    def list_tasks(
        self,
        page: int = 1,
        limit: int = 25,
        order_by: str = "updated_at",
        order_direction: str = "desc",
        workflow_id: str | None = None,
        locale: str | None = None,
    ) -> TaskListResult:
        return self._run(
            self._async_client.list_tasks(
                page=page,
                limit=limit,
                order_by=order_by,
                order_direction=order_direction,
                workflow_id=workflow_id,
                locale=locale,
            )
        )

    def create_task(
        self,
        workflow_id: str = "proactive",
        goal_prompt: str = "",
        *,
        max_iterations: int = 100,
        reasoning_effort: str = "medium",
        system_prompt: str | None = None,
        developer_prompt: str | None = None,
        ticket_id: str | None = None,
        ticket_text: str | None = None,
        summary: str | None = None,
        problem_summary: str | None = None,
        solution_strategy: str | None = None,
        agent_model_id: str | None = None,
        orchestrator_model_id: str | None = None,
        available_tools: list[str] | None = None,
        attachment_ids: list[str] | None = None,
        options: dict[str, Any] | None = None,
    ) -> TaskCreateResponse:
        return self._run(
            self._async_client.create_task(
                workflow_id=workflow_id,
                goal_prompt=goal_prompt,
                max_iterations=max_iterations,
                reasoning_effort=reasoning_effort,
                system_prompt=system_prompt,
                developer_prompt=developer_prompt,
                ticket_id=ticket_id,
                ticket_text=ticket_text,
                summary=summary,
                problem_summary=problem_summary,
                solution_strategy=solution_strategy,
                agent_model_id=agent_model_id,
                orchestrator_model_id=orchestrator_model_id,
                available_tools=available_tools,
                attachment_ids=attachment_ids,
                options=options,
            )
        )

    def get_task_status(self, task_id: str, *, locale: str | None = None) -> TaskDetail:
        return self._run(self._async_client.get_task_status(task_id, locale=locale))

    def get_task_conversation(
        self,
        task_id: str,
        *,
        include_summaries: bool = True,
        exclude_archived: bool = False,
        locale: str | None = None,
    ) -> ConversationResult:
        return self._run(
            self._async_client.get_task_conversation(
                task_id,
                include_summaries=include_summaries,
                exclude_archived=exclude_archived,
                locale=locale,
            )
        )

    def get_archived_message_content(self, task_id: str, message_id: int) -> ArchivedContent:
        return self._run(self._async_client.get_archived_message_content(task_id, message_id))

    def get_task_compactions(self, task_id: str) -> list[CompactionEvent]:
        return self._run(self._async_client.get_task_compactions(task_id))

    def get_task_journal(self, task_id: str) -> TaskJournal:
        return self._run(self._async_client.get_task_journal(task_id))

    def cancel_task(self, task_id: str) -> SuccessResponse:
        return self._run(self._async_client.cancel_task(task_id))

    def delete_task(self, task_id: str) -> TaskDeleteResult:
        return self._run(self._async_client.delete_task(task_id))

    def delete_tasks(self, task_ids: list[str]) -> TaskDeleteResult:
        return self._run(self._async_client.delete_tasks(task_ids))

    # ==================================================================
    # 2. Attachments
    # ==================================================================

    def upload_attachment(
        self, file_path: str | Path, *, mime_type: str | None = None
    ) -> AttachmentUploadResponse:
        return self._run(self._async_client.upload_attachment(file_path, mime_type=mime_type))

    def download_attachment(
        self, attachment_id: str, *, outfile: str | Path | None = None
    ) -> bytes:
        return self._run(self._async_client.download_attachment(attachment_id, outfile=outfile))

    # ==================================================================
    # 3. Workflow-Specific Interactions
    # ==================================================================

    # -- Interactive --

    def send_interactive_message(
        self, task_id: str, message: str, *, attachment_ids: list[str] | None = None
    ) -> SuccessResponse:
        return self._run(
            self._async_client.send_interactive_message(
                task_id, message, attachment_ids=attachment_ids
            )
        )

    def mark_interactive_complete(self, task_id: str) -> SuccessResponse:
        return self._run(self._async_client.mark_interactive_complete(task_id))

    def mark_interactive_failed(self, task_id: str) -> SuccessResponse:
        return self._run(self._async_client.mark_interactive_failed(task_id))

    def approve_interactive_action(self, task_id: str, *, approved: bool = True) -> SuccessResponse:
        return self._run(self._async_client.approve_interactive_action(task_id, approved=approved))

    # -- Proactive --

    def send_proactive_guide(
        self, task_id: str, message: str, *, attachment_ids: list[str] | None = None
    ) -> SuccessResponse:
        return self._run(
            self._async_client.send_proactive_guide(task_id, message, attachment_ids=attachment_ids)
        )

    def respond_proactive_help(self, task_id: str, response: str) -> SuccessResponse:
        return self._run(self._async_client.respond_proactive_help(task_id, response))

    def approve_proactive_action(self, task_id: str, *, approved: bool = True) -> SuccessResponse:
        return self._run(self._async_client.approve_proactive_action(task_id, approved=approved))

    # -- Ticket --

    def send_ticket_guide(
        self, task_id: str, message: str, *, attachment_ids: list[str] | None = None
    ) -> SuccessResponse:
        return self._run(
            self._async_client.send_ticket_guide(task_id, message, attachment_ids=attachment_ids)
        )

    def respond_ticket_help(self, task_id: str, response: str) -> SuccessResponse:
        return self._run(self._async_client.respond_ticket_help(task_id, response))

    def approve_ticket_action(self, task_id: str, *, approved: bool = True) -> SuccessResponse:
        return self._run(self._async_client.approve_ticket_action(task_id, approved=approved))

    def wake_ticket(self, task_id: str) -> SuccessResponse:
        return self._run(self._async_client.wake_ticket(task_id))

    # -- Matrix --

    def send_matrix_message(
        self, task_id: str, message: str, *, attachment_ids: list[str] | None = None
    ) -> SuccessResponse:
        return self._run(
            self._async_client.send_matrix_message(task_id, message, attachment_ids=attachment_ids)
        )

    def mark_matrix_complete(self, task_id: str) -> SuccessResponse:
        return self._run(self._async_client.mark_matrix_complete(task_id))

    def mark_matrix_failed(self, task_id: str) -> SuccessResponse:
        return self._run(self._async_client.mark_matrix_failed(task_id))

    def approve_matrix_action(self, task_id: str, *, approved: bool = True) -> SuccessResponse:
        return self._run(self._async_client.approve_matrix_action(task_id, approved=approved))

    def get_matrix_conversation(
        self, task_id: str, phase: int, *, include_summaries: bool = True
    ) -> MatrixConversationResult:
        return self._run(
            self._async_client.get_matrix_conversation(
                task_id, phase, include_summaries=include_summaries
            )
        )

    # -- VSA --

    def create_vsa_task(
        self,
        user_id: str,
        goal_prompt: str,
        *,
        title: str | None = None,
        attachment_ids: list[str] | None = None,
        options: dict[str, Any] | None = None,
        delegated_token: str | None = None,
    ) -> VSATaskCreateResponse:
        return self._run(
            self._async_client.create_vsa_task(
                user_id,
                goal_prompt,
                title=title,
                attachment_ids=attachment_ids,
                options=options,
                delegated_token=delegated_token,
            )
        )

    def send_vsa_message(
        self,
        task_id: str,
        message: str,
        *,
        attachment_ids: list[str] | None = None,
        delegated_token: str | None = None,
    ) -> SuccessResponse:
        return self._run(
            self._async_client.send_vsa_message(
                task_id,
                message,
                attachment_ids=attachment_ids,
                delegated_token=delegated_token,
            )
        )

    def rename_vsa_task(self, task_id: str, title: str) -> SuccessResponse:
        return self._run(self._async_client.rename_vsa_task(task_id, title))

    def regenerate_vsa_title(self, task_id: str) -> SuccessResponse:
        return self._run(self._async_client.regenerate_vsa_title(task_id))

    def mark_vsa_complete(self, task_id: str) -> SuccessResponse:
        return self._run(self._async_client.mark_vsa_complete(task_id))

    def mark_vsa_failed(self, task_id: str) -> SuccessResponse:
        return self._run(self._async_client.mark_vsa_failed(task_id))

    def stop_vsa(self, task_id: str) -> SuccessResponse:
        return self._run(self._async_client.stop_vsa(task_id))

    def delete_vsa(self, task_id: str) -> SuccessResponse:
        return self._run(self._async_client.delete_vsa(task_id))

    def list_vsa_tasks(
        self, user_id: str, *, limit: int = 200, offset: int = 0
    ) -> list[TaskSummary]:
        return self._run(self._async_client.list_vsa_tasks(user_id, limit=limit, offset=offset))

    def search_vsa_tasks(self, user_id: str, query: str, *, limit: int = 200) -> list[TaskSummary]:
        return self._run(self._async_client.search_vsa_tasks(user_id, query, limit=limit))

    def delete_vsa_tasks_bulk(self, task_ids: list[str]) -> SuccessResponse:
        return self._run(self._async_client.delete_vsa_tasks_bulk(task_ids))

    # -- Self-Managed (Mio) --

    def send_mio_message(
        self, task_id: str, message: str, *, attachment_ids: list[str] | None = None
    ) -> SuccessResponse:
        return self._run(
            self._async_client.send_mio_message(task_id, message, attachment_ids=attachment_ids)
        )

    def approve_mio_action(
        self, task_id: str, *, approved: bool = True, feedback: str = ""
    ) -> SuccessResponse:
        return self._run(
            self._async_client.approve_mio_action(task_id, approved=approved, feedback=feedback)
        )

    def wake_mio(self, task_id: str) -> SuccessResponse:
        return self._run(self._async_client.wake_mio(task_id))

    def send_mio_user_away(self, task_id: str) -> SuccessResponse:
        return self._run(self._async_client.send_mio_user_away(task_id))

    def mark_mio_complete(self, task_id: str) -> SuccessResponse:
        return self._run(self._async_client.mark_mio_complete(task_id))

    def mark_mio_failed(self, task_id: str) -> SuccessResponse:
        return self._run(self._async_client.mark_mio_failed(task_id))

    def archive_mio(self, task_id: str) -> SuccessResponse:
        return self._run(self._async_client.archive_mio(task_id))

    def get_mio_context(self, task_id: str) -> MioContext:
        return self._run(self._async_client.get_mio_context(task_id))

    # ==================================================================
    # 4. Tools
    # ==================================================================

    def list_tools(self) -> ToolsListResult:
        return self._run(self._async_client.list_tools())

    # ==================================================================
    # 5. Debug Endpoints
    # ==================================================================

    def get_workflow_states(self) -> WorkflowStates:
        return self._run(self._async_client.get_workflow_states())

    def update_task_models(
        self,
        task_id: str,
        *,
        agent_model_id: str | None = None,
        orchestrator_model_id: str | None = None,
    ) -> SuccessResponse:
        return self._run(
            self._async_client.update_task_models(
                task_id,
                agent_model_id=agent_model_id,
                orchestrator_model_id=orchestrator_model_id,
            )
        )

    def update_task_iteration(
        self,
        task_id: str,
        *,
        iteration: int | None = None,
        max_iterations: int | None = None,
    ) -> SuccessResponse:
        return self._run(
            self._async_client.update_task_iteration(
                task_id,
                iteration=iteration,
                max_iterations=max_iterations,
            )
        )

    def update_task_workflow_data(
        self, task_id: str, workflow_data: dict[str, Any]
    ) -> SuccessResponse:
        return self._run(self._async_client.update_task_workflow_data(task_id, workflow_data))

    def delete_message(self, task_id: str, message_id: int) -> SuccessResponse:
        return self._run(self._async_client.delete_message(task_id, message_id))

    def delete_messages(self, task_id: str, message_ids: list[int]) -> dict[str, Any]:
        return self._run(self._async_client.delete_messages(task_id, message_ids))

    def update_message(
        self,
        task_id: str,
        message_id: int,
        *,
        content: str | None = None,
        reasoning: str | None = None,
    ) -> SuccessResponse:
        return self._run(
            self._async_client.update_message(
                task_id,
                message_id,
                content=content,
                reasoning=reasoning,
            )
        )

    def reset_matrix_to_phase(self, task_id: str, phase: int) -> SuccessResponse:
        return self._run(self._async_client.reset_matrix_to_phase(task_id, phase))

    def get_message_translations(self, task_id: str, message_id: int) -> MessageTranslationsResult:
        return self._run(self._async_client.get_message_translations(task_id, message_id))

    # ==================================================================
    # 6. Error Events
    # ==================================================================

    def list_errors(
        self,
        page: int = 1,
        limit: int = 50,
        *,
        task_id: str | None = None,
        severity: list[str] | None = None,
        source: list[str] | None = None,
        workflow_id: str | None = None,
        error_code: str | None = None,
        exception_type: str | None = None,
        holder_id: str | None = None,
        request_id: str | None = None,
        search: str | None = None,
        since: str | None = None,
        until: str | None = None,
        order_direction: str = "desc",
    ) -> dict[str, Any]:
        return self._run(
            self._async_client.list_errors(
                page=page,
                limit=limit,
                task_id=task_id,
                severity=severity,
                source=source,
                workflow_id=workflow_id,
                error_code=error_code,
                exception_type=exception_type,
                holder_id=holder_id,
                request_id=request_id,
                search=search,
                since=since,
                until=until,
                order_direction=order_direction,
            )
        )

    def get_error_detail(self, error_id: str) -> ErrorEventDetail:
        return self._run(self._async_client.get_error_detail(error_id))

    def get_error_stats(self, *, since: str | None = None, top_n: int = 10) -> ErrorStatsResult:
        return self._run(self._async_client.get_error_stats(since=since, top_n=top_n))

    def count_errors(self, since: str, *, severity: str | None = None) -> ErrorCountResult:
        return self._run(self._async_client.count_errors(since, severity=severity))

    def purge_errors(self) -> ErrorPurgeResult:
        return self._run(self._async_client.purge_errors())

    # ==================================================================
    # 7. Health & Metrics
    # ==================================================================

    def health(self) -> HealthStatus:
        return self._run(self._async_client.health())

    def health_detailed(self) -> HealthDetail:
        return self._run(self._async_client.health_detailed())

    def ready(self) -> ReadinessResult:
        return self._run(self._async_client.ready())

    def health_leader(self) -> LeaderStatus:
        return self._run(self._async_client.health_leader())

    def get_metrics(self, *, types: str | None = None) -> MetricSnapshot:
        return self._run(self._async_client.get_metrics(types=types))

    # ==================================================================
    # 8. Configuration
    # ==================================================================

    def get_system_status(self) -> SystemStatus:
        return self._run(self._async_client.get_system_status())

    def update_settings(self, **settings: Any) -> SystemStatus:
        return self._run(self._async_client.update_settings(**settings))

    def get_configuration_status(self) -> ConfigurationStatus:
        return self._run(self._async_client.get_configuration_status())

    def set_agent_model(self, model: str) -> SuccessResponse:
        return self._run(self._async_client.set_agent_model(model))

    def set_orchestrator_model(self, model: str) -> SuccessResponse:
        return self._run(self._async_client.set_orchestrator_model(model))

    def get_llm_backend_status(self) -> dict[str, Any]:
        return self._run(self._async_client.get_llm_backend_status())

    def add_llm_backend(self, host: str, api_key: str) -> SuccessResponse:
        return self._run(self._async_client.add_llm_backend(host, api_key))

    def remove_llm_backend(self, host: str) -> SuccessResponse:
        return self._run(self._async_client.remove_llm_backend(host))

    def get_mcp_server_status(self) -> dict[str, Any]:
        return self._run(self._async_client.get_mcp_server_status())

    def add_mcp_server(self, host: str, api_key: str) -> SuccessResponse:
        return self._run(self._async_client.add_mcp_server(host, api_key))

    def remove_mcp_server(self, host: str) -> SuccessResponse:
        return self._run(self._async_client.remove_mcp_server(host))

    def get_taskhandler_status(self) -> TaskHandlerStatus:
        return self._run(self._async_client.get_taskhandler_status())

    def get_taskhandler_status_local(self) -> TaskHandlerStatusLocal:
        return self._run(self._async_client.get_taskhandler_status_local())

    def set_concurrent_tasks_per_replica(self, max_tasks: int) -> SuccessResponse:
        return self._run(self._async_client.set_concurrent_tasks_per_replica(max_tasks))

    def get_summary_worker_status(self) -> SummaryWorkerStatus:
        return self._run(self._async_client.get_summary_worker_status())

    def set_compactor_model(self, model_name: str) -> SuccessResponse:
        return self._run(self._async_client.set_compactor_model(model_name))

    def set_translate_model(self, model_name: str) -> SuccessResponse:
        return self._run(self._async_client.set_translate_model(model_name))

    def get_token_worker_status(self) -> TokenWorkerStatus:
        return self._run(self._async_client.get_token_worker_status())

    def get_slots_status(self) -> SlotsStatus:
        return self._run(self._async_client.get_slots_status())

    # ==================================================================
    # 9. Auth / WebSocket status
    # ==================================================================

    def get_auth_config(self) -> AuthConfig:
        return self._run(self._async_client.get_auth_config())

    def get_websocket_status(self) -> WebSocketStatus:
        return self._run(self._async_client.get_websocket_status())

    # ==================================================================
    # 10. SSE Status Stream
    # ==================================================================

    def stream_task_status(
        self, task_id: str, timeout: float | None = None
    ) -> list[dict[str, Any]]:
        """Collect all SSE status events for a task.

        The async version is a streaming generator; the sync version
        runs the stream to completion and returns all events as a list.
        """

        async def _collect() -> list[dict[str, Any]]:
            events: list[dict[str, Any]] = []
            async for event in self._async_client.stream_task_status(task_id, timeout=timeout):
                events.append(event)
            return events

        return self._run(_collect())
