"""
Honeypot handler module for the Discord bot.
Handles automatic banning of users who post in honeypot channels.
"""

import discord
from discord import app_commands
from datetime import datetime, timezone
from typing import Optional
import database
from logging_config import logger


async def is_honeypot_channel(channel_id: str, guild_id: str) -> bool:
    """
    Check if a channel is a honeypot channel.
    
    Args:
        channel_id: The Discord channel ID
        guild_id: The Discord guild ID
        
    Returns:
        bool: True if the channel is a honeypot, False otherwise
    """
    return database.is_honeypot_channel(channel_id, guild_id)


async def handle_honeypot_message(message: discord.Message) -> bool:
    """
    Handle a message posted in a honeypot channel.
    Bans the user and deletes their messages.
    
    Args:
        message: The Discord message
        
    Returns:
        bool: True if the user was banned, False otherwise
    """
    if not message.guild:
        return False
    
    # Skip bot messages
    if message.author.bot:
        return False
    
    # Skip users with admin/manage guild permissions
    if isinstance(message.author, discord.Member):
        if message.author.guild_permissions.administrator or message.author.guild_permissions.manage_guild:
            logger.info(f"Skipping honeypot ban for admin user {message.author.id} in guild {message.guild.id}")
            return False
    
    try:
        # Ban the user and delete their messages from the last 24 hours (86400 seconds)
        await message.author.ban(
            reason=f"Posted in honeypot channel #{message.channel.name}",
            delete_message_seconds=86400  # 24 hours
        )
        
        logger.warning(
            f"HONEYPOT BAN: User {message.author} ({message.author.id}) banned for posting in "
            f"honeypot channel {message.channel.name} ({message.channel.id}) in guild {message.guild.name}"
        )
        
        # Log to mod channel if configured
        await log_honeypot_ban(message)
        
        return True
        
    except discord.Forbidden:
        logger.error(f"Failed to ban user {message.author.id}: Bot lacks permission")
    except discord.HTTPException as e:
        logger.error(f"Failed to ban user {message.author.id}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error banning user {message.author.id}: {e}", exc_info=True)
    
    return False


async def log_honeypot_ban(message: discord.Message):
    """
    Log a honeypot ban to the configured mod log channel.
    
    Args:
        message: The message that triggered the ban
    """
    import config
    
    if not message.guild:
        return
    
    # Get mod log channel from config (if set)
    mod_log_channel_id = getattr(config, 'MOD_LOG_CHANNEL_ID', None)
    
    # Also check for guild-specific mod log channels
    guild_mod_log_channels = getattr(config, 'GUILD_MOD_LOG_CHANNELS', {})
    guild_specific_channel = guild_mod_log_channels.get(str(message.guild.id))
    
    # Use guild-specific channel if available, otherwise fall back to global
    target_channel_id = guild_specific_channel or mod_log_channel_id
    
    if not target_channel_id:
        return
    
    try:
        log_channel = message.guild.get_channel(int(target_channel_id))
        if not log_channel:
            logger.warning(f"Mod log channel {target_channel_id} not found in guild {message.guild.id}")
            return
        
        # Create embed for the log
        embed = discord.Embed(
            title="🍯 Honeypot Ban",
            description=f"A user was automatically banned for posting in a honeypot channel.",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(name="User", value=f"{message.author.mention} ({message.author.id})", inline=False)
        embed.add_field(name="Channel", value=f"{message.channel.mention} ({message.channel.id})", inline=False)
        embed.add_field(name="Message Content", value=message.content[:1000] if message.content else "*(No text content)*", inline=False)
        
        if message.attachments:
            attachment_info = f"{len(message.attachments)} attachment(s)"
            for i, att in enumerate(message.attachments[:3], 1):
                attachment_info += f"\n{i}. {att.filename}"
            if len(message.attachments) > 3:
                attachment_info += f"\n... and {len(message.attachments) - 3} more"
            embed.add_field(name="Attachments", value=attachment_info, inline=False)
        
        await log_channel.send(embed=embed)
        
    except Exception as e:
        logger.error(f"Failed to log honeypot ban: {e}", exc_info=True)


async def set_honeypot_channel(
    channel: discord.TextChannel,
    admin_user: discord.User
) -> bool:
    """
    Set a channel as a honeypot channel.
    
    Args:
        channel: The channel to set as honeypot
        admin_user: The admin who set the honeypot
        
    Returns:
        bool: True if successful, False otherwise
    """
    result = database.add_honeypot_channel(
        str(channel.id),
        channel.name,
        str(channel.guild.id),
        channel.guild.name,
        str(admin_user.id),
        admin_user.name
    )
    
    if result:
        logger.info(f"Set channel {channel.name} ({channel.id}) as honeypot in guild {channel.guild.id}")
        
        # Set channel topic to warn humans (but bots won't read it)
        try:
            await channel.edit(topic="🍯 HONEYPOT CHANNEL - DO NOT POST HERE. This channel is used to catch spammers. Real users cannot see this channel.")
        except discord.Forbidden:
            logger.warning(f"Could not set honeypot topic for channel {channel.id}: No permission")
        except Exception as e:
            logger.warning(f"Could not set honeypot topic for channel {channel.id}: {e}")
    
    return result


async def remove_honeypot_channel(channel: discord.TextChannel) -> bool:
    """
    Remove a channel from being a honeypot channel.
    
    Args:
        channel: The channel to remove from honeypot
        
    Returns:
        bool: True if successful, False otherwise
    """
    result = database.remove_honeypot_channel(str(channel.id), str(channel.guild.id))
    
    if result:
        logger.info(f"Removed channel {channel.name} ({channel.id}) from honeypot in guild {channel.guild.id}")
        
        # Clear channel topic
        try:
            await channel.edit(topic=None)
        except discord.Forbidden:
            logger.warning(f"Could not clear honeypot topic for channel {channel.id}: No permission")
        except Exception as e:
            logger.warning(f"Could not clear honeypot topic for channel {channel.id}: {e}")
    
    return result


async def get_guild_honeypot_channels(guild_id: str) -> list:
    """
    Get all honeypot channels for a guild.
    
    Args:
        guild_id: The Discord guild ID
        
    Returns:
        List of honeypot channel records
    """
    return database.get_honeypot_channels_for_guild(guild_id)
