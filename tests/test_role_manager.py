"""
Tests for the role_manager module.

This test suite verifies the functionality of self-assignable role management,
including adding roles, removing roles, error handling, and permission validation.
"""

import pytest
from unittest.mock import AsyncMock, Mock, MagicMock
import discord
from role_manager import RoleManager


class TestRoleManagerAddRole:
    """Test suite for RoleManager.add_role_to_member()"""

    @pytest.mark.asyncio
    async def test_add_role_success(self):
        """Test successfully adding a role to a member"""
        # Create mock member
        member = Mock(spec=discord.Member)
        member.id = 12345
        member.roles = []

        # Create mock role
        mock_role = Mock(spec=discord.Role)
        mock_role.id = 98765
        mock_role.name = "voice gang"
        mock_role.mention = "@voice gang"
        mock_role.position = 5

        # Create mock guild and bot member
        mock_guild = Mock(spec=discord.Guild)
        mock_guild.id = 11111
        mock_guild.roles = [mock_role]

        mock_bot_member = Mock(spec=discord.Member)
        mock_bot_top_role = Mock()
        mock_bot_top_role.position = 10
        mock_bot_member.top_role = mock_bot_top_role

        mock_guild.me = mock_bot_member
        member.guild = mock_guild

        # Mock the add_roles method
        member.add_roles = AsyncMock()

        # Execute test
        success, message = await RoleManager.add_role_to_member(member, "voice-gang")

        # Assertions
        assert success is True
        assert "@voice gang" in message
        assert "✅" in message
        member.add_roles.assert_called_once_with(mock_role, reason="Self-assigned via /join command")

    @pytest.mark.asyncio
    async def test_add_role_already_has_role(self):
        """Test adding a role that the user already has"""
        # Create mock member with existing role
        mock_role = Mock(spec=discord.Role)
        mock_role.id = 98765
        mock_role.name = "voice gang"
        mock_role.mention = "@voice gang"

        member = Mock(spec=discord.Member)
        member.id = 12345
        member.roles = [mock_role]

        # Create mock guild
        mock_guild = Mock(spec=discord.Guild)
        mock_guild.id = 11111
        mock_guild.roles = [mock_role]
        member.guild = mock_guild

        # Execute test
        success, message = await RoleManager.add_role_to_member(member, "voice-gang")

        # Assertions
        assert success is False
        assert "already have" in message.lower()

    @pytest.mark.asyncio
    async def test_add_invalid_role_key(self):
        """Test attempting to add a non-whitelisted role"""
        member = Mock(spec=discord.Member)

        # Execute test
        success, message = await RoleManager.add_role_to_member(member, "admin")

        # Assertions
        assert success is False
        assert "not self-assignable" in message

    @pytest.mark.asyncio
    async def test_add_role_not_found_in_guild(self):
        """Test adding a role that doesn't exist in the guild"""
        member = Mock(spec=discord.Member)
        member.id = 12345
        member.roles = []

        # Create mock guild with no roles
        mock_guild = Mock(spec=discord.Guild)
        mock_guild.id = 11111
        mock_guild.roles = []  # Empty roles list
        member.guild = mock_guild

        # Execute test
        success, message = await RoleManager.add_role_to_member(member, "voice-gang")

        # Assertions
        assert success is False
        assert "not found" in message.lower()
        assert "contact an admin" in message.lower()

    @pytest.mark.asyncio
    async def test_add_role_hierarchy_error(self):
        """Test adding a role when bot doesn't have sufficient hierarchy position"""
        member = Mock(spec=discord.Member)
        member.id = 12345
        member.roles = []

        # Create mock role with higher position than bot
        mock_role = Mock(spec=discord.Role)
        mock_role.id = 98765
        mock_role.name = "voice gang"
        mock_role.position = 15  # Higher than bot's position

        # Create mock guild and bot member
        mock_guild = Mock(spec=discord.Guild)
        mock_guild.id = 11111
        mock_guild.roles = [mock_role]

        mock_bot_member = Mock(spec=discord.Member)
        mock_bot_top_role = Mock()
        mock_bot_top_role.position = 10  # Bot's position is lower
        mock_bot_member.top_role = mock_bot_top_role

        mock_guild.me = mock_bot_member
        member.guild = mock_guild

        # Execute test
        success, message = await RoleManager.add_role_to_member(member, "voice-gang")

        # Assertions
        assert success is False
        assert "hierarchy" in message.lower()

    @pytest.mark.asyncio
    async def test_add_role_forbidden_error(self):
        """Test adding a role when bot lacks permissions"""
        member = Mock(spec=discord.Member)
        member.id = 12345
        member.roles = []

        # Create mock role
        mock_role = Mock(spec=discord.Role)
        mock_role.id = 98765
        mock_role.name = "voice gang"
        mock_role.position = 5

        # Create mock guild and bot member
        mock_guild = Mock(spec=discord.Guild)
        mock_guild.id = 11111
        mock_guild.roles = [mock_role]

        mock_bot_member = Mock(spec=discord.Member)
        mock_bot_top_role = Mock()
        mock_bot_top_role.position = 10
        mock_bot_member.top_role = mock_bot_top_role

        mock_guild.me = mock_bot_member
        member.guild = mock_guild

        # Mock add_roles to raise Forbidden
        member.add_roles = AsyncMock(side_effect=discord.Forbidden(Mock(), "Insufficient permissions"))

        # Execute test
        success, message = await RoleManager.add_role_to_member(member, "voice-gang")

        # Assertions
        assert success is False
        assert "permission" in message.lower()

    @pytest.mark.asyncio
    async def test_add_role_http_error(self):
        """Test adding a role when Discord API returns an HTTP error"""
        member = Mock(spec=discord.Member)
        member.id = 12345
        member.roles = []

        # Create mock role
        mock_role = Mock(spec=discord.Role)
        mock_role.id = 98765
        mock_role.name = "voice gang"
        mock_role.position = 5

        # Create mock guild and bot member
        mock_guild = Mock(spec=discord.Guild)
        mock_guild.id = 11111
        mock_guild.roles = [mock_role]

        mock_bot_member = Mock(spec=discord.Member)
        mock_bot_top_role = Mock()
        mock_bot_top_role.position = 10
        mock_bot_member.top_role = mock_bot_top_role

        mock_guild.me = mock_bot_member
        member.guild = mock_guild

        # Mock add_roles to raise HTTPException
        member.add_roles = AsyncMock(side_effect=discord.HTTPException(Mock(), "Service unavailable"))

        # Execute test
        success, message = await RoleManager.add_role_to_member(member, "voice-gang")

        # Assertions
        assert success is False
        assert "discord error" in message.lower()


class TestRoleManagerRemoveRole:
    """Test suite for RoleManager.remove_role_from_member()"""

    @pytest.mark.asyncio
    async def test_remove_role_success(self):
        """Test successfully removing a role from a member"""
        # Create mock role
        mock_role = Mock(spec=discord.Role)
        mock_role.id = 98765
        mock_role.name = "live gang"
        mock_role.mention = "@live gang"
        mock_role.position = 5

        # Create mock member with the role
        member = Mock(spec=discord.Member)
        member.id = 12345
        member.roles = [mock_role]

        # Create mock guild and bot member
        mock_guild = Mock(spec=discord.Guild)
        mock_guild.id = 11111
        mock_guild.roles = [mock_role]

        mock_bot_member = Mock(spec=discord.Member)
        mock_bot_top_role = Mock()
        mock_bot_top_role.position = 10
        mock_bot_member.top_role = mock_bot_top_role

        mock_guild.me = mock_bot_member
        member.guild = mock_guild

        # Mock the remove_roles method
        member.remove_roles = AsyncMock()

        # Execute test
        success, message = await RoleManager.remove_role_from_member(member, "live-gang")

        # Assertions
        assert success is True
        assert "live gang" in message.lower()
        assert "✅" in message
        member.remove_roles.assert_called_once_with(mock_role, reason="Self-removed via /leave command")

    @pytest.mark.asyncio
    async def test_remove_role_user_doesnt_have(self):
        """Test removing a role that the user doesn't have"""
        # Create mock role
        mock_role = Mock(spec=discord.Role)
        mock_role.id = 98765
        mock_role.name = "live gang"
        mock_role.mention = "@live gang"

        # Create mock member without the role
        member = Mock(spec=discord.Member)
        member.id = 12345
        member.roles = []

        # Create mock guild
        mock_guild = Mock(spec=discord.Guild)
        mock_guild.id = 11111
        mock_guild.roles = [mock_role]
        member.guild = mock_guild

        # Execute test
        success, message = await RoleManager.remove_role_from_member(member, "live-gang")

        # Assertions
        assert success is False
        assert "don't have" in message.lower()

    @pytest.mark.asyncio
    async def test_remove_invalid_role_key(self):
        """Test attempting to remove a non-whitelisted role"""
        member = Mock(spec=discord.Member)

        # Execute test
        success, message = await RoleManager.remove_role_from_member(member, "moderator")

        # Assertions
        assert success is False
        assert "not self-assignable" in message

    @pytest.mark.asyncio
    async def test_remove_role_not_found_in_guild(self):
        """Test removing a role that doesn't exist in the guild"""
        member = Mock(spec=discord.Member)
        member.id = 12345
        member.roles = []

        # Create mock guild with no roles
        mock_guild = Mock(spec=discord.Guild)
        mock_guild.id = 11111
        mock_guild.roles = []
        member.guild = mock_guild

        # Execute test
        success, message = await RoleManager.remove_role_from_member(member, "live-gang")

        # Assertions
        assert success is False
        assert "not found" in message.lower()

    @pytest.mark.asyncio
    async def test_remove_role_forbidden_error(self):
        """Test removing a role when bot lacks permissions"""
        # Create mock role
        mock_role = Mock(spec=discord.Role)
        mock_role.id = 98765
        mock_role.name = "live gang"
        mock_role.position = 5

        # Create mock member with the role
        member = Mock(spec=discord.Member)
        member.id = 12345
        member.roles = [mock_role]

        # Create mock guild and bot member
        mock_guild = Mock(spec=discord.Guild)
        mock_guild.id = 11111
        mock_guild.roles = [mock_role]

        mock_bot_member = Mock(spec=discord.Member)
        mock_bot_top_role = Mock()
        mock_bot_top_role.position = 10
        mock_bot_member.top_role = mock_bot_top_role

        mock_guild.me = mock_bot_member
        member.guild = mock_guild

        # Mock remove_roles to raise Forbidden
        member.remove_roles = AsyncMock(side_effect=discord.Forbidden(Mock(), "Insufficient permissions"))

        # Execute test
        success, message = await RoleManager.remove_role_from_member(member, "live-gang")

        # Assertions
        assert success is False
        assert "permission" in message.lower()


class TestRoleManagerHelpers:
    """Test suite for RoleManager helper methods"""

    def test_get_role_description(self):
        """Test getting role descriptions"""
        # Test voice-gang description
        desc = RoleManager.get_role_description("voice-gang")
        assert "voice chat" in desc.lower()

        # Test live-gang description
        desc = RoleManager.get_role_description("live-gang")
        assert "live" in desc.lower()

        # Test unknown role key
        desc = RoleManager.get_role_description("unknown-role")
        assert "self-assignable" in desc.lower()

    def test_get_role_display_name(self):
        """Test getting role display names"""
        # Test voice-gang display name
        display = RoleManager.get_role_display_name("voice-gang")
        assert "Voice Gang" in display
        assert "voice chat" in display.lower()

        # Test live-gang display name
        display = RoleManager.get_role_display_name("live-gang")
        assert "Live Gang" in display
        assert "stream" in display.lower()

        # Test unknown role key
        display = RoleManager.get_role_display_name("unknown-role")
        assert display == "unknown-role"

    def test_allowed_roles_constant(self):
        """Test that ALLOWED_ROLES is properly defined"""
        assert isinstance(RoleManager.ALLOWED_ROLES, dict)
        assert "voice-gang" in RoleManager.ALLOWED_ROLES
        assert "live-gang" in RoleManager.ALLOWED_ROLES
        assert RoleManager.ALLOWED_ROLES["voice-gang"] == "voice gang"
        assert RoleManager.ALLOWED_ROLES["live-gang"] == "live gang"
