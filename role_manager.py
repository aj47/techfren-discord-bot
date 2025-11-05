"""
Role Manager Module

This module provides functionality for managing self-assignable roles in the Discord bot.
Users can join or leave specific roles that are whitelisted for self-assignment.

Supports:
- Adding roles to members
- Removing roles from members
- Validating role permissions and hierarchy
- Audit logging for role changes
"""

import discord
from typing import Tuple
import logging
import config

logger = logging.getLogger(__name__)


class RoleManager:
    """Handles self-assignable role operations for the Discord bot."""

    # Import roles from config to maintain single source of truth
    ALLOWED_ROLES = config.SELF_ASSIGNABLE_ROLES

    @staticmethod
    async def add_role_to_member(
        member: discord.Member,
        role_key: str
    ) -> Tuple[bool, str]:
        """
        Add a self-assignable role to a member.

        Args:
            member: The Discord member to add the role to
            role_key: The key of the role (e.g., 'voice-gang')

        Returns:
            Tuple of (success: bool, message: str)
            - success: True if the role was added successfully, False otherwise
            - message: Human-readable message describing the result

        Raises:
            No exceptions - all errors are caught and returned as messages
        """
        # Validate role is in whitelist
        if role_key not in RoleManager.ALLOWED_ROLES:
            logger.warning(f"Attempt to add non-whitelisted role: {role_key}")
            return False, f"Role '{role_key}' is not self-assignable"

        role_name = RoleManager.ALLOWED_ROLES[role_key]

        # Find the role in the guild
        role = discord.utils.get(member.guild.roles, name=role_name)

        if not role:
            logger.error(f"Role '{role_name}' not found in guild {member.guild.id}")
            return False, f"Role '{role_name}' not found. Please contact an admin to set it up."

        # Check if user already has the role
        if role in member.roles:
            logger.debug(f"User {member.id} already has role {role.id}")
            return False, f"You already have the {role.mention} role"

        # Verify bot has permission to manage this role
        bot_member = member.guild.me
        if role.position >= bot_member.top_role.position:
            logger.error(
                f"Bot cannot manage role {role.id} (position {role.position}) - "
                f"bot's top role position is {bot_member.top_role.position}"
            )
            return False, "Bot cannot manage this role due to role hierarchy. Please contact an admin."

        # Attempt to add the role
        try:
            await member.add_roles(role, reason="Self-assigned via /join command")
            logger.info(f"Added role {role.id} ({role_name}) to user {member.id}")
            return True, f"✅ You now have the {role.mention} role!"
        except discord.Forbidden:
            logger.exception(f"Bot lacks permission to add role {role.id} to user {member.id}")
            return False, "Bot lacks permission to manage this role. Please contact an admin."
        except discord.HTTPException as e:
            logger.exception(f"HTTP error adding role {role.id} to user {member.id}: {e}")
            return False, f"Failed to add role due to a Discord error: {str(e)}"

    @staticmethod
    async def remove_role_from_member(
        member: discord.Member,
        role_key: str
    ) -> Tuple[bool, str]:
        """
        Remove a self-assignable role from a member.

        Args:
            member: The Discord member to remove the role from
            role_key: The key of the role (e.g., 'voice-gang')

        Returns:
            Tuple of (success: bool, message: str)
            - success: True if the role was removed successfully, False otherwise
            - message: Human-readable message describing the result

        Raises:
            No exceptions - all errors are caught and returned as messages
        """
        # Validate role is in whitelist
        if role_key not in RoleManager.ALLOWED_ROLES:
            logger.warning(f"Attempt to remove non-whitelisted role: {role_key}")
            return False, f"Role '{role_key}' is not self-assignable"

        role_name = RoleManager.ALLOWED_ROLES[role_key]

        # Find the role in the guild
        role = discord.utils.get(member.guild.roles, name=role_name)

        if not role:
            logger.error(f"Role '{role_name}' not found in guild {member.guild.id}")
            return False, f"Role '{role_name}' not found. Please contact an admin."

        # Check if user has the role
        if role not in member.roles:
            logger.debug(f"User {member.id} does not have role {role.id}")
            return False, f"You don't have the {role.mention} role"

        # Verify bot has permission to manage this role
        bot_member = member.guild.me
        if role.position >= bot_member.top_role.position:
            logger.error(
                f"Bot cannot manage role {role.id} (position {role.position}) - "
                f"bot's top role position is {bot_member.top_role.position}"
            )
            return False, "Bot cannot manage this role due to role hierarchy. Please contact an admin."

        # Attempt to remove the role
        try:
            await member.remove_roles(role, reason="Self-removed via /leave command")
            logger.info(f"Removed role {role.id} ({role_name}) from user {member.id}")
            return True, f"✅ You no longer have the **{role_name}** role"
        except discord.Forbidden:
            logger.exception(f"Bot lacks permission to remove role {role.id} from user {member.id}")
            return False, "Bot lacks permission to manage this role. Please contact an admin."
        except discord.HTTPException as e:
            logger.exception(f"HTTP error removing role {role.id} from user {member.id}: {e}")
            return False, f"Failed to remove role due to a Discord error: {str(e)}"

    @staticmethod
    def get_role_description(role_key: str) -> str:
        """
        Get a human-readable description for a role.

        Args:
            role_key: The key of the role (e.g., 'voice-gang')

        Returns:
            Description string for the role
        """
        descriptions = {
            'voice-gang': "Get pinged when people want to voice chat",
            'live-gang': "Get notified when techfren goes live"
        }
        return descriptions.get(role_key, "Self-assignable role")

    @staticmethod
    def get_role_display_name(role_key: str) -> str:
        """
        Get a user-friendly display name for a role.

        Args:
            role_key: The key of the role (e.g., 'voice-gang')

        Returns:
            Display name for the role
        """
        display_names = {
            'voice-gang': "Voice Gang - Get pinged for voice chats",
            'live-gang': "Live Gang - Get notified when streams start"
        }
        return display_names.get(role_key, role_key)
