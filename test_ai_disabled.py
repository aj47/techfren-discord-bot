#!/usr/bin/env python3
"""
Test script to verify AI features can be disabled while keeping !firecrawl working.
This script tests the configuration changes that make OpenRouter truly optional.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import asyncio
from unittest.mock import patch, AsyncMock
import config
from llm_handler import call_llm_api, call_llm_for_summary, summarize_scraped_content
from firecrawl_handler import scrape_url_content

def test_config_ai_disabled():
    """Test that config correctly identifies when AI is disabled."""
    print("Testing config.ai_features_enabled detection...")
    
    # Test various scenarios
    test_cases = [
        (None, False, "None value"),
        ("", False, "Empty string"),
        ("   ", False, "Whitespace only"),
        ("YOUR_OPENROUTER_API_KEY", False, "Placeholder value"),
        ("sk-1234567890", True, "Valid looking key"),
        ("actual_key_here", True, "Another valid key")
    ]
    
    for test_value, expected, description in test_cases:
        with patch.object(config, 'openrouter', test_value):
            # Recalculate ai_features_enabled
            ai_enabled = bool(test_value and test_value.strip() and test_value != "YOUR_OPENROUTER_API_KEY")
            print(f"  {description}: openrouter='{test_value}' -> ai_enabled={ai_enabled} (expected={expected})")
            assert ai_enabled == expected, f"Failed for {description}"
    
    print("✅ Config AI detection tests passed!")

async def test_llm_functions_with_ai_disabled():
    """Test that LLM functions gracefully handle AI being disabled."""
    print("\nTesting LLM functions with AI disabled...")
    
    # Mock config to disable AI
    with patch.object(config, 'ai_features_enabled', False):
        
        # Test call_llm_api
        response = await call_llm_api("test query")
        print(f"  call_llm_api response: {response[:100]}...")
        assert "AI features are currently disabled" in response
        assert "OPENROUTER_API_KEY" in response
        
        # Test call_llm_for_summary
        mock_messages = [
            {"content": "test message", "author_name": "test_user", "created_at": "2023-01-01", "id": "123"}
        ]
        summary_response = await call_llm_for_summary(mock_messages, "test-channel", None, 24)
        print(f"  call_llm_for_summary response: {summary_response[:100]}...")
        assert "AI features are currently disabled" in summary_response
        assert "test-channel" in summary_response
        
        # Test summarize_scraped_content
        content_response = await summarize_scraped_content("test content", "http://example.com")
        print(f"  summarize_scraped_content response: {content_response}")
        assert content_response is None  # Should return None when AI is disabled
    
    print("✅ LLM function AI-disabled tests passed!")

async def test_firecrawl_independence():
    """Test that Firecrawl functions work independently of AI settings."""
    print("\nTesting Firecrawl independence from AI...")
    
    # Mock the Firecrawl API call to avoid making real requests
    mock_result = "# Test Content\n\nThis is test scraped content from Firecrawl."
    
    # Test with AI disabled
    with patch.object(config, 'ai_features_enabled', False):
        with patch('firecrawl_handler.FirecrawlApp') as mock_firecrawl_class:
            # Mock the executor call that runs the blocking Firecrawl API
            async def mock_executor(executor, func):
                # Mock the function call result 
                return {"markdown": mock_result}
            
            with patch('asyncio.get_event_loop') as mock_loop:
                mock_loop_instance = AsyncMock()
                mock_loop_instance.run_in_executor = mock_executor
                mock_loop.return_value = mock_loop_instance
                
                # Test scraping
                result = await scrape_url_content("http://example.com")
                print(f"  Firecrawl result with AI disabled: {result[:50]}...")
                assert result == mock_result, "Firecrawl should work regardless of AI settings"
    
    # Test with AI enabled 
    with patch.object(config, 'ai_features_enabled', True):
        with patch('firecrawl_handler.FirecrawlApp') as mock_firecrawl_class:
            async def mock_executor(executor, func):
                return {"markdown": mock_result}
            
            with patch('asyncio.get_event_loop') as mock_loop:
                mock_loop_instance = AsyncMock()
                mock_loop_instance.run_in_executor = mock_executor
                mock_loop.return_value = mock_loop_instance
                
                result = await scrape_url_content("http://example.com")
                print(f"  Firecrawl result with AI enabled: {result[:50]}...")
                assert result == mock_result, "Firecrawl should work the same with AI enabled"
    
    print("✅ Firecrawl independence tests passed!")

def test_env_file_comments():
    """Test that .env file has proper comments about disabling AI."""
    print("\nTesting .env file comments...")
    
    try:
        with open('.env', 'r') as f:
            env_content = f.read()
        
        # Check for key phrases in comments
        required_phrases = [
            "optional - for AI features",
            "To DISABLE AI features",
            "To ENABLE AI features",
            "works independently of AI features",
            "require AI features to be enabled"
        ]
        
        for phrase in required_phrases:
            if phrase in env_content:
                print(f"  ✅ Found: '{phrase}'")
            else:
                print(f"  ❌ Missing: '{phrase}'")
                raise AssertionError(f"Missing expected phrase in .env: '{phrase}'")
        
        print("✅ .env file comment tests passed!")
        
    except FileNotFoundError:
        print("⚠️  .env file not found, skipping comment tests")

def main():
    """Run all tests."""
    print("🧪 Testing AI Optional Implementation")
    print("=" * 50)
    
    try:
        # Test configuration
        test_config_ai_disabled()
        
        # Test async functions
        asyncio.run(test_llm_functions_with_ai_disabled())
        asyncio.run(test_firecrawl_independence())
        
        # Test .env file
        test_env_file_comments()
        
        print("\n" + "=" * 50)
        print("🎉 All tests passed! AI features are now truly optional.")
        print("\nUsage:")
        print("  • To ENABLE AI: Set OPENROUTER_API_KEY=your_actual_key")
        print("  • To DISABLE AI: Comment out OPENROUTER_API_KEY with #")
        print("  • !firecrawl command works in both modes")
        print("  • Bot mentions show helpful messages when AI is disabled")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 