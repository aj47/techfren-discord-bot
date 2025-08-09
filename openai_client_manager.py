"""
OpenAI Client Manager

This module provides centralized management for OpenAI client initialization,
configuration, and error handling to eliminate code duplication across the codebase.
"""

from openai import AsyncOpenAI
from logging_config import logger
import config
from typing import Optional, Dict, Any
import asyncio


class OpenAIClientManager:
    """
    Centralized manager for OpenAI client operations.
    
    This class provides static methods for:
    - Creating and configuring OpenAI clients
    - Standardized error handling 
    - Configuration validation
    - Header management
    """

    @staticmethod
    def validate_config() -> bool:
        """
        Validate that the OpenRouter API key is available and properly configured.
        
        Returns:
            bool: True if configuration is valid, False otherwise
        """
        if not hasattr(config, 'openrouter') or not config.openrouter:
            logger.error("OpenRouter API key not found in config.py or is empty")
            return False
        
        if not isinstance(config.openrouter, str) or len(config.openrouter.strip()) < 10:
            logger.error("OpenRouter API key appears to be invalid (too short or not a string)")
            return False
            
        return True

    @staticmethod
    async def create_client() -> Optional[AsyncOpenAI]:
        """
        Create and configure an OpenAI client with standard settings.
        
        Returns:
            Optional[AsyncOpenAI]: Configured client instance or None if configuration is invalid
        """
        try:
            if not OpenAIClientManager.validate_config():
                return None

            client = AsyncOpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=config.openrouter,
                timeout=60.0
            )
            
            logger.debug("OpenAI client created successfully")
            return client

        except Exception as e:
            logger.error(f"Error creating OpenAI client: {str(e)}", exc_info=True)
            return None

    @staticmethod
    def get_headers() -> Dict[str, str]:
        """
        Get standard headers for OpenAI API requests.
        
        Returns:
            Dict[str, str]: Dictionary of headers to include in requests
        """
        return {
            "HTTP-Referer": "https://techfren.net",
            "X-Title": "TechFren Discord Bot",
        }

    @staticmethod
    def get_model() -> str:
        """
        Get the configured LLM model or return default.
        
        Returns:
            str: The model name to use for requests
        """
        return getattr(config, 'llm_model', "x-ai/grok-3-mini-beta")

    @staticmethod
    async def handle_openai_error(error: Exception) -> str:
        """
        Standardized error handling for OpenAI operations.
        
        Args:
            error (Exception): The exception that occurred
            
        Returns:
            str: User-friendly error message
        """
        if isinstance(error, asyncio.TimeoutError):
            logger.error("OpenAI API request timed out")
            return "Sorry, the request timed out. Please try again later."
        else:
            logger.error(f"Error with OpenAI API: {str(error)}", exc_info=True)
            return "Sorry, I encountered an error while processing your request. Please try again later."

    @staticmethod
    async def make_chat_completion(
        client: AsyncOpenAI, 
        messages: list, 
        model: Optional[str] = None,
        max_tokens: int = 4000,
        temperature: float = 0.7
    ) -> Optional[str]:
        """
        Make a chat completion request with standardized parameters and error handling.
        
        Args:
            client (AsyncOpenAI): The OpenAI client instance
            messages (list): List of message dictionaries for the conversation
            model (Optional[str]): Model to use (defaults to configured model)
            max_tokens (int): Maximum tokens in response
            temperature (float): Sampling temperature
            
        Returns:
            Optional[str]: The completion response or None if failed
        """
        try:
            if model is None:
                model = OpenAIClientManager.get_model()

            completion = await client.chat.completions.create(
                extra_headers=OpenAIClientManager.get_headers(),
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature
            )

            response = completion.choices[0].message.content
            logger.info(f"OpenAI API response received successfully: {response[:50]}{'...' if len(response) > 50 else ''}")
            return response

        except Exception as e:
            error_message = await OpenAIClientManager.handle_openai_error(e)
            return error_message