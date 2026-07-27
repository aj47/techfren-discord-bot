#!/usr/bin/env python3
"""Standalone launcher for the Hermes validation hook app.

Reads the same env vars as the bot's hook and starts the aiohttp server.
Use only for integration testing or if the bot is unavailable.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from aiohttp import web  # noqa: E402
from hermes_hook import build_app, HERMES_HOOK_BIND, HERMES_HOOK_PORT, HERMES_HOOK_SECRET  # noqa: E402


async def main() -> None:
    if not HERMES_HOOK_SECRET:
        print("Refusing to start without HERMES_HOOK_SECRET", file=sys.stderr)
        sys.exit(2)
    app = build_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, HERMES_HOOK_BIND, HERMES_HOOK_PORT)
    await site.start()
    print(f"Hook listening on http://{HERMES_HOOK_BIND}:{HERMES_HOOK_PORT}")
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
