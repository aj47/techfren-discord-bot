import discord
from discord.abc import Messageable
import re
from typing import Optional, Dict, Any, cast, List
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

async def split_long_message(message, max_length=1950):
    """
    Split a long message into multiple parts to avoid Discord's 2000 character limit

    Args:
        message (str): The message to split
        max_length (int): Maximum length of each part 
                         (default: 1950 to leave room for part indicators)

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
        # If adding this paragraph would exceed effective_max_length, start a new part
        if len(current_part) + len(paragraph) + 2 > effective_max_length: # +2 for potential "\n\n"
            if current_part:
                parts.append(current_part.strip())
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

    # Add part indicators only if there are multiple parts
    if len(parts) > 1:
        for i in range(len(parts)):
            parts[i] = f"[Part {i+1}/{len(parts)}]\n{parts[i]}"
    elif not parts and message: # Handle case where original message was <= max_length but split logic ran
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
            channel: Messageable = message.channel
            if message.reference.channel_id != getattr(channel, 'id', None):
                # Message references a different channel
                guild = message.guild
                if guild:
                    fetched_channel = guild.get_channel(message.reference.channel_id)
                    if not fetched_channel:
                        logger.warning(f"Could not find channel {message.reference.channel_id} for referenced message")
                        return None
                    # Check if the channel supports fetching messages
                    if not isinstance(fetched_channel, Messageable):
                        logger.warning(f"Channel {message.reference.channel_id} does not support message fetching")
                        return None
                    channel = fetched_channel  # fetched_channel is now guaranteed to be Messageable
                else:
                    logger.warning("Cannot fetch cross-channel reference without guild context")
                    return None
            
            # Channel is guaranteed to be messageable at this point
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
        channel = None
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
        
        # Check if channel supports message fetching
        if not isinstance(channel, Messageable):
            logger.warning(f"Channel {channel_id} does not support message fetching")
            return None
        
        # Cast to Messageable since we've verified it's messageable
        messageable_channel = cast(Messageable, channel)
        
        # Fetch the message
        return await messageable_channel.fetch_message(message_id)
    
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
    Get context for a message including any referenced messages and linked messages.
    
    Args:
        message (discord.Message): The message to get context for
        bot (discord.Client): The Discord bot client
        
    Returns:
        Dict[str, Any]: Dictionary containing message context
    """
    linked_messages: List[discord.Message] = []
    context: Dict[str, Any] = {
        'original_message': message,
        'referenced_message': None,
        'linked_messages': linked_messages
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
            linked_messages.append(linked_msg)
    
    return context

def is_message_link_only(message_content: str) -> bool:
    """
    Check if a message contains only links (URLs) with minimal surrounding text,
    or if it's a short, non-intrusive message that won't disrupt the links channel.
    
    Args:
        message_content (str): The message content to validate
        
    Returns:
        bool: True if message contains only links or is acceptably short/non-intrusive, False otherwise
    """
    if not message_content.strip():
        return False
    
    original_content = message_content.strip()
    
    # URL regex pattern - same as used in bot.py for consistency
    url_pattern = r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+(?:/[^\s]*)?(?:\?[^\s]*)?'
    urls = re.findall(url_pattern, message_content)
    
    # If message contains URLs, apply the original logic (links + minimal text)
    if urls:
        # Create a copy of the message content to work with
        content_copy = message_content.strip()
        
        # Remove all found URLs from the message
        for url in urls:
            content_copy = content_copy.replace(url, '')
        
        # Remove common whitespace and punctuation that might accompany links
        # Allow minimal surrounding text like "Check this out:", "Here:", etc.
        content_copy = re.sub(r'[^\w\s]', '', content_copy)  # Remove punctuation
        content_copy = re.sub(r'\s+', ' ', content_copy)      # Normalize whitespace
        content_copy = content_copy.strip()
        
        # If there are more than 15 characters left after removing URLs and punctuation,
        # consider it non-link content (increased from 10 to be more lenient)
        return len(content_copy) <= 15
    
    # For messages without URLs, apply stricter length limits first
    
    # Reject very long messages immediately (over 50 characters)
    if len(original_content) > 50:
        return False
    
    # Allow very short messages (under 25 characters total)
    if len(original_content) <= 25:
        return True
    
    # Allow emoji-only messages (including Discord custom emojis)
    emoji_pattern = r'^[\s\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U00002600-\U000027BF\U0001F900-\U0001F9FF\U0001F018-\U0001F0FF<:>\w:]+$'
    if re.match(emoji_pattern, original_content):
        return True
    
    # Allow common short, non-intrusive responses
    short_responses = {
        'thanks', 'thank you', 'ty', 'thx', 'nice', 'cool', 'good', 'great', 'awesome',
        'interesting', 'helpful', 'useful', 'wow', 'nice find', 'good find', 'solid',
        'love it', 'like it', 'this', '+1', '👍', '👏', '🔥', '💯', '❤️', '♥️',
        'yep', 'yes', 'yeah', 'yup', 'nope', 'no', 'nah', 'maybe', 'possibly',
        'lol', 'haha', 'hehe', 'omg', 'damn', 'shit', 'fuck', 'based', 'cringe',
        'facts', 'true', 'real', 'fr', 'frfr', 'bet', 'word', 'same', 'mood',
        'this is it', 'exactly', 'agree', 'disagree', 'idk', 'not sure',
        'hmm', 'interesting take', 'hot take', 'bad take', 'good take'
    }
    
    # Convert to lowercase and check if it's in our allowlist
    content_lower = original_content.lower().strip()
    
    # Remove common punctuation for comparison
    content_clean = re.sub(r'[^\w\s]', '', content_lower).strip()
    
    if content_clean in short_responses:
        return True
    
    # Allow short messages that end with common reaction words (and are under 35 chars)
    for response in short_responses:
        if content_clean.endswith(response) and len(original_content) <= 35:
            return True
    
    # For messages 26-50 characters, be more restrictive
    # Only allow if they contain common positive/reaction words
    if 26 <= len(original_content) <= 50:
        # Check if message contains any of the approved short responses
        for response in short_responses:
            if response in content_clean:
                return True
        # If no approved words found, reject it
        return False
    
    # All other cases: reject
    return False
