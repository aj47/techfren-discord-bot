"""
Mermaid.js handler for rendering diagrams in Discord bot responses.
This module handles the detection, rendering, and embedding of Mermaid.js diagrams.
"""

import re
import io
import aiohttp
import base64
import json
import zlib
from typing import Optional, Dict, Any, List, Tuple
from logging_config import logger
import discord
from discord import File

# Mermaid diagrams are now rendered automatically in all bot responses

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
        self.kroki_post_url = "https://kroki.io/"
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
            
            # Special configuration for pie charts with vibrant colors
            if 'pie' in mermaid_code.lower():
                config = {
                    "theme": "base",
                    "themeVariables": {
                        "pie1": "#FF6B6B",      # Red
                        "pie2": "#4ECDC4",      # Teal
                        "pie3": "#45B7D1",      # Blue
                        "pie4": "#96CEB4",      # Green
                        "pie5": "#FFEAA7",      # Yellow
                        "pie6": "#DDA0DD",      # Plum
                        "pie7": "#98D8C8",      # Mint
                        "pie8": "#FFB6C1",      # Pink
                        "pieStrokeColor": "#000000",     # Black border
                        "pieSectionTextSize": "16px",
                        "pieLegendTextSize": "14px",
                        "pieSectionTextColor": "#000000" # Black text
                    }
                }
            else:
                # Standard configuration for other diagrams
                config = {
                    "theme": theme,
                    "themeVariables": {
                        "primaryColor": "#437286",
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
            
            # Method 1: Try Kroki POST API (most reliable)
            try:
                payload = {
                    "diagram_source": mermaid_code,
                    "diagram_type": "mermaid",
                    "output_format": "png"
                }
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        self.kroki_post_url,
                        json=payload,
                        timeout=10
                    ) as response:
                        if response.status == 200:
                            image_data = await response.read()
                            logger.info(f"Successfully rendered Mermaid diagram using Kroki POST API")
                            return image_data
                        else:
                            error_text = await response.text()
                            logger.warning(f"Kroki POST API returned status {response.status}: {error_text}")
            except Exception as e:
                logger.warning(f"Failed to render with Kroki POST API: {e}")
            
            # Method 2: Fallback to Kroki GET API
            try:
                # Encode for Kroki using proper zlib compression + base64
                compressed = zlib.compress(mermaid_code.encode('utf-8'), 9)
                encoded = base64.urlsafe_b64encode(compressed).decode('utf-8')
                
                url = f"{self.kroki_api_url}{encoded}"
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=10) as response:
                        if response.status == 200:
                            image_data = await response.read()
                            logger.info(f"Successfully rendered Mermaid diagram using Kroki GET API")
                            return image_data
                        else:
                            error_text = await response.text()
                            logger.warning(f"Kroki GET API returned status {response.status}: {error_text}")
            except Exception as e:
                logger.warning(f"Failed to render with Kroki GET API: {e}")
                
            logger.error("All Mermaid rendering methods failed")
            logger.debug(f"Failed to render diagram: {mermaid_code[:100]}..." if len(mermaid_code) > 100 else f"Failed to render diagram: {mermaid_code}")
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
    
    # Pattern for all Mermaid diagram types
    # Matches: ```mermaid, ```flowchart, ```graph, ```sequenceDiagram, etc.
    valid_types = ['mermaid', 'flowchart', 'graph', 'sequenceDiagram', 'classDiagram', 'stateDiagram', 'erDiagram', 'journey', 'gantt', 'pie', 'gitgraph']
    
    # Pattern 1: ```<type> blocks (handles types with parameters)
    for diagram_type in valid_types:
        if diagram_type == 'mermaid':
            # For ```mermaid blocks, content starts after newline
            pattern = rf'```{diagram_type}\s*\n(.*?)\n```'
            matches = re.finditer(pattern, text, re.DOTALL | re.IGNORECASE)
            
            for match in matches:
                content = match.group(1).strip()
                mermaid_code = content
                start_idx = match.start()
                end_idx = match.end()
                mermaid_blocks.append((mermaid_code, start_idx, end_idx))
        else:
            # For diagram types that may have parameters (flowchart TD, graph LR, etc.)
            pattern = rf'```{diagram_type}(\s+[^\n]*)?\n(.*?)\n```'
            matches = re.finditer(pattern, text, re.DOTALL | re.IGNORECASE)
            
            for match in matches:
                type_params = match.group(1).strip() if match.group(1) else ""
                content = match.group(2).strip()
                # Combine type with parameters and content
                mermaid_code = f"{diagram_type}{' ' + type_params if type_params else ''}\n{content}"
                start_idx = match.start()
                end_idx = match.end()
                mermaid_blocks.append((mermaid_code, start_idx, end_idx))
    
    # Pattern 2: Plain ``` blocks that contain Mermaid diagram types
    plain_pattern = r'```\s*\n(.*?)\n```'
    plain_matches = re.finditer(plain_pattern, text, re.DOTALL | re.IGNORECASE)
    
    for match in plain_matches:
        content = match.group(1).strip()
        # Check if content starts with a valid Mermaid diagram type
        if any(content.startswith(vt) for vt in valid_types[1:]):  # Skip 'mermaid' keyword
            mermaid_code = content
            start_idx = match.start()
            end_idx = match.end()
            # Avoid duplicates from pattern 1
            if not any(abs(start_idx - existing[1]) < 10 for existing in mermaid_blocks):
                mermaid_blocks.append((mermaid_code, start_idx, end_idx))
    
    # Sort by start index to maintain order
    mermaid_blocks.sort(key=lambda x: x[1])
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
        
        logger.info(f"Found {len(mermaid_blocks)} Mermaid diagram(s) in response")
        
        # Ensure we always have at least 2 diagrams for better visualization
        if len(mermaid_blocks) == 1:
            first_diagram = mermaid_blocks[0][0].lower()
            
            if 'pie' in first_diagram:
                # Add a default flowchart
                default_flow = "flowchart TD\n    A[Topic] --> B[Discussion]\n    B --> C[Conclusion]"
                mermaid_blocks.append((default_flow, -1, -1))
                logger.info("Added default flowchart to complement pie chart")
            else:
                # Add a default pie chart
                default_pie = "pie title \"Data Distribution\"\n    \"Category A\" : 40\n    \"Category B\" : 35\n    \"Category C\" : 25"
                mermaid_blocks.append((default_pie, -1, -1))
                logger.info("Added default pie chart to complement diagram")
        elif len(mermaid_blocks) == 0:
            # If no diagrams found, add both default ones
            default_flow = "flowchart TD\n    A[Start] --> B[Process]\n    B --> C[End]"
            default_pie = "pie title \"Overview\"\n    \"Main Topic\" : 60\n    \"Supporting\" : 40"
            mermaid_blocks.append((default_flow, -1, -1))
            mermaid_blocks.append((default_pie, -1, -1))
            logger.info("Added both default diagrams")
        
        logger.info(f"Total diagrams to render: {len(mermaid_blocks)}")
        
        # Use default theme for all automatic rendering
        theme = 'default'
        
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
                
                # Replace the Mermaid block with a reference (only if it was in original text)
                if start_idx != -1 and end_idx != -1:
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

# All Mermaid commands have been removed - diagrams are now automatically rendered in all LLM responses
