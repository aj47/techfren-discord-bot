"""Tests for the Fred-mention access nudge.

Pure decision helpers plus a mocked Discord reply. Does not import bot.py.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import config
from fred_mention_nudge import (
    FRED_BOT_USER_ID,
    NUDGE_COOLDOWN,
    clear_nudge_cooldowns,
    handle_fred_mention_nudge,
    has_active_fred_access,
    mentions_fred,
    nudge_text,
    should_nudge_fred_mention,
)


NOW = datetime(2026, 10, 5, 17, 0, tzinfo=timezone.utc)
GUILD = "1010083670599671838"
ROLE = "fred-access"


def _should(**overrides):
    defaults = dict(
        author_is_bot=False,
        guild_id=GUILD,
        mentioned_user_ids=[FRED_BOT_USER_ID],
        content=f"<@{FRED_BOT_USER_ID}> hello",
        role_names=["fren"],
        expiry=None,
        now=NOW,
        last_nudge_at=None,
        access_role_name=ROLE,
    )
    defaults.update(overrides)
    return should_nudge_fred_mention(**defaults)


class TestMentionsFred:
    def test_mentions_list(self):
        assert mentions_fred([FRED_BOT_USER_ID], "hey") is True

    def test_mentions_list_int(self):
        assert mentions_fred([int(FRED_BOT_USER_ID)], "") is True

    def test_raw_markup(self):
        assert mentions_fred([], f"hi <@{FRED_BOT_USER_ID}>") is True

    def test_nick_markup(self):
        assert mentions_fred([], f"<@!{FRED_BOT_USER_ID}>") is True

    def test_other_bot_is_not_fred(self):
        assert mentions_fred(["1505312558377340989"], "<@1505312558377340989>") is False

    def test_plain_word_fred_is_not_a_mention(self):
        assert mentions_fred([], "fred didn't respond") is False


class TestHasActiveAccess:
    def test_role_counts(self):
        assert has_active_fred_access([ROLE], None, NOW, ROLE) is True

    def test_future_grant_counts(self):
        expiry = NOW + timedelta(minutes=30)
        assert has_active_fred_access(["fren"], expiry, NOW, ROLE) is True

    def test_expired_grant_does_not(self):
        expiry = NOW - timedelta(minutes=1)
        assert has_active_fred_access(["fren"], expiry, NOW, ROLE) is False

    def test_never_redeemed(self):
        assert has_active_fred_access(["fren"], None, NOW, ROLE) is False


class TestShouldNudge:
    def test_ping_without_access(self):
        assert _should() is True

    def test_no_mention(self):
        assert _should(mentioned_user_ids=[], content="hello") is False

    def test_has_role(self):
        assert _should(role_names=[ROLE]) is False

    def test_has_active_grant(self):
        assert _should(expiry=NOW + timedelta(hours=1)) is False

    def test_expired_grant_without_role(self):
        assert _should(expiry=NOW - timedelta(hours=1)) is True

    def test_bot_author(self):
        assert _should(author_is_bot=True) is False

    def test_dm(self):
        assert _should(guild_id=None) is False

    def test_cooldown_blocks_repeat(self):
        assert _should(last_nudge_at=NOW - timedelta(minutes=2)) is False

    def test_cooldown_expired(self):
        assert _should(last_nudge_at=NOW - NUDGE_COOLDOWN) is True

    def test_peasbot_mention_is_ignored(self):
        peas = "1505312558377340989"
        assert _should(mentioned_user_ids=[peas], content=f"<@{peas}>") is False


class TestNudgeText:
    def test_plain_command(self):
        text = nudge_text(10, 1)
        assert "`/fred`" in text
        assert "10 points / 1 hour" in text

    def test_clickable_command(self):
        text = nudge_text(10, 1, command_id="123")
        assert "</fred:123>" in text
        assert "`/fred`" not in text

    def test_matches_live_config_defaults(self):
        text = nudge_text(config.FRENBOT_ACCESS_COST, config.FRENBOT_ACCESS_DURATION_HOURS)
        assert "10 points / 1 hour" in text


def _message(*, bot=False, guild=True, mentions=None, content=None, roles=None):
    message = MagicMock()
    message.id = 1556712839119642665
    message.content = content if content is not None else f"<@{FRED_BOT_USER_ID}> hi"
    message.author.bot = bot
    message.author.id = 1255850818423357510
    message.author.name = "astrixbob"
    message.author.roles = []
    for name in roles or ["fren"]:
        mock_role = MagicMock()
        mock_role.name = name
        message.author.roles.append(mock_role)
    if mentions is None:
        user = MagicMock()
        user.id = int(FRED_BOT_USER_ID)
        message.mentions = [user]
    else:
        message.mentions = mentions
    if guild:
        message.guild.id = int(GUILD)
    else:
        message.guild = None
    message.reply = AsyncMock()
    return message


@pytest.fixture(autouse=True)
def _clean_cooldowns():
    clear_nudge_cooldowns()
    yield
    clear_nudge_cooldowns()


@pytest.mark.asyncio
async def test_handler_replies_when_no_access():
    message = _message()
    with patch("fred_mention_nudge.database.get_frenbot_access_expiry", return_value=None):
        posted = await handle_fred_mention_nudge(message, command_id="99")
    assert posted is True
    message.reply.assert_awaited_once()
    sent = message.reply.await_args.args[0]
    assert "</fred:99>" in sent
    assert "10 points / 1 hour" in sent
    assert message.reply.await_args.kwargs["mention_author"] is False


@pytest.mark.asyncio
async def test_handler_skips_when_role_held():
    message = _message(roles=["fred-access"])
    with patch("fred_mention_nudge.database.get_frenbot_access_expiry", return_value=None):
        posted = await handle_fred_mention_nudge(message)
    assert posted is False
    message.reply.assert_not_awaited()


@pytest.mark.asyncio
async def test_handler_skips_bots_and_dms():
    with patch("fred_mention_nudge.database.get_frenbot_access_expiry", return_value=None):
        bot_msg = _message(bot=True)
        assert await handle_fred_mention_nudge(bot_msg) is False
        bot_msg.reply.assert_not_awaited()

        dm = _message(guild=False)
        assert await handle_fred_mention_nudge(dm) is False
        dm.reply.assert_not_awaited()


@pytest.mark.asyncio
async def test_handler_cooldown_after_first_reply():
    first = _message()
    second = _message()
    with patch("fred_mention_nudge.database.get_frenbot_access_expiry", return_value=None):
        assert await handle_fred_mention_nudge(first) is True
        assert await handle_fred_mention_nudge(second) is False
    first.reply.assert_awaited_once()
    second.reply.assert_not_awaited()
