"""Delete a message only when every stored message from its author is promo.

The messages table is pruned to about a day, so this keeps its own durable
per-message record. One ordinary message, ever, stops the delete forever.

\"Promotional\" is a fixed list, not a language-model call. It runs on every
message, so it has to be cheap and it has to be wrong in the safe direction:
a pitch it does not recognise is left alone.
"""

from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Optional

import database
from logging_config import logger


# Holders of these roles are never deleted. Ids, not names: a self-assigned
# role can copy a name, and it cannot copy an id.
EXEMPT_ROLE_IDS = frozenset({
    "1235430975870210149",  # legend
    "1303355924903104563",  # MVP
    "1303354826251436045",  # active
})


# Short pitches and off-platform funnels. A bare link is not enough: members
# share GitHub and docs links all day.
_PROMO_PATTERNS = (
    r"discord\.gg/\S+",
    r"discord(?:app)?\.com/invite/\S+",
    r"(?:https?://)?t\.me/\S+",
    r"(?:https?://)?wa\.me/\S+",
    r"chat\.whatsapp\.com/\S+",
    r"\bdm me\b",
    r"\bfree airdrop\b",
    r"\bclaim (?:your |free )?(?:tokens|airdrop|nft)\b",
    r"\bearn \$\d+",
    r"\blimited time\b",
)

_PROMO_RE = re.compile("|".join(_PROMO_PATTERNS), re.IGNORECASE)


@dataclass(frozen=True)
class Verdict:
    """What to do with one message, given the author's stored history."""

    delete: bool
    total: int
    promo: int
    reason: str


def is_promotional(content: str) -> bool:
    """True when the text matches a known promotional pattern."""
    if not content:
        return False
    return _PROMO_RE.search(content) is not None


DEFAULT_ARCHIVE = os.path.expanduser("~/.local/share/discrawl/discrawl.db")


def load_archive_history(user_id: str, guild_id: str, archive_path: str = DEFAULT_ARCHIVE) -> int:
    """Copy this member's older messages in, once.

    Returns how many were copied. Returns 0 when the member was already loaded.
    A missing or unreadable archive is logged and skipped. It must not look
    like an all-promo history.
    """
    user_id, guild_id = str(user_id), str(guild_id)
    if database.promo_history_loaded(user_id, guild_id):
        return 0
    try:
        uri = f"file:{archive_path}?mode=ro"
        with sqlite3.connect(uri, uri=True) as conn:
            rows = conn.execute(
                "SELECT id, content FROM messages WHERE author_id = ? AND guild_id = ?",
                (user_id, guild_id),
            ).fetchall()
    except Exception as exc:
        logger.error(f"Promo-only: could not read history for {user_id}: {exc}")
        return 0
    copied = 0
    for message_id, content in rows:
        if database.promo_message_exists(str(message_id)):
            continue
        record_message(user_id, guild_id, str(message_id), content or "")
        copied += 1
    database.mark_promo_history_loaded(user_id, guild_id)
    return copied


def record_message(user_id: str, guild_id: str, message_id: str, content: str) -> None:
    """Remember one message and whether it is promotional. Idempotent on id."""
    database.record_promo_message(
        user_id=str(user_id),
        guild_id=str(guild_id),
        message_id=str(message_id),
        content=content or "",
        is_promo=is_promotional(content or ""),
    )


def holds_exempt_role(roles) -> bool:
    """True when the member holds legend, MVP, or active."""
    for role in roles or []:
        if str(getattr(role, "id", "")) in EXEMPT_ROLE_IDS:
            return True
    return False


def verdict_for(user_id: str, guild_id: str, content: str, message_id: str = "", exempt: bool = False) -> Verdict:
    """
    Decide whether to delete this message.

    Counts the message being judged together with everything already stored
    for this member in this guild. A message id that is already stored is not
    counted twice. Deletes only when every stored message is promotional.
    An exempt role is never deleted, whatever the history says.
    """
    if exempt:
        return Verdict(False, 0, 0, "exempt role")
    counts = database.promo_message_counts(str(user_id), str(guild_id))
    already_stored = bool(message_id) and database.promo_message_exists(
        str(message_id)
    )
    total = counts["total"] + (0 if already_stored else 1)
    promo = counts["promo"] + (
        0 if already_stored else (1 if is_promotional(content or "") else 0)
    )

    if promo == total and total >= 1:
        return Verdict(True, total, promo, "all stored messages are promotional")
    return Verdict(False, total, promo, "history is not all promotional")


def note_decision(verdict: Verdict, user_id: str, channel_name: str) -> None:
    """Log a would-delete. Dry-run callers use this and then do nothing."""
    if verdict.delete:
        logger.warning(
            f"Promo-only DRY RUN: would delete message from {user_id} "
            f"(#{channel_name}) - {verdict.promo}/{verdict.total} promotional"
        )


async def handle_promo_message(message, enabled: bool, dry_run: bool) -> Optional[Verdict]:
    """
    Record the message, judge the author's history, and delete only when live.

    Returns None when the check does not apply (disabled, a bot, no guild).
    A delete that Discord refuses is logged and swallowed: this must not break
    the rest of message handling.
    """
    if not enabled:
        return None
    author = getattr(message, "author", None)
    guild = getattr(message, "guild", None)
    if author is None or guild is None:
        return None
    if getattr(author, "bot", False) or getattr(message, "webhook_id", None):
        return None
    if holds_exempt_role(getattr(author, "roles", ())):
        return Verdict(False, 0, 0, "exempt role")

    content = getattr(message, "content", "") or ""
    user_id = str(author.id)
    load_archive_history(user_id, str(guild.id))
    record_message(user_id, str(guild.id), str(message.id), content)
    verdict = verdict_for(user_id, str(guild.id), content, message_id=str(message.id))

    if not verdict.delete:
        return verdict
    if dry_run:
        channel = getattr(message, "channel", None)
        note_decision(verdict, user_id, str(getattr(channel, "name", "?")))
        return verdict

    try:
        await message.delete()
        logger.warning(
            f"Promo-only: deleted message {message.id} from {user_id} "
            f"- {verdict.promo}/{verdict.total} promotional"
        )
    except Exception as exc:
        logger.error(f"Promo-only: could not delete message {message.id}: {exc}")
    return verdict
