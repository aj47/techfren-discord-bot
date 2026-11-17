"""Delete a message only when every stored message from its author is promo.

The messages table is pruned to about a day, so this keeps its own durable
per-message record. One ordinary message, ever, stops the delete forever.

\"Promotional\" is a fixed list, not a language-model call. It runs on every
message, so it has to be cheap and it has to be wrong in the safe direction:
a pitch it does not recognise is left alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import database
from logging_config import logger


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


def record_message(user_id: str, guild_id: str, message_id: str, content: str) -> None:
    """Remember one message and whether it is promotional. Idempotent on id."""
    database.record_promo_message(
        user_id=str(user_id),
        guild_id=str(guild_id),
        message_id=str(message_id),
        content=content or "",
        is_promo=is_promotional(content or ""),
    )


def verdict_for(user_id: str, guild_id: str, content: str, message_id: str = "") -> Verdict:
    """
    Decide whether to delete this message.

    Counts the message being judged together with everything already stored
    for this member in this guild. A message id that is already stored is not
    counted twice. Deletes only when there are at least MIN_MESSAGES and every
    one of them is promotional.
    """
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

    content = getattr(message, "content", "") or ""
    user_id = str(author.id)
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
