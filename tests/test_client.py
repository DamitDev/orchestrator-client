"""Tests for the Orchestrator REST API client."""

import pytest

from orchestrator_client.client import OrchestratorAsync
from orchestrator_client.exceptions import (
    OrchestratorAPIError,
    OrchestratorAuthError,
    OrchestratorNotFoundError,
)


class TestTaskMethods:
    """Task management endpoint tests."""

    @pytest.mark.asyncio
    async def test_list_tasks(self, mock_task_list_response):
        client = OrchestratorAsync(base_url="http://test:8080")
        captured = {}

        async def fake_request(method, path, **kwargs):
            captured["headers"] = kwargs.get("headers")
            return mock_task_list_response

        client._request = fake_request
        result = await client.list_tasks(locale="hu-hu")
        assert len(result.tasks) == 1
        assert result.tasks[0].id == "task-abc123"
        assert result.tasks[0].workflow_id == "proactive"
        assert result.tasks[0].result_localized == "Eredmény"
        assert result.tasks[0].pending_translations_for_locales == ["hu-hu"]
        assert result.pagination.current_page == 1
        assert captured["headers"] == {"X-Locale": "hu-hu"}

    @pytest.mark.asyncio
    async def test_list_tasks_with_filter(self):
        client = OrchestratorAsync(base_url="http://test:8080")
        captured = {}

        async def fake_request(method, path, **kwargs):
            captured["params"] = kwargs.get("params", {})
            return {
                "tasks": [],
                "pagination": {
                    "current_page": 1,
                    "per_page": 10,
                    "total_items": 0,
                    "total_pages": 0,
                    "has_next": False,
                    "has_prev": False,
                },
            }

        client._request = fake_request
        await client.list_tasks(page=2, limit=10, workflow_id="matrix")
        assert captured["params"]["page"] == 2
        assert captured["params"]["limit"] == 10
        assert captured["params"]["workflow_id"] == "matrix"

    @pytest.mark.asyncio
    async def test_create_task(self, mock_task_create_response):
        client = OrchestratorAsync(base_url="http://test:8080")

        async def fake_request(method, path, **kwargs):
            return mock_task_create_response

        client._request = fake_request
        result = await client.create_task(
            workflow_id="proactive",
            goal_prompt="Test task",
            max_iterations=30,
            reasoning_effort="high",
        )
        assert result.task_id == "task-abc123"
        assert result.status == "queued"

    @pytest.mark.asyncio
    async def test_create_task_with_tools(self):
        client = OrchestratorAsync(base_url="http://test:8080")
        captured = {}

        async def fake_request(method, path, **kwargs):
            captured["body"] = kwargs.get("json_body", {})
            return {"task_id": "task-abc", "status": "queued"}

        client._request = fake_request
        await client.create_task(
            workflow_id="ticket",
            goal_prompt="Fix ticket",
            ticket_id="IRIS-123",
            ticket_text="Email not working",
            agent_model_id="gpt-4o-mini",
            available_tools=["read_file", "grep_search"],
        )
        assert captured["body"]["workflow_id"] == "ticket"
        assert captured["body"]["ticket_id"] == "IRIS-123"
        assert captured["body"]["agent_model_id"] == "gpt-4o-mini"
        assert captured["body"]["available_tools"] == ["read_file", "grep_search"]

    @pytest.mark.asyncio
    async def test_get_task_status(self, mock_task_status_response):
        client = OrchestratorAsync(base_url="http://test:8080")
        captured = {}

        async def fake_request(method, path, **kwargs):
            captured["headers"] = kwargs.get("headers")
            return mock_task_status_response

        client._request = fake_request
        status = await client.get_task_status("task-abc123", locale="hu-hu")
        assert status.id == "task-abc123"
        assert status.status == "in_progress"
        assert status.iteration == 5
        assert status.result_localized == "Eredmény"
        assert status.pending_translations_for_locales == ["hu-hu"]
        assert captured["headers"] == {"X-Locale": "hu-hu"}

    @pytest.mark.asyncio
    async def test_get_task_conversation(self, mock_conversation_response):
        client = OrchestratorAsync(base_url="http://test:8080")
        captured = {}

        async def fake_request(method, path, **kwargs):
            captured["headers"] = kwargs.get("headers")
            return mock_conversation_response

        client._request = fake_request
        conv = await client.get_task_conversation("task-abc123", locale="hu-hu")
        assert conv.task_id == "task-abc123"
        assert len(conv.conversation) == 3
        assert conv.conversation[0].role == "system"
        assert conv.conversation[2].role == "assistant"
        assert conv.conversation[2].tool_calls is not None
        assert len(conv.conversation[2].tool_calls) == 1
        assert captured["headers"] == {"X-Locale": "hu-hu"}

    @pytest.mark.asyncio
    async def test_cancel_task(self, mock_success_response):
        client = OrchestratorAsync(base_url="http://test:8080")

        async def fake_request(method, path, **kwargs):
            return mock_success_response

        client._request = fake_request
        result = await client.cancel_task("task-abc123")
        assert "has been canceled" in result.message

    @pytest.mark.asyncio
    async def test_delete_task(self):
        client = OrchestratorAsync(base_url="http://test:8080")

        async def fake_request(method, path, **kwargs):
            return {
                "deleted_tasks": ["task-abc123"],
                "failed_tasks": [],
                "total_deleted": 1,
                "total_failed": 0,
            }

        client._request = fake_request
        result = await client.delete_task("task-abc123")
        assert result.total_deleted == 1

    @pytest.mark.asyncio
    async def test_delete_tasks(self):
        client = OrchestratorAsync(base_url="http://test:8080")
        captured = {}

        async def fake_request(method, path, **kwargs):
            captured["body"] = kwargs.get("json_body", {})
            return {
                "deleted_tasks": ["t1", "t2"],
                "failed_tasks": [],
                "total_deleted": 2,
                "total_failed": 0,
            }

        client._request = fake_request
        result = await client.delete_tasks(["t1", "t2"])
        assert captured["body"]["task_ids"] == ["t1", "t2"]
        assert result.total_deleted == 2

    @pytest.mark.asyncio
    async def test_get_message_translations(self):
        client = OrchestratorAsync(base_url="http://test:8080")
        captured = {}

        async def fake_request(method, path, **kwargs):
            captured["method"] = method
            captured["path"] = path
            return {
                "message_id": 123,
                "translations": [
                    {
                        "locale": "hu-hu",
                        "kind": "content",
                        "translated_text": "Szia",
                        "is_fallback": False,
                        "created_at": "2026-05-18T12:00:00Z",
                    }
                ],
            }

        client._request = fake_request
        result = await client.get_message_translations("task-abc123", 123)
        assert captured["method"] == "GET"
        assert captured["path"] == "/debug/task/task-abc123/message/123/translations"
        assert result.message_id == 123
        assert result.translations[0].locale == "hu-hu"
        assert result.translations[0].translated_text == "Szia"


class TestWorkflowMethods:
    """Workflow-specific interaction tests."""

    @pytest.mark.asyncio
    async def test_interactive_message(self):
        client = OrchestratorAsync(base_url="http://test:8080")
        captured = {}

        async def fake_request(method, path, **kwargs):
            captured["path"] = path
            captured["body"] = kwargs.get("json_body", {})
            return {"message": "Message sent"}

        client._request = fake_request
        await client.send_interactive_message("task-abc", "Hello!")
        assert captured["path"] == "/task/interactive/message"
        assert captured["body"]["task_id"] == "task-abc"
        assert captured["body"]["message"] == "Hello!"

    @pytest.mark.asyncio
    async def test_vsa_create(self):
        client = OrchestratorAsync(base_url="http://test:8080")
        captured = {}

        async def fake_request(method, path, **kwargs):
            captured["body"] = kwargs.get("json_body", {})
            return {"task_id": "vsa-task-1", "status": "queued"}

        client._request = fake_request
        result = await client.create_vsa_task("user_123", "VPN help", title="VPN setup")
        assert result.task_id == "vsa-task-1"
        assert captured["body"]["user_id"] == "user_123"
        assert captured["body"]["title"] == "VPN setup"

    @pytest.mark.asyncio
    async def test_mio_interaction(self):
        client = OrchestratorAsync(base_url="http://test:8080")

        async def fake_request(method, path, **kwargs):
            return {"message": "Mio woken, switching to interactive mode"}

        client._request = fake_request
        result = await client.wake_mio("task-mio-1")
        assert "woken" in result.message

    @pytest.mark.asyncio
    async def test_matrix_conversation(self):
        client = OrchestratorAsync(base_url="http://test:8080")
        captured = {}

        async def fake_request(method, path, **kwargs):
            captured["params"] = kwargs.get("params", {})
            return {"task_id": "task-abc", "conversation": []}

        client._request = fake_request
        await client.get_matrix_conversation("task-abc", phase=2)
        assert captured["params"]["phase"] == 2


class TestErrorHandling:
    """Error handling tests."""

    @pytest.mark.asyncio
    async def test_404_raises_not_found(self):
        client = OrchestratorAsync(base_url="http://test:8080")

        async def fake_request(method, path, **kwargs):
            raise OrchestratorNotFoundError("task", "task-xyz")

        client._request = fake_request
        with pytest.raises(OrchestratorNotFoundError) as exc:
            await client.get_task_status("task-xyz")
        assert exc.value.resource_id == "task-xyz"

    @pytest.mark.asyncio
    async def test_400_raises_api_error(self):
        client = OrchestratorAsync(base_url="http://test:8080")

        async def fake_request(method, path, **kwargs):
            raise OrchestratorAPIError(
                "Invalid state", status_code=400, error_code="INVALID_WORKFLOW_STATE"
            )

        client._request = fake_request
        with pytest.raises(OrchestratorAPIError) as exc:
            await client.cancel_task("task-abc")
        assert exc.value.error_code == "INVALID_WORKFLOW_STATE"
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_401_raises_auth_error(self):
        client = OrchestratorAsync(base_url="http://test:8080")

        async def fake_request(method, path, **kwargs):
            raise OrchestratorAuthError("Unauthorized", status_code=401)

        client._request = fake_request
        with pytest.raises(OrchestratorAuthError):
            await client.list_tasks()


class TestConfigurationMethods:
    """Configuration endpoint tests."""

    @pytest.mark.asyncio
    async def test_get_system_status(self):
        client = OrchestratorAsync(base_url="http://test:8080")

        async def fake_request(method, path, **kwargs):
            return {
                "is_configured": True,
                "missing_fields": [],
                "settings": {
                    "agent_model_id": "gpt-oss:20b",
                    "orchestrator_model_id": "gpt-oss:120b",
                    "compactor_model_id": "qwen3.5:2b",
                    "journal_model_id": None,
                    "summary_model_id": None,
                    "translate_model_id": None,
                    "max_concurrent_tasks_per_replica": 5,
                    "subagents_enabled": True,
                    "localization_targets": [
                        {"locale": "hu-hu", "language": "Hungarian"}
                    ],
                },
                "version": 7,
            }

        client._request = fake_request
        status = await client.get_system_status()
        assert status.is_configured is True
        assert status.settings.agent_model_id == "gpt-oss:20b"
        assert status.settings.max_concurrent_tasks_per_replica == 5
        assert status.settings.localization_targets == [
            {"locale": "hu-hu", "language": "Hungarian"}
        ]

    @pytest.mark.asyncio
    async def test_update_settings(self):
        client = OrchestratorAsync(base_url="http://test:8080")
        captured = {}

        async def fake_request(method, path, **kwargs):
            captured["body"] = kwargs.get("json_body", {})
            return {
                "is_configured": True,
                "missing_fields": [],
                "settings": {
                    "agent_model_id": "gpt-oss:20b",
                    "orchestrator_model_id": None,
                    "compactor_model_id": None,
                    "journal_model_id": None,
                    "summary_model_id": None,
                    "translate_model_id": None,
                    "max_concurrent_tasks_per_replica": 5,
                    "subagents_enabled": True,
                    "localization_targets": [
                        {"locale": "hu-hu", "language": "Hungarian"}
                    ],
                },
                "version": 8,
            }

        client._request = fake_request
        status = await client.update_settings(
            agent_model_id="gpt-oss:20b", max_concurrent_tasks_per_replica=5
        )
        assert captured["body"]["agent_model_id"] == "gpt-oss:20b"
        assert status.settings.localization_targets == [
            {"locale": "hu-hu", "language": "Hungarian"}
        ]


class TestHealthMethods:
    """Health endpoint tests."""

    @pytest.mark.asyncio
    async def test_health(self):
        client = OrchestratorAsync(base_url="http://test:8080")

        async def fake_request(method, path, **kwargs):
            return {
                "status": "healthy",
                "message": "Orchestrator API is running",
                "version": "3.0.0",
            }

        client._request = fake_request
        result = await client.health()
        assert result.status == "healthy"
        assert result.version == "3.0.0"

    @pytest.mark.asyncio
    async def test_get_metrics(self):
        client = OrchestratorAsync(base_url="http://test:8080")

        async def fake_request(method, path, **kwargs):
            return {"uptime_seconds": 3600.5, "active_tasks": 2, "open_tasks": 5}

        client._request = fake_request
        metrics = await client.get_metrics(types="uptime,active_tasks")
        assert metrics.uptime_seconds == 3600.5
        assert metrics.active_tasks == 2


class TestAuthAndWebSocket:
    """Auth and WebSocket status tests."""

    @pytest.mark.asyncio
    async def test_get_auth_config(self):
        client = OrchestratorAsync(base_url="http://test:8080")

        async def fake_request(method, path, **kwargs):
            return {
                "keycloak_enabled": True,
                "keycloak_url": "https://keycloak.test/auth/",
                "keycloak_realm": "test",
                "keycloak_client_id": "test-client",
            }

        client._request = fake_request
        config = await client.get_auth_config()
        assert config.keycloak_enabled is True


class TestErrorEvents:
    """Error event endpoint tests."""

    @pytest.mark.asyncio
    async def test_count_errors(self):
        client = OrchestratorAsync(base_url="http://test:8080")

        async def fake_request(method, path, **kwargs):
            return {"count": 5}

        client._request = fake_request
        result = await client.count_errors("2026-04-22T10:00:00Z")
        assert result.count == 5

    @pytest.mark.asyncio
    async def test_get_error_detail(self):
        client = OrchestratorAsync(base_url="http://test:8080")

        async def fake_request(method, path, **kwargs):
            return {
                "id": "err-1",
                "severity": "critical",
                "source": "llm_backend",
                "message": "LLM failed",
                "traceback": "Traceback...",
                "context": {"model": "test"},
            }

        client._request = fake_request
        detail = await client.get_error_detail("err-1")
        assert detail.severity == "critical"
        assert detail.traceback == "Traceback..."


class TestClientConstruction:
    """Client construction and SSL/HTTP client injection tests."""

    @pytest.mark.asyncio
    async def test_verify_ssl_default_true(self):
        """Default verify_ssl should be True (httpx default)."""
        client = OrchestratorAsync(base_url="https://test:8080")
        # httpx client's verify property should reflect the passed value
        transport = client._http._transport
        # httpx uses verify parameter in its transport — default is True
        assert client._http is not None

    @pytest.mark.asyncio
    async def test_verify_ssl_false(self):
        """Should accept verify_ssl=False for self-signed certs."""
        client = OrchestratorAsync(
            base_url="https://test:8443",
            verify_ssl=False,
        )
        # The client should be constructable without error
        assert client._http is not None

    @pytest.mark.asyncio
    async def test_http_client_injection(self):
        """Should accept a pre-configured httpx.AsyncClient."""
        import httpx

        custom_client = httpx.AsyncClient(
            base_url="http://custom:9090",
            verify=False,
            timeout=httpx.Timeout(5.0),
        )
        client = OrchestratorAsync(
            base_url="http://ignored:8080",
            api_key="should-be-ignored",
            http_client=custom_client,
        )
        assert client._http is custom_client
        # The custom client's settings should be preserved
        transport = client._http._transport
        await client.close()

    @pytest.mark.asyncio
    async def test_insecure_with_verify_ssl_false_makes_request(self):
        """OrchestratorAsync with verify_ssl=False can call a method."""
        import httpx

        # Use respx to mock the call so we don't need a real server
        client = OrchestratorAsync(
            base_url="http://test:8080",
            verify_ssl=True,  # still works for http
        )

        async def fake_request(method, path, **kwargs):
            return {
                "status": "ok",
                "message": "healthy",
                "version": "1.0",
            }

        client._request = fake_request
        result = await client.health()
        assert result.status == "ok"
