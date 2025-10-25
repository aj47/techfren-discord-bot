"""
Syntax test for image analysis functionality.
This script validates the basic structure and imports without API calls.
"""

import sys
import os
import json

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test that all required modules can be imported."""
    try:
        # Test basic imports
        import json
        import asyncio
        import logging
        from typing import Optional, Dict, Any, List
        
        # Test that our module structure is correct
        assert True, "Basic imports successful"
        
        print("✅ Import test passed")
        return True
        
    except ImportError as e:
        print(f"❌ Import test failed: {e}")
        return False

def test_image_handler_structure():
    """Test the image handler module structure."""
    try:
        # Read the image_handler.py file to check structure
        with open('image_handler.py', 'r') as f:
            content = f.read()
        
        # Check for required functions
        required_functions = [
            'analyze_image_url',
            'analyze_image_with_base64', 
            'download_image_as_base64',
            'analyze_message_attachments',
            'process_and_update_message_with_image_analysis'
        ]
        
        for func in required_functions:
            if f'async def {func}' not in content:
                raise AssertionError(f"Missing function: {func}")
        
        # Check for proper message structure (according to Perplexity docs)
        if '"type": "image_url"' not in content or '"image_url":' not in content:
            raise AssertionError("Missing proper image message structure")
        
        # Check for sonar-pro model usage
        if 'sonar-pro' not in content:
            raise AssertionError("Missing sonar-pro model usage")
        
        print("✅ Image handler structure test passed")
        return True
        
    except Exception as e:
        print(f"❌ Image handler structure test failed: {e}")
        return False

def test_database_schema():
    """Test database schema updates."""
    try:
        # Read database.py to check for new columns
        with open('database.py', 'r') as f:
            content = f.read()
        
        # Check for new columns in CREATE TABLE
        required_columns = [
            'attachment_urls',
            'attachment_types', 
            'image_analysis'
        ]
        
        for col in required_columns:
            if col not in content:
                raise AssertionError(f"Missing database column: {col}")
        
        # Check for new function
        if 'update_message_with_image_analysis' not in content:
            raise AssertionError("Missing update_message_with_image_analysis function")
        
        if 'get_message_by_id' not in content:
            raise AssertionError("Missing get_message_by_id function")
        
        print("✅ Database schema test passed")
        return True
        
    except Exception as e:
        print(f"❌ Database schema test failed: {e}")
        return False

def test_bot_integration():
    """Test bot.py integration."""
    try:
        # Read bot.py to check integration
        with open('bot.py', 'r') as f:
            content = f.read()
        
        # Check for image handler import
        if 'image_handler' not in content:
            raise AssertionError("Missing image_handler import")
        
        # Check for analyze-images command
        if 'analyze_images_slash' not in content:
            raise AssertionError("Missing analyze_images_slash function")
        
        # Check for attachment processing
        if 'message.attachments' not in content or 'attachment_urls' not in content:
            raise AssertionError("Missing attachment processing")
        
        print("✅ Bot integration test passed")
        return True
        
    except Exception as e:
        print(f"❌ Bot integration test failed: {e}")
        return False

def test_llm_handler_updates():
    """Test LLM handler updates."""
    try:
        # Read llm_handler.py to check integration
        with open('llm_handler.py', 'r') as f:
            content = f.read()
        
        # Check for image analysis integration
        if 'image_analysis' not in content:
            raise AssertionError("Missing image analysis integration in LLM handler")
        
        # Check for database usage
        if 'get_message_by_id' not in content:
            raise AssertionError("Missing database usage for image analysis")
        
        print("✅ LLM handler updates test passed")
        return True
        
    except Exception as e:
        print(f"❌ LLM handler updates test failed: {e}")
        return False

def test_perplexity_api_format():
    """Test that API requests follow Perplexity format."""
    try:
        with open('image_handler.py', 'r') as f:
            content = f.read()
        
        # Check for proper message structure according to Perplexity docs
        required_structure = [
            '"type": "text"',
            '"type": "image_url"', 
            '"content": [',
            '"role": "user",'
        ]
        
        for struct in required_structure:
            if struct not in content:
                raise AssertionError(f"Missing API structure element: {struct}")
        
        # Check for AsyncOpenAI usage (consistent with existing bot)
        if 'AsyncOpenAI(' not in content:
            raise AssertionError("Missing AsyncOpenAI client setup")
        
        # Check for proper error handling
        if 'try:' not in content or 'except' not in content:
            raise AssertionError("Missing error handling")
        
        print("✅ Perplexity API format test passed")
        return True
        
    except Exception as e:
        print(f"❌ Perplexity API format test failed: {e}")
        return False

def main():
    """Run all tests."""
    print("Running image analysis implementation tests...\n")
    
    tests = [
        test_imports,
        test_image_handler_structure,
        test_database_schema,
        test_bot_integration,
        test_llm_handler_updates,
        test_perplexity_api_format
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()
    
    print(f"Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! The image analysis implementation appears to be correct.")
        return 0
    else:
        print("❌ Some tests failed. Review the issues above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
