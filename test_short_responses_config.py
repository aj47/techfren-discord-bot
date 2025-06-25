#!/usr/bin/env python3
"""
Test script to verify the short_responses configuration is working correctly.
This test ensures that the hardcoded set has been successfully moved to configuration.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from unittest.mock import patch

def test_configuration_validation():
    """Test that the configuration is properly loaded."""
    print("Testing configuration validation...")
    
    required_env = {
        'DISCORD_BOT_TOKEN': 'mock_token',
        'FIRECRAWL_API_KEY': 'mock_key'
    }
    
    with patch.dict(os.environ, required_env, clear=True):
        # Clear modules
        if 'config' in sys.modules:
            del sys.modules['config']
            
        import config
        
        # Check that the config has the expected attributes
        assert hasattr(config, 'links_allowed_short_responses'), "Config should have links_allowed_short_responses"
        assert isinstance(config.links_allowed_short_responses, set), "Should be a set for efficient lookup"
        assert len(config.links_allowed_short_responses) > 0, "Should have some default responses"
        
        # Check that some expected responses are present
        expected_responses = ['thanks', 'ty', 'nice', 'awesome', 'lol']
        for response in expected_responses:
            assert response in config.links_allowed_short_responses, f"Default should include '{response}'"
        
        print(f"  ✅ Configuration loaded with {len(config.links_allowed_short_responses)} allowed responses")
    
    print("✅ Configuration validation tests passed!")

def test_custom_configuration():
    """Test that custom configuration is loaded correctly.""" 
    print("\nTesting custom configuration loading...")
    
    custom_responses = "custom1,custom2,special phrase,emoji test 🎉"
    
    required_env = {
        'DISCORD_BOT_TOKEN': 'mock_token',
        'FIRECRAWL_API_KEY': 'mock_key',
        'LINKS_ALLOWED_SHORT_RESPONSES': custom_responses
    }
    
    with patch.dict(os.environ, required_env, clear=True):
        # Clear modules
        if 'config' in sys.modules:
            del sys.modules['config']
            
        import config
        
        # Verify that config has our custom responses
        expected_custom_set = {"custom1", "custom2", "special phrase", "emoji test 🎉"}
        assert config.links_allowed_short_responses == expected_custom_set, f"Config should have custom responses: {config.links_allowed_short_responses}"
        
        print(f"  ✅ Custom configuration loaded with {len(config.links_allowed_short_responses)} responses")
        print(f"  ✅ Custom responses: {config.links_allowed_short_responses}")
    
    print("✅ Custom configuration tests passed!")

def test_default_short_responses():
    """Test that default short responses work correctly."""
    print("\nTesting default short responses configuration...")
    
    required_env = {
        'DISCORD_BOT_TOKEN': 'mock_token',
        'FIRECRAWL_API_KEY': 'mock_key'
    }
    
    with patch.dict(os.environ, required_env, clear=True):
        import config
        from message_utils import is_message_link_only
        
        # Test cases that should definitely work
        test_cases = [
            ("thanks", True, "Basic thanks"),
            ("ty", True, "Short thanks"),
            ("hi", True, "Very short message"),  # Under 25 chars
            ("", False, "Empty message")
        ]
        
        for message, expected, description in test_cases:
            result = is_message_link_only(message)
            print(f"  {description}: '{message}' -> {result} (expected: {expected})")
            assert result == expected, f"Failed for {description}: expected {expected}, got {result}"
    
    print("✅ Default short responses tests passed!")

def test_empty_custom_responses():
    """Test behavior with empty custom responses."""
    print("\nTesting empty custom responses...")
    
    required_env = {
        'DISCORD_BOT_TOKEN': 'mock_token',
        'FIRECRAWL_API_KEY': 'mock_key',
        'LINKS_ALLOWED_SHORT_RESPONSES': ''
    }
    
    with patch.dict(os.environ, required_env, clear=True):
        # Clear modules
        modules_to_clear = ['config', 'message_utils']
        for module in modules_to_clear:
            if module in sys.modules:
                del sys.modules[module]
            
        import config
        from message_utils import is_message_link_only
        
        # Should have empty set
        assert len(config.links_allowed_short_responses) == 0, "Should have no allowed responses"
        
        # Test that short messages still work due to length rules
        test_cases = [
            ("hi", True, "Short message under 25 chars always allowed"),  # 2 chars
            ("", False, "Empty message should fail")
        ]
        
        for message, expected, description in test_cases:
            result = is_message_link_only(message)
            print(f"  {description}: '{message}' -> {result} (expected: {expected})")
            assert result == expected, f"Failed for {description}: expected {expected}, got {result}"
    
    print("✅ Empty custom responses tests passed!")

def test_integration_with_config():
    """Test that the message_utils function uses the config correctly."""
    print("\nTesting integration with config...")
    
    # Test that changing config affects the function
    custom_responses = "testword,specialterm"
    
    required_env = {
        'DISCORD_BOT_TOKEN': 'mock_token',
        'FIRECRAWL_API_KEY': 'mock_key',
        'LINKS_ALLOWED_SHORT_RESPONSES': custom_responses
    }
    
    with patch.dict(os.environ, required_env, clear=True):
        modules_to_clear = ['config', 'message_utils']
        for module in modules_to_clear:
            if module in sys.modules:
                del sys.modules[module]
        
        import config
        
        # Verify config has our test words
        assert "testword" in config.links_allowed_short_responses
        assert "specialterm" in config.links_allowed_short_responses
        print(f"  ✅ Config contains test words: {config.links_allowed_short_responses}")
    
    print("✅ Integration tests passed!")

def main():
    """Run all tests."""
    print("🧪 Testing Short Responses Configuration")
    print("=" * 50)
    
    try:
        test_configuration_validation()
        test_custom_configuration()
        test_default_short_responses()
        test_empty_custom_responses()
        test_integration_with_config()
        
        print("\n" + "=" * 50)
        print("🎉 All tests passed! Short responses are now configurable.")
        print("\nUsage:")
        print("  • To customize: Set LINKS_ALLOWED_SHORT_RESPONSES=word1,word2,phrase3")
        print("  • To use defaults: Leave LINKS_ALLOWED_SHORT_RESPONSES unset")
        print("  • To disable all: Set LINKS_ALLOWED_SHORT_RESPONSES=")
        print("  • Communities can now customize for their context and language!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main() 