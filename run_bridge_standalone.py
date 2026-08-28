"""
Run ONLY the techfriendcommunity bridge under its own bot token.

Useful for running the mirror from another machine before the main bot is
redeployed. Same bridge.py, same env vars:
  DISCORD_BOT_TOKEN, CONVEX_INGEST_URL, BRIDGE_SECRET, [BRIDGE_GUILD_ID], [BRIDGE_EXCLUDE_CHANNEL_IDS]
Requires the Message Content intent and Manage Webhooks permission.
"""
import logging
import os

import discord
from dotenv import load_dotenv

import bridge

load_dotenv(override=True)
os.environ.setdefault("BRIDGE_ENABLED", "true")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = False

client = discord.Client(intents=intents)


@client.event
async def on_ready():
    logging.info("standalone bridge logged in as %s", client.user)
    await bridge.start_bridge(client)


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return
    await bridge.handle_bridge_message(message)


@client.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    await bridge.handle_bridge_message_edit(before, after)


@client.event
async def on_raw_message_delete(payload: discord.RawMessageDeleteEvent):
    await bridge.handle_bridge_message_delete(payload)


@client.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    await bridge.handle_bridge_reaction(payload)


if __name__ == "__main__":
    token = os.environ["DISCORD_BOT_TOKEN"]
    client.run(token)
