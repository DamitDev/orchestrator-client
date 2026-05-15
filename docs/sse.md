# SSE Status Stream

For lightweight status-only monitoring without a Socket.IO dependency,
the REST client provides an SSE (Server-Sent Events) stream.

This is useful for simple polling scenarios where you only need
status updates, not the full realtime conversation stream.

## Sync Usage

```python
from orchestrator_client import Orchestrator

with Orchestrator() as client:
    events = client.stream_task_status("task-abc123", timeout=30)

    for event in events:
        if event["event_type"] == "status":
            data = event["data"]
            print(
                f"Iteration {data['iteration']}/{data['max_iterations']}: "
                f"{data['status']}"
            )
        elif event["event_type"] == "done":
            print("Task reached terminal state")
            break
        elif event["event_type"] == "deleted":
            print("Task was deleted")
            break
```

The sync version collects all events into a list (the stream runs
to completion and returns when done).

## Async Usage

```python
from orchestrator_client import OrchestratorAsync

async with OrchestratorAsync() as client:
    async for event in client.stream_task_status("task-abc123"):
        if event["event_type"] == "status":
            data = event["data"]
            print(f"Iter {data['iteration']}: {data['status']}")
        elif event["event_type"] == "done":
            print("Task completed")
            break
```

The async version is a true streaming generator — events arrive in
real time as the SSE connection pushes them.

## Event Types

| `event_type` | Meaning |
|---|---|
| `status` | Current task status snapshot (same fields as `get_task_status`) |
| `done` | Task reached a terminal state (completed, failed, cancelled) |
| `deleted` | Task was removed |

## When to Use SSE vs Socket.IO

| Criteria | SSE | Socket.IO |
|---|---|---|
| Dependencies | None (built into httpx) | Requires `python-socketio` |
| Event types | Only status lifecycle | All events (conversation, streaming) |
| Bi-directional | No | Yes (ping/pong, rooms) |
| Complexity | Minimal | Full subscription model |

Use SSE for simple monitoring dashboards or CI pipelines that only
need to know when a task finishes. Use Socket.IO for interactive
UIs that need conversation streaming and human-interaction events.
