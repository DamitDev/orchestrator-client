"""Tests for the synchronous SyncOrchestratorClient wrapper."""

import pytest

from orchestrator_client.sync_client import Orchestrator as SyncOrchestrator


class TestSyncClient:
    """Sync client mirrors the async client's method signatures and responses."""

    @pytest.fixture
    def client(self):
        c = SyncOrchestrator(base_url="http://test:8080")

        async def fake_request(method, path, **kwargs):
            if path == "/tasks":
                return {
                    "tasks": [
                        {
                            "id": "task-sync-1",
                            "status": "completed",
                            "workflow_id": "proactive",
                            "iteration": 10,
                            "max_iterations": 50,
                            "goal_prompt": "Test",
                            "result": "Done",
                            "result_localized": "Kész",
                            "approval_reason": "",
                            "ticket_id": None,
                            "available_tools": None,
                            "insight": "Done",
                            "insight_localized": "Kész",
                            "created_at": "2025-10-14T10:30:00Z",
                            "updated_at": "2025-10-14T10:35:00Z",
                            "pending_translations_for_locales": [],
                        }
                    ],
                    "pagination": {
                        "current_page": 1,
                        "per_page": 25,
                        "total_items": 1,
                        "total_pages": 1,
                        "has_next": False,
                        "has_prev": False,
                    },
                }
            if path == "/task/create":
                return {"task_id": "task-sync-1", "status": "queued"}
            if path == "/task/status":
                return {
                    "id": "task-sync-1",
                    "status": "in_progress",
                    "workflow_id": "proactive",
                    "iteration": 5,
                    "max_iterations": 50,
                    "goal_prompt": "Test",
                    "result": "",
                    "result_localized": "Eredmény",
                    "approval_reason": "",
                    "ticket_id": None,
                    "insight": "Working...",
                    "insight_localized": "Munka...",
                    "subtask_ids": [],
                    "created_at": "2025-10-14T10:30:00Z",
                    "updated_at": "2025-10-14T10:35:00Z",
                    "pending_translations_for_locales": ["hu-hu"],
                }
            if path == "/debug/task/task-sync-1/message/123/translations":
                return {
                    "message_id": 123,
                    "translations": [
                        {
                            "locale": "hu-hu",
                            "kind": "content",
                            "translated_text": "Szia",
                            "is_fallback": False,
                            "created_at": None,
                        }
                    ],
                }
            if path == "/task/cancel":
                return {"message": "Task cancelled"}
            if path == "/health":
                return {"status": "healthy", "message": "OK", "version": "3.0.0"}
            return {}

        c._async_client._request = fake_request
        yield c
        c.close()

    def test_list_tasks(self, client):
        result = client.list_tasks()
        assert len(result.tasks) == 1
        assert result.tasks[0].id == "task-sync-1"
        assert result.pagination.current_page == 1

    def test_create_task(self, client):
        result = client.create_task(workflow_id="proactive", goal_prompt="Test")
        assert result.task_id == "task-sync-1"
        assert result.status == "queued"

    def test_get_task_status(self, client):
        status = client.get_task_status("task-sync-1", locale="hu-hu")
        assert status.id == "task-sync-1"
        assert status.status == "in_progress"
        assert status.result_localized == "Eredmény"
        assert status.pending_translations_for_locales == ["hu-hu"]

    def test_get_message_translations(self, client):
        result = client.get_message_translations("task-sync-1", 123)
        assert result.message_id == 123
        assert result.translations[0].translated_text == "Szia"

    def test_cancel_task(self, client):
        result = client.cancel_task("task-sync-1")
        assert result.message == "Task cancelled"

    def test_health(self, client):
        result = client.health()
        assert result.status == "healthy"

    def test_context_manager(self):
        """Sync client works as a context manager."""
        with SyncOrchestrator(base_url="http://test:8080") as c:
            assert c is not None
