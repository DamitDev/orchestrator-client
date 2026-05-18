"""Tests for the Socket.IO realtime client."""

from unittest.mock import AsyncMock

import pytest

from orchestrator_client.socketio import (
    EVENT_MESSAGE_TRANSLATION_READY,
    RealtimeClient,
)


@pytest.mark.asyncio
async def test_connect_includes_locale_query():
    client = RealtimeClient(
        "http://test:8080",
        client_id="client-1",
        locale="hu-hu",
    )
    client._sio.connect = AsyncMock()

    await client.connect()

    client._sio.connect.assert_awaited_once_with(
        "http://test:8080",
        socketio_path="/socket.io",
        query={"client_id": "client-1", "locale": "hu-hu"},
        wait_timeout=10,
    )


@pytest.mark.asyncio
async def test_subscribe_locale_joins_locale_room():
    client = RealtimeClient("http://test:8080")
    client._sio.emit = AsyncMock()

    await client.subscribe_locale("hu-hu")

    client._sio.emit.assert_awaited_once_with("join", {"rooms": ["locale:hu-hu"]})


@pytest.mark.asyncio
async def test_dispatch_message_translation_ready_event():
    client = RealtimeClient("http://test:8080")
    seen = []

    async def handler(event):
        seen.append(event)

    client.on(EVENT_MESSAGE_TRANSLATION_READY, handler)

    await client._dispatch(
        {
            "type": "message",
            "event": {
                "event_type": EVENT_MESSAGE_TRANSLATION_READY,
                "task_id": "task-1",
                "message_id": 123,
                "locale": "hu-hu",
                "translated_content": "Szia",
                "message_index": 1,
                "translation_failed": False,
            },
        }
    )

    assert seen == [
        {
            "event_type": EVENT_MESSAGE_TRANSLATION_READY,
            "task_id": "task-1",
            "message_id": 123,
            "locale": "hu-hu",
            "translated_content": "Szia",
            "message_index": 1,
            "translation_failed": False,
        }
    ]
