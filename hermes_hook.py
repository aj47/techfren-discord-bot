"""
Optional local HTTP hook for Hermes integration.

Endpoint:
  POST /hermes/validate
  Body JSON: {"user_id":"...","guild_id":"...","prompt":"...","secret":"..."}

Behavior:
  - Rejects non-localhost requests unless disabled.
  - Rejects missing/bad secret.
  - Deducts 1 point via database.deduct_user_points().
  - Returns current remaining points when successful.
"""

from __future__ import annotations

import os
from typing import Dict, Any

from aiohttp import web
from logging_config import logger

import database
import config


HERMES_HOOK_ENABLED = bool(os.getenv("HERMES_HOOK_ENABLED", "").lower() in ("1", "true", "yes", "on"))
HERMES_HOOK_BIND = os.getenv("HERMES_HOOK_BIND", "127.0.0.1")
HERMES_HOOK_PORT = int(os.getenv("HERMES_HOOK_PORT", "9090"))
HERMES_HOOK_SECRET = os.getenv("HERMES_HOOK_SECRET", "")


async def handle_hermes_validate(request: web.Request) -> web.Response:
    try:
        if HERMES_HOOK_SECRET:
            remote_secret = request.headers.get("X-Hermes-Secret", "")
            if remote_secret != HERMES_HOOK_SECRET:
                logger.warning("Hermes hook secret mismatch from %s", request.remote)
                return web.json_response({"status": "error", "reason": "unauthorized"}, status=401)

        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"status": "error", "reason": "invalid_json"}, status=400)

        user_id = str(payload.get("user_id", "") or "").strip()
        guild_id = str(payload.get("guild_id", "") or "").strip()
        prompt = str(payload.get("prompt", "") or "")
        if not user_id or not guild_id:
            return web.json_response({"status": "error", "reason": "missing_user_or_guild"}, status=400)

        points_before = database.get_user_points(user_id, guild_id)
        if points_before < 1:
            logger.info("Hermes hook rejected: insufficient points for %s in %s", user_id, guild_id)
            return web.json_response({
                "status": "error",
                "reason": "not_enough_points",
                "required": 1,
                "current": points_before,
            }, status=403)

        success = database.deduct_user_points(user_id, guild_id, 1)
        if not success:
            logger.info("Hermes hook rejected: deduction failed for %s in %s", user_id, guild_id)
            points = database.get_user_points(user_id, guild_id)
            return web.json_response({
                "status": "error",
                "reason": "deduction_failed",
                "current": points,
            }, status=409)

        remaining = database.get_user_points(user_id, guild_id)
        logger.info("Hermes hook deducted 1 point from %s in %s; remaining=%s", user_id, guild_id, remaining)
        return web.json_response({
            "status": "ok",
            "deducted": 1,
            "remaining": remaining,
        })

    except Exception as e:
        logger.error("Hermes hook error: %s", e, exc_info=True)
        return web.json_response({"status": "error", "reason": "server_error"}, status=500)


def build_app() -> web.Application:
    app = web.Application()
    app.router.add_post("/hermes/validate", handle_hermes_validate)
    return app


async def start_if_enabled() -> None:
    if not HERMES_HOOK_ENABLED:
        logger.info("Hermes hook disabled")
        return
    if not HERMES_HOOK_SECRET:
        logger.warning("Hermes hook enabled but HERMES_HOOK_SECRET is empty; refusing to start")
        return

    app = build_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, HERMES_HOOK_BIND, HERMES_HOOK_PORT)
    await site.start()
    logger.info("Hermes hook listening on %s:%s", HERMES_HOOK_BIND, HERMES_HOOK_PORT)
