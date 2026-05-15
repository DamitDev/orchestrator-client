"""Shared test fixtures and mocks for orchestrator-client tests."""

import json
from typing import Any

import pytest


@pytest.fixture
def mock_task_list_response() -> dict:
    return {
        "tasks": [
            {
                "id": "task-abc123",
                "status": "in_progress",
                "workflow_id": "proactive",
                "iteration": 5,
                "max_iterations": 50,
                "goal_prompt": "Analyze logs",
                "result": "",
                "approval_reason": "",
                "ticket_id": None,
                "available_tools": None,
                "insight": "Analyzing...",
                "insight_localized": "Elemzés...",
                "created_at": "2025-10-14T10:30:00Z",
                "updated_at": "2025-10-14T10:35:00Z",
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


@pytest.fixture
def mock_task_create_response() -> dict:
    return {"task_id": "task-abc123", "status": "queued"}


@pytest.fixture
def mock_task_status_response() -> dict:
    return {
        "id": "task-abc123",
        "status": "in_progress",
        "workflow_id": "proactive",
        "iteration": 5,
        "max_iterations": 50,
        "goal_prompt": "Analyze logs",
        "result": "",
        "approval_reason": "",
        "ticket_id": None,
        "insight": "Analyzing...",
        "insight_localized": "Elemzés...",
        "subtask_ids": [],
        "created_at": "2025-10-14T10:30:00Z",
        "updated_at": "2025-10-14T10:35:00Z",
    }


@pytest.fixture
def mock_conversation_response() -> dict:
    return {
        "task_id": "task-abc123",
        "conversation": [
            {
                "id": 1,
                "role": "system",
                "content": "You are a helpful AI assistant...",
                "created_at": "2025-10-14T10:30:00Z",
            },
            {
                "id": 2,
                "role": "user",
                "content": "Analyze the logs",
                "created_at": "2025-10-14T10:31:00Z",
            },
            {
                "id": 3,
                "role": "assistant",
                "content": "I'll help you analyze...",
                "tool_calls": [
                    {
                        "id": "call_abc",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": '{"path": "/var/log/app.log"}'},
                    }
                ],
                "created_at": "2025-10-14T10:32:00Z",
            },
        ],
    }


@pytest.fixture
def mock_success_response() -> dict:
    return {"message": "Task task-abc123 has been canceled"}


@pytest.fixture
def mock_error_response() -> dict:
    return {"error": {"code": "TASK_NOT_FOUND", "message": "Task with id task-xyz not found", "details": None}}


class MockAsyncResponse:
    """Minimal async httpx.Response stand-in for tests."""

    def __init__(self, status_code: int, json_data: Any = None, text: str = "", headers: dict = None):
        self.status_code = status_code
        self._json_data = json_data
        self._text = text
        self.headers = headers or {"content-type": "application/json"}
        self.content = b""

    def json(self) -> Any:
        if self._json_data is not None:
            return self._json_data
        raise json.JSONDecodeError("No JSON", "", 0)

    @property
    def text(self) -> str:
        return self._text

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300
