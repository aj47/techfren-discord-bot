#!/usr/bin/env python3
"""
Command-line debug interface for the Discord bot.
This allows you to test bot functionality by typing messages as if they were
coming from the #bot-devs channel.
"""

import asyncio
import sys
import signal
from datetime import datetime

# Import debug bot components with error handling
try:
    from debug_bot import process_debug_message, get_debug_bot
    from logging_config import logger
except ImportError as e:
    print(f"❌ Failed to import bot components: {e}")
    print("💡 Make sure you have installed all dependencies:")
    print("   pip install -r requirements.txt")
    sys.exit(1)


class DebugCLI:
    """Command-line interface for debugging the Discord bot"""
    
    def __init__(self):
        self.running = True
        self.user_id = 123456789
        self.username = "DebugUser"
        
    def print_welcome(self):
        """Print welcome message and instructions"""
        print("=" * 60)
        print("🤖 Discord Bot Debug CLI")
        print("=" * 60)
        print("This interface simulates sending messages to the #bot-devs channel.")
        print("You can test all bot commands here without connecting to Discord.")
        print()
        print("Available commands:")
        print("  @bot <query>     - Send a query to the bot (mention command)")
        print("  /sum-day         - Generate daily summary")
        print("  /sum-hr <hours>  - Generate summary for specified hours")
        print("  .help            - Show this help message")
        print("  .user <name>     - Change your username")
        print("  .quit or .exit   - Exit the debug CLI")
        print()
        print("Note: The bot will process your messages and respond as if you")
        print("      were in a real Discord channel.")
        print("=" * 60)
        print()
        
    def print_help(self):
        """Print help message"""
        print()
        print("🔧 Debug CLI Commands:")
        print("  @bot <query>     - Ask the bot a question")
        print("                     Example: @bot What is Python?")
        print("  /sum-day         - Get summary of messages from past 24 hours")
        print("  /sum-hr <hours>  - Get summary of messages from past N hours")
        print("                     Example: /sum-hr 6")
        print()
        print("🛠️  CLI Controls:")
        print("  .help            - Show this help")
        print("  .user <name>     - Change your debug username")
        print("                     Example: .user TestUser")
        print("  .quit or .exit   - Exit the debug interface")
        print()
        print("💡 Tips:")
        print("  - All bot functionality works including rate limiting")
        print("  - Messages are stored in the same database as the real bot")
        print("  - URL processing and scraping will work if configured")
        print("  - Use Ctrl+C to force quit if needed")
        print()
        
    async def handle_cli_command(self, command: str) -> bool:
        """
        Handle CLI-specific commands (starting with .)
        
        Args:
            command: The command to handle
            
        Returns:
            True if command was handled, False if it should be processed as bot message
        """
        command = command.strip()
        
        if command in ['.quit', '.exit']:
            print("👋 Goodbye!")
            self.running = False
            return True
            
        elif command == '.help':
            self.print_help()
            return True
            
        elif command.startswith('.user '):
            new_username = command[6:].strip()
            if new_username:
                old_username = self.username
                self.username = new_username
                print(f"✅ Username changed from '{old_username}' to '{new_username}'")
            else:
                print("❌ Please provide a username. Example: .user TestUser")
            return True
            
        return False
        
    async def process_input(self, user_input: str):
        """Process user input and send to bot"""
        user_input = user_input.strip()
        
        if not user_input:
            return
            
        # Handle CLI commands
        if user_input.startswith('.'):
            await self.handle_cli_command(user_input)
            return
            
        # Convert @bot to proper mention format
        if user_input.startswith('@bot '):
            user_input = f"<@111111111> {user_input[5:]}"
        elif user_input == '@bot':
            user_input = "<@111111111>"
            
        # Process through bot
        try:
            await process_debug_message(user_input, self.user_id, self.username)
        except Exception as e:
            print(f"❌ Error processing message: {e}")
            logger.error(f"CLI error processing message: {e}", exc_info=True)
            
    async def run(self):
        """Main CLI loop"""
        # Initialize bot
        print("🔄 Initializing debug bot...")
        bot = await get_debug_bot()
        if bot is None:
            print("❌ Failed to initialize bot. Check your configuration.")
            return
            
        print("✅ Bot initialized successfully!")
        self.print_welcome()
        
        # Set up signal handler for graceful shutdown
        def signal_handler(signum, frame):
            print("\n🛑 Received interrupt signal. Shutting down...")
            self.running = False
            
        signal.signal(signal.SIGINT, signal_handler)
        
        # Main input loop
        try:
            while self.running:
                try:
                    # Get user input
                    user_input = input(f"[{self.username}] > ").strip()
                    
                    if user_input:
                        await self.process_input(user_input)
                        
                except EOFError:
                    # Handle Ctrl+D
                    print("\n👋 Goodbye!")
                    break
                except KeyboardInterrupt:
                    # Handle Ctrl+C
                    print("\n🛑 Interrupted. Use .quit to exit gracefully.")
                    continue
                    
        except Exception as e:
            print(f"❌ Unexpected error in CLI: {e}")
            logger.error(f"Unexpected CLI error: {e}", exc_info=True)
            
        print("🔄 Debug CLI shutting down...")


async def main():
    """Main entry point"""
    cli = DebugCLI()
    await cli.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)
