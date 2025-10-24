from logging_config import logger
from rate_limiter import update_rate_limit_config


def _validate_required_string(config_module, attr_name, min_length=10, display_name=None):
    """Validate a required string configuration attribute."""
    if display_name is None:
        display_name = attr_name.replace('_', ' ').title()

    if not hasattr(config_module, attr_name) or not getattr(config_module, attr_name):
        logger.error(f"{display_name} not found in config.py or is empty")
        raise ValueError(f"{display_name} is missing or empty in config.py")

    value = getattr(config_module, attr_name)
    if not isinstance(value, str) or len(value) < min_length:
        logger.warning(f"{display_name} in config.py appears to be invalid (too short or not a string).")


def _validate_url(config_module, attr_name, display_name=None):
    """Validate a URL configuration attribute."""
    if display_name is None:
        display_name = attr_name.replace('_', ' ').title()

    value = getattr(config_module, attr_name, "")
    if not isinstance(value, str) or not value.startswith("http"):
        logger.warning(f"{display_name} in config.py appears to be invalid (should be a valid HTTP/HTTPS URL).")


def _validate_optional_string(config_module, attr_name, min_length=10, display_name=None):
    """Validate an optional string configuration attribute."""
    if display_name is None:
        display_name = attr_name.replace('_', ' ').title()

    if hasattr(config_module, attr_name) and getattr(config_module, attr_name):
        value = getattr(config_module, attr_name)
        if not isinstance(value, str) or len(value) < min_length:
            logger.warning(f"{display_name} in config.py appears to be invalid (too short or not a string).")
            return False
        return True
    return False


def _validate_rate_limiting(config_module):
    """Validate and configure rate limiting settings."""
    custom_rate_limit_seconds = getattr(config_module, "rate_limit_seconds", 10)
    custom_max_requests_per_minute = getattr(config_module, "max_requests_per_minute", 6)

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


def _validate_reports_channel(config_module):
    """Validate optional reports channel configuration."""
    if hasattr(config_module, "reports_channel_id") and config_module.reports_channel_id:
        try:
            int(config_module.reports_channel_id)
            logger.info(f"Reports channel ID configured: {config_module.reports_channel_id}")
        except (ValueError, TypeError):
            logger.warning(
                f"Invalid reports_channel_id in config: '{config_module.reports_channel_id}'. It should be an integer. Reports will not be posted."
            )


def _validate_summary_time(config_module):
    """Validate optional summary time configuration."""
    summary_hour = getattr(config_module, "summary_hour", 0)
    summary_minute = getattr(config_module, "summary_minute", 0)

    try:
        sh = int(summary_hour)
        sm = int(summary_minute)
        if not (0 <= sh <= 23 and 0 <= sm <= 59):
            logger.warning(
                f"Invalid summary_hour ({sh}) or summary_minute ({sm}) in config. Using default 00:00 UTC."
            )
            if hasattr(config_module, "summary_hour"):
                config_module.summary_hour = 0
            if hasattr(config_module, "summary_minute"):
                config_module.summary_minute = 0
        else:
            logger.info(f"Custom daily summary time configured: {sh:02d}:{sm:02d} UTC")
    except (ValueError, TypeError):
        logger.warning(
            f"Invalid summary_hour ('{summary_hour}') or summary_minute ('{summary_minute}') in config. Using default 00:00 UTC."
        )
        if hasattr(config_module, "summary_hour"):
            config_module.summary_hour = 0
        if hasattr(config_module, "summary_minute"):
            config_module.summary_minute = 0


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
    # Validate Discord token
    _validate_required_string(config_module, "token", min_length=50, display_name="Discord token")

    # Validate LLM configuration
    _validate_required_string(config_module, "llm_api_key", display_name="LLM API key")
    _validate_required_string(config_module, "llm_base_url", display_name="LLM Base URL")
    _validate_url(config_module, "llm_base_url", display_name="LLM Base URL")
    _validate_required_string(config_module, "llm_model", min_length=1, display_name="LLM Model")

    # Log LLM configuration
    logger.info(f"Using LLM model: {config_module.llm_model} at {config_module.llm_base_url}")

    # Validate Firecrawl API key
    _validate_required_string(config_module, "firecrawl_api_key", display_name="Firecrawl API key")

    # Validate optional Apify API token
    if _validate_optional_string(config_module, "apify_api_token", display_name="Apify API token"):
        logger.info("Apify API token found in config.py. Twitter/X.com links will be processed using Apify.")
    else:
        logger.info("Apify API token not found in config.py. Twitter/X.com links will be processed using Firecrawl.")

    # Validate rate limiting configuration
    _validate_rate_limiting(config_module)

    # Validate optional configurations
    _validate_reports_channel(config_module)
    _validate_summary_time(config_module)

    return True
