# Socket.IO Realtime Events

The `RealtimeClient` connects to the orchestrator's Socket.IO endpoint (same host:port as the REST API, path `/socket.io`) and uses a room-based subscription model.

## Connection

```python
from orchestrator_client import RealtimeClient

async with RealtimeClient(
    base_url="http://localhost:8080",
    client_id="my-app",  # optional identifier
) as rt:
    await rt.subscribe_task("task-abc123")
    ...
```

After connecting, you **must** join at least one room to receive events.

## Room Subscriptions

```python
# Room naming convention
"all"                    — Receive every event
"event:{event_type}"     — A specific event type
"task:{task_id}"         — All events for a specific task

# Subscribe
await rt.join_rooms(["all"])
await rt.join_rooms(["event:task_status_changed", "event:message_added"])
await rt.join_rooms(["task:task-abc123"])

# Convenience shortcuts
await rt.subscribe_all()
await rt.subscribe_task("task-abc123")
await rt.subscribe_events("task_status_changed", "message_added")

# Unsubscribe
await rt.leave_rooms(["event:message_added"])
await rt.unsubscribe_task("task-abc123")
await rt.unsubscribe_events("message_added")
```

## Handling Events

```python
# Register a handler for a specific event type
@rt.on("task_status_changed")
async def handle_status(event):
    print(f"{event['task_id']}: {event['old_status']} -> {event['new_status']}")

@rt.on("message_added")
async def handle_message(event):
    print(f"[{event['role']}] {event['content'][:100]}")
    if event.get("tool_calls"):
        print(f"  {len(event['tool_calls'])} tool call(s)")
    for att in event.get("attachments", []):
        print(f"  attachment: {att['filename']} ({att['mime_type']})")

# Remove handlers
rt.off("task_status_changed")               # remove all for type
rt.off("message_added", handle_message)     # remove specific handler
```

The server wraps all events in a `message` Socket.IO event with payload
`{"type": "message", "event": {...}}`. The client auto-unwraps this
and dispatches the inner `event` dict to matching handlers.

## Event Types

### Task Lifecycle

| Event | Key Fields |
|---|---|
| `task_created` | `task_id`, `workflow_id`, `goal_prompt`, `max_iterations`, `reasoning_effort`, `parent_task_id` (subagent), `subagent_description` |
| `task_status_changed` | `task_id`, `old_status`, `new_status` |
| `task_iteration_changed` | `task_id`, `new_iteration`, `max_iterations` |
| `task_deleted` | `task_id` |
| `task_result_updated` | `task_id`, `result` |
| `task_insight_updated` | `task_id`, `insight`, `insight_localized`, `message_index` |

### Conversation

| Event | Key Fields |
|---|---|
| `message_added` | `task_id`, `message_id`, `message_index`, `role`, `content`, `tool_calls`, `reasoning`, `attachments` |
| `message_streaming` | `task_id`, `message_id`, `content_delta`, `reasoning_delta`, `is_complete`, `stream_index` |
| `message_summary_generated` | `task_id`, `message_id`, `summary_id`, `reasoning_summary`, `tool_call_summary`, `tool_output_summary` |
| `message_updated` | `task_id`, `message_id`, `content`, `reasoning` |
| `message_deleted` | `task_id`, `message_id` |
| `iteration_reminder_added` | `task_id`, `message` |

### Human Interaction

| Event | Key Fields |
|---|---|
| `approval_requested` | `task_id`, `tool_name`, `reason` |
| `approval_provided` | `task_id`, `approved` |
| `help_requested` | `task_id`, `help_message` |
| `help_provided` | `task_id`, `response` |
| `user_message_added` | `task_id`, `message` |

### System

| Event | Key Fields |
|---|---|
| `llm_backend_changed` | — |
| `mcp_server_changed` | — |
| `model_config_changed` | — |
| `task_handler_status_changed` | — |
| `summary_worker_status` | `running`, `processed_count`, `queue_size` |
| `token_worker_status` | `running`, `processed_count` |
| `token_count_updated` | `task_id`, `message_id`, `message_tokens`, `total_tokens` |
| `messages_archived` | `task_id`, `count` |

### Mio (Self-Managed)

| Event | Key Fields |
|---|---|
| `mio_memory_created` | `task_id`, `memory_id`, `title`, `content`, `tags` |
| `mio_memory_updated` | `task_id`, `memory_id`, `content`, `tags` |
| `mio_memory_deleted` | `task_id`, `memory_id` |
| `task_workflow_data_changed` | `task_id`, `workflow_data` |

### Error

| Event | Key Fields |
|---|---|
| `error_event_recorded` | `error_id`, `severity`, `source`, `task_id`, `workflow_id`, `error_code`, `exception_type`, `message` |

_Note: This event carries a compact summary only. Full traceback and context
must be fetched via `GET /errors/{error_id}`._

## Streaming Messages

Message streaming uses delta events. Accumulate deltas client-side
until `is_complete: true`:

```python
streaming = {}

@rt.on("message_streaming")
async def on_stream(event):
    msg_id = event["message_id"]
    if msg_id not in streaming:
        streaming[msg_id] = {"content": "", "reasoning": ""}
    streaming[msg_id]["content"] += event.get("content_delta", "")
    streaming[msg_id]["reasoning"] += event.get("reasoning_delta", "")
    if event.get("is_complete"):
        final = streaming.pop(msg_id)
        print(f"Stream complete: {final['content']}")

@rt.on("message_added")
async def on_message(event):
    # Final message (after streaming ends)
    print(f"[{event['role']}] {event['content']}")
```

## Ping/Pong

```python
await rt.ping()  # server responds with "pong" event
```

## Connection State

```python
print(rt.connected)  # bool
```

## Complete Example

```python
import asyncio
from orchestrator_client import RealtimeClient

async def monitor_task(task_id: str):
    async with RealtimeClient("http://localhost:8080") as rt:
        await rt.subscribe_task(task_id)

        @rt.on("task_status_changed")
        async def on_status(event):
            print(f"[{event['new_status']}] {event['task_id']}")

        @rt.on("message_added")
        async def on_msg(event):
            if event["role"] == "assistant":
                print(f"  Agent: {event['content'][:80]}...")

        @rt.on("error_event_recorded")
        async def on_error(event):
            print(f"  ERROR ({event['severity']}): {event['message']}")

        await rt.wait()  # block until disconnected

asyncio.run(monitor_task("task-abc123"))
```
