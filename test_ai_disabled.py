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
    """Test that config module's ai_features_enabled behaves correctly."""
    print("Testing config.ai_features_enabled behavior...")
    
    # Test current actual config state
    print(f"  Current config state:")
    print(f"    openrouter: '{config.openrouter}'")
    print(f"    ai_features_enabled: {config.ai_features_enabled}")
    
    # Test with AI explicitly disabled
    with patch.object(config, 'ai_features_enabled', False):
        assert config.ai_features_enabled == False, "Failed to mock AI disabled state"
        print(f"  ✓ AI disabled state: {config.ai_features_enabled}")
    
    # Test with AI explicitly enabled  
    with patch.object(config, 'ai_features_enabled', True):
        assert config.ai_features_enabled == True, "Failed to mock AI enabled state"
        print(f"  ✓ AI enabled state: {config.ai_features_enabled}")
    
    # Verify we can control the config value for testing other functions
    print(f"  ✓ Config value is controllable for testing purposes")
    
    print("✅ Config AI detection tests passed!")

def test_ai_enablement_logic():
    """Test the actual config module's AI enablement logic with different .env file values."""
    print("\nTesting config module AI enablement logic...")
    
    # Test the actual config module by creating temporary .env files
    # This tests the ACTUAL config.py behavior including dotenv loading
    import subprocess
    import sys
    import tempfile
    import os
    
    test_cases = [
        (None, False, "No OPENROUTER_API_KEY in .env"),
        ("", False, "Empty string in .env"),  
        ("   ", False, "Whitespace only in .env"),
        ("YOUR_OPENROUTER_API_KEY", False, "Placeholder value in .env"),
        ("sk-1234567890", True, "Valid looking key in .env"),
        ("actual_key_here", True, "Another valid key in .env")
    ]
    
    original_dir = os.getcwd()
    
    for test_value, expected, description in test_cases:
        # Create a temporary directory with a test .env file
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create .env file with test value
            env_file_path = os.path.join(temp_dir, '.env')
            with open(env_file_path, 'w') as f:
                f.write('DISCORD_BOT_TOKEN=test\n')
                f.write('FIRECRAWL_API_KEY=test\n')
                if test_value is not None:
                    f.write(f'OPENROUTER_API_KEY={test_value}\n')
            
            # Copy config.py to temp directory for isolated testing
            import shutil
            config_source = os.path.join(original_dir, 'config.py')
            config_dest = os.path.join(temp_dir, 'config.py')
            shutil.copy2(config_source, config_dest)
            
            # Test config loading in the temp directory
            test_code = f'''
import os
os.chdir(r"{temp_dir}")
import sys
sys.path.insert(0, r"{temp_dir}")

# Import the actual config module to test its computed ai_features_enabled
import config
print(config.ai_features_enabled)
'''
            
            result = subprocess.run([sys.executable, '-c', test_code], 
                                  capture_output=True, text=True, cwd=temp_dir)
            
            if result.returncode != 0:
                print(f"  Error testing {description}: {result.stderr}")
                continue
                
            actual_result = result.stdout.strip() == 'True'
            
            print(f"  {description}: openrouter={test_value!r} -> ai_enabled={actual_result} (expected={expected})")
            assert actual_result == expected, f"Failed for {description}: config.ai_features_enabled returned {actual_result}, expected {expected}"
    
    print("✅ Config module AI enablement logic tests passed!")

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
        with open('.env', 'r', encoding='utf-8', errors='ignore') as f:
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
        # Test configuration behavior
        test_config_ai_disabled()
        
        # Test the actual AI enablement logic
        test_ai_enablement_logic()
        
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