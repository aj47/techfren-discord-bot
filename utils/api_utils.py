"""
Shared API utilities for validating configuration and creating clients.
"""
import config
from logging_config import logger
from openai import OpenAI


def validate_api_key(key_name: str, service_name: str) -> bool:
    """
    Validate that an API key exists in config and is not empty.
    
    Args:
        key_name (str): The config attribute name (e.g., 'openrouter', 'apify_token')
        service_name (str): Human-readable service name for error messages
        
    Returns:
        bool: True if key exists and is not empty, False otherwise
    """
    if not hasattr(config, key_name) or not getattr(config, key_name):
        logger.error(f"{service_name} API key not found in config.py or is empty")
        return False
    return True


def get_openai_client() -> OpenAI:
    """
    Get a configured OpenAI client for OpenRouter API.
    
    Returns:
        OpenAI: Configured client instance
        
    Raises:
        ValueError: If OpenRouter API key is not configured
    """
    if not validate_api_key('openrouter', 'OpenRouter'):
        raise ValueError("OpenRouter API key not configured")
    
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=config.openrouter
    )


def get_llm_model() -> str:
    """
    Get the configured LLM model or return default.
    
    Returns:
        str: Model name to use
    """
    return getattr(config, 'llm_model', "x-ai/grok-3-mini-beta")


def ensure_https_url(url: str) -> str:
    """
    Ensure a URL starts with https://
    
    Args:
        url (str): The URL to format
        
    Returns:
        str: URL with https:// prefix
    """
    if not url.startswith('http'):
        return f"https://{url}"
    return url