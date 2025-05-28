"""
Singleton LLM client to avoid duplicate client creation.
"""
import logging
from openai import OpenAI
from typing import Optional
import config

logger = logging.getLogger('discord_bot')

class LLMClient:
    """Singleton OpenAI client for LLM operations."""
    
    _instance: Optional['LLMClient'] = None
    _client: Optional[OpenAI] = None
    
    def __new__(cls) -> 'LLMClient':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize_client()
        return cls._instance
    
    def _initialize_client(self) -> None:
        """Initialize the OpenAI client with configuration."""
        try:
            if not hasattr(config, 'openrouter') or not config.openrouter:
                logger.error("OpenRouter API key not found in config")
                self._client = None
                return
            
            self._client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=config.openrouter,
            )
            logger.info("LLM client initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize LLM client: {e}")
            self._client = None
    
    @property
    def client(self) -> Optional[OpenAI]:
        """Get the OpenAI client instance."""
        return self._client
    
    def is_available(self) -> bool:
        """Check if the LLM client is available and properly configured."""
        return self._client is not None
    
    def reinitialize(self) -> None:
        """Reinitialize the client (useful for config changes)."""
        self._initialize_client()

# Global instance getter
def get_llm_client() -> LLMClient:
    """Get the singleton LLM client instance."""
    return LLMClient()

# Convenience function to get the raw OpenAI client
def get_openai_client() -> Optional[OpenAI]:
    """Get the OpenAI client directly."""
    llm_client = get_llm_client()
    return llm_client.client if llm_client.is_available() else None