"""
Discord API rate limiting utility with exponential backoff.
Handles Discord's rate limits gracefully to prevent bot failures.
"""

import asyncio
import time
import discord
from typing import Dict, Optional, Callable, Any, Awaitable
from logging_config import logger

class DiscordRateLimiter:
    """
    Discord API rate limiter with exponential backoff and bucket management.
    """
    
    def __init__(self):
        # Rate limit tracking per endpoint/bucket
        self._buckets: Dict[str, Dict[str, Any]] = {}
        self._global_rate_limit_reset: Optional[float] = None
        
    async def handle_rate_limit(
        self, 
        func: Callable[..., Awaitable[Any]], 
        bucket_key: str,
        *args, 
        **kwargs
    ) -> Any:
        """
        Execute a Discord API call with rate limit handling.
        
        Args:
            func: The async function to call
            bucket_key: A unique key identifying the rate limit bucket
            *args: Arguments to pass to the function
            **kwargs: Keyword arguments to pass to the function
            
        Returns:
            The result of the function call
            
        Raises:
            discord.HTTPException: If the request fails after retries
        """
        max_retries = 5
        base_delay = 1.0
        
        for attempt in range(max_retries):
            try:
                # Check for global rate limit
                if self._global_rate_limit_reset:
                    current_time = time.time()
                    if current_time < self._global_rate_limit_reset:
                        sleep_time = self._global_rate_limit_reset - current_time
                        logger.warning(f"Global rate limit active, sleeping for {sleep_time:.2f} seconds")
                        await asyncio.sleep(sleep_time)
                        self._global_rate_limit_reset = None
                
                # Check bucket-specific rate limit
                bucket_info = self._buckets.get(bucket_key, {})
                reset_time = bucket_info.get('reset_time', 0)
                
                if reset_time and time.time() < reset_time:
                    sleep_time = reset_time - time.time()
                    logger.warning(f"Bucket {bucket_key} rate limited, sleeping for {sleep_time:.2f} seconds")
                    await asyncio.sleep(sleep_time)
                
                # Execute the function
                result = await func(*args, **kwargs)
                
                # Success - reset bucket info on successful call
                if bucket_key in self._buckets:
                    self._buckets[bucket_key]['reset_time'] = 0
                
                return result
                
            except discord.HTTPException as e:
                if e.status == 429:  # Rate limited
                    retry_after = getattr(e, 'retry_after', None)
                    if retry_after:
                        # Handle Discord's retry-after header
                        if e.code == 0:  # Global rate limit
                            self._global_rate_limit_reset = time.time() + retry_after
                            logger.warning(f"Global rate limit hit, retry after {retry_after} seconds")
                        else:  # Bucket-specific rate limit
                            self._buckets[bucket_key] = {
                                'reset_time': time.time() + retry_after
                            }
                            logger.warning(f"Bucket {bucket_key} rate limited, retry after {retry_after} seconds")
                        
                        await asyncio.sleep(retry_after)
                        continue
                    else:
                        # No retry-after header, use exponential backoff
                        delay = base_delay * (2 ** attempt)
                        logger.warning(f"Rate limited without retry-after header, using exponential backoff: {delay} seconds")
                        await asyncio.sleep(delay)
                        continue
                        
                elif e.status in [500, 502, 503, 504]:  # Server errors
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(f"Discord server error {e.status}, retrying in {delay} seconds (attempt {attempt + 1}/{max_retries})")
                        await asyncio.sleep(delay)
                        continue
                    else:
                        logger.error(f"Discord server error {e.status} after {max_retries} attempts")
                        raise
                        
                else:
                    # Other HTTP errors that shouldn't be retried
                    raise
                    
            except Exception as e:
                # Non-HTTP exceptions shouldn't be retried
                logger.error(f"Non-HTTP exception in Discord API call: {e}")
                raise
        
        # If we get here, we've exhausted all retries
        raise discord.HTTPException(response=None, message="Max retries exceeded for Discord API call")

# Global instance
discord_rate_limiter = DiscordRateLimiter()

async def rate_limited_send(channel: discord.abc.Messageable, *args, **kwargs) -> Optional[discord.Message]:
    """
    Send a message with rate limiting protection.
    
    Args:
        channel: The channel to send the message to
        *args: Arguments to pass to channel.send()
        **kwargs: Keyword arguments to pass to channel.send()
        
    Returns:
        The sent message or None if failed
    """
    try:
        bucket_key = f"send_message_{channel.id}"
        return await discord_rate_limiter.handle_rate_limit(
            channel.send, bucket_key, *args, **kwargs
        )
    except Exception as e:
        logger.error(f"Failed to send message to channel {channel.id}: {e}")
        return None

async def rate_limited_followup_send(interaction: discord.Interaction, *args, **kwargs) -> Optional[discord.WebhookMessage]:
    """
    Send a followup message with rate limiting protection.
    
    Args:
        interaction: The interaction to send the followup for
        *args: Arguments to pass to interaction.followup.send()
        **kwargs: Keyword arguments to pass to interaction.followup.send()
        
    Returns:
        The sent message or None if failed
    """
    try:
        bucket_key = f"followup_send_{interaction.channel.id if interaction.channel else 'dm'}"
        return await discord_rate_limiter.handle_rate_limit(
            interaction.followup.send, bucket_key, *args, **kwargs
        )
    except Exception as e:
        logger.error(f"Failed to send followup message: {e}")
        return None

async def rate_limited_thread_create(channel: discord.TextChannel, *args, **kwargs) -> Optional[discord.Thread]:
    """
    Create a thread with rate limiting protection.
    
    Args:
        channel: The channel to create the thread in
        *args: Arguments to pass to channel.create_thread()
        **kwargs: Keyword arguments to pass to channel.create_thread()
        
    Returns:
        The created thread or None if failed
    """
    try:
        bucket_key = f"create_thread_{channel.id}"
        return await discord_rate_limiter.handle_rate_limit(
            channel.create_thread, bucket_key, *args, **kwargs
        )
    except Exception as e:
        logger.error(f"Failed to create thread in channel {channel.id}: {e}")
        return None
