from logging_config import logger
from rate_limiter import update_rate_limit_config

def validate_config(config_module):
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
        logger.error("Discord token not found in config.py or is empty")
        raise ValueError("Bot token is missing or empty in config.py")

    if not isinstance(config_module.token, str) or len(config_module.token) < 50:
        # This is a warning, not a critical error, as token length can vary.
        logger.warning("Discord token in config.py appears to be invalid (too short or not a string).")

    # Check Perplexity API key
    if not hasattr(config_module, 'perplexity') or not config_module.perplexity:
        logger.error("Perplexity API key not found in config.py or is empty")
        raise ValueError("Perplexity API key is missing or empty in config.py")

    if not isinstance(config_module.perplexity, str) or len(config_module.perplexity) < 20:
        # This is a warning.
        logger.warning("Perplexity API key in config.py appears to be invalid (too short or not a string).")
        
    # Check Firecrawl API key (optional - required for link scraping)
    has_firecrawl = hasattr(config_module, 'firecrawl_api_key') and config_module.firecrawl_api_key and \
                    isinstance(config_module.firecrawl_api_key, str) and len(config_module.firecrawl_api_key) >= 10
    
    if not hasattr(config_module, 'firecrawl_api_key') or not config_module.firecrawl_api_key:
        logger.warning("Firecrawl API key not found in config.py or is empty - Firecrawl link scraping features will be disabled")
    elif not isinstance(config_module.firecrawl_api_key, str) or len(config_module.firecrawl_api_key) < 10:
        logger.warning("Firecrawl API key in config.py appears to be invalid (too short or not a string).")
        has_firecrawl = False
        
    # Check Apify API token (optional)
    has_apify = hasattr(config_module, 'apify_api_token') and config_module.apify_api_token and \
                isinstance(config_module.apify_api_token, str) and len(config_module.apify_api_token) >= 10
    
    if hasattr(config_module, 'apify_api_token') and config_module.apify_api_token:
        if not isinstance(config_module.apify_api_token, str) or len(config_module.apify_api_token) < 10:
            logger.warning("Apify API token in config.py appears to be invalid (too short or not a string).")
            has_apify = False
        else:
            logger.info("Apify API token found in config.py. Twitter/X.com links will be processed using Apify.")
    else:
        # Check combined state for X.com link scraping
        if not has_apify and not has_firecrawl:
            logger.warning("Neither Apify nor Firecrawl API credentials found. Twitter/X.com link scraping will be disabled.")
        elif has_firecrawl:
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

    # Check for optional reports channel ID
    if hasattr(config_module, 'reports_channel_id') and config_module.reports_channel_id:
        try:
            int(config_module.reports_channel_id)
            logger.info(f"Reports channel ID configured: {config_module.reports_channel_id}")
        except (ValueError, TypeError):
            logger.warning(f"Invalid reports_channel_id in config: '{config_module.reports_channel_id}'. It should be an integer. Reports will not be posted.")
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
