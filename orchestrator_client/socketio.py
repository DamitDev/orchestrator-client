"""RealtimeClient — async Socket.IO wrapper for orchestrator realtime events.

Connects to the orchestrator's Socket.IO endpoint (same host:port as the
REST API, path ``/socket.io``) and provides a typed subscription layer
using the server's room-based event system.

Usage::

    from orchestrator_client import RealtimeClient

    async with RealtimeClient("http://localhost:8080") as rt:
        await rt.subscribe_task("task-abc123")

        @rt.on("task_status_changed")
        async def handle_status(event: dict):
            print(event["new_status"])

        # Keep connection alive
        await rt.wait()
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

import socketio

logger = logging.getLogger(__name__)

# All known event types from the server for reference
EVENT_TASK_CREATED = "task_created"
EVENT_TASK_STATUS_CHANGED = "task_status_changed"
EVENT_TASK_ITERATION_CHANGED = "task_iteration_changed"
EVENT_TASK_DELETED = "task_deleted"
EVENT_TASK_BULK_DELETED = "task_bulk_deleted"
EVENT_TASK_RESULT_UPDATED = "task_result_updated"
EVENT_TASK_INSIGHT_UPDATED = "task_insight_updated"
EVENT_MESSAGE_ADDED = "message_added"
EVENT_MESSAGE_STREAMING = "message_streaming"
EVENT_MESSAGE_SUMMARY_GENERATED = "message_summary_generated"
EVENT_MESSAGE_TRANSLATION_READY = "message_translation_ready"
EVENT_MESSAGE_UPDATED = "message_updated"
EVENT_MESSAGE_DELETED = "message_deleted"
EVENT_APPROVAL_REQUESTED = "approval_requested"
EVENT_APPROVAL_PROVIDED = "approval_provided"
EVENT_HELP_REQUESTED = "help_requested"
EVENT_HELP_PROVIDED = "help_provided"
EVENT_USER_MESSAGE_ADDED = "user_message_added"
EVENT_ITERATION_REMINDER_ADDED = "iteration_reminder_added"
EVENT_MIO_MEMORY_CREATED = "mio_memory_created"
EVENT_MIO_MEMORY_UPDATED = "mio_memory_updated"
EVENT_MIO_MEMORY_DELETED = "mio_memory_deleted"
EVENT_TASK_WORKFLOW_DATA_CHANGED = "task_workflow_data_changed"
EVENT_LLM_BACKEND_CHANGED = "llm_backend_changed"
EVENT_MCP_SERVER_CHANGED = "mcp_server_changed"
EVENT_MODEL_CONFIG_CHANGED = "model_config_changed"
EVENT_TASK_HANDLER_STATUS_CHANGED = "task_handler_status_changed"
EVENT_SUMMARY_WORKER_STATUS = "summary_worker_status"
EVENT_TOKEN_WORKER_STATUS = "token_worker_status"
EVENT_TOKEN_COUNT_UPDATED = "token_count_updated"
EVENT_MESSAGES_ARCHIVED = "messages_archived"
EVENT_ERROR_EVENT_RECORDED = "error_event_recorded"
EVENT_SUBPROCESS_STARTED = "subprocess_started"
EVENT_SUBPROCESS_COMPLETED = "subprocess_completed"
EVENT_SUBPROCESS_FAILED = "subprocess_failed"


class RealtimeClient:
    """Async Socket.IO client for orchestrator realtime events.

    Args:
        base_url:  Base URL of the orchestrator (e.g. ``http://localhost:8080``).
                   The Socket.IO path ``/socket.io`` is appended automatically.
        client_id: Optional client identifier sent as query parameter.

    The server wraps all events in the ``message`` Socket.IO event with a
    payload ``{"type": "message", "event": {...}}``. This client
    automatically unwraps the envelope and dispatches to handlers
    registered via ``on(event_type, handler)``.
    """

    def __init__(
        self,
        base_url: str,
        *,
        client_id: str = "orchestrator-client",
        locale: str | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._client_id = client_id
        self._locale = locale
        self._sio = socketio.AsyncClient()
        self._handlers: dict[str, list[Callable[[dict[str, Any]], Awaitable[None]]]] = {}
        self._connected = False

        # Register the raw message handler
        @self._sio.on("message")
        async def _on_message(payload: Any) -> None:
            await self._dispatch(payload)

        @self._sio.on("connect")
        async def _on_connect() -> None:
            self._connected = True
            logger.info("RealtimeClient connected to %s", self._base_url)

        @self._sio.on("disconnect")
        async def _on_disconnect() -> None:
            self._connected = False
            logger.info("RealtimeClient disconnected from %s", self._base_url)

        @self._sio.on("connection_established")
        async def _on_welcome(data: Any) -> None:
            logger.debug("RealtimeClient welcome: %s", data)

        @self._sio.on("rooms_updated")
        async def _on_rooms_updated(data: Any) -> None:
            logger.debug("RealtimeClient rooms updated: %s", data)

        @self._sio.on("pong")
        async def _on_pong(data: Any) -> None:
            logger.debug("RealtimeClient pong: %s", data)

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        """Establish the Socket.IO connection.

        After connecting, you must join at least one room via
        ``join_rooms()`` or the convenience methods
        (``subscribe_task``, ``subscribe_events``) to start
        receiving events.
        """
        query: dict[str, str] = {"client_id": self._client_id}
        if self._locale:
            query["locale"] = self._locale

        await self._sio.connect(
            self._base_url,
            socketio_path="/socket.io",
            query=query,
            wait_timeout=10,
        )

    async def disconnect(self) -> None:
        """Close the Socket.IO connection."""
        await self._sio.disconnect()
        self._connected = False

    async def __aenter__(self) -> "RealtimeClient":
        await self.connect()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.disconnect()

    async def join_rooms(self, rooms: list[str]) -> None:
        """Subscribe to one or more rooms.

        Room naming convention::

            "all"                    — Receive all events
            "event:{event_type}"    — Specific event type (e.g. ``event:task_status_changed``)
            "task:{task_id}"         — All events for a specific task
            "locale:{locale}"        — Locale-scoped translation-ready events

        The server responds with a ``rooms_updated`` event confirming
        the subscription.
        """
        await self._sio.emit("join", {"rooms": rooms})

    async def leave_rooms(self, rooms: list[str]) -> None:
        """Unsubscribe from one or more rooms."""
        await self._sio.emit("leave", {"rooms": rooms})

    async def subscribe_task(self, task_id: str) -> None:
        """Shortcut: subscribe to all events for a specific task."""
        await self.join_rooms([f"task:{task_id}"])

    async def unsubscribe_task(self, task_id: str) -> None:
        """Shortcut: unsubscribe from a specific task."""
        await self.leave_rooms([f"task:{task_id}"])

    async def subscribe_events(self, *event_types: str) -> None:
        """Shortcut: subscribe to specific event types.

        Example::

            await rt.subscribe_events("task_status_changed", "message_added")
        """
        rooms = [f"event:{t}" for t in event_types]
        await self.join_rooms(rooms)

    async def unsubscribe_events(self, *event_types: str) -> None:
        """Shortcut: unsubscribe from specific event types."""
        rooms = [f"event:{t}" for t in event_types]
        await self.leave_rooms(rooms)

    async def subscribe_all(self) -> None:
        """Shortcut: subscribe to all events."""
        await self.join_rooms(["all"])

    async def subscribe_locale(self, locale: str) -> None:
        """Shortcut: subscribe to translation-ready events for a locale."""
        await self.join_rooms([f"locale:{locale}"])

    async def unsubscribe_locale(self, locale: str) -> None:
        """Shortcut: unsubscribe from translation-ready events for a locale."""
        await self.leave_rooms([f"locale:{locale}"])

    async def ping(self) -> None:
        """Send a ping to verify the connection is alive.

        The server responds with a ``pong`` event.
        """
        await self._sio.emit("ping", {})

    def on(self, event_type: str, handler: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        """Register a handler for a specific event type.

        The handler receives the decoded event dict (the contents of the
        ``event`` field from the server's ``message`` payload).

        Example::

            @rt.on("task_status_changed")
            async def handle(event):
                print(f"Task {event['task_id']}: {event['old_status']} -> {event['new_status']}")
        """
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def off(self, event_type: str, handler: Callable | None = None) -> None:
        """Remove a handler for a specific event type.

        If ``handler`` is ``None``, all handlers for that type are removed.
        """
        if event_type not in self._handlers:
            return
        if handler is None:
            del self._handlers[event_type]
        else:
            self._handlers[event_type] = [h for h in self._handlers[event_type] if h is not handler]
            if not self._handlers[event_type]:
                del self._handlers[event_type]

    async def wait(self) -> None:
        """Block until the connection is closed.

        Useful for long-running monitoring scripts that keep the client
        alive and process incoming events.
        """
        await self._sio.wait()

    # ------------------------------------------------------------------
    # Internal dispatch
    # ------------------------------------------------------------------

    async def _dispatch(self, payload: Any) -> None:
        """Unwrap the server's ``message`` event envelope and dispatch."""
        if not isinstance(payload, dict):
            return

        # Handle packed ``message`` event: {"type": "message", "event": {...}}
        event_data = payload.get("event", payload)
        if not isinstance(event_data, dict):
            return

        event_type = event_data.get("event_type")
        if not event_type:
            return

        handlers = self._handlers.get(event_type, [])
        for handler in handlers:
            try:
                await handler(event_data)
            except Exception:
                logger.exception("Handler error for event %s", event_type)
