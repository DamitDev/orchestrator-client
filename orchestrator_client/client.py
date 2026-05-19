"""OrchestratorAsync — async REST API wrapper for the DAMIT AIOps Orchestrator.

Provides a complete mapping of the orchestrator's HTTP endpoints with
automatic retry (exponential backoff), typed responses via dataclasses,
and configurable auth via bearer token.

Usage::

    from orchestrator_client import OrchestratorAsync

    async with OrchestratorAsync() as client:
        tasks = await client.list_tasks(workflow_id="proactive")
        for t in tasks.tasks:
            print(t.id, t.status)
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx

from orchestrator_client.exceptions import (
    OrchestratorAPIError,
    OrchestratorAuthError,
    OrchestratorConnectionError,
    OrchestratorNotFoundError,
)
from orchestrator_client.models import (
    ArchivedContent,
    AttachmentMeta,
    AttachmentUploadResponse,
    AuthConfig,
    CatalogValidationIssue,
    CatalogValidationResult,
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
    MCPRefreshResult,
    Message,
    MessageDeleteMultipleResult,
    MessageTranslation,
    MessageTranslationsResult,
    MetricSnapshot,
    MioContext,
    MioMemoriesResult,
    MioMemoryItem,
    Pagination,
    ReadinessResult,
    ReloadServicesResult,
    ReloadStatus,
    SlotsStatus,
    SubagentsStatus,
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
    ToolCall,
    ToolCatalogEntry,
    ToolCatalogResult,
    ToolInfo,
    ToolsListResult,
    VSATaskCreateResponse,
    WebSocketClientInfo,
    WebSocketStatus,
    WorkflowStates,
)

logger = logging.getLogger(__name__)

_RETRY_BACKOFF_BASE = 0.5
_DEFAULT_TIMEOUT = 30.0


def _build_pagination(data: dict) -> Pagination:
    p = data.get("pagination", {})
    return Pagination(
        current_page=p.get("current_page", 1),
        per_page=p.get("per_page", 25),
        total_items=p.get("total_items", 0),
        total_pages=p.get("total_pages", 1),
        has_next=p.get("has_next", False),
        has_prev=p.get("has_prev", False),
    )


def _build_task_summary(t: dict) -> TaskSummary:
    return TaskSummary(
        id=t.get("id", ""),
        status=t.get("status", ""),
        workflow_id=t.get("workflow_id", ""),
        iteration=t.get("iteration", 0),
        max_iterations=t.get("max_iterations", 0),
        goal_prompt=t.get("goal_prompt", ""),
        result=t.get("result", ""),
        result_localized=t.get("result_localized"),
        approval_reason=t.get("approval_reason", ""),
        ticket_id=t.get("ticket_id"),
        available_tools=t.get("available_tools"),
        insight=t.get("insight"),
        insight_localized=t.get("insight_localized"),
        created_at=t.get("created_at", ""),
        updated_at=t.get("updated_at", ""),
        pending_translations_for_locales=t.get("pending_translations_for_locales"),
    )


class OrchestratorAsync:
    """Async HTTP client for the Orchestrator REST API.

    Args:
        base_url:  Base URL of the orchestrator API (e.g. ``http://localhost:8080``).
                   Supports subpath deployments — include the subpath in the URL
                   (e.g. ``https://oapi.local/uat``).
        api_key:   Optional bearer token sent as ``Authorization: Bearer <key>``.
        timeout:   Default per-request timeout in seconds.
        max_retries: Max retry attempts on transient failures (default 3).
        verify_ssl: Whether to verify SSL certificates. Set to ``False`` for
                    self-signed certificates (default ``True``).
        http_client: Optional pre-configured ``httpx.AsyncClient``. When provided,
                     ``base_url``, ``api_key``, ``timeout``, and ``verify_ssl``
                     are ignored in favour of the client's own configuration.
        locale:    Optional locale tag (e.g. ``"hu-hu"``, ``"en-us"``) sent as
                   ``X-Locale`` on every request so the API returns translated
                   content.  When not set the API returns its default (English)
                   content.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        api_key: str | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
        max_retries: int = 3,
        verify_ssl: bool = True,
        http_client: httpx.AsyncClient | None = None,
        locale: str | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._max_retries = max_retries

        if http_client is not None:
            self._http = http_client
        else:
            headers: dict[str, str] = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            if locale:
                headers["X-Locale"] = locale

            self._http = httpx.AsyncClient(
                base_url=self._base_url,
                headers=headers,
                timeout=httpx.Timeout(connect=timeout, read=timeout, write=timeout, pool=timeout),
                follow_redirects=True,
                verify=verify_ssl,
            )

    async def close(self) -> None:
        """Close the underlying HTTP session."""
        await self._http.aclose()

    async def __aenter__(self) -> "OrchestratorAsync":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        params: dict | None = None,
        headers: dict | None = None,
        raw_response: bool = False,
    ) -> Any:
        """Execute an HTTP request with retry and error envelope parsing.

        Args:
            method:      HTTP method (GET, POST, DELETE, etc.).
            path:        URL path (e.g. ``/tasks``).
            json_body:   Optional JSON body.
            params:      Optional query parameters.
            headers:     Optional extra headers.
            raw_response: If True, return the raw ``httpx.Response``
                          (for binary content like attachments).
        Returns:
            Parsed JSON dict or raw ``httpx.Response``.
        """
        url = self._make_url(path)

        for attempt in range(1, self._max_retries + 1):
            try:
                response = await self._http.request(
                    method,
                    url,
                    json=json_body,
                    params=params,
                    headers=headers,
                )
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                if attempt == self._max_retries:
                    raise OrchestratorConnectionError(
                        f"Orchestrator unreachable after {self._max_retries} attempts: {exc}"
                    ) from exc
                delay = _RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
                logger.warning(
                    "Request failed (attempt %d/%d), retrying in %.1fs: %s",
                    attempt,
                    self._max_retries,
                    delay,
                    exc,
                )
                await asyncio.sleep(delay)
                continue

            if response.status_code == 401:
                raise OrchestratorAuthError(
                    f"Authentication failed for {method} {path}",
                    status_code=401,
                )
            if response.status_code == 403:
                raise OrchestratorAuthError(
                    f"Access denied for {method} {path}",
                    status_code=403,
                )
            if response.status_code == 404:
                raise OrchestratorNotFoundError(
                    resource_type="resource",
                    resource_id=path,
                    detail=f"Endpoint returned 404: {method} {path}",
                )

            if response.status_code >= 500:
                if attempt == self._max_retries:
                    break
                delay = _RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
                logger.warning(
                    "Server error %d (attempt %d/%d), retrying in %.1fs",
                    response.status_code,
                    attempt,
                    self._max_retries,
                    delay,
                )
                await asyncio.sleep(delay)
                continue

            break
        else:
            # All retries exhausted — fall through to error handling below
            pass

        if raw_response:
            return response

        if response.is_success:
            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type:
                return response.json()
            return {"_text": response.text}

        # Error handling
        try:
            body = response.json()
            error = body.get("error", body)
            error_code = error.get("code") if isinstance(error, dict) else None
            error_message = (
                error.get("message", response.text) if isinstance(error, dict) else response.text
            )
            error_details = error.get("details") if isinstance(error, dict) else None
        except (ValueError, AttributeError):
            error_code = None
            error_message = response.text
            error_details = None

        raise OrchestratorAPIError(
            detail=error_message,
            status_code=response.status_code,
            error_code=error_code,
            details=error_details if isinstance(error_details, dict) else None,
        )

    # ==================================================================
    # 1. Task Management
    # ==================================================================

    async def list_tasks(
        self,
        page: int = 1,
        limit: int = 25,
        order_by: str = "updated_at",
        order_direction: str = "desc",
        workflow_id: str | None = None,
        locale: str | None = None,
    ) -> TaskListResult:
        """List tasks with pagination and optional workflow filter.

        Args:
            page:            Page number (1-indexed).
            limit:           Items per page (max 250).
            order_by:        Sort field (``created_at`` or ``updated_at``).
            order_direction: Sort direction (``asc`` or ``desc``).
            workflow_id:     Optional workflow type filter (e.g. ``proactive``, ``matrix``).
            locale:          Optional locale sent as ``X-Locale``.
        """
        params: dict[str, Any] = {
            "page": page,
            "limit": limit,
            "order_by": order_by,
            "order_direction": order_direction,
        }
        if workflow_id:
            params["workflow_id"] = workflow_id

        headers = {"X-Locale": locale} if locale else None
        data = await self._request("GET", "/tasks", params=params, headers=headers)
        tasks = [_build_task_summary(t) for t in data.get("tasks", [])]
        pagination = _build_pagination(data)
        return TaskListResult(tasks=tasks, pagination=pagination)

    async def create_task(
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
        """Create a new task.

        Args:
            workflow_id:          Workflow type (``interactive``, ``proactive``,
                                  ``ticket``, ``matrix``, ``self_managed``,
                                  ``subagent``, ``vsa``).
            goal_prompt:          Task goal and instructions.
            max_iterations:       Max iterations (1-200).
            reasoning_effort:     Reasoning depth (``low``, ``medium``, ``high``).
            system_prompt:        Custom system prompt override.
            developer_prompt:     Custom developer prompt override.
            ticket_id:            Ticket ID (ticket workflow only).
            ticket_text:          Ticket text.
            summary:              Ticket summary.
            problem_summary:      Problem description.
            solution_strategy:    Proposed solution.
            agent_model_id:       Override agent model.
            orchestrator_model_id: Override orchestrator model.
            available_tools:      Allowed tools (``None`` = all, ``[]`` = none).
            attachment_ids:       Previously uploaded attachment IDs (max 5).
            options:              Per-task feature toggles, e.g.
                                  ``{"disable_summaries": True}``.  ``None``
                                  keeps all features enabled.  Unknown keys
                                  are rejected by the server with 422.
        """
        body: dict[str, Any] = {
            "workflow_id": workflow_id,
            "goal_prompt": goal_prompt,
            "max_iterations": max_iterations,
            "reasoning_effort": reasoning_effort,
        }
        if system_prompt is not None:
            body["system_prompt"] = system_prompt
        if developer_prompt is not None:
            body["developer_prompt"] = developer_prompt
        if ticket_id is not None:
            body["ticket_id"] = ticket_id
        if ticket_text is not None:
            body["ticket_text"] = ticket_text
        if summary is not None:
            body["summary"] = summary
        if problem_summary is not None:
            body["problem_summary"] = problem_summary
        if solution_strategy is not None:
            body["solution_strategy"] = solution_strategy
        if agent_model_id is not None:
            body["agent_model_id"] = agent_model_id
        if orchestrator_model_id is not None:
            body["orchestrator_model_id"] = orchestrator_model_id
        if available_tools is not None:
            body["available_tools"] = available_tools
        if attachment_ids is not None:
            body["attachment_ids"] = attachment_ids
        if options is not None:
            body["options"] = options

        data = await self._request("POST", "/task/create", json_body=body)
        return TaskCreateResponse(
            task_id=data.get("task_id", ""),
            status=data.get("status", ""),
        )

    async def get_task_status(self, task_id: str, *, locale: str | None = None) -> TaskDetail:
        """Get full task status by ID."""
        headers = {"X-Locale": locale} if locale else None
        data = await self._request(
            "GET",
            "/task/status",
            params={"task_id": task_id},
            headers=headers,
        )
        return TaskDetail(
            **_build_task_summary(data).__dict__,
            subtask_ids=data.get("subtask_ids", []),
            workflow_data=data.get("workflow_data"),
            options=data.get("options"),
        )

    async def get_task_conversation(
        self,
        task_id: str,
        *,
        include_summaries: bool = True,
        exclude_archived: bool = False,
        locale: str | None = None,
    ) -> ConversationResult:
        """Get the full conversation for a task.

        Args:
            task_id:           Task identifier.
            include_summaries: Whether to include AI-generated summaries.
            exclude_archived:  If True, skip archived/compacted rows.
            locale:            Optional locale sent as ``X-Locale``.
        """
        params: dict[str, Any] = {"task_id": task_id}
        if not include_summaries:
            params["include_summaries"] = "false"
        if exclude_archived:
            params["exclude_archived"] = "true"

        headers = {"X-Locale": locale} if locale else None
        data = await self._request("GET", "/task/conversation", params=params, headers=headers)
        messages = [_build_message(m) for m in data.get("conversation", [])]
        return ConversationResult(
            task_id=data.get("task_id", task_id),
            conversation=messages,
        )

    async def get_archived_message_content(self, task_id: str, message_id: int) -> ArchivedContent:
        """Get the original content of an archived message."""
        params = {"task_id": task_id, "message_id": message_id}
        data = await self._request("GET", "/task/message/archived-content", params=params)
        return ArchivedContent(
            id=data.get("id", 0),
            content=data.get("content", ""),
            archived=data.get("archived", False),
            archived_reason=data.get("archived_reason"),
            created_at=data.get("created_at", ""),
        )

    async def get_task_compactions(self, task_id: str) -> list[CompactionEvent]:
        """List compaction events for a task, newest first."""
        data = await self._request("GET", "/task/compactions", params={"task_id": task_id})
        return [
            CompactionEvent(
                id=e.get("id", 0),
                task_id=e.get("task_id", task_id),
                triggered_at=e.get("triggered_at", ""),
                trigger_reason=e.get("trigger_reason", ""),
                pre_token_count=e.get("pre_token_count", 0),
                post_token_count=e.get("post_token_count", 0),
                cleared_tool_count=e.get("cleared_tool_count", 0),
                messages_archived=e.get("messages_archived", 0),
                boundary_message_id=e.get("boundary_message_id"),
                consecutive_failures_at_start=e.get("consecutive_failures_at_start", 0),
                duration_ms=e.get("duration_ms", 0),
                workflow_id=e.get("workflow_id", ""),
                compactor_model_id=e.get("compactor_model_id", ""),
            )
            for e in data
        ]

    async def get_task_journal(self, task_id: str) -> TaskJournal:
        """Get the structured journal for a task.

        If the journal hasn't been created yet, returns ``exists: false``.
        """
        data = await self._request("GET", "/task/journal", params={"task_id": task_id})
        return TaskJournal(
            task_id=data.get("task_id", task_id),
            exists=data.get("exists", False),
            content=data.get("content"),
            updated_at=data.get("updated_at"),
            version=data.get("version"),
            sections_over_budget=data.get("sections_over_budget"),
        )

    async def cancel_task(self, task_id: str) -> SuccessResponse:
        """Cancel a running task."""
        data = await self._request("POST", "/task/cancel", json_body={"task_id": task_id})
        return SuccessResponse(message=data.get("message", ""))

    async def delete_task(self, task_id: str) -> TaskDeleteResult:
        """Delete a single task (must be in a terminal state)."""
        data = await self._request("POST", "/task/delete", json_body={"task_id": task_id})
        return TaskDeleteResult(
            deleted_tasks=data.get("deleted_tasks", []),
            failed_tasks=data.get("failed_tasks", []),
            total_deleted=data.get("total_deleted", 0),
            total_failed=data.get("total_failed", 0),
        )

    async def delete_tasks(self, task_ids: list[str]) -> TaskDeleteResult:
        """Delete multiple tasks in one request."""
        data = await self._request(
            "POST", "/task/delete/multiple", json_body={"task_ids": task_ids}
        )
        return TaskDeleteResult(
            deleted_tasks=data.get("deleted_tasks", []),
            failed_tasks=data.get("failed_tasks", []),
            total_deleted=data.get("total_deleted", 0),
            total_failed=data.get("total_failed", 0),
        )

    async def set_task_status(self, task_id: str, status: str) -> SuccessResponse:
        """Force-set a task to a specific status (admin use)."""
        data = await self._request(
            "POST", "/task/set_status", json_body={"task_id": task_id, "status": status}
        )
        return SuccessResponse(message=data.get("message", ""))

    # ==================================================================
    # 2. Attachments
    # ==================================================================

    async def upload_attachment(
        self, file_path: str | Path, *, mime_type: str | None = None
    ) -> AttachmentUploadResponse:
        """Upload a file as an attachment.

        Supported types: images (PNG, JPEG, GIF, WebP) and text files.
        Size limit: 1 MB per file.

        Args:
            file_path: Path to the file to upload.
            mime_type: Optional MIME type override. If not provided, the
                       server infers it from the file extension.

        Returns:
            Attachment metadata including the ``id`` to use in create_task
            or workflow message calls.
        """
        path = Path(file_path)
        files = {"file": (path.name, path.read_bytes(), mime_type)}
        # Use raw httpx request for multipart — _request helper handles JSON
        url = self._make_url("/attachment")
        resp = await self._http.post(url, files=files)
        if resp.is_success:
            data = resp.json()
        else:
            try:
                body = resp.json()
                err = body.get("error", body)
                raise OrchestratorAPIError(
                    detail=err.get("message", resp.text),
                    status_code=resp.status_code,
                    error_code=err.get("code"),
                )
            except (ValueError, AttributeError):
                raise OrchestratorAPIError(
                    detail=resp.text,
                    status_code=resp.status_code,
                )

        return AttachmentUploadResponse(
            id=data.get("id", ""),
            filename=data.get("filename", path.name),
            mime_type=data.get("mime_type", mime_type or ""),
            size=data.get("size", 0),
            width=data.get("width"),
            height=data.get("height"),
            token_count=data.get("token_count"),
        )

    async def download_attachment(
        self, attachment_id: str, *, outfile: str | Path | None = None
    ) -> bytes:
        """Download an attachment's binary content.

        Args:
            attachment_id: The attachment ID returned by ``upload_attachment``.
            outfile:       Optional path to save the file to. If not provided,
                           the raw bytes are returned.

        Returns:
            The binary content of the attachment (always returned, even
            when ``outfile`` is set).
        """
        response = await self._request("GET", f"/attachment/{attachment_id}", raw_response=True)
        content = response.content
        if outfile:
            Path(outfile).write_bytes(content)
        return content

    # ==================================================================
    # 3. Workflow-Specific Interactions
    # ==================================================================

    # -- Interactive --

    async def send_interactive_message(
        self, task_id: str, message: str, *, attachment_ids: list[str] | None = None
    ) -> SuccessResponse:
        body: dict[str, Any] = {"task_id": task_id, "message": message}
        if attachment_ids is not None:
            body["attachment_ids"] = attachment_ids
        data = await self._request("POST", "/task/interactive/message", json_body=body)
        return SuccessResponse(message=data.get("message", ""))

    async def mark_interactive_complete(self, task_id: str) -> SuccessResponse:
        data = await self._request(
            "POST", "/task/interactive/mark_complete", json_body={"task_id": task_id}
        )
        return SuccessResponse(message=data.get("message", ""))

    async def mark_interactive_failed(self, task_id: str) -> SuccessResponse:
        data = await self._request(
            "POST", "/task/interactive/mark_failed", json_body={"task_id": task_id}
        )
        return SuccessResponse(message=data.get("message", ""))

    async def approve_interactive_action(
        self, task_id: str, *, approved: bool = True
    ) -> SuccessResponse:
        data = await self._request(
            "POST",
            "/task/interactive/action",
            json_body={"task_id": task_id, "approved": approved},
        )
        return SuccessResponse(message=data.get("message", ""))

    async def stop_interactive(self, task_id: str) -> SuccessResponse:
        """Stop an interactive workflow task."""
        data = await self._request("POST", "/task/interactive/stop", json_body={"task_id": task_id})
        return SuccessResponse(message=data.get("message", ""))

    # -- Proactive --

    async def send_proactive_guide(
        self, task_id: str, message: str, *, attachment_ids: list[str] | None = None
    ) -> SuccessResponse:
        body: dict[str, Any] = {"task_id": task_id, "message": message}
        if attachment_ids is not None:
            body["attachment_ids"] = attachment_ids
        data = await self._request("POST", "/task/proactive/guide", json_body=body)
        return SuccessResponse(message=data.get("message", ""))

    async def respond_proactive_help(self, task_id: str, response: str) -> SuccessResponse:
        data = await self._request(
            "POST",
            "/task/proactive/help",
            json_body={"task_id": task_id, "response": response},
        )
        return SuccessResponse(message=data.get("message", ""))

    async def approve_proactive_action(
        self, task_id: str, *, approved: bool = True
    ) -> SuccessResponse:
        data = await self._request(
            "POST",
            "/task/proactive/action",
            json_body={"task_id": task_id, "approved": approved},
        )
        return SuccessResponse(message=data.get("message", ""))

    # -- Ticket --

    async def send_ticket_guide(
        self, task_id: str, message: str, *, attachment_ids: list[str] | None = None
    ) -> SuccessResponse:
        body: dict[str, Any] = {"task_id": task_id, "message": message}
        if attachment_ids is not None:
            body["attachment_ids"] = attachment_ids
        data = await self._request("POST", "/task/ticket/guide", json_body=body)
        return SuccessResponse(message=data.get("message", ""))

    async def respond_ticket_help(self, task_id: str, response: str) -> SuccessResponse:
        data = await self._request(
            "POST",
            "/task/ticket/help",
            json_body={"task_id": task_id, "response": response},
        )
        return SuccessResponse(message=data.get("message", ""))

    async def approve_ticket_action(
        self, task_id: str, *, approved: bool = True
    ) -> SuccessResponse:
        data = await self._request(
            "POST",
            "/task/ticket/action",
            json_body={"task_id": task_id, "approved": approved},
        )
        return SuccessResponse(message=data.get("message", ""))

    async def wake_ticket(self, task_id: str) -> SuccessResponse:
        data = await self._request("POST", "/task/ticket/wake", json_body={"task_id": task_id})
        return SuccessResponse(message=data.get("message", ""))

    # -- Matrix --

    async def send_matrix_message(
        self, task_id: str, message: str, *, attachment_ids: list[str] | None = None
    ) -> SuccessResponse:
        body: dict[str, Any] = {"task_id": task_id, "message": message}
        if attachment_ids is not None:
            body["attachment_ids"] = attachment_ids
        data = await self._request("POST", "/task/matrix/message", json_body=body)
        return SuccessResponse(message=data.get("message", ""))

    async def mark_matrix_complete(self, task_id: str) -> SuccessResponse:
        data = await self._request(
            "POST", "/task/matrix/mark_complete", json_body={"task_id": task_id}
        )
        return SuccessResponse(message=data.get("message", ""))

    async def mark_matrix_failed(self, task_id: str) -> SuccessResponse:
        data = await self._request(
            "POST", "/task/matrix/mark_failed", json_body={"task_id": task_id}
        )
        return SuccessResponse(message=data.get("message", ""))

    async def approve_matrix_action(
        self, task_id: str, *, approved: bool = True
    ) -> SuccessResponse:
        data = await self._request(
            "POST",
            "/task/matrix/action",
            json_body={"task_id": task_id, "approved": approved},
        )
        return SuccessResponse(message=data.get("message", ""))

    async def get_matrix_conversation(
        self, task_id: str, phase: int, *, include_summaries: bool = True
    ) -> MatrixConversationResult:
        params: dict[str, Any] = {"task_id": task_id, "phase": phase}
        if not include_summaries:
            params["include_summaries"] = "false"
        data = await self._request("GET", "/task/matrix/conversation", params=params)
        messages = [_build_message(m) for m in data.get("conversation", [])]
        return MatrixConversationResult(
            task_id=data.get("task_id", task_id),
            conversation=messages,
        )

    # -- VSA --

    async def create_vsa_task(
        self,
        user_id: str,
        goal_prompt: str,
        *,
        title: str | None = None,
        attachment_ids: list[str] | None = None,
        options: dict[str, Any] | None = None,
        delegated_token: str | None = None,
    ) -> VSATaskCreateResponse:
        """Create a new VSA task.

        Args:
            user_id:          User identifier.
            goal_prompt:      Initial message or goal.
            title:            Optional title; AI-generated if omitted.
            attachment_ids:   Previously uploaded attachment IDs (max 5).
            options:          Per-task feature toggles (same keys as
                              ``create_task``).  ``None`` keeps all features on.
            delegated_token:  Short-lived AiDIT delegated token obtained via
                              RFC 8693 token exchange (typically injected by the
                              iris LoopBack proxy).  Stored encrypted; the
                              orchestrator transparently appends it as ``token``
                              to mcp-aidit tool-call arguments.
        """
        body: dict[str, Any] = {"user_id": user_id, "goal_prompt": goal_prompt}
        if title is not None:
            body["title"] = title
        if attachment_ids is not None:
            body["attachment_ids"] = attachment_ids
        if options is not None:
            body["options"] = options
        if delegated_token is not None:
            body["delegated_token"] = delegated_token
        data = await self._request("POST", "/task/vsa/create", json_body=body)
        return VSATaskCreateResponse(task_id=data.get("task_id", ""), status=data.get("status", ""))

    async def send_vsa_message(
        self,
        task_id: str,
        message: str,
        *,
        attachment_ids: list[str] | None = None,
        delegated_token: str | None = None,
    ) -> SuccessResponse:
        """Send a message to an existing VSA task (or reopen a completed one).

        Args:
            task_id:          ID of the VSA task.
            message:          Message content to send.
            attachment_ids:   Previously uploaded attachment IDs (max 5).
            delegated_token:  Short-lived AiDIT delegated token.  When provided,
                              overwrites the token stored for the task.  Omitting
                              the argument leaves the existing token unchanged.
        """
        body: dict[str, Any] = {"task_id": task_id, "message": message}
        if attachment_ids is not None:
            body["attachment_ids"] = attachment_ids
        if delegated_token is not None:
            body["delegated_token"] = delegated_token
        data = await self._request("POST", "/task/vsa/message", json_body=body)
        return SuccessResponse(message=data.get("message", ""))

    async def rename_vsa_task(self, task_id: str, title: str) -> SuccessResponse:
        data = await self._request(
            "POST", "/task/vsa/rename", json_body={"task_id": task_id, "title": title}
        )
        return SuccessResponse(message=data.get("message", ""))

    async def regenerate_vsa_title(self, task_id: str) -> SuccessResponse:
        data = await self._request(
            "POST", "/task/vsa/regenerate_title", json_body={"task_id": task_id}
        )
        return SuccessResponse(message=data.get("message", ""))

    async def mark_vsa_complete(self, task_id: str) -> SuccessResponse:
        data = await self._request(
            "POST", "/task/vsa/mark_complete", json_body={"task_id": task_id}
        )
        return SuccessResponse(message=data.get("message", ""))

    async def mark_vsa_failed(self, task_id: str) -> SuccessResponse:
        data = await self._request("POST", "/task/vsa/mark_failed", json_body={"task_id": task_id})
        return SuccessResponse(message=data.get("message", ""))

    async def stop_vsa(self, task_id: str) -> SuccessResponse:
        data = await self._request("POST", "/task/vsa/stop", json_body={"task_id": task_id})
        return SuccessResponse(message=data.get("message", ""))

    async def delete_vsa(self, task_id: str) -> SuccessResponse:
        data = await self._request("POST", "/task/vsa/delete", json_body={"task_id": task_id})
        return SuccessResponse(message=data.get("message", ""))

    async def list_vsa_tasks(
        self, user_id: str, *, limit: int = 200, offset: int = 0
    ) -> list[TaskSummary]:
        params = {"user_id": user_id, "limit": limit, "offset": offset}
        data = await self._request("GET", "/task/vsa/list", params=params)
        return [_build_task_summary(t) for t in data]

    async def search_vsa_tasks(
        self, user_id: str, query: str, *, limit: int = 200
    ) -> list[TaskSummary]:
        params = {"user_id": user_id, "query": query, "limit": limit}
        data = await self._request("GET", "/task/vsa/search", params=params)
        return [_build_task_summary(t) for t in data]

    async def delete_vsa_tasks_bulk(self, task_ids: list[str]) -> SuccessResponse:
        data = await self._request(
            "POST", "/task/vsa/delete_bulk", json_body={"task_ids": task_ids}
        )
        return SuccessResponse(message=data.get("message", ""))

    # -- Self-Managed (Mio) --

    async def send_mio_message(
        self, task_id: str, message: str, *, attachment_ids: list[str] | None = None
    ) -> SuccessResponse:
        body: dict[str, Any] = {"task_id": task_id, "message": message}
        if attachment_ids is not None:
            body["attachment_ids"] = attachment_ids
        data = await self._request("POST", "/task/self_managed/message", json_body=body)
        return SuccessResponse(message=data.get("message", ""))

    async def approve_mio_action(
        self, task_id: str, *, approved: bool = True, feedback: str = ""
    ) -> SuccessResponse:
        body: dict[str, Any] = {"task_id": task_id, "approved": approved}
        if feedback:
            body["feedback"] = feedback
        data = await self._request("POST", "/task/self_managed/action", json_body=body)
        return SuccessResponse(message=data.get("message", ""))

    async def wake_mio(self, task_id: str) -> SuccessResponse:
        data = await self._request(
            "POST", "/task/self_managed/wake", json_body={"task_id": task_id}
        )
        return SuccessResponse(message=data.get("message", ""))

    async def send_mio_user_away(self, task_id: str) -> SuccessResponse:
        data = await self._request(
            "POST", "/task/self_managed/user_away", json_body={"task_id": task_id}
        )
        return SuccessResponse(message=data.get("message", ""))

    async def mark_mio_complete(self, task_id: str) -> SuccessResponse:
        data = await self._request(
            "POST", "/task/self_managed/mark_complete", json_body={"task_id": task_id}
        )
        return SuccessResponse(message=data.get("message", ""))

    async def mark_mio_failed(self, task_id: str) -> SuccessResponse:
        data = await self._request(
            "POST", "/task/self_managed/mark_failed", json_body={"task_id": task_id}
        )
        return SuccessResponse(message=data.get("message", ""))

    async def archive_mio(self, task_id: str) -> SuccessResponse:
        data = await self._request(
            "POST", "/task/self_managed/archive", json_body={"task_id": task_id}
        )
        return SuccessResponse(message=data.get("message", ""))

    async def get_mio_context(self, task_id: str) -> MioContext:
        data = await self._request("GET", "/task/self_managed/context", params={"task_id": task_id})
        return MioContext(
            task_id=data.get("task_id", task_id),
            model_id=data.get("model_id", ""),
            current_tokens=data.get("current_tokens", 0),
            context_limit=data.get("context_limit", 0),
            usage_percentage=data.get("usage_percentage", 0.0),
            total_messages=data.get("total_messages", 0),
            active_messages=data.get("active_messages", 0),
            archived_messages=data.get("archived_messages", 0),
            messages_without_token_count=data.get("messages_without_token_count", 0),
        )

    async def get_mio_memories(
        self, task_id: str, *, include_common: bool = False
    ) -> MioMemoriesResult:
        """Get long-term memories for a Mio task."""
        data = await self._request(
            "GET",
            "/task/self_managed/memories",
            params={"task_id": task_id, "include_common": str(include_common).lower()},
        )
        memories = [
            MioMemoryItem(
                id=m.get("id", ""),
                title=m.get("title", ""),
                content=m.get("content", ""),
                tags=m.get("tags", []),
                created_at=m.get("created_at", ""),
                updated_at=m.get("updated_at", ""),
                task_id=m.get("task_id"),
                linked_task_id=m.get("linked_task_id"),
            )
            for m in data.get("memories", [])
        ]
        return MioMemoriesResult(memories=memories, total=data.get("total", 0))

    # ==================================================================
    # 4. Tools
    # ==================================================================

    async def list_tools(self) -> ToolsListResult:
        """Get all available tools from MCP servers and built-in tools."""
        data = await self._request("GET", "/tools/all")
        tools = [ToolInfo(**t) for t in data.get("tools", [])]
        return ToolsListResult(
            tools=tools,
            total_tools=data.get("total_tools", 0),
            servers=data.get("servers", []),
        )

    async def get_tool_catalog(self) -> ToolCatalogResult:
        """Get the full tool catalog with metadata, tags, and fragment info."""
        data = await self._request("GET", "/tools/catalog")
        tools = [
            ToolCatalogEntry(
                name=t.get("name", ""),
                description=t.get("description", ""),
                provenance_kind=t.get("provenance_kind", ""),
                category=t.get("category", ""),
                tags=t.get("tags", []),
                dangerous=t.get("dangerous", False),
                has_fragment=t.get("has_fragment", False),
                provenance_server=t.get("provenance_server"),
                workflow_ids=t.get("workflow_ids"),
            )
            for t in data.get("tools", [])
        ]
        return ToolCatalogResult(
            tools=tools,
            total_tools=data.get("total_tools", 0),
            providers=data.get("providers", []),
        )

    async def refresh_mcp_tools(self) -> MCPRefreshResult:
        """Trigger a refresh of all MCP server tool registries."""
        data = await self._request("POST", "/tools/mcp/refresh")
        return MCPRefreshResult(
            results=data.get("results", {}),
            total_refreshed=data.get("total_refreshed", 0),
        )

    async def validate_tool_catalog(self) -> CatalogValidationResult:
        """Validate tool catalog fragment coverage."""
        data = await self._request("GET", "/tools/validate")
        issues = [
            CatalogValidationIssue(
                tool_name=i.get("tool_name", ""),
                issue_type=i.get("issue_type", ""),
                detail=i.get("detail", ""),
            )
            for i in data.get("issues", [])
        ]
        return CatalogValidationResult(issues=issues, total_issues=data.get("total_issues", 0))

    # ==================================================================
    # 5. Debug Endpoints
    # ==================================================================

    async def get_workflow_states(self) -> WorkflowStates:
        data = await self._request("GET", "/debug/workflow_states")
        return WorkflowStates(
            valid_states=data.get("valid_states", {}),
            processable_states=data.get("processable_states", {}),
            waiting_states=data.get("waiting_states", {}),
            stopped_states=data.get("stopped_states", {}),
            intermediate_states=data.get("intermediate_states", {}),
        )

    async def update_task_models(
        self,
        task_id: str,
        *,
        agent_model_id: str | None = None,
        orchestrator_model_id: str | None = None,
    ) -> SuccessResponse:
        body: dict[str, Any] = {"task_id": task_id}
        if agent_model_id is not None:
            body["agent_model_id"] = agent_model_id
        if orchestrator_model_id is not None:
            body["orchestrator_model_id"] = orchestrator_model_id
        data = await self._request("POST", "/debug/task/models", json_body=body)
        return SuccessResponse(message=data.get("message", ""))

    async def update_task_iteration(
        self,
        task_id: str,
        *,
        iteration: int | None = None,
        max_iterations: int | None = None,
    ) -> SuccessResponse:
        body: dict[str, Any] = {"task_id": task_id}
        if iteration is not None:
            body["iteration"] = iteration
        if max_iterations is not None:
            body["max_iterations"] = max_iterations
        data = await self._request("POST", "/debug/task/iteration", json_body=body)
        return SuccessResponse(message=data.get("message", ""))

    async def update_task_workflow_data(
        self, task_id: str, workflow_data: dict[str, Any]
    ) -> SuccessResponse:
        body = {"task_id": task_id, "workflow_data": workflow_data}
        data = await self._request("POST", "/debug/task/workflow_data", json_body=body)
        return SuccessResponse(message=data.get("message", ""))

    async def delete_message(self, task_id: str, message_id: int) -> SuccessResponse:
        body = {"task_id": task_id, "message_id": message_id}
        data = await self._request("POST", "/debug/task/message/delete", json_body=body)
        return SuccessResponse(message=data.get("message", ""))

    async def delete_messages(
        self, task_id: str, message_ids: list[int]
    ) -> MessageDeleteMultipleResult:
        body = {"task_id": task_id, "message_ids": message_ids}
        data = await self._request("POST", "/debug/task/message/delete/multiple", json_body=body)
        return MessageDeleteMultipleResult(
            deleted_ids=data.get("deleted_ids", []),
            failed_ids=data.get("failed_ids", []),
            total_deleted=data.get("total_deleted", 0),
            total_failed=data.get("total_failed", 0),
        )

    async def update_message(
        self,
        task_id: str,
        message_id: int,
        *,
        content: str | None = None,
        reasoning: str | None = None,
    ) -> SuccessResponse:
        body: dict[str, Any] = {"task_id": task_id, "message_id": message_id}
        if content is not None:
            body["content"] = content
        if reasoning is not None:
            body["reasoning"] = reasoning
        data = await self._request("POST", "/debug/task/message/update", json_body=body)
        return SuccessResponse(message=data.get("message", ""))

    async def reset_matrix_to_phase(self, task_id: str, phase: int) -> SuccessResponse:
        body = {"task_id": task_id, "phase": phase}
        data = await self._request("POST", "/debug/task/matrix/reset_to_phase", json_body=body)
        return SuccessResponse(message=data.get("message", ""))

    async def get_message_translations(
        self, task_id: str, message_id: int
    ) -> MessageTranslationsResult:
        """Return all stored translation rows for a message."""
        data = await self._request(
            "GET",
            f"/debug/task/{task_id}/message/{message_id}/translations",
        )
        return MessageTranslationsResult(
            message_id=data.get("message_id", message_id),
            translations=[
                MessageTranslation(
                    locale=row.get("locale", ""),
                    kind=row.get("kind", ""),
                    translated_text=row.get("translated_text", ""),
                    is_fallback=row.get("is_fallback", False),
                    created_at=row.get("created_at"),
                )
                for row in data.get("translations", [])
            ],
        )

    # ==================================================================
    # 6. Error Events
    # ==================================================================

    async def list_errors(
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
        """Paginated, filterable error event list.

        Returns a dict with ``items`` (list of error events) and ``pagination``.
        The full traceback and context are omitted from list results; use
        ``get_error_detail()`` for those.
        """
        params: dict[str, Any] = {
            "page": page,
            "limit": limit,
            "order_direction": order_direction,
        }
        if task_id is not None:
            params["task_id"] = task_id
        if severity:
            # Multi-select: repeat query param
            params["severity"] = severity
        if source:
            params["source"] = source
        if workflow_id is not None:
            params["workflow_id"] = workflow_id
        if error_code is not None:
            params["error_code"] = error_code
        if exception_type is not None:
            params["exception_type"] = exception_type
        if holder_id is not None:
            params["holder_id"] = holder_id
        if request_id is not None:
            params["request_id"] = request_id
        if search is not None:
            params["search"] = search
        if since is not None:
            params["since"] = since
        if until is not None:
            params["until"] = until
        return await self._request("GET", "/errors", params=params)

    async def get_error_detail(self, error_id: str) -> ErrorEventDetail:
        """Get full error detail including traceback and context."""
        data = await self._request("GET", f"/errors/{error_id}")
        return ErrorEventDetail(
            id=data.get("id", ""),
            created_at=data.get("created_at", ""),
            severity=data.get("severity", ""),
            source=data.get("source", ""),
            task_id=data.get("task_id"),
            workflow_id=data.get("workflow_id"),
            error_code=data.get("error_code"),
            exception_type=data.get("exception_type"),
            message=data.get("message", ""),
            holder_id=data.get("holder_id"),
            request_id=data.get("request_id"),
            traceback=data.get("traceback"),
            context=data.get("context"),
        )

    async def get_error_stats(
        self, *, since: str | None = None, top_n: int = 10
    ) -> ErrorStatsResult:
        params: dict[str, Any] = {"top_n": top_n}
        if since is not None:
            params["since"] = since
        data = await self._request("GET", "/errors/stats", params=params)
        return ErrorStatsResult(
            total=data.get("total", 0),
            by_severity=data.get("by_severity", {}),
            by_source=data.get("by_source", {}),
            by_workflow_id=data.get("by_workflow_id", {}),
            by_exception_type=data.get("by_exception_type", {}),
            top_task_ids=data.get("top_task_ids", []),
            top_holder_ids=data.get("top_holder_ids", []),
        )

    async def count_errors(self, since: str, *, severity: str | None = None) -> ErrorCountResult:
        params: dict[str, Any] = {"since": since}
        if severity is not None:
            params["severity"] = severity
        data = await self._request("GET", "/errors/count", params=params)
        return ErrorCountResult(count=data.get("count", 0))

    async def purge_errors(self) -> ErrorPurgeResult:
        """Delete all error events (DEV mode only)."""
        data = await self._request("DELETE", "/errors")
        return ErrorPurgeResult(deleted=data.get("deleted", 0))

    # ==================================================================
    # 7. Health & Metrics
    # ==================================================================

    async def health(self) -> HealthStatus:
        data = await self._request("GET", "/health")
        return HealthStatus(
            status=data.get("status", ""),
            message=data.get("message", ""),
            version=data.get("version", ""),
        )

    async def health_detailed(self) -> HealthDetail:
        data = await self._request("GET", "/health/detailed")
        components = {}
        for name, info in data.get("components", {}).items():
            if isinstance(info, dict):
                components[name] = type(
                    "ComponentHealth",
                    (),
                    {
                        "connected": info.get("connected"),
                        "running": info.get("running"),
                        "latency_ms": info.get("latency_ms"),
                    },
                )()
        return HealthDetail(
            status=data.get("status", ""),
            message=data.get("message", ""),
            version=data.get("version", ""),
            components=components,
        )

    async def ready(self) -> ReadinessResult:
        data = await self._request("GET", "/ready")
        checks = {}
        for name, info in data.get("checks", {}).items():
            if isinstance(info, dict):
                checks[name] = type(
                    "ReadinessCheck",
                    (),
                    {"ok": info.get("ok", False), "detail": info.get("detail")},
                )()
        return ReadinessResult(
            ready=data.get("ready", False),
            reason=data.get("reason"),
            is_startup_complete=data.get("is_startup_complete", False),
            is_shutting_down=data.get("is_shutting_down", False),
            checks=checks,
        )

    async def health_leader(self) -> LeaderStatus:
        data = await self._request("GET", "/health/leader")
        locks = [
            type(
                "LockStatus",
                (),
                {
                    "name": lock.get("name", ""),
                    "is_leader": lock.get("is_leader", False),
                    "is_running": lock.get("is_running", False),
                    "ttl_seconds": lock.get("ttl_seconds", 0.0),
                    "token": lock.get("token"),
                },
            )()
            for lock in data.get("locks", [])
        ]
        return LeaderStatus(holder_id=data.get("holder_id", ""), locks=locks)

    async def get_metrics(self, *, types: str | None = None) -> MetricSnapshot:
        params = {}
        if types is not None:
            params["type"] = types
        data = await self._request("GET", "/metrics", params=params)
        return MetricSnapshot(
            uptime_seconds=data.get("uptime_seconds"),
            active_tasks=data.get("active_tasks"),
            open_tasks=data.get("open_tasks"),
            llm_generated_tokens=data.get("llm_generated_tokens"),
            llm_avg_response_time_sec=data.get("llm_avg_response_time_sec"),
            llm_requests_per_minute=data.get("llm_requests_per_minute"),
            avg_task_solution_time_sec=data.get("avg_task_solution_time_sec"),
        )

    # ==================================================================
    # 8. Configuration
    # ==================================================================

    async def get_system_status(self) -> SystemStatus:
        data = await self._request("GET", "/configuration/system/status")
        settings_data = data.get("settings", {}) or {}
        settings = type(
            "SystemStatusSettings",
            (),
            {
                k: settings_data.get(k)
                for k in [
                    "agent_model_id",
                    "orchestrator_model_id",
                    "compactor_model_id",
                    "journal_model_id",
                    "summary_model_id",
                    "translate_model_id",
                    "max_concurrent_tasks_per_replica",
                    "subagents_enabled",
                    "localization_targets",
                ]
            },
        )()
        return SystemStatus(
            is_configured=data.get("is_configured", False),
            missing_fields=data.get("missing_fields", []),
            settings=settings,
            version=data.get("version", 0),
        )

    async def update_settings(self, **settings: Any) -> SystemStatus:
        data = await self._request("POST", "/configuration/system/settings", json_body=settings)
        settings_data = data.get("settings", {}) or {}
        settings_obj = type(
            "SystemStatusSettings",
            (),
            {
                k: settings_data.get(k)
                for k in [
                    "agent_model_id",
                    "orchestrator_model_id",
                    "compactor_model_id",
                    "journal_model_id",
                    "summary_model_id",
                    "translate_model_id",
                    "max_concurrent_tasks_per_replica",
                    "subagents_enabled",
                    "localization_targets",
                ]
            },
        )()
        return SystemStatus(
            is_configured=data.get("is_configured", False),
            missing_fields=data.get("missing_fields", []),
            settings=settings_obj,
            version=data.get("version", 0),
        )

    async def get_configuration_status(self) -> ConfigurationStatus:
        data = await self._request("GET", "/configuration/status")
        return ConfigurationStatus(
            agent_model=data.get("agent_model"),
            orchestrator_model=data.get("orchestrator_model"),
            summary_model=data.get("summary_model"),
            translate_model=data.get("translate_model"),
            llm_backends_count=data.get("llm_backends_count", 0),
            mcp_servers_count=data.get("mcp_servers_count", 0),
            total_tasks=data.get("total_tasks", 0),
            queued_tasks=data.get("queued_tasks", 0),
            active_tasks=data.get("active_tasks", 0),
            pending_approval_tasks=data.get("pending_approval_tasks", 0),
            subagents_enabled=data.get("subagents_enabled", False),
            localization_targets=data.get("localization_targets", []),
        )

    async def set_agent_model(self, model: str) -> SuccessResponse:
        data = await self._request("POST", "/configuration/agent", json_body={"model": model})
        return SuccessResponse(message=data.get("message", ""))

    async def set_orchestrator_model(self, model: str) -> SuccessResponse:
        data = await self._request(
            "POST", "/configuration/orchestrator", json_body={"model": model}
        )
        return SuccessResponse(message=data.get("message", ""))

    async def get_llm_backend_status(self) -> dict[str, Any]:
        return await self._request("GET", "/configuration/llmbackend/status")

    async def add_llm_backend(self, host: str, api_key: str) -> SuccessResponse:
        data = await self._request(
            "POST",
            "/configuration/llmbackend/add",
            json_body={"host": host, "api_key": api_key},
        )
        return SuccessResponse(message=data.get("message", ""))

    async def remove_llm_backend(self, host: str) -> SuccessResponse:
        data = await self._request(
            "POST", "/configuration/llmbackend/remove", json_body={"host": host}
        )
        return SuccessResponse(message=data.get("message", ""))

    async def get_mcp_server_status(self) -> dict[str, Any]:
        return await self._request("GET", "/configuration/mcpserver/status")

    async def add_mcp_server(self, host: str, api_key: str) -> SuccessResponse:
        data = await self._request(
            "POST",
            "/configuration/mcpserver/add",
            json_body={"host": host, "api_key": api_key},
        )
        return SuccessResponse(message=data.get("message", ""))

    async def remove_mcp_server(self, host: str) -> SuccessResponse:
        data = await self._request(
            "POST", "/configuration/mcpserver/remove", json_body={"host": host}
        )
        return SuccessResponse(message=data.get("message", ""))

    async def get_taskhandler_status(self) -> TaskHandlerStatus:
        data = await self._request("GET", "/configuration/taskhandler/status")
        replicas = [
            type(
                "TaskHandlerReplica",
                (),
                {
                    "holder_id": r.get("holder_id", ""),
                    "max_concurrent_tasks_per_replica": r.get(
                        "max_concurrent_tasks_per_replica", 0
                    ),
                    "currently_running_tasks": r.get("currently_running_tasks", 0),
                    "running_task_ids": r.get("running_task_ids", []),
                    "lease_ttl_seconds": r.get("lease_ttl_seconds", 0.0),
                    "started_at": r.get("started_at", ""),
                    "last_heartbeat_at": r.get("last_heartbeat_at", ""),
                },
            )()
            for r in data.get("replicas", [])
        ]
        cluster_data = data.get("cluster", {})
        cluster = type(
            "TaskHandlerCluster",
            (),
            {
                "max_concurrent_tasks_per_replica": cluster_data.get(
                    "max_concurrent_tasks_per_replica", 0
                ),
                "currently_running_tasks": cluster_data.get("currently_running_tasks", 0),
                "running_task_ids": cluster_data.get("running_task_ids", []),
                "replicas_alive": cluster_data.get("replicas_alive", 0),
                "queued_tasks": cluster_data.get("queued_tasks", 0),
                "active_tasks": cluster_data.get("active_tasks", 0),
                "total_tasks": cluster_data.get("total_tasks", 0),
            },
        )()
        return TaskHandlerStatus(cluster=cluster, replicas=replicas)

    async def get_taskhandler_status_local(self) -> TaskHandlerStatusLocal:
        data = await self._request("GET", "/configuration/taskhandler/status/local")
        return TaskHandlerStatusLocal(
            running=data.get("running", False),
            max_concurrent_tasks=data.get("max_concurrent_tasks", 0),
            currently_running_tasks=data.get("currently_running_tasks", 0),
            running_task_ids=data.get("running_task_ids", []),
            holder_id=data.get("holder_id", ""),
            total_tasks=data.get("total_tasks", 0),
            queued_tasks=data.get("queued_tasks", 0),
            active_tasks=data.get("active_tasks", 0),
        )

    async def set_concurrent_tasks_per_replica(self, max_tasks: int) -> SuccessResponse:
        data = await self._request(
            "POST",
            "/configuration/taskhandler/concurrent-per-replica",
            params={"max_tasks": max_tasks},
        )
        return SuccessResponse(message=data.get("message", ""))

    async def get_summary_worker_status(self) -> SummaryWorkerStatus:
        data = await self._request("GET", "/configuration/summary-worker/status")
        return SummaryWorkerStatus(
            running=data.get("running", False),
            uptime_seconds=data.get("uptime_seconds", 0.0),
            max_concurrent_summaries=data.get("max_concurrent_summaries", 0),
            processed_count=data.get("processed_count", 0),
            queued_count=data.get("queued_count", 0),
            pending_count=data.get("pending_count", 0),
            queue_size=data.get("queue_size", 0),
            error_count=data.get("error_count", 0),
            model_id=data.get("model_id", ""),
            translate_model_id=data.get("translate_model_id", ""),
            is_leader=data.get("is_leader", False),
        )

    async def set_compactor_model(self, model_name: str) -> SuccessResponse:
        data = await self._request(
            "POST",
            "/configuration/summary-worker/model",
            json_body={"model_name": model_name},
        )
        return SuccessResponse(message=data.get("message", ""))

    async def set_translate_model(self, model_name: str) -> SuccessResponse:
        data = await self._request(
            "POST",
            "/configuration/summary-worker/translate-model",
            json_body={"model_name": model_name},
        )
        return SuccessResponse(message=data.get("message", ""))

    async def get_token_worker_status(self) -> TokenWorkerStatus:
        data = await self._request("GET", "/configuration/token-worker/status")
        return TokenWorkerStatus(
            running=data.get("running", False),
            uptime_seconds=data.get("uptime_seconds", 0.0),
            processed_count=data.get("processed_count", 0),
            queue_size=data.get("queue_size", 0),
            error_count=data.get("error_count", 0),
            encoding=data.get("encoding", ""),
        )

    async def get_slots_status(self) -> SlotsStatus:
        data = await self._request("GET", "/configuration/slots/status")
        slots = [
            type(
                "SlotInfo",
                (),
                {
                    "id": s.get("id", ""),
                    "ip": s.get("ip", ""),
                    "status": s.get("status", ""),
                    "task_id": s.get("task_id"),
                    "last_activity": s.get("last_activity"),
                    "idle_seconds": s.get("idle_seconds"),
                },
            )()
            for s in data.get("slots", [])
        ]
        return SlotsStatus(
            enabled=data.get("enabled", False),
            total_slots=data.get("total_slots", 0),
            available_slots=data.get("available_slots", 0),
            slot_tools=data.get("slot_tools", []),
            acquire_timeout_seconds=data.get("acquire_timeout_seconds", 0),
            slots=slots,
        )

    async def get_subagents_status(self) -> SubagentsStatus:
        """Get subagent feature flag status."""
        data = await self._request("GET", "/configuration/subagents/status")
        return SubagentsStatus(subagents_enabled=data.get("subagents_enabled", False))

    async def set_subagents_enabled(self, enabled: bool) -> SuccessResponse:
        """Enable or disable subagent support."""
        data = await self._request(
            "POST", "/configuration/subagents", json_body={"enabled": enabled}
        )
        return SuccessResponse(message=data.get("message", ""))

    async def reload_services(self) -> ReloadServicesResult:
        """Trigger a reload of LLM backends, MCP servers, and slot manager."""
        data = await self._request("POST", "/configuration/reload")
        return ReloadServicesResult(
            timestamp=data.get("timestamp", ""),
            llm_backends=data.get("llm_backends", {}),
            mcp_servers=data.get("mcp_servers", {}),
            slot_manager=data.get("slot_manager", {}),
            next_scheduled_reload=data.get("next_scheduled_reload"),
        )

    async def get_reload_status(self) -> ReloadStatus:
        """Get the auto-reload schedule and last reload info."""
        data = await self._request("GET", "/configuration/reload/status")
        return ReloadStatus(
            enabled=data.get("enabled", False),
            interval_hours=data.get("interval_hours"),
            last_reload=data.get("last_reload"),
            next_scheduled_reload=data.get("next_scheduled_reload"),
        )

    # ==================================================================
    # 9. Auth / WebSocket status
    # ==================================================================

    async def get_auth_config(self) -> AuthConfig:
        data = await self._request("GET", "/auth/config")
        return AuthConfig(
            keycloak_enabled=data.get("keycloak_enabled", False),
            keycloak_url=data.get("keycloak_url"),
            keycloak_realm=data.get("keycloak_realm"),
            keycloak_client_id=data.get("keycloak_client_id"),
        )

    async def get_websocket_status(self) -> WebSocketStatus:
        data = await self._request("GET", "/websocket/status")
        clients = [
            WebSocketClientInfo(
                client_id=c.get("client_id", ""),
                connected_at=c.get("connected_at", ""),
            )
            for c in data.get("clients", [])
        ]
        return WebSocketStatus(
            connected_clients=data.get("connected_clients", 0),
            clients=clients,
            event_listener_healthy=data.get("event_listener_healthy", False),
            last_event_time=data.get("last_event_time"),
        )

    # ==================================================================
    # 10. SSE Status Stream
    # ==================================================================

    async def stream_task_status(
        self, task_id: str, timeout: float | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        """SSE stream for real-time task status updates.

        This is a lighter alternative to Socket.IO for status-only monitoring.
        Yields parsed JSON events as the task progresses. The stream ends
        when the task reaches a terminal state (``completed``, ``failed``,
        ``cancelled``).

        Args:
            task_id: Task to monitor.
            timeout:  Max seconds to keep the stream alive. ``None`` = no limit.

        Yields:
            Dicts with ``event_type`` (``status``, ``done``, ``deleted``)
            and ``data`` (the task status payload).
        """
        url = self._make_url(f"/task/{task_id}/status/stream")
        async with self._http.stream("GET", url, timeout=timeout) as response:
            event_type = ""
            data_lines: list[str] = []
            async for line in response.aiter_lines():
                line = line.strip()
                if line.startswith("event: "):
                    event_type = line[7:]
                elif line.startswith("data: "):
                    data_lines.append(line[6:])
                elif line == "":
                    # Empty line = end of event
                    if data_lines:
                        import json as _json

                        payload = _json.loads("".join(data_lines))
                        yield {"event_type": event_type or "status", "data": payload}
                    event_type = ""
                    data_lines = []


def _build_message(m: dict) -> "Message":
    """Build a Message dataclass from a raw API response dict."""
    attachments = [
        AttachmentMeta(
            id=a.get("id", ""),
            filename=a.get("filename", ""),
            mime_type=a.get("mime_type", ""),
            size=a.get("size", 0),
        )
        for a in m.get("attachments", []) or []
    ]
    tool_calls = None
    if m.get("tool_calls"):
        tool_calls = [
            ToolCall(
                id=tc.get("id", ""),
                type=tc.get("type", "function"),
                function=tc.get("function", {}),
            )
            for tc in m["tool_calls"]
        ]
    return Message(
        id=m.get("id", 0),
        role=m.get("role", ""),
        content=m.get("content", ""),
        created_at=m.get("created_at", ""),
        kind=m.get("kind"),
        name=m.get("name"),
        tool_calls=tool_calls,
        tool_call_id=m.get("tool_call_id"),
        reasoning=m.get("reasoning"),
        reasoning_summary=m.get("reasoning_summary"),
        tool_call_summary=m.get("tool_call_summary"),
        tool_output_summary=m.get("tool_output_summary"),
        summary_source=m.get("summary_source"),
        archived=m.get("archived", False),
        archived_reason=m.get("archived_reason"),
        attachments=attachments,
    )
