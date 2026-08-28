"""
Bridge: forwards Discord activity to the techfriendcommunity Convex backend.

Self-contained by design — plain async functions called from bot.py's existing
event handlers (see BRIDGE.md). Never raises into the caller; a bridge outage
must not affect the rest of the bot.

Events are batched and POSTed to <CONVEX_INGEST_URL> with a bearer secret.
Outbound web/email posts do NOT go through this module: the backend posts
straight to per-channel Discord webhooks that this module creates on startup.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any, Optional

import aiohttp
import discord

logger = logging.getLogger(__name__)

WEBHOOK_NAME = "techfriendcommunity"
LINK_RE = re.compile(r"^!link\s+([A-Za-z0-9]{6})\s*$")
_MAX_BATCH = 100
_FLUSH_INTERVAL = 1.0
_MAX_RETRY_DELAY = 60.0
_LEADERBOARD_INTERVAL = 600.0  # seconds between leaderboard pushes


def _cfg(name: str, default: Optional[str] = None) -> Optional[str]:
    """Read a setting from config.py if importable, else from the environment."""
    try:
        import config  # noqa: WPS433

        val = getattr(config, name.lower(), None)
        if val is not None:
            return str(val)
    except Exception:
        pass
    return os.getenv(name, default)


class Bridge:
    def __init__(self, url: str, secret: str, guild_id: Optional[int], excluded: set[int]):
        self.url = url.rstrip("/")
        self.secret = secret
        self.guild_id = guild_id
        self.excluded = excluded
        self.channel_ids: set[int] = set()
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._session: Optional[aiohttp.ClientSession] = None
        self._task: Optional[asyncio.Task] = None
        self._leaderboard_task: Optional[asyncio.Task] = None
        self._bot: Optional[discord.Client] = None

    # -- lifecycle -----------------------------------------------------------
    async def start(self, bot: discord.Client) -> None:
        self._bot = bot
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._flush_loop(), name="bridge-flush")
        if self._leaderboard_task is None or self._leaderboard_task.done():
            self._leaderboard_task = asyncio.create_task(self._leaderboard_loop(), name="bridge-leaderboard")
        await self.sync_channels()
        logger.info("bridge started: %d channels mirrored -> %s", len(self.channel_ids), self.url)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None
        if self._leaderboard_task:
            self._leaderboard_task.cancel()
            self._leaderboard_task = None
        await self._flush(drain=True)
        if self._session:
            await self._session.close()
            self._session = None

    # -- channel sync + webhooks --------------------------------------------
    def _guilds(self) -> list[discord.Guild]:
        assert self._bot is not None
        guilds = list(self._bot.guilds)
        if self.guild_id:
            guilds = [g for g in guilds if g.id == self.guild_id]
        return guilds

    def _is_public(self, channel: discord.TextChannel) -> bool:
        if channel.id in self.excluded:
            return False
        perms = channel.permissions_for(channel.guild.default_role)
        return perms.view_channel and perms.read_message_history

    async def _ensure_webhook(self, channel: discord.TextChannel) -> Optional[str]:
        try:
            for wh in await channel.webhooks():
                if wh.name == WEBHOOK_NAME and wh.url:
                    return wh.url
            wh = await channel.create_webhook(name=WEBHOOK_NAME, reason="techfriendcommunity web bridge")
            return wh.url
        except discord.Forbidden:
            logger.warning("bridge: no Manage Webhooks permission in #%s; web posting disabled there", channel.name)
        except Exception as e:  # noqa: BLE001
            logger.warning("bridge: webhook setup failed for #%s: %s", channel.name, e)
        return None

    async def sync_channels(self) -> None:
        payload = []
        for guild in self._guilds():
            for ch in sorted(guild.text_channels, key=lambda c: c.position):
                if not self._is_public(ch):
                    continue
                self.channel_ids.add(ch.id)
                payload.append({
                    "id": str(ch.id),
                    "name": ch.name,
                    "topic": ch.topic,
                    "position": ch.position,
                    "webhookUrl": await self._ensure_webhook(ch),
                })
        if payload:
            self.enqueue({"type": "channel.sync", "channels": payload})

    # -- event builders ------------------------------------------------------
    def enqueue(self, event: dict[str, Any]) -> None:
        self._queue.put_nowait(event)

    def on_message(self, message: discord.Message) -> None:
        if message.channel.id not in self.channel_ids:
            return
        if message.type not in (discord.MessageType.default, discord.MessageType.reply):
            return
        m = LINK_RE.match(message.content or "")
        if m and not message.author.bot:
            self.enqueue({
                "type": "link.code",
                "code": m.group(1).upper(),
                "discordUserId": str(message.author.id),
                "name": message.author.display_name,
                "avatar": str(message.author.display_avatar.url),
            })
            asyncio.create_task(self._ack_link(message))
            return
        self.enqueue({
            "type": "message.create",
            "id": str(message.id),
            "channelId": str(message.channel.id),
            "authorId": str(message.author.id),
            "authorName": message.author.display_name,
            "authorAvatar": str(message.author.display_avatar.url),
            "isBot": bool(message.author.bot),
            "webhookId": str(message.webhook_id) if message.webhook_id else None,
            "content": message.content or "",
            "createdAt": int(message.created_at.timestamp() * 1000),
            "replyToId": str(message.reference.message_id) if message.reference and message.reference.message_id else None,
            "attachmentUrls": [a.url for a in message.attachments],
        })

    async def _ack_link(self, message: discord.Message) -> None:
        try:
            await message.add_reaction("✅")
        except Exception:  # noqa: BLE001
            pass

    def on_message_edit(self, after: discord.Message) -> None:
        if after.channel.id not in self.channel_ids:
            return
        self.enqueue({
            "type": "message.edit",
            "id": str(after.id),
            "content": after.content or "",
            "editedAt": int((after.edited_at or after.created_at).timestamp() * 1000),
        })

    def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent) -> None:
        if payload.channel_id not in self.channel_ids:
            return
        self.enqueue({"type": "message.delete", "id": str(payload.message_id)})

    def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.channel_id not in self.channel_ids:
            return
        self.enqueue({
            "type": "reaction.add",
            "messageId": str(payload.message_id),
            "emoji": str(payload.emoji),
            "userId": str(payload.user_id),
        })

    # -- leaderboard mirror --------------------------------------------------
    # The bot's user_points table is the community's only points system. The web
    # app renders it read-only, so push it here on a timer rather than letting
    # the site compute a competing score.
    def _leaderboard_rows(self) -> list[dict[str, Any]]:
        import database  # imported lazily so bridge.py stays standalone-runnable

        guild_ids = [str(self.guild_id)] if self.guild_id else [str(g.id) for g in self._guilds()]
        rows = []
        for gid in guild_ids:
            for entry in database.get_leaderboard(gid, limit=1000):
                points = int(entry.get("total_points") or 0)
                if points <= 0:
                    continue
                rows.append({
                    "discordUserId": str(entry["author_id"]),
                    "name": entry.get("author_name") or "member",
                    "points": points,
                })
        rows.sort(key=lambda r: r["points"], reverse=True)
        return rows

    async def push_leaderboard(self) -> None:
        rows = await asyncio.to_thread(self._leaderboard_rows)
        if not rows:
            # A sync replaces the mirror wholesale, so an empty push would clear
            # the published leaderboard. No-one having any points is not a real
            # state; an empty read means the bot's database was unreadable.
            logger.warning("bridge: leaderboard read came back empty, not pushing")
            return
        self.enqueue({"type": "leaderboard.sync", "rows": rows})
        logger.info("bridge: leaderboard mirrored (%d members)", len(rows))

    async def _leaderboard_loop(self) -> None:
        while True:
            try:
                await self.push_leaderboard()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                logger.warning("bridge leaderboard push failed: %s", e)
            try:
                await asyncio.sleep(_LEADERBOARD_INTERVAL)
            except asyncio.CancelledError:
                raise

    # -- delivery ------------------------------------------------------------
    async def _flush_loop(self) -> None:
        delay = _FLUSH_INTERVAL
        while True:
            try:
                await asyncio.sleep(delay)
                ok = await self._flush()
                delay = _FLUSH_INTERVAL if ok else min(_MAX_RETRY_DELAY, delay * 2)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                logger.warning("bridge flush loop error: %s", e)
                delay = min(_MAX_RETRY_DELAY, delay * 2)

    async def _flush(self, drain: bool = False) -> bool:
        if self._session is None:
            return False
        while not self._queue.empty():
            batch: list[dict[str, Any]] = []
            while not self._queue.empty() and len(batch) < _MAX_BATCH:
                batch.append(self._queue.get_nowait())
            try:
                async with self._session.post(
                    f"{self.url}/discord/ingest",
                    json={"events": batch},
                    headers={"Authorization": f"Bearer {self.secret}"},
                ) as resp:
                    if resp.status >= 400:
                        text = await resp.text()
                        logger.warning("bridge ingest %s: %s", resp.status, text[:200])
                        if resp.status in (400, 413):
                            continue  # malformed batch: drop rather than loop forever
                        raise RuntimeError(f"ingest {resp.status}")
            except Exception as e:  # noqa: BLE001
                # Requeue at the front by rebuilding the queue; batches are small.
                pending = batch + [self._queue.get_nowait() for _ in range(self._queue.qsize())]
                for ev in pending:
                    self._queue.put_nowait(ev)
                if not drain:
                    logger.warning("bridge delivery failed, will retry: %s", e)
                return False
        return True


# ---- module-level API used by bot.py -----------------------------------------
_bridge: Optional[Bridge] = None


def bridge_enabled() -> bool:
    return (_cfg("BRIDGE_ENABLED", "false") or "false").lower() in ("1", "true", "yes")


async def start_bridge(bot: discord.Client) -> None:
    """Call from on_ready. No-op unless BRIDGE_ENABLED, CONVEX_INGEST_URL, BRIDGE_SECRET are set."""
    global _bridge
    try:
        if not bridge_enabled():
            return
        url, secret = _cfg("CONVEX_INGEST_URL"), _cfg("BRIDGE_SECRET")
        if not url or not secret:
            logger.warning("bridge enabled but CONVEX_INGEST_URL / BRIDGE_SECRET missing; not starting")
            return
        guild_id = _cfg("BRIDGE_GUILD_ID")
        excluded = {int(x) for x in (_cfg("BRIDGE_EXCLUDE_CHANNEL_IDS", "") or "").split(",") if x.strip()}
        if _bridge is None:
            _bridge = Bridge(url, secret, int(guild_id) if guild_id else None, excluded)
        await _bridge.start(bot)
    except Exception as e:  # noqa: BLE001
        logger.error("bridge failed to start: %s", e)


async def stop_bridge() -> None:
    global _bridge
    if _bridge:
        await _bridge.stop()
        _bridge = None


def _safe(fn, *args) -> None:
    try:
        if _bridge is not None:
            fn(*args)
    except Exception as e:  # noqa: BLE001
        logger.warning("bridge event error: %s", e)


async def handle_bridge_message(message: discord.Message) -> None:
    _safe(lambda m: _bridge.on_message(m), message)  # type: ignore[union-attr]


async def handle_bridge_message_edit(before: discord.Message, after: discord.Message) -> None:
    _safe(lambda a: _bridge.on_message_edit(a), after)  # type: ignore[union-attr]


async def handle_bridge_message_delete(payload: discord.RawMessageDeleteEvent) -> None:
    _safe(lambda p: _bridge.on_raw_message_delete(p), payload)  # type: ignore[union-attr]


async def handle_bridge_reaction(payload: discord.RawReactionActionEvent) -> None:
    _safe(lambda p: _bridge.on_raw_reaction_add(p), payload)  # type: ignore[union-attr]
