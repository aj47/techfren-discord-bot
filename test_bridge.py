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


@pytest.mark.asyncio
async def test_push_leaderboard_mirrors_bot_points():
    """The mirror carries the bot's own points, ranked, with zeroes dropped."""
    b = _make_bridge()
    b.guild_id = 99
    fake_db = MagicMock()
    fake_db.get_leaderboard.return_value = [
        {"author_id": 7, "author_name": "peas", "total_points": 255, "lifetime_points": 340},
        {"author_id": 8, "author_name": "techfren", "total_points": 253, "lifetime_points": 253},
        {"author_id": 9, "author_name": "lurker", "total_points": 0, "lifetime_points": 0},
    ]
    with patch.dict("sys.modules", {"database": fake_db}):
        await b.push_leaderboard()

    fake_db.get_leaderboard.assert_called_once_with("99", limit=bridge._LEADERBOARD_LIMIT)
    event = b._queue.get_nowait()
    assert event["type"] == "leaderboard.sync"
    assert event["complete"] is True
    assert event["rows"] == [
        {"discordUserId": "7", "name": "peas", "points": 255, "lifetimePoints": 340},
        {"discordUserId": "8", "name": "techfren", "points": 253, "lifetimePoints": 253},
    ]


@pytest.mark.asyncio
async def test_push_leaderboard_keeps_a_member_who_spent_everything():
    """A zero balance after spending is not the same as never having earned:
    dropping that member would erase the mirror's only record of it."""
    b = _make_bridge()
    b.guild_id = 99
    fake_db = MagicMock()
    fake_db.get_leaderboard.return_value = [
        {"author_id": 7, "author_name": "peas", "total_points": 10, "lifetime_points": 10},
        {"author_id": 8, "author_name": "spender", "total_points": 0, "lifetime_points": 96},
        {"author_id": 9, "author_name": "lurker", "total_points": 0, "lifetime_points": 0},
    ]
    with patch.dict("sys.modules", {"database": fake_db}):
        await b.push_leaderboard()

    rows = b._queue.get_nowait()["rows"]
    assert rows == [
        {"discordUserId": "7", "name": "peas", "points": 10, "lifetimePoints": 10},
        {"discordUserId": "8", "name": "spender", "points": 0, "lifetimePoints": 96},
    ]


@pytest.mark.asyncio
async def test_push_leaderboard_survives_a_bot_without_the_lifetime_column():
    """Rows read before the migration have no lifetime_points; the balance is
    the floor, never a zero that would read as "earned nothing"."""
    b = _make_bridge()
    b.guild_id = 99
    fake_db = MagicMock()
    fake_db.get_leaderboard.return_value = [
        {"author_id": 7, "author_name": "peas", "total_points": 42},
    ]
    with patch.dict("sys.modules", {"database": fake_db}):
        await b.push_leaderboard()

    assert b._queue.get_nowait()["rows"] == [
        {"discordUserId": "7", "name": "peas", "points": 42, "lifetimePoints": 42},
    ]


@pytest.mark.asyncio
async def test_push_leaderboard_never_breaks_the_loop():
    """A database failure must not kill the bridge's leaderboard task."""
    b = _make_bridge()
    b.guild_id = 99
    fake_db = MagicMock()
    fake_db.get_leaderboard.side_effect = RuntimeError("db down")
    with patch.dict("sys.modules", {"database": fake_db}):
        with pytest.raises(RuntimeError):
            await b.push_leaderboard()
    assert b._queue.empty()


@pytest.mark.asyncio
async def test_push_leaderboard_never_publishes_an_empty_board():
    """A sync replaces the mirror, so an empty read must not wipe it."""
    b = _make_bridge()
    b.guild_id = 99
    fake_db = MagicMock()
    fake_db.get_leaderboard.return_value = []
    with patch.dict("sys.modules", {"database": fake_db}):
        await b.push_leaderboard()
    assert b._queue.empty()


@pytest.mark.asyncio
async def test_push_leaderboard_flags_a_truncated_read():
    """Hitting the row cap means absent members are unknown, not removed."""
    b = _make_bridge()
    b.guild_id = 99
    fake_db = MagicMock()
    fake_db.get_leaderboard.return_value = [
        {"author_id": i, "author_name": f"m{i}", "total_points": 1}
        for i in range(bridge._LEADERBOARD_LIMIT)
    ]
    with patch.dict("sys.modules", {"database": fake_db}):
        await b.push_leaderboard()
    assert b._queue.get_nowait()["complete"] is False


def test_edit_carries_attachments_so_images_survive():
    """The receiver rebuilds content from text + attachments; an edit that
    omits them would erase a message's images from the site."""
    b = _make_bridge()
    after = _message(content="now with a caption")
    att = Mock()
    att.url = "https://cdn.discordapp.com/attachments/1/2/shot.png"
    after.attachments = [att]
    after.edited_at = None

    b.on_message_edit(after)

    event = b._queue.get_nowait()
    assert event["type"] == "message.edit"
    assert event["attachmentUrls"] == ["https://cdn.discordapp.com/attachments/1/2/shot.png"]
