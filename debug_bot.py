"""
Debug bot runner for testing Discord bot functionality without connecting to Discord.
This module initializes the bot components and provides a way to process messages
through the existing command handlers using mock Discord objects.
"""

import asyncio
import sys
import os
import time
from datetime import datetime, timezone
from typing import Optional

def check_dependencies():
    """Check if required dependencies are installed"""
    missing_deps = []

    try:
        import openai
    except ImportError:
        missing_deps.append("openai")

    try:
        import discord
    except ImportError:
        missing_deps.append("discord.py")

    try:
        from dotenv import load_dotenv
    except ImportError:
        missing_deps.append("python-dotenv")

    if missing_deps:
        print("❌ Missing required dependencies:")
        for dep in missing_deps:
            print(f"   - {dep}")
        print("\n💡 Install dependencies with:")
        print("   pip install -r requirements.txt")
        print("\n   Or install individually:")
        for dep in missing_deps:
            print(f"   pip install {dep}")
        return False
    return True

# Check dependencies before importing bot components
if not check_dependencies():
    sys.exit(1)

# Import bot components
import database
from logging_config import logger
from config_validator import validate_config
from command_handler import handle_bot_command, handle_sum_day_command, handle_sum_hr_command
from mock_discord import MockClient, MockMessage, create_debug_message
import re


class DebugBot:
    """Debug version of the Discord bot for testing without Discord connection"""
    
    def __init__(self):
        self.client = MockClient()
        self.initialized = False
        
    async def initialize(self):
        """Initialize the bot components (database, config, etc.)"""
        try:
            # Import and validate config
            import config
            validate_config(config)
            
            # Initialize database
            database.init_database()
            
            # Check database connection
            if not database.check_database_connection():
                logger.critical('Database connection check failed.')
                return False
                
            message_count = database.get_message_count()
            logger.info(f'Debug bot initialized. Database message count: {message_count}')
            
            # Log database file information
            db_file_path = os.path.join(os.getcwd(), database.DB_FILE)
            if os.path.exists(db_file_path):
                logger.info(f'Database file exists at: {db_file_path}')
                logger.info(f'Database file size: {os.path.getsize(db_file_path)} bytes')
            else:
                logger.critical(f'Database file does not exist at: {db_file_path}')
                return False
                
            self.initialized = True
            logger.info("Debug bot initialization complete")
            return True
            
        except ImportError:
            logger.critical("Config file not found", exc_info=True)
            print("ERROR: Please create a config.py file or .env file with your configuration.")
            return False
        except Exception as e:
            logger.critical(f"Unexpected error during debug bot initialization: {e}", exc_info=True)
            return False
    
    async def process_message(self, message: MockMessage):
        """Process a message through the bot's command handlers"""
        if not self.initialized:
            print("ERROR: Bot not initialized. Call initialize() first.")
            return
            
        # Store message in database (similar to real bot)
        try:
            # Determine if this is a command and what type
            is_command = False
            command_type = None
            
            bot_mention = f'<@{self.client.user.id}>'
            bot_mention_alt = f'<@!{self.client.user.id}>'
            if message.content.startswith(bot_mention) or message.content.startswith(bot_mention_alt):
                is_command = True
                command_type = "mention"
            elif message.content.startswith('/sum-day'):
                is_command = True
                command_type = "/sum-day"
            elif message.content.startswith('/sum-hr'):
                is_command = True
                command_type = "/sum-hr"
            
            # Store in database
            guild_id = str(message.guild.id) if message.guild else None
            channel_id = str(message.channel.id)
            
            success = database.store_message(
                message_id=str(message.id),
                author_id=str(message.author.id),
                author_name=str(message.author),
                channel_id=channel_id,
                channel_name=message.channel.name,
                content=message.content,
                created_at=message.created_at,
                guild_id=guild_id,
                guild_name=message.guild.name if message.guild else None,
                is_bot=message.author.bot,
                is_command=is_command,
                command_type=command_type
            )
            
            if not success:
                logger.warning(f"Failed to store debug message {message.id} in database")
                
        except Exception as e:
            logger.error(f"Error storing debug message in database: {str(e)}", exc_info=True)
        
        # Process commands
        bot_mention = f'<@{self.client.user.id}>'
        bot_mention_alt = f'<@!{self.client.user.id}>'
        is_mention_command = message.content.startswith(bot_mention) or message.content.startswith(bot_mention_alt)
        is_sum_day_command = message.content.startswith('/sum-day')
        is_sum_hr_command = message.content.startswith('/sum-hr')
        
        try:
            if is_mention_command:
                logger.debug(f"Processing mention command in debug mode")
                await handle_bot_command(message, self.client.user)
            elif is_sum_day_command:
                await handle_sum_day_command(message, self.client.user)
            elif is_sum_hr_command:
                await handle_sum_hr_command(message, self.client.user)
            else:
                print("[DEBUG]: Message doesn't match any known command patterns")
                print(f"[DEBUG]: Content: '{message.content}'")
                print(f"[DEBUG]: Expected mention: '{bot_mention}' or '{bot_mention_alt}'")
                
        except Exception as e:
            logger.error(f"Error processing debug command: {e}", exc_info=True)
            print(f"[ERROR]: Failed to process command: {e}")


# Global debug bot instance
debug_bot = None


async def get_debug_bot():
    """Get or create the debug bot instance"""
    global debug_bot
    if debug_bot is None:
        debug_bot = DebugBot()
        success = await debug_bot.initialize()
        if not success:
            print("Failed to initialize debug bot")
            return None
    return debug_bot


async def process_debug_message(content: str, user_id: int = 123456789, username: str = "DebugUser"):
    """
    Process a debug message through the bot
    
    Args:
        content: The message content
        user_id: The user ID (default: 123456789)
        username: The username (default: "DebugUser")
    """
    bot = await get_debug_bot()
    if bot is None:
        return
        
    message = create_debug_message(content, user_id, username)
    print(f"[USER MESSAGE]: {content}")
    await bot.process_message(message)


if __name__ == "__main__":
    """Run a simple test of the debug bot"""
    async def test_debug_bot():
        print("Testing debug bot...")
        
        # Test mention command
        await process_debug_message(f"<@111111111> Hello, how are you?")
        
        # Test sum-day command
        await process_debug_message("/sum-day")
        
    asyncio.run(test_debug_bot())
