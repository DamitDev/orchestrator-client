# REST API Client

The `orchestrator-client` package provides two client classes for the Orchestrator REST API:

- **`Orchestrator`** (sync) — primary interface, no asyncio needed
- **`OrchestratorAsync`** (async) — for use inside async code

Both expose the same methods with the same signatures. The sync variant wraps the async client with a persistent internal event loop.

## Creating a Client

```python
from orchestrator_client import Orchestrator, OrchestratorAsync, load_config

# Using env vars
config = load_config()
client = Orchestrator(
    base_url=config.base_url,
    api_key=config.api_key,
    timeout=config.timeout,
    max_retries=config.max_retries,
)

# Async
async with OrchestratorAsync(base_url="http://localhost:8080") as client:
    ...
```

Both support context manager syntax. The sync client's `close()` is called automatically on `__exit__`.

---

## Task Management

### List Tasks

```python
result = client.list_tasks(
    page=1,
    limit=25,
    order_by="updated_at",      # "created_at" or "updated_at"
    order_direction="desc",     # "asc" or "desc"
    workflow_id=None,           # filter: "proactive", "matrix", "ticket", etc.
)

for task in result.tasks:
    print(task.id, task.status, task.iteration, task.workflow_id)

print(result.pagination.total_items, result.pagination.total_pages)
```

Response: `TaskListResult(tasks: list[TaskSummary], pagination: Pagination)`

### Create Task

```python
task = client.create_task(
    workflow_id="proactive",
    goal_prompt="Analyze the application logs",
    max_iterations=50,
    reasoning_effort="high",           # "low", "medium", "high"
    system_prompt=None,                # custom system prompt override
    developer_prompt=None,             # custom developer prompt override
    ticket_id=None,                    # for ticket workflow
    agent_model_id=None,               # override agent model
    orchestrator_model_id=None,        # override orchestrator model
    available_tools=None,              # None = all tools, [] = no tools
    attachment_ids=None,               # max 5, from upload_attachment()
)

print(task.task_id)  # e.g. "task-abc123"
print(task.status)   # "queued"
```

Workflow types: `interactive`, `proactive`, `ticket`, `matrix`, `self_managed`, `subagent`, `vsa`.

### Get Task Status

```python
status = client.get_task_status("task-abc123")
print(status.status)            # "queued", "in_progress", "completed", "failed", "cancelled"
print(status.iteration)         # current iteration number
print(status.max_iterations)    # max before auto-fail
print(status.insight)           # current reasoning headline
print(status.subtask_ids)       # sub-agent task IDs spawned by this task
print(status.workflow_data)     # workflow-specific data dict
```

### Get Conversation

```python
conv = client.get_task_conversation(
    "task-abc123",
    include_summaries=True,
    exclude_archived=False,
)

for msg in conv.conversation:
    print(f"[{msg.id}] {msg.role}: {msg.content[:100]}")
    if msg.tool_calls:
        for tc in msg.tool_calls:
            print(f"  -> {tc.function['name']}({tc.function['arguments']})")
    if msg.reasoning_summary:
        print(f"  reasoning: {msg.reasoning_summary[:80]}")
```

Each message has: `id`, `role`, `content`, `kind`, `name`, `tool_calls`, `reasoning`, `reasoning_summary`, `tool_call_summary`, `tool_output_summary`, `attachments`, `archived`, `archived_reason`, `created_at`.

### Archived Content

```python
archived = client.get_archived_message_content("task-abc123", message_id=42)
print(archived.content)  # full original tool output
```

### Compactions & Journal

```python
# Compaction events
events = client.get_task_compactions("task-abc123")
for e in events:
    print(e.triggered_at, e.pre_token_count, "->", e.post_token_count)

# Task journal
journal = client.get_task_journal("task-abc123")
if journal.exists:
    print(journal.content)
```

### Cancel & Delete

```python
# Cancel a running task
client.cancel_task("task-abc123")

# Delete a single task (must be in terminal state)
result = client.delete_task("task-abc123")
print(result.deleted_tasks, result.failed_tasks)

# Delete multiple
result = client.delete_tasks(["task-abc", "task-def"])
```

---

## Attachments

Attachments use a two-step flow: upload first (returns an ID), then pass the ID to a task create or message call.

```python
# Upload
att = client.upload_attachment("/path/to/screenshot.png")
print(att.id, att.filename, att.mime_type, att.size)

# Download
data = client.download_attachment(att.id)                   # returns bytes
client.download_attachment(att.id, outfile="/tmp/output")   # also writes to file

# Use in task creation
task = client.create_task(
    workflow_id="interactive",
    goal_prompt="What do you see in this image?",
    attachment_ids=[att.id],  # max 5
)
```

---

## Workflow Interactions

### Interactive

```python
client.send_interactive_message("task-abc", "Check line 42")
client.mark_interactive_complete("task-abc")
client.mark_interactive_failed("task-abc")
client.approve_interactive_action("task-abc", approved=True)
```

### Proactive

```python
client.send_proactive_guide("task-abc", "Focus on the caching layer")
client.respond_proactive_help("task-abc", "Check the connection pool")
client.approve_proactive_action("task-abc", approved=False)
```

### Ticket (inherits Proactive + wake)

```python
client.send_ticket_guide("task-abc", "Prioritize the login issue")
client.respond_ticket_help("task-abc", "Check the auth service logs")
client.approve_ticket_action("task-abc", approved=True)
client.wake_ticket("task-abc")  # wake from sleeping state
```

### Matrix

```python
client.send_matrix_message("task-abc", "Phase 2 needs attention")
client.mark_matrix_complete("task-abc")
client.mark_matrix_failed("task-abc")
client.approve_matrix_action("task-abc", approved=True)
conv = client.get_matrix_conversation("task-abc", phase=2)
```

### VSA (user-scoped chat)

```python
task = client.create_vsa_task("user_123", "How do I set up VPN?", title="VPN help")
client.send_vsa_message(task.task_id, "Thanks, one more question")
client.rename_vsa_task(task.task_id, "Updated title")
client.regenerate_vsa_title(task.task_id)
client.mark_vsa_complete(task.task_id)
client.mark_vsa_failed(task.task_id)
client.stop_vsa(task.task_id)
client.delete_vsa(task.task_id)

# List and search
tasks = client.list_vsa_tasks("user_123", limit=50, offset=0)
results = client.search_vsa_tasks("user_123", "VPN", limit=20)
client.delete_vsa_tasks_bulk(["task-1", "task-2"])
```

### Self-Managed (Mio)

```python
client.send_mio_message("task-mio-1", "Hello Mio!")
client.approve_mio_action("task-mio-1", approved=True, feedback="Proceed")
client.wake_mio("task-mio-1")
client.send_mio_user_away("task-mio-1")
client.mark_mio_complete("task-mio-1")
client.mark_mio_failed("task-mio-1")
client.archive_mio("task-mio-1")

ctx = client.get_mio_context("task-mio-1")
print(ctx.current_tokens, ctx.context_limit, ctx.usage_percentage)
```

---

## Tools

```python
tools = client.list_tools()
for t in tools.tools:
    print(t.name, t.server)
print(f"Total: {tools.total_tools}, servers: {tools.servers}")
```

---

## Configuration

### System Settings

```python
status = client.get_system_status()
print(status.is_configured, status.missing_fields, status.settings.agent_model_id)

# Partial update
updated = client.update_settings(
    agent_model_id="gpt-oss:20b",
    max_concurrent_tasks_per_replica=5,
)
print(updated.version)  # incremented on each write
```

### Full Config Status

```python
config = client.get_configuration_status()
print(config.agent_model, config.orchestrator_model)
for backend in config.llmbackends:
    print(backend.host, backend.models)
for server in config.mcpservers:
    print(server.name, server.tools)
```

### Model Management

```python
client.set_agent_model("gpt-oss:20b")
client.set_orchestrator_model("gpt-oss:120b")
```

### LLM Backends

```python
status = client.get_llm_backend_status()
client.add_llm_backend("http://localhost:11434/v1", api_key="ollama")
client.remove_llm_backend("http://localhost:11434/v1")
```

### MCP Servers

```python
status = client.get_mcp_server_status()
client.add_mcp_server("http://localhost:8001/", api_key="key")
client.remove_mcp_server("http://localhost:8001/")
```

### Task Handler

```python
# Cluster-wide status
cluster = client.get_taskhandler_status()
print(cluster.cluster.currently_running_tasks, cluster.cluster.queued_tasks)
for replica in cluster.replicas:
    print(replica.holder_id, replica.currently_running_tasks)

# Local pod status
local = client.get_taskhandler_status_local()
print(local.holder_id, local.running, local.running_task_ids)

# Set concurrency (1-200)
client.set_concurrent_tasks_per_replica(5)
```

### Workers

```python
# Summary worker (compactor)
sw = client.get_summary_worker_status()
print(sw.running, sw.processed_count, sw.queue_size)
client.set_compactor_model("qwen3.5:2b")
client.set_translate_model("gpt-oss:20b")

# Token worker
tw = client.get_token_worker_status()
print(tw.running, tw.processed_count, tw.encoding)
```

### Slots

```python
slots = client.get_slots_status()
print(slots.enabled, slots.available_slots, "/", slots.total_slots)
for slot in slots.slots:
    print(slot.id, slot.status, slot.task_id)
```

---

## Debug Endpoints

```python
# Workflow states
states = client.get_workflow_states()
print(states.valid_states["proactive"])

# Override models on a running task
client.update_task_models("task-abc", agent_model_id="gpt-4o-mini")

# Override iteration
client.update_task_iteration("task-abc", iteration=3, max_iterations=50)

# Patch workflow_data
client.update_task_workflow_data("task-abc", {"phase": 2, "aspect_goal": "..."})

# Message manipulation
client.delete_message("task-abc", message_id=42)
client.delete_messages("task-abc", [42, 43])
client.update_message("task-abc", 42, content="New content...")

# Matrix phase reset
client.reset_matrix_to_phase("task-abc", phase=2)
```

---

## Error Events

```python
# List (paginated, filterable)
errors = client.list_errors(
    page=1, limit=50,
    severity=["error", "critical"],
    task_id="task-abc123",
    since="2026-04-22T10:00:00Z",
)
for item in errors.get("items", []):
    print(item["severity"], item["error_code"], item["message"])

# Full detail (includes traceback + context)
detail = client.get_error_detail("err-uuid-here")
print(detail.traceback, detail.context)

# Stats
stats = client.get_error_stats(since="2026-04-22T10:00:00Z", top_n=10)
print(stats.total, stats.by_severity)

# Count (fast)
count = client.count_errors("2026-04-22T10:00:00Z", severity="critical")
print(count.count)

# Purge (DEV mode only)
client.purge_errors()
```

---

## Health & Metrics

```python
# Quick liveness
h = client.health()
print(h.status, h.version)

# Detailed (redis, event listener, token worker)
detail = client.health_detailed()
print(detail.components)

# Readiness (for K8s probes)
ready = client.ready()
print(ready.ready, ready.reason)

# Leader election status
leader = client.health_leader()
print(leader.holder_id)
for lock in leader.locks:
    print(lock.name, lock.is_leader)

# Metrics
metrics = client.get_metrics(types="uptime,active_tasks,llm")
print(metrics.uptime_seconds, metrics.active_tasks)
```

---

## Auth & WebSocket Status

```python
# Keycloak config (if enabled)
auth = client.get_auth_config()
print(auth.keycloak_enabled)

# Active WebSocket connections
ws = client.get_websocket_status()
print(ws.connected_clients)
```

---

## SSE Status Stream

For lightweight status-only monitoring (no Socket.IO dependency):

```python
events = client.stream_task_status("task-abc123", timeout=30)
for event in events:
    if event["event_type"] == "status":
        data = event["data"]
        print(f"Iter {data['iteration']}/{data['max_iterations']}: {data['status']}")
```

---

## Async Variant

The async variant has identical methods, just with `await`:

```python
from orchestrator_client import OrchestratorAsync

async with OrchestratorAsync() as client:
    task = await client.create_task(workflow_id="proactive", goal_prompt="Test")
    status = await client.get_task_status(task.task_id)
    conv = await client.get_task_conversation(task.task_id)
    for msg in conv.conversation:
        print(f"[{msg.role}] {msg.content[:80]}")

    # SSE streaming (async generator)
    async for event in client.stream_task_status(task.task_id):
        print(event)
```
