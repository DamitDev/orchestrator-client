# orchestrator-client

Async Python client for the [DAMIT AIOps Orchestrator](https://github.com/DamitDev/damit-aiops) REST API and Socket.IO realtime events.

## Install

```bash
pip install orchestrator-client
```

Requires Python >= 3.12.

## Quick Start

```python
import asyncio
from orchestrator_client import OrchestratorClient, RealtimeClient, OrchestratorError


async def main():
    # --- REST API ---
    async with OrchestratorClient(
        base_url="http://localhost:8080",
        api_key="your-bearer-token",  # optional
    ) as client:
        # Create a task
        result = await client.create_task(
            workflow_id="proactive",
            goal_prompt="Analyze the application logs for errors",
            max_iterations=50,
            reasoning_effort="high",
        )
        task_id = result.task_id
        print(f"Created task: {task_id}")

        # Poll for status
        status = await client.get_task_status(task_id)
        print(f"Status: {status.status}, iteration: {status.iteration}")

        # List tasks
        tasks = await client.list_tasks(workflow_id="proactive", limit=10)
        for t in tasks.tasks:
            print(f"  {t.id}: {t.status}")

        # Get conversation
        conv = await client.get_task_conversation(task_id)
        for msg in conv.conversation:
            print(f"  [{msg.role}] {msg.content[:80]}...")

        # Cancel a task
        await client.cancel_task(task_id)

    # --- Realtime Events ---
    async with RealtimeClient("http://localhost:8080") as rt:
        # Subscribe to a specific task
        await rt.subscribe_task("task-abc123")

        # Or subscribe to event types
        await rt.subscribe_events("task_status_changed", "message_added")

        # Register handlers
        @rt.on("task_status_changed")
        async def on_status(event):
            print(f"{event['task_id']}: {event['old_status']} -> {event['new_status']}")

        @rt.on("message_added")
        async def on_message(event):
            print(f"[{event['role']}] {event['content'][:80]}...")

        # Keep alive for 30 seconds
        await asyncio.sleep(30)


asyncio.run(main())
```

## Configuration via Environment Variables

| Variable | Default | Description |
|---|---|---|
| `ORCHESTRATOR_URL` | `http://localhost:8080` | Base URL (supports subpath, e.g. `https://oapi.local/uat`) |
| `ORCHESTRATOR_API_KEY` | *(none)* | Optional bearer token |
| `ORCHESTRATOR_TIMEOUT` | `30.0` | HTTP timeout in seconds |
| `ORCHESTRATOR_MAX_RETRIES` | `3` | Max retry attempts on transient failures |

```python
from orchestrator_client import OrchestratorClient, load_config

config = load_config()
async with OrchestratorClient(
    base_url=config.base_url,
    api_key=config.api_key,
    timeout=config.timeout,
    max_retries=config.max_retries,
) as client:
    ...
```

## API Surface

### Task Management

| Method | Endpoint |
|---|---|
| `list_tasks()` | `GET /tasks` |
| `create_task()` | `POST /task/create` |
| `get_task_status()` | `GET /task/status` |
| `get_task_conversation()` | `GET /task/conversation` |
| `get_archived_message_content()` | `GET /task/message/archived-content` |
| `get_task_compactions()` | `GET /task/compactions` |
| `get_task_journal()` | `GET /task/journal` |
| `cancel_task()` | `POST /task/cancel` |
| `delete_task()` | `POST /task/delete` |
| `delete_tasks()` | `POST /task/delete/multiple` |

### Attachments

| Method | Endpoint |
|---|---|
| `upload_attachment()` | `POST /attachment` (multipart) |
| `download_attachment()` | `GET /attachment/{id}` |

### Workflow Interactions

Each workflow type has specific methods:

- **Interactive**: `send_interactive_message()`, `mark_interactive_complete()`, `mark_interactive_failed()`, `approve_interactive_action()`
- **Proactive**: `send_proactive_guide()`, `respond_proactive_help()`, `approve_proactive_action()`
- **Ticket**: `send_ticket_guide()`, `respond_ticket_help()`, `approve_ticket_action()`, `wake_ticket()`
- **Matrix**: `send_matrix_message()`, `mark_matrix_complete()`, `mark_matrix_failed()`, `approve_matrix_action()`, `get_matrix_conversation()`
- **VSA**: `create_vsa_task()`, `send_vsa_message()`, `rename_vsa_task()`, `regenerate_vsa_title()`, `mark_vsa_complete()`, `mark_vsa_failed()`, `stop_vsa()`, `delete_vsa()`, `list_vsa_tasks()`, `search_vsa_tasks()`, `delete_vsa_tasks_bulk()`
- **Self-Managed (Mio)**: `send_mio_message()`, `approve_mio_action()`, `wake_mio()`, `send_mio_user_away()`, `mark_mio_complete()`, `mark_mio_failed()`, `archive_mio()`, `get_mio_context()`

### Tools & Configuration

`list_tools()`, `get_system_status()`, `update_settings()`, `get_configuration_status()`, `set_agent_model()`, `set_orchestrator_model()`, LLM backend CRUD, MCP server CRUD, task handler status, summary worker status, token worker status, slot status.

### Debug

`get_workflow_states()`, `update_task_models()`, `update_task_iteration()`, `update_task_workflow_data()`, `delete_message()`, `delete_messages()`, `update_message()`, `reset_matrix_to_phase()`

### Error Events

`list_errors()`, `get_error_detail()`, `get_error_stats()`, `count_errors()`, `purge_errors()` (DEV only)

### Health & Metrics

`health()`, `health_detailed()`, `ready()`, `health_leader()`, `get_metrics()`

### Auth & WebSocket status

`get_auth_config()`, `get_websocket_status()`

## Socket.IO Realtime Events

The `RealtimeClient` uses room-based subscriptions:

```python
# Room naming
"all"                    — Receive all events
"event:{event_type}"     — Specific event type
"task:{task_id}"         — All events for a specific task
```

### All Event Types

**Task Lifecycle**: `task_created`, `task_status_changed`, `task_iteration_changed`, `task_deleted`, `task_result_updated`, `task_insight_updated`

**Conversation**: `message_added`, `message_streaming`, `message_summary_generated`, `message_updated`, `message_deleted`, `iteration_reminder_added`

**Human Interaction**: `approval_requested`, `approval_provided`, `help_requested`, `help_provided`, `user_message_added`

**System**: `llm_backend_changed`, `mcp_server_changed`, `model_config_changed`, `task_handler_status_changed`, `summary_worker_status`, `token_worker_status`, `token_count_updated`, `messages_archived`

**Mio**: `mio_memory_created`, `mio_memory_updated`, `mio_memory_deleted`, `task_workflow_data_changed`

**Error**: `error_event_recorded`

## Exceptions

All exceptions inherit from `OrchestratorError` and carry `status_code` and `error_code`:

| Exception | Meaning |
|---|---|
| `OrchestratorConnectionError` | Network / DNS / timeout |
| `OrchestratorAuthError` | 401/403 |
| `OrchestratorNotFoundError` | 404 — also carries `.resource_type` and `.resource_id` |
| `OrchestratorAPIError` | 400/500 with `error_code` and `details` |
| `OrchestratorConfigError` | Bad env vars / missing config |

## SSE Status Stream

For lightweight status-only monitoring without Socket.IO:

```python
async for event in client.stream_task_status("task-abc123"):
    if event["event_type"] == "status":
        data = event["data"]
        print(f"Iteration {data['iteration']}/{data['max_iterations']}: {data['status']}")
    elif event["event_type"] == "done":
        print("Task reached terminal state")
        break
```

## Testing

```bash
pip install -e ".[dev]"
pytest
```

## License

Apache 2.0
