"""Utility functions for tracking GIF posting frequency per user."""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Deque, Dict, Optional, Tuple

from logging_config import logger

GIF_LIMIT_PER_WINDOW = 1
GIF_TIME_WINDOW = timedelta(minutes=5)

_gif_post_history: Dict[str, Deque[datetime]] = {}
_lock: Optional[asyncio.Lock] = None


def _get_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


def _normalize_timestamp(timestamp: Optional[datetime]) -> datetime:
    if timestamp is None:
        return datetime.now(timezone.utc)

    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)

    return timestamp.astimezone(timezone.utc)


async def check_and_record_gif_post(
    user_id: str, timestamp: Optional[datetime] = None
) -> Tuple[bool, int]:
    """Check whether a user can post a GIF and record the attempt if allowed."""

    now = _normalize_timestamp(timestamp)
    cutoff = now - GIF_TIME_WINDOW

    lock = _get_lock()
    async with lock:
        history = _gif_post_history.get(user_id)
        if history is None:
            history = deque()
            _gif_post_history[user_id] = history

        while history and history[0] <= cutoff:
            history.popleft()

        if len(history) >= GIF_LIMIT_PER_WINDOW:
            next_allowed_time = history[0] + GIF_TIME_WINDOW
            seconds_remaining = int((next_allowed_time - now).total_seconds())
            logger.debug(
                "User %s is over the GIF limit with %d entries; %d seconds remaining",
                user_id,
                len(history),
                seconds_remaining,
            )
            return False, max(seconds_remaining, 0)

        history.append(now)
        logger.debug(
            "Recorded GIF for user %s; %d GIF(s) in the current window",
            user_id,
            len(history),
        )
        return True, 0


__all__ = ["check_and_record_gif_post", "GIF_LIMIT_PER_WINDOW", "GIF_TIME_WINDOW"]
