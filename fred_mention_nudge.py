"""
Nudge people who ping Fred without having paid for access.

Fred (frenbot, guild nick ``fred``) only answers members who hold the
``fred-access`` role, which ``/fred`` grants for a timed window. Without a
hint, a mention just sits there. tfbot replies once, pointing at ``/fred``.

Decision helpers are pure so they can be tested without importing ``bot.py``
(that file takes the single-instance lock while production is running).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, Optional, Sequence, Tuple

import discord

import config
import database
from logging_config import logger


# frenbot#0588 — the account whose guild nick is Fred. Not peasbot, not tfbot.
FRED_BOT_USER_ID = "1462905798702268661"

# Don't stack a nudge on every ping in a thread. 10 minutes per member/guild.
NUDGE_COOLDOWN = timedelta(minutes=10)

# In-memory last-nudge times. Process-local is enough: a restart just
# re-allows one extra reply, which is better than a DB write for a hint.
_last_nudge_at: Dict[Tuple[str, str], datetime] = {}


def _as_id_set(ids: Iterable[object]) -> set:
    return {str(i) for i in ids if i is not None}


def mentions_fred(
    mentioned_user_ids: Iterable[object],
    content: Optional[str],
    fred_user_id: str = FRED_BOT_USER_ID,
) -> bool:
    """True if the message pings Fred, via the mentions list or raw markup."""
    fred_id = str(fred_user_id)
    if fred_id in _as_id_set(mentioned_user_ids):
        return True
    text = content or ""
    return f"<@{fred_id}>" in text or f"<@!{fred_id}>" in text


def has_active_fred_access(
    role_names: Iterable[str],
    expiry: Optional[datetime],
    now: datetime,
    access_role_name: str,
) -> bool:
    """
    True if the member can already talk to Fred.

    Either the live Discord role *or* an unexpired grant counts: the role is
    what Fred itself checks, the grant is what ``/fred`` recorded. Skip the
    nudge if either is true so we don't tell someone who just paid to pay again.
    """
    if access_role_name in set(role_names):
        return True
    if expiry is None:
        return False
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return expiry > now


def cooldown_blocks(
    last_nudge_at: Optional[datetime],
    now: datetime,
    cooldown: timedelta = NUDGE_COOLDOWN,
) -> bool:
    """True if we already nudged this member inside the cooldown window."""
    if last_nudge_at is None:
        return False
    if last_nudge_at.tzinfo is None:
        last_nudge_at = last_nudge_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now - last_nudge_at < cooldown


def should_nudge_fred_mention(
    *,
    author_is_bot: bool,
    guild_id: Optional[str],
    mentioned_user_ids: Iterable[object],
    content: Optional[str],
    role_names: Iterable[str],
    expiry: Optional[datetime],
    now: datetime,
    last_nudge_at: Optional[datetime],
    access_role_name: str,
    fred_user_id: str = FRED_BOT_USER_ID,
    cooldown: timedelta = NUDGE_COOLDOWN,
) -> bool:
    """Decide whether tfbot should reply. No I/O."""
    if author_is_bot or not guild_id:
        return False
    if not mentions_fred(mentioned_user_ids, content, fred_user_id):
        return False
    if has_active_fred_access(role_names, expiry, now, access_role_name):
        return False
    if cooldown_blocks(last_nudge_at, now, cooldown):
        return False
    return True


def nudge_text(
    cost: int,
    hours: int,
    command_id: Optional[str] = None,
) -> str:
    """One-line hint. Clickable slash mention when we know the command id."""
    command = f"</fred:{command_id}>" if command_id else "`/fred`"
    hour_label = "hour" if hours == 1 else "hours"
    point_label = "point" if cost == 1 else "points"
    return (
        f"Fred only answers after you enable access with {command} "
        f"({cost} {point_label} / {hours} {hour_label})."
    )


def _member_role_names(author: object) -> Sequence[str]:
    roles = getattr(author, "roles", None) or ()
    return [getattr(role, "name", "") for role in roles]


def _mentioned_user_ids(message: discord.Message) -> Sequence[str]:
    mentions = getattr(message, "mentions", None) or ()
    return [str(user.id) for user in mentions if getattr(user, "id", None)]


def remember_nudge(guild_id: str, user_id: str, when: datetime) -> None:
    _last_nudge_at[(str(guild_id), str(user_id))] = when


def last_nudge(guild_id: str, user_id: str) -> Optional[datetime]:
    return _last_nudge_at.get((str(guild_id), str(user_id)))


def clear_nudge_cooldowns() -> None:
    """Test helper."""
    _last_nudge_at.clear()


async def handle_fred_mention_nudge(
    message: discord.Message,
    command_id: Optional[str] = None,
) -> bool:
    """
    Reply if this is a Fred ping from someone without access.

    Returns True when a nudge was posted. Failures are logged and swallowed
    so a Discord hiccup never blocks the rest of on_message.
    """
    try:
        if message.guild is None or message.author.bot:
            return False

        guild_id = str(message.guild.id)
        user_id = str(message.author.id)
        now = datetime.now(timezone.utc)
        role_name = getattr(config, "FRENBOT_ACCESS_ROLE_NAME", "fred-access")

        expiry = database.get_frenbot_access_expiry(user_id, guild_id)
        if not should_nudge_fred_mention(
            author_is_bot=False,
            guild_id=guild_id,
            mentioned_user_ids=_mentioned_user_ids(message),
            content=message.content,
            role_names=_member_role_names(message.author),
            expiry=expiry,
            now=now,
            last_nudge_at=last_nudge(guild_id, user_id),
            access_role_name=role_name,
        ):
            return False

        cost = getattr(config, "FRENBOT_ACCESS_COST", 10)
        hours = getattr(config, "FRENBOT_ACCESS_DURATION_HOURS", 1)
        text = nudge_text(cost, hours, command_id=command_id)

        await message.reply(
            text,
            mention_author=False,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        remember_nudge(guild_id, user_id, now)
        logger.info(
            "Nudged %s (%s) in guild %s to /fred after a Fred mention",
            getattr(message.author, "name", user_id),
            user_id,
            guild_id,
        )
        return True
    except discord.Forbidden:
        logger.warning(
            "No permission to reply with a Fred-access nudge on message %s",
            getattr(message, "id", "?"),
        )
        return False
    except discord.HTTPException as e:
        logger.warning(
            "Failed to reply with a Fred-access nudge on message %s: %s",
            getattr(message, "id", "?"),
            e,
        )
        return False
    except Exception as e:
        logger.error(
            "Error handling Fred-access nudge for message %s: %s",
            getattr(message, "id", "?"),
            e,
            exc_info=True,
        )
        return False
