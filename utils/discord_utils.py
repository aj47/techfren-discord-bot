"""
Shared Discord utilities for common Discord patterns.
"""
import discord

# Standard AllowedMentions configuration used throughout the bot
SAFE_ALLOWED_MENTIONS = discord.AllowedMentions(everyone=False, roles=False, users=True)