"""
Mock Discord objects for debugging and testing the bot without connecting to Discord.
These classes simulate the Discord.py library objects with the same interface.
"""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
import asyncio
import time


def generate_mock_message_id():
    """Generate a unique message ID for mock messages"""
    return int(time.time() * 1000000)  # Use microsecond timestamp


class MockUser:
    """Mock Discord User object"""
    def __init__(self, user_id: int = 123456789, name: str = "DebugUser", bot: bool = False):
        self.id = user_id
        self.name = name
        self.bot = bot
        self.display_name = name
        
    def __str__(self):
        return self.name


class MockChannel:
    """Mock Discord Channel object"""
    def __init__(self, channel_id: int = 987654321, name: str = "bot-devs"):
        self.id = channel_id
        self.name = name
        self._messages: List[Dict[str, Any]] = []
        
    async def send(self, content: str, allowed_mentions=None):
        """Mock sending a message to the channel"""
        message_id = generate_mock_message_id()
        mock_message = MockMessage(
            message_id=message_id,
            content=content,
            author=MockUser(user_id=111111111, name="TechFrenBot", bot=True),
            channel=self,
            guild=MockGuild()
        )
        self._messages.append({
            'id': message_id,
            'content': content,
            'author': 'TechFrenBot',
            'timestamp': datetime.now(timezone.utc)
        })
        print(f"[BOT RESPONSE]: {content}")
        return mock_message
        
    async def create_thread(self, name: str):
        """Mock creating a thread"""
        thread = MockThread(name=name, parent_channel=self)
        print(f"[THREAD CREATED]: {name}")
        return thread


class MockThread(MockChannel):
    """Mock Discord Thread object (inherits from MockChannel)"""
    def __init__(self, name: str, parent_channel: MockChannel):
        super().__init__(channel_id=parent_channel.id + 1000, name=name)
        self.parent_channel = parent_channel
        
    async def send(self, content: str, allowed_mentions=None):
        """Mock sending a message to the thread"""
        message_id = generate_mock_message_id()
        mock_message = MockMessage(
            message_id=message_id,
            content=content,
            author=MockUser(user_id=111111111, name="TechFrenBot", bot=True),
            channel=self,
            guild=MockGuild()
        )
        self._messages.append({
            'id': message_id,
            'content': content,
            'author': 'TechFrenBot',
            'timestamp': datetime.now(timezone.utc)
        })
        print(f"[BOT RESPONSE in {self.name}]: {content}")
        return mock_message


class MockGuild:
    """Mock Discord Guild (server) object"""
    def __init__(self, guild_id: int = 555555555, name: str = "Debug Server"):
        self.id = guild_id
        self.name = name
        self.text_channels = [MockChannel(name="bot-devs"), MockChannel(name="general")]


class MockMessage:
    """Mock Discord Message object"""
    def __init__(self, message_id: int, content: str, author: MockUser,
                 channel: MockChannel, guild: Optional[MockGuild] = None):
        self.id = message_id
        self.content = content
        self.author = author
        self.channel = channel
        self.guild = guild or MockGuild()
        self.created_at = datetime.now(timezone.utc)

    async def create_thread(self, name: str):
        """Mock creating a thread from this message"""
        return await self.channel.create_thread(name)

    async def delete(self):
        """Mock deleting a message"""
        print(f"[MESSAGE DELETED]: {self.content[:50]}...")
        return True


class MockClient:
    """Mock Discord Client object"""
    def __init__(self):
        self.user = MockUser(user_id=111111111, name="TechFrenBot", bot=True)
        self.guilds = [MockGuild()]
        
    async def close(self):
        """Mock closing the client"""
        print("[DEBUG]: Mock client closed")


class MockAllowedMentions:
    """Mock Discord AllowedMentions object"""
    @staticmethod
    def none():
        return MockAllowedMentions()


# Mock the discord module components we need
class MockDiscord:
    """Mock discord module"""
    class Intents:
        @staticmethod
        def default():
            return MockIntents()
            
        message_content = True
    
    Client = MockClient
    AllowedMentions = MockAllowedMentions
    LoginFailure = Exception
    NotFound = Exception


class MockIntents:
    """Mock Discord Intents object"""
    def __init__(self):
        self.message_content = True


def create_debug_message(content: str, user_id: int = 123456789, username: str = "DebugUser") -> MockMessage:
    """
    Create a mock message for debugging purposes

    Args:
        content: The message content
        user_id: The user ID (default: 123456789)
        username: The username (default: "DebugUser")

    Returns:
        MockMessage object ready for processing
    """
    author = MockUser(user_id=user_id, name=username)
    channel = MockChannel(name="bot-devs")
    guild = MockGuild()

    message = MockMessage(
        message_id=generate_mock_message_id(),
        content=content,
        author=author,
        channel=channel,
        guild=guild
    )

    return message
