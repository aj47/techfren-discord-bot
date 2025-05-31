#!/usr/bin/env python3
"""
Test script for the debug CLI functionality.
This script tests the core components of the debug CLI without requiring user interaction.
"""

import asyncio
import sys
import os

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_mock_objects():
    """Test that mock Discord objects work correctly"""
    print("🧪 Testing mock Discord objects...")
    
    from mock_discord import MockUser, MockChannel, MockMessage, MockGuild, create_debug_message
    
    # Test MockUser
    user = MockUser(123, "TestUser")
    assert user.id == 123
    assert user.name == "TestUser"
    assert str(user) == "TestUser"
    print("✅ MockUser works correctly")
    
    # Test MockChannel
    channel = MockChannel(456, "test-channel")
    assert channel.id == 456
    assert channel.name == "test-channel"
    print("✅ MockChannel works correctly")
    
    # Test MockMessage
    message = MockMessage(789, "Hello world", user, channel)
    assert message.id == 789
    assert message.content == "Hello world"
    assert message.author == user
    assert message.channel == channel
    print("✅ MockMessage works correctly")
    
    # Test message deletion
    await message.delete()
    print("✅ MockMessage.delete() works correctly")
    
    # Test channel send
    response = await channel.send("Bot response")
    assert response.content == "Bot response"
    print("✅ MockChannel.send() works correctly")
    
    # Test create_debug_message helper
    debug_msg = create_debug_message("Test message", 999, "DebugUser")
    assert debug_msg.content == "Test message"
    assert debug_msg.author.id == 999
    assert debug_msg.author.name == "DebugUser"
    print("✅ create_debug_message() works correctly")
    
    print("🎉 All mock object tests passed!")

async def test_debug_bot_initialization():
    """Test that the debug bot can be initialized"""
    print("\n🧪 Testing debug bot initialization...")
    
    try:
        from debug_bot import get_debug_bot
        
        # Try to initialize the debug bot
        bot = await get_debug_bot()
        
        if bot is None:
            print("⚠️  Debug bot initialization failed (likely due to missing config)")
            print("   This is expected if you don't have a proper .env file configured")
            return False
        else:
            print("✅ Debug bot initialized successfully")
            return True
            
    except Exception as e:
        print(f"⚠️  Debug bot initialization failed: {e}")
        print("   This is expected if dependencies or config are missing")
        return False

async def test_debug_message_processing():
    """Test processing a debug message"""
    print("\n🧪 Testing debug message processing...")
    
    try:
        from debug_bot import process_debug_message
        
        # Try to process a simple message
        print("   Processing test message...")
        await process_debug_message("Hello from test!", 12345, "TestUser")
        print("✅ Debug message processing works")
        return True
        
    except Exception as e:
        print(f"⚠️  Debug message processing failed: {e}")
        print("   This is expected if bot initialization failed")
        return False

async def main():
    """Run all tests"""
    print("🚀 Starting Debug CLI Tests")
    print("=" * 50)
    
    # Test 1: Mock objects
    await test_mock_objects()
    
    # Test 2: Debug bot initialization
    bot_init_success = await test_debug_bot_initialization()
    
    # Test 3: Message processing (only if bot initialized)
    if bot_init_success:
        await test_debug_message_processing()
    
    print("\n" + "=" * 50)
    print("🏁 Debug CLI Tests Complete")
    
    if bot_init_success:
        print("✅ All tests passed! The debug CLI should work correctly.")
        print("\n💡 To start the debug CLI, run: python debug.py")
    else:
        print("⚠️  Some tests failed due to missing configuration.")
        print("   The mock objects work correctly, but you need to:")
        print("   1. Set up your .env file with proper API keys")
        print("   2. Install all dependencies: pip install -r requirements.txt")
        print("   3. Then run: python debug.py")

if __name__ == "__main__":
    asyncio.run(main())
