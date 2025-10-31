import discord
import re
from typing import Optional, Dict, Any
import logging

def generate_discord_message_link(guild_id: str, channel_id: str, message_id: str) -> str:
    """
    Generate a Discord message link from guild ID, channel ID, and message ID.

    Args:
        guild_id (str): The Discord guild (server) ID
        channel_id (str): The Discord channel ID
        message_id (str): The Discord message ID

    Returns:
        str: The Discord message link
    """
    if guild_id:
        return f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"
    else:
        # For DMs, use @me instead of guild_id
        return f"https://discord.com/channels/@me/{channel_id}/{message_id}"

async def split_long_message(message, max_length=1900):
    """
    Split a long message into multiple parts to avoid Discord's 2000 character limit
    Enhanced to handle very long AI responses from increased token limits.

    Args:
        message (str): The message to split
        max_length (int): Maximum length of each part 
                         (default: 1900 to leave room for part indicators and safety margin)

    Returns:
        list: List of message parts
    """
    # First, check if we need to split at all
    # We need to account for potential part indicators when determining if splitting is needed
    max_part_indicator_length = len("[Part 999/999]\n")  # Generous estimate for part indicator

    if len(message) <= max_length:
        return [message]

    parts = []
    current_part = ""
    # Reduce max_length to account for part indicators that will be added later
    effective_max_length = max_length - max_part_indicator_length

    # Split by paragraphs first (double newlines)
    paragraphs = message.split("\n\n")

    for paragraph in paragraphs:
        # Special handling for bullet points and numbered lists
        # Check if this is a list section (starts with -, *, •, or number)
        is_list = paragraph.strip() and (paragraph.strip()[0] in '-*•' or paragraph.strip()[0].isdigit())
        
        # If adding this paragraph would exceed effective_max_length, start a new part
        if len(current_part) + len(paragraph) + 2 > effective_max_length: # +2 for potential "\n\n"
            if current_part:
                # Don't break in the middle of a list if possible
                if is_list and len(paragraph) < effective_max_length // 2:
                    # If it's a short list item, try to keep it with the previous content
                    parts.append(current_part.strip())
                    current_part = paragraph
                else:
                    parts.append(current_part.strip())
                    current_part = paragraph
            else:
                current_part = paragraph
        else:
            if current_part:
                current_part += "\n\n" + paragraph
            else:
                current_part = paragraph

        # Inner loop to handle cases where a single paragraph (or the current_part) is too long
        while len(current_part) > effective_max_length:
            # Find a good split point (prefer sentence, then word)
            split_at = -1
            # Try to split at the last sentence ending before effective_max_length
            for i in range(min(len(current_part), effective_max_length) -1, -1, -1):
                if current_part[i] == '.' and (i + 1 < len(current_part) and current_part[i+1] == ' '):
                    split_at = i + 1 # Include the period, split after space
                    break

            if split_at == -1: # If no sentence found, try to split at the last space
                for i in range(min(len(current_part), effective_max_length) -1, -1, -1):
                    if current_part[i] == ' ':
                        split_at = i
                        break

            if split_at == -1: # If no space found, force split at effective_max_length
                split_at = effective_max_length

            parts.append(current_part[:split_at].strip())
            current_part = current_part[split_at:].strip()

    # Add the last part if it's not empty
    if current_part:
        parts.append(current_part.strip())

    # Return parts without pagination indicators
    if not parts and message: # Handle case where original message was <= max_length but split logic ran
        return [message]

    return parts

async def fetch_referenced_message(message: discord.Message) -> Optional[discord.Message]:
    """
    Fetch the message that this message is replying to.
    
    Args:
        message (discord.Message): The message to check for references
        
    Returns:
        Optional[discord.Message]: The referenced message if found, None otherwise
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Check if message has a reference (reply)
        if message.reference and message.reference.message_id:
            # Try to get the referenced message from cache first
            if message.reference.cached_message:
                return message.reference.cached_message
            
            # If not in cache, fetch it from the channel
            channel = message.channel
            if message.reference.channel_id != channel.id:
                # Message references a different channel
                guild = message.guild
                if guild:
                    channel = guild.get_channel(message.reference.channel_id)
                    if not channel:
                        logger.warning(f"Could not find channel {message.reference.channel_id} for referenced message")
                        return None
                else:
                    logger.warning("Cannot fetch cross-channel reference without guild context")
                    return None
            
            return await channel.fetch_message(message.reference.message_id)
    
    except (discord.HTTPException, discord.NotFound) as e:
        logger.warning(f"Failed to fetch referenced message: {e}")
    except Exception as e:
        logger.error(f"Unexpected error fetching referenced message: {e}")
    
    return None

async def fetch_message_from_link(link: str, bot: discord.Client) -> Optional[discord.Message]:
    """
    Fetch a Discord message from a Discord message link.
    
    Args:
        link (str): Discord message link (e.g., https://discord.com/channels/guild_id/channel_id/message_id)
        bot (discord.Client): The Discord bot client
        
    Returns:
        Optional[discord.Message]: The message if found, None otherwise
    """
    logger = logging.getLogger(__name__)
    
    # Parse Discord message link
    pattern = r'https://discord\.com/channels/(@me|\d+)/(\d+)/(\d+)'
    match = re.match(pattern, link)
    
    if not match:
        logger.warning(f"Invalid Discord message link format: {link}")
        return None
    
    guild_id_str, channel_id_str, message_id_str = match.groups()
    
    try:
        channel_id = int(channel_id_str)
        message_id = int(message_id_str)
        
        # Get the channel
        if guild_id_str == "@me":
            # DM channel
            channel = bot.get_channel(channel_id)
        else:
            guild_id = int(guild_id_str)
            guild = bot.get_guild(guild_id)
            if not guild:
                logger.warning(f"Bot is not in guild {guild_id}")
                return None
            channel = guild.get_channel(channel_id)
        
        if not channel:
            logger.warning(f"Could not find channel {channel_id}")
            return None
        
        # Fetch the message
        return await channel.fetch_message(message_id)
    
    except (ValueError, discord.HTTPException, discord.NotFound) as e:
        logger.warning(f"Failed to fetch message from link {link}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error fetching message from link {link}: {e}")
    
    return None

def extract_message_links(text: str) -> list[str]:
    """
    Extract Discord message links from text.
    
    Args:
        text (str): Text to search for Discord message links
        
    Returns:
        list[str]: List of Discord message links found
    """
    pattern = r'https://discord\.com/channels/(?:@me|\d+)/\d+/\d+'
    return re.findall(pattern, text)

async def get_message_context(message: discord.Message, bot: discord.Client) -> Dict[str, Any]:
    """
    Get context for a message including any referenced messages, linked messages, and the original message.
    
    Args:
        message (discord.Message): The message to get context for
        bot (discord.Client): The Discord bot client
        
    Returns:
        Dict[str, Any]: Dictionary containing message context with original_message, referenced_message, and linked_messages
    """
    context = {
        'original_message': message,
        'referenced_message': None,
        'linked_messages': []
    }
    
    # Get referenced message (reply)
    referenced_msg = await fetch_referenced_message(message)
    if referenced_msg:
        context['referenced_message'] = referenced_msg
    
    # Get messages from links in the message content
    message_links = extract_message_links(message.content)
    for link in message_links:
        linked_msg = await fetch_message_from_link(link, bot)
        if linked_msg:
            context['linked_messages'].append(linked_msg)
    
    return context
