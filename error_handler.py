"""
Error handling module for the Discord bot.
Provides standardized error handling functions for different types of errors.
"""

import discord
import traceback
from logging_config import logger
from typing import Optional, Callable, Any, Dict, Union, Tuple

# Error types for categorization
class ErrorCategory:
    """Enum-like class for error categories"""
    DATABASE = "database"
    NETWORK = "network"
    DISCORD_API = "discord_api"
    LLM_API = "llm_api"
    RATE_LIMIT = "rate_limit"
    VALIDATION = "validation"
    PERMISSION = "permission"
    CONFIGURATION = "configuration"
    UNKNOWN = "unknown"

# User-friendly error messages
ERROR_MESSAGES = {
    ErrorCategory.DATABASE: "A database error occurred. Please try again later.",
    ErrorCategory.NETWORK: "A network error occurred. Please check your connection and try again.",
    ErrorCategory.DISCORD_API: "An error occurred while communicating with Discord. Please try again later.",
    ErrorCategory.LLM_API: "An error occurred while generating a response. Please try again later.",
    ErrorCategory.RATE_LIMIT: "You've reached the rate limit. Please wait a moment before trying again.",
    ErrorCategory.VALIDATION: "Invalid input provided. Please check your command and try again.",
    ErrorCategory.PERMISSION: "You don't have permission to perform this action.",
    ErrorCategory.CONFIGURATION: "The bot is not properly configured for this action.",
    ErrorCategory.UNKNOWN: "An unexpected error occurred. Please try again later."
}

async def handle_error(
    error: Exception,
    error_category: str = ErrorCategory.UNKNOWN,
    message: Optional[discord.Message] = None,
    channel: Optional[discord.TextChannel] = None,
    custom_message: Optional[str] = None,
    log_message: Optional[str] = None,
    notify_user: bool = True,
    client_user: Optional[discord.ClientUser] = None,
    store_response: Optional[Callable] = None,
    context: Optional[Dict[str, Any]] = None
) -> Union[discord.Message, None]:
    """
    Handle an error with standardized logging and optional user notification.
    
    Args:
        error: The exception that was raised
        error_category: Category of the error (use ErrorCategory constants)
        message: The Discord message that triggered the command (if available)
        channel: The Discord channel to send the error message to (if message not provided)
        custom_message: Custom error message to show to the user (overrides default for category)
        log_message: Custom message to include in the log
        notify_user: Whether to send an error message to the user
        client_user: The bot's user object (required if store_response is provided)
        store_response: Function to store the bot's response in the database
        context: Additional context information for logging
        
    Returns:
        The sent error message object if notify_user is True, otherwise None
    """
    # Determine the error message to show to the user
    user_message = custom_message or ERROR_MESSAGES.get(error_category, ERROR_MESSAGES[ErrorCategory.UNKNOWN])
    
    # Create detailed log message
    error_details = f"{log_message + ': ' if log_message else ''}{str(error)}"
    
    # Add context information to the log if provided
    if context:
        context_str = ", ".join(f"{k}={v}" for k, v in context.items())
        error_details = f"{error_details} (Context: {context_str})"
    
    # Log the error with appropriate level based on category
    if error_category in [ErrorCategory.DATABASE, ErrorCategory.DISCORD_API, ErrorCategory.LLM_API, 
                          ErrorCategory.CONFIGURATION, ErrorCategory.UNKNOWN]:
        logger.error(error_details, exc_info=True)
    else:
        logger.warning(error_details)
    
    # Notify the user if requested and possible
    if notify_user:
        try:
            # Determine which channel to send to
            target_channel = None
            if message:
                target_channel = message.channel
            elif channel:
                target_channel = channel
                
            if target_channel:
                error_response = await target_channel.send(user_message)
                
                # Store the error response in the database if requested
                if store_response and client_user and error_response:
                    try:
                        guild = message.guild if message else getattr(channel, 'guild', None)
                        await store_response(
                            error_response, 
                            client_user, 
                            guild, 
                            target_channel, 
                            user_message
                        )
                    except Exception as store_error:
                        logger.warning(f"Failed to store error response: {store_error}")
                
                return error_response
        except Exception as notify_error:
            logger.warning(f"Failed to send error notification: {notify_error}")
    
    return None

def categorize_exception(exception: Exception) -> str:
    """
    Automatically categorize an exception based on its type.
    
    Args:
        exception: The exception to categorize
        
    Returns:
        The error category as a string
    """
    error_type = type(exception).__name__
    error_str = str(exception).lower()
    
    # Database errors
    if any(db_err in error_type for db_err in ['SQL', 'DB', 'Database']):
        return ErrorCategory.DATABASE
    
    # Network errors
    if any(net_err in error_type for net_err in ['Timeout', 'Connection', 'HTTP']):
        return ErrorCategory.NETWORK
    
    # Discord API errors
    if error_type.startswith('Discord') or 'discord' in error_str:
        return ErrorCategory.DISCORD_API
    
    # LLM API errors
    if 'openai' in error_str or 'llm' in error_str or 'model' in error_str or 'token' in error_str:
        return ErrorCategory.LLM_API
    
    # Rate limit errors
    if 'rate' in error_str and 'limit' in error_str:
        return ErrorCategory.RATE_LIMIT
    
    # Validation errors
    if any(val_err in error_type for val_err in ['Value', 'Type', 'Argument', 'Attribute']):
        return ErrorCategory.VALIDATION
    
    # Permission errors
    if 'permission' in error_str or 'access' in error_str or 'forbidden' in error_str:
        return ErrorCategory.PERMISSION
    
    # Configuration errors
    if 'config' in error_str or 'setting' in error_str:
        return ErrorCategory.CONFIGURATION
    
    # Default to unknown
    return ErrorCategory.UNKNOWN

async def handle_command_error(
    error: Exception,
    message: discord.Message,
    client_user: discord.ClientUser,
    command_name: str,
    store_response_func: Callable,
    custom_message: Optional[str] = None,
    processing_message: Optional[discord.Message] = None
) -> None:
    """
    Handle an error that occurred during command processing.
    
    Args:
        error: The exception that was raised
        message: The Discord message that triggered the command
        client_user: The bot's user object
        command_name: The name of the command that failed
        store_response_func: Function to store the bot's response in the database
        custom_message: Custom error message to show to the user
        processing_message: A "processing" message to delete if it exists
    """
    # Categorize the error
    error_category = categorize_exception(error)
    
    # Create context for logging
    context = {
        'command': command_name,
        'user': str(message.author),
        'channel': str(message.channel),
        'guild': str(message.guild) if message.guild else 'DM'
    }
    
    # Handle the error
    await handle_error(
        error=error,
        error_category=error_category,
        message=message,
        custom_message=custom_message,
        log_message=f"Error processing {command_name} command",
        notify_user=True,
        client_user=client_user,
        store_response=store_response_func,
        context=context
    )
    
    # Delete the processing message if it exists
    if processing_message:
        try:
            await processing_message.delete()
        except discord.NotFound:
            # Message might have been deleted already
            pass
        except Exception as del_error:
            logger.warning(f"Could not delete processing message: {del_error}")

async def handle_background_task_error(
    error: Exception,
    task_name: str,
    context: Optional[Dict[str, Any]] = None,
    notify_channel: Optional[discord.TextChannel] = None,
    client_user: Optional[discord.ClientUser] = None,
    store_response_func: Optional[Callable] = None
) -> None:
    """
    Handle an error that occurred during a background task.
    
    Args:
        error: The exception that was raised
        task_name: The name of the task that failed
        context: Additional context information for logging
        notify_channel: Channel to notify about the error (if applicable)
        client_user: The bot's user object (required if notify_channel and store_response_func are provided)
        store_response_func: Function to store the bot's response in the database
    """
    # Categorize the error
    error_category = categorize_exception(error)
    
    # Create log message
    log_message = f"Error in background task '{task_name}'"
    
    # Handle the error
    await handle_error(
        error=error,
        error_category=error_category,
        channel=notify_channel,
        log_message=log_message,
        notify_user=notify_channel is not None,
        client_user=client_user,
        store_response=store_response_func,
        context=context
    )

def is_user_error(error: Exception) -> bool:
    """
    Determine if an error is caused by user input rather than a system issue.
    
    Args:
        error: The exception to check
        
    Returns:
        True if the error is likely caused by user input, False otherwise
    """
    error_category = categorize_exception(error)
    return error_category in [ErrorCategory.VALIDATION, ErrorCategory.PERMISSION, ErrorCategory.RATE_LIMIT]