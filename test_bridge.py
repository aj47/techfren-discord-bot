"""Unit tests for bridge.py — no network, no Discord connection."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import discord
import pytest

import bridge


def _make_bridge(channel_ids=(1,)):
    b = bridge.Bridge("https://x.convex.site", "secret", None, set())
    b.channel_ids = set(channel_ids)
    return b


def _message(content="hello", channel_id=1, bot=False, webhook_id=None, msg_type=discord.MessageType.default):
    m = Mock(spec=discord.Message)
    m.id = 555
    m.content = content
    m.type = msg_type
    m.channel = Mock()
    m.channel.id = channel_id
    m.author = Mock()
    m.author.id = 42
    m.author.bot = bot
    m.author.display_name = "AJ"
    m.author.display_avatar = Mock()
    m.author.display_avatar.url = "https://cdn/avatar.png"
    m.webhook_id = webhook_id
    m.created_at = MagicMock()
    m.created_at.timestamp.return_value = 1_700_000_000.0
    m.reference = None
    m.attachments = []
    m.add_reaction = AsyncMock()
    return m


def test_message_create_event_shape():
    b = _make_bridge()
    b.on_message(_message())
    ev = b._queue.get_nowait()
    assert ev["type"] == "message.create"
    assert ev["id"] == "555" and ev["channelId"] == "1" and ev["authorId"] == "42"
    assert ev["createdAt"] == 1_700_000_000_000
    assert ev["isBot"] is False and ev["webhookId"] is None


def test_ignores_unmirrored_channel():
    b = _make_bridge(channel_ids=(99,))
    b.on_message(_message(channel_id=1))
    assert b._queue.empty()


def test_link_code_becomes_link_event():
    b = _make_bridge()
    msg = _message(content="!link abc123")
    with patch("bridge.asyncio.create_task") as ct:
        b.on_message(msg)
        assert ct.called
    ev = b._queue.get_nowait()
    assert ev == {
        "type": "link.code", "code": "ABC123", "discordUserId": "42",
        "name": "AJ", "avatar": "https://cdn/avatar.png",
    }
    assert b._queue.empty()


def test_reaction_and_delete_events():
    b = _make_bridge()
    r = Mock(spec=discord.RawReactionActionEvent)
    r.channel_id, r.message_id, r.user_id, r.emoji = 1, 7, 9, "👍"
    b.on_raw_reaction_add(r)
    d = Mock(spec=discord.RawMessageDeleteEvent)
    d.channel_id, d.message_id = 1, 7
    b.on_raw_message_delete(d)
    assert b._queue.get_nowait() == {"type": "reaction.add", "messageId": "7", "emoji": "👍", "userId": "9"}
    assert b._queue.get_nowait() == {"type": "message.delete", "id": "7"}


@pytest.mark.asyncio
async def test_flush_posts_batch_with_bearer():
    b = _make_bridge()
    b.enqueue({"type": "message.delete", "id": "1"})
    resp = MagicMock()
    resp.status = 200
    resp.__aenter__.return_value = resp
    resp.__aexit__.return_value = False
    session = MagicMock()
    session.post.return_value = resp
    b._session = session
    assert await b._flush() is True
    args, kwargs = session.post.call_args
    assert args[0].endswith("/discord/ingest")
    assert kwargs["headers"]["Authorization"] == "Bearer secret"
    assert kwargs["json"] == {"events": [{"type": "message.delete", "id": "1"}]}
    assert b._queue.empty()


@pytest.mark.asyncio
async def test_flush_requeues_on_failure():
    b = _make_bridge()
    b.enqueue({"type": "message.delete", "id": "1"})
    session = MagicMock()
    session.post.side_effect = RuntimeError("boom")
    b._session = session
    assert await b._flush() is False
    assert b._queue.qsize() == 1


@pytest.mark.asyncio
async def test_handlers_never_raise_when_disabled():
    bridge._bridge = None
    await bridge.handle_bridge_message(_message())
    await bridge.handle_bridge_reaction(Mock())
