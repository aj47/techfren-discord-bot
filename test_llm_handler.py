"""
Test suite for LLM handler functionality.
Tests the OpenAI integration and summarization logic.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import logging

# Import the module to test
import llm_handler

# Set up logging for tests
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('test_llm_handler')


class TestLLMHandler:
    """Test the LLM handler functionality."""

    @pytest.mark.asyncio
    async def test_summarize_content_success(self):
        """Test successful content summarization."""
        # Mock OpenAI response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "This is a test summary."
        
        with patch('llm_handler.openai.ChatCompletion.acreate', return_value=mock_response):
            result = await llm_handler.summarize_content("Test content to summarize")
            
            assert result is not None
            assert "This is a test summary." in result

    @pytest.mark.asyncio
    async def test_summarize_content_api_error(self):
        """Test handling of OpenAI API errors."""
        with patch('llm_handler.openai.ChatCompletion.acreate', side_effect=Exception("API Error")):
            result = await llm_handler.summarize_content("Test content")
            
            # Should handle error gracefully
            assert result is None or "error" in result.lower()

    @pytest.mark.asyncio
    async def test_summarize_content_empty_input(self):
        """Test handling of empty input."""
        result = await llm_handler.summarize_content("")
        
        # Should handle empty input gracefully
        assert result is None or result == ""

    @pytest.mark.asyncio
    async def test_summarize_content_long_input(self):
        """Test handling of very long input content."""
        long_content = "This is a test. " * 1000  # Very long content
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Summary of long content."
        
        with patch('llm_handler.openai.ChatCompletion.acreate', return_value=mock_response):
            result = await llm_handler.summarize_content(long_content)
            
            assert result is not None
            assert len(result) < len(long_content)  # Should be shorter than input

    @pytest.mark.asyncio
    async def test_config_validation(self):
        """Test that the handler validates OpenAI API key configuration."""
        with patch('config.openai_api_key', None):
            # Should handle missing API key gracefully
            result = await llm_handler.summarize_content("Test content")
            assert result is None or "configuration" in result.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
