import re
from typing import Any
from logging_config import logger
from rate_limiter import update_rate_limit_config

def _is_valid_discord_id(value: Any) -> bool:
    """
    Validate if a value is a valid Discord ID.
    
    Args:
        value: The value to validate
        
    Returns:
        bool: True if valid Discord ID, False otherwise
    """
    try:
        # Convert to string first
        str_value = str(value).strip()
        
        # Discord IDs are 17-20 digit integers
        if not str_value.isdigit():
            return False
            
        # Check length (Discord IDs are typically 17-20 digits)
        if not (17 <= len(str_value) <= 20):
            return False
            
        # Convert to int to ensure it's a valid number
        int_value = int(str_value)
        
        # Discord IDs should be positive
        return int_value > 0
        
    except (ValueError, TypeError):
        return False

def _is_valid_api_key(value: Any, min_length: int = 10) -> bool:
    """
    Validate if a value is a valid API key format.
    
    Args:
        value: The value to validate
        min_length: Minimum length for the API key
        
    Returns:
        bool: True if valid API key format, False otherwise
    """
    try:
        if not isinstance(value, str):
            return False
        
        # Remove whitespace
        value = value.strip()
        
        # Check minimum length
        if len(value) < min_length:
            return False
            
        # Check for obvious placeholder values
        placeholder_patterns = [
            r'^your[_\-]?api[_\-]?key$',
            r'^your[_\-]?token$',
            r'^placeholder$',
            r'^change[_\-]?me$',
            r'^example$'
        ]
        
        for pattern in placeholder_patterns:
            if re.match(pattern, value, re.IGNORECASE):
                return False
                
        return True
        
    except (ValueError, TypeError):
        return False

def validate_config(config_module: Any) -> bool:
    """
    Validate the configuration file (config.py)

    Args:
        config_module: The imported config module

    Returns:
        bool: True if the configuration is valid

    Raises:
        ValueError: If critical configuration is invalid or missing
    """
    # Check Discord token
    if not hasattr(config_module, 'token') or not config_module.token:
        logger.error("Required configuration missing: Discord token")
        raise ValueError("Critical configuration is missing or invalid. Please check your setup.")

    if not _is_valid_api_key(config_module.token, min_length=50):
        # This is a warning, not a critical error, as token length can vary.
        logger.warning("Discord token appears to be invalid (too short, not a string, or placeholder value).")

    # Check OpenRouter API key
    if not hasattr(config_module, 'openrouter') or not config_module.openrouter:
        logger.error("Required configuration missing: OpenRouter API key")
        raise ValueError("Critical configuration is missing or invalid. Please check your setup.")

    if not _is_valid_api_key(config_module.openrouter, min_length=20):
        # This is a warning.
        logger.warning("OpenRouter API key appears to be invalid (too short, not a string, or placeholder value).")
        
    # Check Firecrawl API key
    if not hasattr(config_module, 'firecrawl_api_key') or not config_module.firecrawl_api_key:
        logger.error("Required configuration missing: Firecrawl API key")
        raise ValueError("Critical configuration is missing or invalid. Please check your setup.")

    if not isinstance(config_module.firecrawl_api_key, str) or len(config_module.firecrawl_api_key) < 10:
        # This is a warning.
        logger.warning("Firecrawl API key appears to be invalid (too short or not a string).")
        
    # Check Apify API token (optional)
    if hasattr(config_module, 'apify_api_token') and config_module.apify_api_token:
        if not isinstance(config_module.apify_api_token, str) or len(config_module.apify_api_token) < 10:
            # This is a warning.
            logger.warning("Apify API token in config.py appears to be invalid (too short or not a string).")
        else:
            logger.info("Apify API token found in config.py. Twitter/X.com links will be processed using Apify.")
    else:
        logger.info("Apify API token not found in config.py. Twitter/X.com links will be processed using Firecrawl.")

    # Check optional rate limiting configuration and update the rate_limiter module
    # Default values are set in rate_limiter.py (10 seconds, 6 requests/minute)
    custom_rate_limit_seconds = getattr(config_module, 'rate_limit_seconds', 10)
    custom_max_requests_per_minute = getattr(config_module, 'max_requests_per_minute', 6)

    try:
        new_rate_limit_seconds = int(custom_rate_limit_seconds)
        if new_rate_limit_seconds <= 0:
            logger.warning(f"rate_limit_seconds in config ('{custom_rate_limit_seconds}') must be positive. Using default.")
            new_rate_limit_seconds = 10 
    except (ValueError, TypeError):
        logger.warning(f"Invalid rate_limit_seconds in config ('{custom_rate_limit_seconds}'), using default.")
        new_rate_limit_seconds = 10
        
    try:
        new_max_requests_per_minute = int(custom_max_requests_per_minute)
        if new_max_requests_per_minute <= 0:
            logger.warning(f"max_requests_per_minute in config ('{custom_max_requests_per_minute}') must be positive. Using default.")
            new_max_requests_per_minute = 6
    except (ValueError, TypeError):
        logger.warning(f"Invalid max_requests_per_minute in config ('{custom_max_requests_per_minute}'), using default.")
        new_max_requests_per_minute = 6

    update_rate_limit_config(new_rate_limit_seconds, new_max_requests_per_minute)
    
    # Check for optional LLM model
    if hasattr(config_module, 'llm_model') and config_module.llm_model:
        if isinstance(config_module.llm_model, str) and len(config_module.llm_model.strip()) > 0:
            logger.info(f"Using custom LLM model from config: {config_module.llm_model}")
        else:
            logger.warning(f"llm_model in config.py is present but invalid. Using default model.")
    else:
        logger.info("No custom llm_model in config.py. Using default model.")

    # Check for optional reports channel ID with Discord ID format validation
    if hasattr(config_module, 'reports_channel_id') and config_module.reports_channel_id:
        if _is_valid_discord_id(config_module.reports_channel_id):
            logger.info(f"Reports channel ID configured: {config_module.reports_channel_id}")
        else:
            logger.warning(f"Invalid reports_channel_id in config: '{config_module.reports_channel_id}'. It should be a valid Discord channel ID. Reports will not be posted.")
            # Optionally, you could set config_module.reports_channel_id = None here if it's invalid
            
    # Check for optional summary time
    summary_hour = getattr(config_module, 'summary_hour', 0)
    summary_minute = getattr(config_module, 'summary_minute', 0)
    try:
        sh = int(summary_hour)
        sm = int(summary_minute)
        if not (0 <= sh <= 23 and 0 <= sm <= 59):
            logger.warning(f"Invalid summary_hour ({sh}) or summary_minute ({sm}) in config. Using default 00:00 UTC.")
            # Reset to default if invalid, so summarization_tasks uses valid values
            if hasattr(config_module, 'summary_hour'): config_module.summary_hour = 0
            if hasattr(config_module, 'summary_minute'): config_module.summary_minute = 0
        else:
            logger.info(f"Custom daily summary time configured: {sh:02d}:{sm:02d} UTC")
    except (ValueError, TypeError):
        logger.warning(f"Invalid summary_hour ('{summary_hour}') or summary_minute ('{summary_minute}') in config. Using default 00:00 UTC.")
        if hasattr(config_module, 'summary_hour'): config_module.summary_hour = 0
        if hasattr(config_module, 'summary_minute'): config_module.summary_minute = 0
        
    return True
