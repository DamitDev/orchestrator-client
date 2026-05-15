# orchestrator-client

Async and sync Python client for the [DAMIT AIOps Orchestrator](https://github.com/DamitDev/orchestrator) REST API and Socket.IO realtime events.

## Install

```bash
pip install orchestrator-client
```

Requires Python >= 3.12.

## Quick Start

```python
from orchestrator_client import Orchestrator

client = Orchestrator(base_url="http://localhost:8080")

# Create a task
task = client.create_task(
    workflow_id="proactive",
    goal_prompt="Analyze system logs for errors",
    max_iterations=50,
)
print(f"Created: {task.task_id}")

# Poll status
status = client.get_task_status(task.task_id)
print(f"Status: {status.status}, iteration {status.iteration}/{status.max_iterations}")

# List tasks
tasks = client.list_tasks(workflow_id="proactive", limit=10)
for t in tasks.tasks:
    print(f"  {t.id}: {t.status}")

# Cancel
client.cancel_task(task.task_id)

client.close()
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `ORCHESTRATOR_URL` | `http://localhost:8080` | Base URL (supports subpath) |
| `ORCHESTRATOR_API_KEY` | — | Optional bearer token |
| `ORCHESTRATOR_TIMEOUT` | `30.0` | HTTP timeout (seconds) |
| `ORCHESTRATOR_MAX_RETRIES` | `3` | Max retry attempts |

## Async Variant

For use inside async code (e.g. FastAPI, asyncio scripts):

```python
from orchestrator_client import OrchestratorAsync

async with OrchestratorAsync() as client:
    status = await client.get_task_status("task-abc123")
```

## Exceptions

All inherit from `OrchestratorError` and carry `status_code` and `error_code`:

| Exception | Meaning |
|---|---|
| `OrchestratorConnectionError` | Network / DNS / timeout |
| `OrchestratorAuthError` | 401/403 |
| `OrchestratorNotFoundError` | 404 |
| `OrchestratorAPIError` | 400/500 with error code |
| `OrchestratorConfigError` | Bad env vars / missing config |

## Documentation

Detailed docs with full method listings and examples:

- [REST API client](docs/client.md) — all endpoints, workflow interactions, configuration
- [Socket.IO realtime](docs/realtime.md) — event types, room subscriptions, streaming
- [SSE status stream](docs/sse.md) — lightweight status-only monitoring

## Testing

```bash
pip install -e ".[dev]"
pytest
```

## License

Apache 2.0
