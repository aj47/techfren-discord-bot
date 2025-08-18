"""
Mermaid.js handler for rendering diagrams in Discord bot responses.
This module handles the detection, rendering, and embedding of Mermaid.js diagrams.
"""

import re
import io
import aiohttp
import base64
import json
from typing import Optional, Dict, Any, List, Tuple
from logging_config import logger
import discord
from discord import File

# Mermaid diagram themes
MERMAID_THEMES = {
    'default': 'default',
    'dark': 'dark',
    'forest': 'forest',
    'neutral': 'neutral',
    'base': 'base'
}

# User theme preferences storage (in production, this should be in database)
user_themes = {}

class MermaidRenderer:
    """Handles rendering of Mermaid.js diagrams to images."""
    
    def __init__(self):
        # mermaid.ink - Official free service by Mermaid.js team
        # Documentation: https://mermaid.ink
        # This is the recommended way to render Mermaid diagrams without self-hosting
        self.render_api_url = "https://mermaid.ink/img/"
        
        # Kroki.io - Open-source free diagram rendering service
        # Documentation: https://docs.kroki.io/
        # Supports multiple diagram types, actively maintained
        self.kroki_api_url = "https://kroki.io/mermaid/png/"
        
    async def render_diagram(self, mermaid_code: str, theme: str = 'default') -> Optional[bytes]:
        """
        Render a Mermaid diagram to PNG image.
        
        Args:
            mermaid_code: The Mermaid diagram code
            theme: The theme to use for rendering
            
        Returns:
            bytes: PNG image data, or None if rendering failed
        """
        try:
            # Clean up the mermaid code
            mermaid_code = mermaid_code.strip()
            
            # Prepare the diagram with theme configuration
            config = {
                "theme": theme,
                "themeVariables": {
                    "primaryColor": "#4372867",
                    "primaryTextColor": "#fff",
                    "primaryBorderColor": "#7C8187",
                    "lineColor": "#5D6D7E",
                    "secondaryColor": "#006FBE",
                    "tertiaryColor": "#E8F6F3"
                }
            }
            
            # Create the full diagram definition with config
            diagram_with_config = {
                "code": mermaid_code,
                "mermaid": {
                    "theme": theme
                },
                "updateEditor": False,
                "autoSync": True,
                "updateDiagram": True
            }
            
            # Method 1: Try mermaid.ink API
            try:
                # Encode the diagram for URL
                encoded = base64.urlsafe_b64encode(
                    json.dumps(diagram_with_config).encode('utf-8')
                ).decode('utf-8').rstrip('=')
                
                url = f"{self.render_api_url}{encoded}"
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=10) as response:
                        if response.status == 200:
                            image_data = await response.read()
                            logger.info(f"Successfully rendered Mermaid diagram using mermaid.ink")
                            return image_data
            except Exception as e:
                logger.warning(f"Failed to render with mermaid.ink: {e}")
            
            # Method 2: Fallback to Kroki API
            try:
                # Encode for Kroki
                encoded = base64.urlsafe_b64encode(
                    mermaid_code.encode('utf-8')
                ).decode('utf-8').rstrip('=')
                
                url = f"{self.kroki_api_url}{encoded}"
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=10) as response:
                        if response.status == 200:
                            image_data = await response.read()
                            logger.info(f"Successfully rendered Mermaid diagram using Kroki")
                            return image_data
            except Exception as e:
                logger.warning(f"Failed to render with Kroki: {e}")
                
            logger.error("All Mermaid rendering methods failed")
            return None
            
        except Exception as e:
            logger.error(f"Error rendering Mermaid diagram: {e}", exc_info=True)
            return None

def extract_mermaid_blocks(text: str) -> List[Tuple[str, int, int]]:
    """
    Extract Mermaid code blocks from text.
    
    Args:
        text: The text to search for Mermaid blocks
        
    Returns:
        List of tuples (mermaid_code, start_index, end_index)
    """
    mermaid_blocks = []
    
    # Pattern for ```mermaid blocks
    pattern = r'```mermaid\s*\n(.*?)\n```'
    matches = re.finditer(pattern, text, re.DOTALL | re.IGNORECASE)
    
    for match in matches:
        mermaid_code = match.group(1).strip()
        start_idx = match.start()
        end_idx = match.end()
        mermaid_blocks.append((mermaid_code, start_idx, end_idx))
    
    return mermaid_blocks

async def process_mermaid_in_response(response_text: str, user_id: str = None) -> Tuple[str, List[discord.File]]:
    """
    Process a response text to find and render Mermaid diagrams.
    
    Args:
        response_text: The text that may contain Mermaid diagrams
        user_id: Optional user ID to get theme preference
        
    Returns:
        Tuple of (modified_text, list_of_discord_files)
    """
    try:
        # Extract Mermaid blocks
        mermaid_blocks = extract_mermaid_blocks(response_text)
        
        if not mermaid_blocks:
            return response_text, []
        
        logger.info(f"Found {len(mermaid_blocks)} Mermaid diagram(s) in response")
        
        # Get user's theme preference
        theme = user_themes.get(user_id, 'default') if user_id else 'default'
        
        # Initialize renderer
        renderer = MermaidRenderer()
        
        # Process each Mermaid block
        discord_files = []
        modified_text = response_text
        offset = 0
        
        for idx, (mermaid_code, start_idx, end_idx) in enumerate(mermaid_blocks):
            # Render the diagram
            image_data = await renderer.render_diagram(mermaid_code, theme)
            
            if image_data:
                # Create Discord file
                file_name = f"diagram_{idx + 1}.png"
                discord_file = discord.File(io.BytesIO(image_data), filename=file_name)
                discord_files.append(discord_file)
                
                # Replace the Mermaid block with a reference
                replacement = f"\n📊 *Diagram {idx + 1} rendered as image (see attachment)*\n"
                
                # Update the text with the replacement
                actual_start = start_idx + offset
                actual_end = end_idx + offset
                modified_text = (
                    modified_text[:actual_start] + 
                    replacement + 
                    modified_text[actual_end:]
                )
                
                # Update offset for next replacement
                offset += len(replacement) - (end_idx - start_idx)
                
                logger.info(f"Successfully rendered Mermaid diagram {idx + 1}")
            else:
                logger.warning(f"Failed to render Mermaid diagram {idx + 1}, keeping original text")
        
        return modified_text, discord_files
        
    except Exception as e:
        logger.error(f"Error processing Mermaid diagrams: {e}", exc_info=True)
        return response_text, []

async def handle_mermaid_command(message: discord.Message, command: str, args: str) -> None:
    """
    Handle Mermaid-specific commands.
    
    Args:
        message: The Discord message object
        command: The command name (e.g., 'render', 'setTheme', 'getTheme')
        args: Command arguments
    """
    try:
        user_id = str(message.author.id)
        
        if command in ['render', 'r']:
            # Render a Mermaid diagram
            if not args:
                await message.reply("Please provide Mermaid diagram code after the command.")
                return
            
            # Get user's theme
            theme = user_themes.get(user_id, 'default')
            
            # Initialize renderer
            renderer = MermaidRenderer()
            
            # Render the diagram
            image_data = await renderer.render_diagram(args, theme)
            
            if image_data:
                # Create embed
                embed = discord.Embed(
                    title="Mermaid Diagram",
                    description="Your diagram has been rendered successfully!",
                    color=0x4372867
                )
                embed.set_footer(text=f"Theme: {theme}")
                
                # Send with image
                file = discord.File(io.BytesIO(image_data), filename="diagram.png")
                embed.set_image(url="attachment://diagram.png")
                
                await message.reply(embed=embed, file=file)
                logger.info(f"Rendered Mermaid diagram for user {message.author}")
            else:
                await message.reply("❌ Failed to render the Mermaid diagram. Please check your syntax.")
                
        elif command == 'setTheme':
            # Set user's theme preference
            if not args or args.lower() not in MERMAID_THEMES:
                themes_list = ", ".join(MERMAID_THEMES.keys())
                await message.reply(f"Please specify a valid theme: {themes_list}")
                return
            
            theme = args.lower()
            user_themes[user_id] = theme
            
            embed = discord.Embed(
                title="Theme Updated",
                description=f"Your Mermaid diagram theme has been set to: **{theme}**",
                color=0x00ff00
            )
            await message.reply(embed=embed)
            logger.info(f"Set theme '{theme}' for user {message.author}")
            
        elif command == 'getTheme':
            # Get user's current theme
            theme = user_themes.get(user_id, 'default')
            
            embed = discord.Embed(
                title="Current Theme",
                description=f"Your current Mermaid diagram theme is: **{theme}**",
                color=0x4372867
            )
            await message.reply(embed=embed)
            
        elif command == 'help':
            # Show help for Mermaid commands
            embed = discord.Embed(
                title="Mermaid.js Bot Help",
                description="Help on using Mermaid.js diagram rendering",
                color=0x4372867
            )
            embed.add_field(
                name="Commands",
                value=(
                    "**!mermaid-render** or **!mermaid-r** `<code>`: Render a Mermaid diagram\n"
                    "**!mermaid-setTheme** `<theme>`: Set your preferred theme\n"
                    "**!mermaid-getTheme**: Get your current theme setting\n"
                    "**!mermaid-help**: Show this help message"
                ),
                inline=False
            )
            embed.add_field(
                name="Available Themes",
                value=", ".join(MERMAID_THEMES.keys()),
                inline=False
            )
            embed.add_field(
                name="Example Diagram",
                value=(
                    "```mermaid\n"
                    "graph TD\n"
                    "    A[Start] --> B{Is it?}\n"
                    "    B -->|Yes| C[OK]\n"
                    "    B -->|No| D[End]\n"
                    "```"
                ),
                inline=False
            )
            embed.add_field(
                name="Helpful Links",
                value=(
                    "[Mermaid.js Documentation](https://mermaid-js.github.io/)\n"
                    "[Mermaid Live Editor](https://mermaid.live/)"
                ),
                inline=False
            )
            
            await message.reply(embed=embed)
            
    except Exception as e:
        logger.error(f"Error handling Mermaid command: {e}", exc_info=True)
        await message.reply("❌ An error occurred while processing your Mermaid command.")

def is_mermaid_command(content: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Check if a message is a Mermaid command.
    
    Args:
        content: Message content
        
    Returns:
        Tuple of (is_command, command_name, arguments)
    """
    mermaid_commands = {
        '!mermaid-render': 'render',
        '!mermaid-r': 'r',
        '!mermaid-setTheme': 'setTheme',
        '!mermaid-getTheme': 'getTheme',
        '!mermaid-help': 'help'
    }
    
    for cmd_prefix, cmd_name in mermaid_commands.items():
        if content.startswith(cmd_prefix):
            args = content[len(cmd_prefix):].strip()
            return True, cmd_name, args
    
    return False, None, None
