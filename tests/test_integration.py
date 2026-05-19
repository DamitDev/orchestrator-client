"""Integration tests against a real orchestrator instance.

These tests require a running orchestrator at ``ORCHESTRATOR_URL``
(default: ``http://localhost:8082``).

Run with::

    ORCHESTRATOR_URL=http://localhost:8082 pytest tests/test_integration.py -v

Or via marker::

    pytest tests/test_integration.py -v -m integration

The tests are automatically skipped if the orchestrator is unreachable.
"""

import os
from pathlib import Path

import pytest

from orchestrator_client import Orchestrator, OrchestratorAsync, load_config
from orchestrator_client.exceptions import OrchestratorConnectionError

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Health check: is the orchestrator reachable?
# ---------------------------------------------------------------------------

def orchestrator_reachable() -> bool:
    """Quick probe — try to reach the orchestrator health endpoint."""
    config = load_config()
    import httpx
    try:
        resp = httpx.get(
            f"{config.base_url}/health",
            timeout=3.0,
        )
        return resp.status_code == 200
    except Exception:
        return False


def pytest_configure(config):
    """Register the 'integration' marker."""
    config.addinivalue_line("markers", "integration: tests requiring a live orchestrator")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def config():
    return load_config()


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="function")
async def async_client(cfg):
    """Per-test async client — isolates event loop per test."""
    if not orchestrator_reachable():
        pytest.skip("Orchestrator is not reachable")
    client = OrchestratorAsync(
        base_url=cfg.base_url,
        api_key=cfg.api_key,
        timeout=cfg.timeout,
        max_retries=cfg.max_retries,
    )
    yield client
    await client.close()


@pytest.fixture(scope="module")
def sync_client(cfg):
    """Shared sync client — created once per module."""
    if not orchestrator_reachable():
        pytest.skip("Orchestrator is not reachable")
    client = Orchestrator(
        base_url=cfg.base_url,
        api_key=cfg.api_key,
        timeout=cfg.timeout,
        max_retries=cfg.max_retries,
    )
    yield client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def unique_goal():
    """Return a unique goal prompt so each test run creates distinct tasks."""
    import uuid
    return f"Integration test task {uuid.uuid4().hex[:8]}"


# ===========================================================================
# Async Client Integration Tests
# ===========================================================================

class TestAsyncIntegration:
    """Real orchestrator interaction via OrchestratorAsync."""

    @pytest.mark.asyncio
    async def test_health(self, async_client):
        """GET /health returns a healthy status."""
        result = await async_client.health()
        assert result.status == "healthy"
        assert result.message
        assert result.version

    @pytest.mark.asyncio
    async def test_health_detailed(self, async_client):
        """GET /health/detailed returns component health."""
        result = await async_client.health_detailed()
        assert result.status == "healthy"
        assert hasattr(result, "components")

    @pytest.mark.asyncio
    async def test_ready(self, async_client):
        """GET /ready returns readiness state."""
        result = await async_client.ready()
        # ready can be True or False depending on state, but response must be valid
        assert hasattr(result, "ready")
        assert hasattr(result, "is_startup_complete")

    @pytest.mark.asyncio
    async def test_metrics(self, async_client):
        """GET /metrics returns metric snapshot."""
        result = await async_client.get_metrics()
        # At minimum uptime should be present
        assert result.uptime_seconds is not None
        assert result.uptime_seconds > 0

    @pytest.mark.asyncio
    async def test_list_tools(self, async_client):
        """GET /tools/all returns tool list."""
        result = await async_client.list_tools()
        assert result.total_tools >= 0
        assert isinstance(result.tools, list)
        assert isinstance(result.servers, list)

    @pytest.mark.asyncio
    async def test_auth_config(self, async_client):
        """GET /auth/config returns auth config (may be disabled)."""
        result = await async_client.get_auth_config()
        # keycloak_enabled is always a bool, regardless of auth state
        assert isinstance(result.keycloak_enabled, bool)

    @pytest.mark.asyncio
    async def test_system_status(self, async_client):
        """GET /configuration/system/status returns system settings."""
        result = await async_client.get_system_status()
        assert isinstance(result.is_configured, bool)
        assert isinstance(result.missing_fields, list)
        assert result.version > 0

    @pytest.mark.asyncio
    async def test_list_tasks(self, async_client):
        """GET /tasks returns a paginated task list."""
        result = await async_client.list_tasks(limit=5)
        assert isinstance(result.tasks, list)
        assert result.pagination.current_page == 1
        assert result.pagination.per_page == 5

    @pytest.mark.asyncio
    async def test_list_tasks_filtered(self, async_client):
        """GET /tasks with workflow filter."""
        result = await async_client.list_tasks(workflow_id="proactive", limit=5)
        assert isinstance(result.tasks, list)

    @pytest.mark.asyncio
    async def test_create_and_cancel_task(self, async_client, unique_goal):
        """Full lifecycle: create a task, verify it exists, cancel it."""
        # Create
        created = await async_client.create_task(
            workflow_id="proactive",
            goal_prompt=unique_goal,
            max_iterations=5,
            reasoning_effort="low",
        )
        assert created.task_id
        assert created.status == "queued"
        task_id = created.task_id

        try:
            # Get status — should be queued or in_progress
            status = await async_client.get_task_status(task_id)
            assert status.id == task_id
            assert status.status in ("queued", "in_progress", "completed", "failed")
            assert status.goal_prompt == unique_goal
            assert status.max_iterations == 5

            # Cancel
            cancel_result = await async_client.cancel_task(task_id)
            assert cancel_result.message

            # Verify cancelled
            cancelled_status = await async_client.get_task_status(task_id)
            assert cancelled_status.status == "cancelled"

        finally:
            # Cleanup
            try:
                await async_client.delete_task(task_id)
            except Exception:
                pass

    @pytest.mark.asyncio
    async def test_create_task_with_options(self, async_client, unique_goal):
        """Create a task with all optional parameters."""
        created = await async_client.create_task(
            workflow_id="interactive",
            goal_prompt=unique_goal,
            max_iterations=10,
            reasoning_effort="high",
            available_tools=["read_file", "grep_search"],
        )
        assert created.task_id
        task_id = created.task_id

        try:
            # Cleanup
            status = await async_client.get_task_status(task_id)
            if status.status not in ("completed", "failed", "cancelled"):
                await async_client.cancel_task(task_id)
            await async_client.delete_task(task_id)
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_create_task_with_disable_summaries_and_translation(self, async_client, unique_goal):
        """Create a task with disable_summaries and disable_translation options."""
        created = await async_client.create_task(
            workflow_id="interactive",
            goal_prompt=unique_goal,
            max_iterations=3,
            options={"disable_summaries": True, "disable_translation": True},
        )
        assert created.task_id
        task_id = created.task_id

        try:
            status = await async_client.get_task_status(task_id)
            assert status.id == task_id
            # options must be echoed back in the status response
            assert status.options is not None
            assert status.options.get("disable_summaries") is True
            assert status.options.get("disable_translation") is True
        finally:
            try:
                if status.status not in ("completed", "failed", "cancelled"):
                    await async_client.cancel_task(task_id)
                await async_client.delete_task(task_id)
            except Exception:
                pass

    @pytest.mark.asyncio
    async def test_configuration_status(self, async_client):
        """GET /configuration/status returns full config snapshot."""
        result = await async_client.get_configuration_status()
        assert hasattr(result, "agent_model")
        assert hasattr(result, "orchestrator_model")
        assert isinstance(result.llmbackends, list)
        assert isinstance(result.mcpservers, list)

    @pytest.mark.asyncio
    async def test_error_list_endpoints(self, async_client):
        """Error event endpoints return valid responses (may be empty)."""
        # Stats (no since param = all time)
        stats = await async_client.get_error_stats(top_n=5)
        assert hasattr(stats, "total")
        assert hasattr(stats, "by_severity")

        # Count with since
        count = await async_client.count_errors("2024-01-01T00:00:00Z")
        assert count.count >= 0

    @pytest.mark.asyncio
    async def test_websocket_status(self, async_client):
        """GET /websocket/status returns client info."""
        result = await async_client.get_websocket_status()
        assert isinstance(result.connected_clients, int)

    @pytest.mark.asyncio
    async def test_workflow_states(self, async_client):
        """GET /debug/workflow_states returns state maps."""
        result = await async_client.get_workflow_states()
        assert "proactive" in result.valid_states
        assert "interactive" in result.valid_states
        assert "matrix" in result.valid_states

    @pytest.mark.asyncio
    async def test_concurrent_per_replica(self, async_client):
        """GET /configuration/taskhandler/concurrent-per-replica returns current value."""
        status = await async_client.get_taskhandler_status()
        assert status.cluster.max_concurrent_tasks_per_replica > 0
        assert len(status.replicas) >= 0

    @pytest.mark.asyncio
    async def test_slots_status(self, async_client):
        """GET /configuration/slots/status returns slot state (may be disabled)."""
        result = await async_client.get_slots_status()
        assert isinstance(result.enabled, bool)

    @pytest.mark.asyncio
    async def test_summary_worker_status(self, async_client):
        """GET /configuration/summary-worker/status returns worker state."""
        result = await async_client.get_summary_worker_status()
        assert isinstance(result.running, bool)

    @pytest.mark.asyncio
    async def test_token_worker_status(self, async_client):
        """GET /configuration/token-worker/status returns worker state."""
        result = await async_client.get_token_worker_status()
        assert isinstance(result.running, bool)


# ===========================================================================
# Sync Client Integration Tests
# ===========================================================================

class TestSyncIntegration:
    """Real orchestrator interaction via Orchestrator (sync wrapper)."""

    def test_health(self, sync_client):
        """GET /health via sync client."""
        result = sync_client.health()
        assert result.status == "healthy"

    def test_list_tools(self, sync_client):
        """GET /tools/all via sync client."""
        result = sync_client.list_tools()
        assert result.total_tools >= 0

    def test_system_status(self, sync_client):
        """GET /configuration/system/status via sync client."""
        result = sync_client.get_system_status()
        assert isinstance(result.is_configured, bool)

    def test_list_tasks(self, sync_client):
        """GET /tasks via sync client."""
        result = sync_client.list_tasks(limit=3)
        assert isinstance(result.tasks, list)

    def test_create_and_cancel_task(self, sync_client, unique_goal):
        """Full lifecycle via sync client."""
        created = sync_client.create_task(
            workflow_id="proactive",
            goal_prompt=unique_goal,
            max_iterations=3,
        )
        assert created.task_id
        task_id = created.task_id

        try:
            status = sync_client.get_task_status(task_id)
            assert status.id == task_id

            cancel_result = sync_client.cancel_task(task_id)
            assert cancel_result.message

        finally:
            try:
                sync_client.delete_task(task_id)
            except Exception:
                pass

    def test_create_task_with_options(self, sync_client, unique_goal):
        """Sync: create a task with disable_summaries=True option."""
        created = sync_client.create_task(
            workflow_id="interactive",
            goal_prompt=unique_goal,
            max_iterations=3,
            options={"disable_summaries": True},
        )
        assert created.task_id
        task_id = created.task_id

        try:
            status = sync_client.get_task_status(task_id)
            assert status.id == task_id
            assert status.options is not None
            assert status.options.get("disable_summaries") is True
        finally:
            try:
                sync_client.cancel_task(task_id)
            except Exception:
                pass
            try:
                sync_client.delete_task(task_id)
            except Exception:
                pass

    def test_conversation_of_existing_task(self, sync_client):
        """Get conversation for an existing task (list first, then fetch)."""
        tasks = sync_client.list_tasks(limit=5, order_by="updated_at", order_direction="desc")
        if tasks.tasks:
            # Try to get the conversation of the most recently updated task
            task_id = tasks.tasks[0].id
            conv = sync_client.get_task_conversation(task_id)
            assert conv.task_id == task_id
            assert isinstance(conv.conversation, list)

    def test_configuration_status(self, sync_client):
        """GET /configuration/status via sync client."""
        result = sync_client.get_configuration_status()
        assert hasattr(result, "agent_model")

    def test_error_stats(self, sync_client):
        """GET /errors/stats via sync client."""
        stats = sync_client.get_error_stats(top_n=3)
        assert hasattr(stats, "total")

    def test_metrics(self, sync_client):
        """GET /metrics via sync client."""
        metrics = sync_client.get_metrics()
        assert metrics.uptime_seconds is not None
        assert metrics.uptime_seconds > 0

    def test_taskhandler_status(self, sync_client):
        """GET /configuration/taskhandler/status via sync client."""
        result = sync_client.get_taskhandler_status()
        assert result.cluster.total_tasks >= 0

    def test_auth_config(self, sync_client):
        """GET /auth/config via sync client."""
        result = sync_client.get_auth_config()
        assert isinstance(result.keycloak_enabled, bool)

    def test_llm_backend_status(self, sync_client):
        """GET /configuration/llmbackend/status via sync client."""
        result = sync_client.get_llm_backend_status()
        assert "backends" in result

    def test_mcp_server_status(self, sync_client):
        """GET /configuration/mcpserver/status via sync client."""
        result = sync_client.get_mcp_server_status()
        assert "servers" in result
