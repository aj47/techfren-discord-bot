"""
Decorators for common functionality like rate limiting and database validation.
"""
import logging
from functools import wraps
from typing import Callable, Any
import discord

logger = logging.getLogger('discord_bot')

def rate_limited(func: Callable) -> Callable:
    """
    Decorator to check rate limits before executing a command.
    Automatically handles rate limit errors and stores responses.
    """
    @wraps(func)
    async def wrapper(message, client_user, *args, **kwargs) -> Any:
        # Import here to avoid circular imports
        from rate_limiter import check_rate_limit
        from command_handler import store_bot_response_db
        
        is_limited, wait_time, reason = check_rate_limit(str(message.author.id))
        if is_limited:
            error_msg = f"Please wait {wait_time:.1f} seconds before making another request." if reason == "cooldown" \
                else f"You've reached the maximum number of requests per minute. Please try again in {wait_time:.1f} seconds."
            bot_response = await message.channel.send(error_msg)
            await store_bot_response_db(bot_response, client_user, message.guild, message.channel, error_msg)
            logger.info(f"Rate limited user {message.author} ({reason}): wait time {wait_time:.1f}s")
            return
        
        return await func(message, client_user, *args, **kwargs)
    return wrapper

def database_required(func: Callable) -> Callable:
    """
    Decorator to check database availability before executing a command.
    Automatically handles database unavailable errors and stores responses.
    """
    @wraps(func)
    async def wrapper(message, client_user, *args, **kwargs) -> Any:
        # Import here to avoid circular imports
        import database
        from command_handler import store_bot_response_db
        
        if not database.db_connection:
            error_msg = "Database connection not available. Please try again later."
            bot_response = await message.channel.send(error_msg)
            await store_bot_response_db(bot_response, client_user, message.guild, message.channel, error_msg)
            return
        
        return await func(message, client_user, *args, **kwargs)
    return wrapper

def config_required(*config_attrs: str):
    """
    Decorator to check if required config attributes exist.
    Usage: @config_required('api_key', 'base_url')
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            import config
            
            for attr in config_attrs:
                if not hasattr(config, attr) or not getattr(config, attr):
                    logger.error(f"Required config attribute '{attr}' not found or empty")
                    return None
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator

def handle_errors(error_message: str = "An error occurred", log_errors: bool = True):
    """
    Decorator to handle common errors and log them consistently.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                if log_errors:
                    logger.error(f"{error_message} in {func.__name__}: {str(e)}", exc_info=True)
                return None
        return wrapper
    return decorator