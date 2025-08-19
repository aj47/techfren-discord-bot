"""
Discord Response Formatter Module

This module provides utilities for formatting bot responses with rich Discord markdown,
including bold, italics, code blocks, quotes, embeds, and more.
"""

import re
from typing import List, Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

class DiscordFormatter:
    """Enhanced Discord message formatter with rich markdown support."""
    
    @staticmethod
    def format_llm_response(content: str, citations: Optional[List[str]] = None) -> str:
        """
        Format an LLM response with enhanced Discord markdown.
        Preserves and enhances **bold**, ```code blocks```, and other Discord formatting.
        
        Args:
            content: The raw LLM response content
            citations: Optional list of citation URLs
            
        Returns:
            Formatted string with Discord markdown
        """
        formatted = content
        
        # First, preserve important Discord formatting patterns
        formatted = DiscordFormatter._preserve_discord_formatting(formatted)
        
        # Handle any Markdown tables in the content
        formatted = DiscordFormatter._convert_markdown_tables(formatted)
        
        # Replace Perplexity-style citations [1], [2] with clickable links if citations provided
        if citations:
            for i, url in enumerate(citations, 1):
                # Make citation numbers into clickable superscript-like links
                formatted = formatted.replace(f"[{i}]", f"[`[{i}]`]({url})")
        
        # Enhanced formatting patterns
        formatting_rules = [
            # Headers - Convert markdown headers to Discord formatting
            (r'^#{1}\s+(.+)$', r'__**\1**__', re.MULTILINE),  # # Header -> bold underline
            (r'^#{2}\s+(.+)$', r'**\1**', re.MULTILINE),      # ## Header -> bold
            (r'^#{3,}\s+(.+)$', r'__\1__', re.MULTILINE),     # ### Header -> underline
            
            # Lists - Enhance bullet points and numbered lists
            (r'^\*\s+(.+)$', r'• \1', re.MULTILINE),          # * item -> • item
            (r'^-\s+(.+)$', r'• \1', re.MULTILINE),           # - item -> • item
            (r'^(\d+)\.\s+(.+)$', r'**\1.** \2', re.MULTILINE), # 1. item -> bold number
            
            # Bold and emphasis - Preserve and enhance
            # Keep existing **bold** as is - Discord supports this natively
            # Keep existing *italic* as is - Discord supports this natively
            
            # Code formatting - Preserve both inline and block code
            # Inline code backticks - keep as is (Discord native)
            (r'`([^`\n]+)`', r'`\1`', 0),  # Preserve inline code
            # Code blocks - keep as is (Discord native)
            (r'```(\w*)\n([\s\S]*?)\n```', r'```\1\n\2\n```', 0),  # Preserve code blocks
            
            # Quotes - Convert quote markers to Discord quote blocks
            (r'^>\s+(.+)$', r'> \1', re.MULTILINE),  # > quote -> Discord quote
            
            # Horizontal rules
            (r'^---+$', r'━━━━━━━━━━━━━━━', re.MULTILINE),
            (r'^\*\*\*+$', r'━━━━━━━━━━━━━━━', re.MULTILINE),
        ]
        
        # Apply formatting rules
        for pattern, replacement, flags in formatting_rules:
            if flags:
                formatted = re.sub(pattern, replacement, formatted, flags=flags)
            else:
                formatted = re.sub(pattern, replacement, formatted)
        
        return formatted
    
    @staticmethod
    def _preserve_discord_formatting(content: str) -> str:
        """
        Preserve and enhance Discord-specific formatting patterns.
        
        Args:
            content: Raw content that may contain Discord formatting
            
        Returns:
            Content with preserved and enhanced Discord formatting
        """
        # Protect code blocks from further processing
        protected_blocks = []
        
        def protect_code_block(match):
            placeholder = f"__PROTECTED_CODE_BLOCK_{len(protected_blocks)}__"
            protected_blocks.append(match.group(0))
            return placeholder
        
        # Protect multi-line code blocks first
        content = re.sub(r'```[\s\S]*?```', protect_code_block, content)
        
        # Enhance existing bold formatting - make sure they're properly spaced
        content = re.sub(r'\*\*([^*\n]+)\*\*', r'**\1**', content)
        
        # Enhance existing italic formatting
        content = re.sub(r'\*([^*\n]+)\*', r'*\1*', content)
        
        # Enhance inline code formatting
        content = re.sub(r'`([^`\n]+)`', r'`\1`', content)
        
        # Restore protected code blocks
        for i, block in enumerate(protected_blocks):
            content = content.replace(f"__PROTECTED_CODE_BLOCK_{i}__", block)
        
        return content
    
    @staticmethod
    def format_summary_response(summary: str, channel_name: str, hours: int) -> str:
        """
        Format a channel summary response with enhanced styling.
        
        Args:
            summary: The raw summary text
            channel_name: Name of the channel
            hours: Number of hours summarized
            
        Returns:
            Formatted summary with Discord markdown
        """
        time_period = f"{hours} hour{'s' if hours != 1 else ''}"
        
        # Add a styled header
        header = f"📊 **Summary of #{channel_name}** *(past {time_period})*\n{'━' * 30}\n\n"
        
        # Process the summary content
        formatted_summary = DiscordFormatter.format_llm_response(summary)
        
        # Enhance specific patterns in summaries
        formatted_summary = DiscordFormatter._enhance_summary_sections(formatted_summary)
        
        return header + formatted_summary
    
    @staticmethod
    def _enhance_summary_sections(content: str) -> str:
        """
        Enhance specific sections commonly found in summaries.
        
        Args:
            content: The summary content
            
        Returns:
            Enhanced content with better formatting
        """
        # Format "Key Topics" or similar sections
        content = re.sub(
            r'^(Key Topics?|Main Topics?|Topics? Discussed):?\s*$',
            r'🔑 **\1:**',
            content,
            flags=re.MULTILINE | re.IGNORECASE
        )
        
        # Format "Notable Quotes" section
        content = re.sub(
            r'^(Notable Quotes?|Top Quotes?|Interesting Quotes?):?\s*$',
            r'💬 **\1:**',
            content,
            flags=re.MULTILINE | re.IGNORECASE
        )
        
        # Format "Sources" section
        content = re.sub(
            r'^(Sources?|References?):?\s*$',
            r'📚 **\1:**',
            content,
            flags=re.MULTILINE | re.IGNORECASE
        )
        
        # Add emphasis to usernames (already backticked)
        # Usernames are typically in backticks like `username`
        # We'll make them bold as well, but skip mermaid blocks
        # First, protect mermaid blocks
        mermaid_blocks = []
        def protect_mermaid(match):
            placeholder = f"__MERMAID_BLOCK_{len(mermaid_blocks)}__"
            mermaid_blocks.append(match.group(0))
            return placeholder
        
        # Temporarily replace mermaid blocks with placeholders
        content = re.sub(r'```mermaid[\s\S]*?```', protect_mermaid, content)
        
        # Now apply bold to backticked content (usernames)
        content = re.sub(r'`([^`]+)`', r'**`\1`**', content)
        
        # Restore mermaid blocks
        for i, block in enumerate(mermaid_blocks):
            content = content.replace(f"__MERMAID_BLOCK_{i}__", block)
        
        # Format URLs to be more compact
        # Look for [text](url) patterns and ensure they're formatted nicely
        content = re.sub(
            r'\[([^\]]+)\]\(([^)]+)\)',
            lambda m: f'[{m.group(1)}](<{m.group(2)}>)',
            content
        )
        
        return content
    
    @staticmethod
    def format_error_message(error_msg: str) -> str:
        """
        Format an error message with appropriate styling.
        
        Args:
            error_msg: The error message
            
        Returns:
            Formatted error message
        """
        return f"❌ **Error:** {error_msg}"
    
    @staticmethod
    def format_success_message(success_msg: str) -> str:
        """
        Format a success message with appropriate styling.
        
        Args:
            success_msg: The success message
            
        Returns:
            Formatted success message
        """
        return f"✅ **Success:** {success_msg}"
    
    @staticmethod
    def format_warning_message(warning_msg: str) -> str:
        """
        Format a warning message with appropriate styling.
        
        Args:
            warning_msg: The warning message
            
        Returns:
            Formatted warning message
        """
        return f"⚠️ **Warning:** {warning_msg}"
    
    @staticmethod
    def format_info_message(info_msg: str) -> str:
        """
        Format an informational message with appropriate styling.
        
        Args:
            info_msg: The info message
            
        Returns:
            Formatted info message
        """
        return f"ℹ️ **Info:** {info_msg}"
    
    @staticmethod
    def format_code_block(code: str, language: str = "") -> str:
        """
        Format code in a Discord code block.
        
        Args:
            code: The code content
            language: Optional language for syntax highlighting
            
        Returns:
            Formatted code block
        """
        return f"```{language}\n{code}\n```"
    
    @staticmethod
    def format_inline_code(code: str) -> str:
        """
        Format text as inline code.
        
        Args:
            code: The code content
            
        Returns:
            Formatted inline code
        """
        return f"`{code}`"
    
    @staticmethod
    def format_quote(text: str, author: Optional[str] = None) -> str:
        """
        Format a quote with optional attribution.
        
        Args:
            text: The quote text
            author: Optional author attribution
            
        Returns:
            Formatted quote
        """
        quote = f"> {text}"
        if author:
            quote += f"\n> — *{author}*"
        return quote
    
    @staticmethod
    def format_link(text: str, url: str) -> str:
        """
        Format a clickable link.
        
        Args:
            text: The link text
            url: The URL
            
        Returns:
            Formatted markdown link
        """
        # Discord prefers URLs in angle brackets for proper embedding
        return f"[{text}](<{url}>)"
    
    @staticmethod
    def format_mention(user_id: str) -> str:
        """
        Format a user mention.
        
        Args:
            user_id: The user's Discord ID
            
        Returns:
            Formatted mention
        """
        return f"<@{user_id}>"
    
    @staticmethod
    def format_channel_mention(channel_id: str) -> str:
        """
        Format a channel mention.
        
        Args:
            channel_id: The channel's Discord ID
            
        Returns:
            Formatted channel mention
        """
        return f"<#{channel_id}>"
    
    @staticmethod
    def format_timestamp(timestamp: int, style: str = "F") -> str:
        """
        Format a Discord timestamp.
        
        Args:
            timestamp: Unix timestamp
            style: Timestamp style (t, T, d, D, f, F, R)
                   t: Short time (16:20)
                   T: Long time (16:20:30)
                   d: Short date (20/04/2021)
                   D: Long date (20 April 2021)
                   f: Short date/time (20 April 2021 16:20)
                   F: Long date/time (Tuesday, 20 April 2021 16:20)
                   R: Relative time (2 hours ago)
            
        Returns:
            Formatted Discord timestamp
        """
        return f"<t:{timestamp}:{style}>"
    
    @staticmethod
    def format_embed_field(name: str, value: str, inline: bool = False) -> Dict[str, Any]:
        """
        Format a field for a Discord embed.
        
        Args:
            name: Field name
            value: Field value
            inline: Whether the field should be inline
            
        Returns:
            Formatted field dictionary
        """
        return {
            "name": name,
            "value": value,
            "inline": inline
        }
    
    @staticmethod
    def create_embed(
        title: Optional[str] = None,
        description: Optional[str] = None,
        color: int = 0x00FF00,
        fields: Optional[List[Dict[str, Any]]] = None,
        footer: Optional[str] = None,
        thumbnail_url: Optional[str] = None,
        image_url: Optional[str] = None,
        author_name: Optional[str] = None,
        author_icon_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a Discord embed structure.
        
        Args:
            title: Embed title
            description: Embed description
            color: Embed color (hex)
            fields: List of field dictionaries
            footer: Footer text
            thumbnail_url: Thumbnail image URL
            image_url: Main image URL
            author_name: Author name
            author_icon_url: Author icon URL
            
        Returns:
            Embed dictionary structure
        """
        embed = {}
        
        if title:
            embed["title"] = title
        if description:
            embed["description"] = description
        if color:
            embed["color"] = color
        if fields:
            embed["fields"] = fields
        if footer:
            embed["footer"] = {"text": footer}
        if thumbnail_url:
            embed["thumbnail"] = {"url": thumbnail_url}
        if image_url:
            embed["image"] = {"url": image_url}
        if author_name:
            author = {"name": author_name}
            if author_icon_url:
                author["icon_url"] = author_icon_url
            embed["author"] = author
        
        return embed
    
    @staticmethod
    def format_list(items: List[str], ordered: bool = False, bold_numbers: bool = True) -> str:
        """
        Format a list with proper Discord formatting.
        
        Args:
            items: List of items
            ordered: Whether to use numbered list
            bold_numbers: Whether to make numbers bold (for ordered lists)
            
        Returns:
            Formatted list string
        """
        if ordered:
            if bold_numbers:
                return "\n".join([f"**{i}.** {item}" for i, item in enumerate(items, 1)])
            else:
                return "\n".join([f"{i}. {item}" for i, item in enumerate(items, 1)])
        else:
            return "\n".join([f"• {item}" for item in items])
    
    @staticmethod
    def format_table(headers: List[str], rows: List[List[str]]) -> str:
        """
        Format a simple table using Discord monospace.
        
        Args:
            headers: List of header strings
            rows: List of row data
            
        Returns:
            Formatted table in code block
        """
        # Calculate column widths
        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                if i < len(col_widths):
                    col_widths[i] = max(col_widths[i], len(str(cell)))
        
        # Build table
        table_lines = []
        
        # Header
        header_line = " | ".join([h.ljust(col_widths[i]) for i, h in enumerate(headers)])
        table_lines.append(header_line)
        
        # Separator
        separator = "-+-".join(["-" * w for w in col_widths])
        table_lines.append(separator)
        
        # Rows
        for row in rows:
            row_line = " | ".join([str(cell).ljust(col_widths[i]) for i, cell in enumerate(row)])
            table_lines.append(row_line)
        
        return "```\n" + "\n".join(table_lines) + "\n```"
    
    @staticmethod
    def _convert_markdown_tables(content: str) -> str:
        """
        Convert Markdown tables to a Discord-friendly format.
        Tables are converted to structured lists with clear headers.
        
        Args:
            content: Content potentially containing Markdown tables
            
        Returns:
            Content with tables converted to Discord-friendly format
        """
        # Pattern to match Markdown tables
        # This matches tables with at least a header row and separator row
        table_pattern = r'\|[^\n]+\|\n\|[-: ]+\|(?:\n\|[^\n]+\|)*'
        
        def convert_table(match):
            table_text = match.group(0)
            lines = table_text.strip().split('\n')
            
            if len(lines) < 2:
                return table_text
            
            # Parse header row
            header_row = lines[0]
            headers = [cell.strip() for cell in header_row.split('|')[1:-1]]
            
            # Skip separator row (line 1)
            # Parse data rows
            data_rows = []
            for line in lines[2:]:
                if line.strip():
                    cells = [cell.strip() for cell in line.split('|')[1:-1]]
                    data_rows.append(cells)
            
            # Check if this looks like a comparison table or has many long cells
            is_complex_table = any(len(cell) > 50 for row in data_rows for cell in row)
            
            if is_complex_table or len(headers) > 3:
                # For complex tables, convert to a structured list format
                result = []
                result.append("📊 **Table:**\n")
                
                for i, row in enumerate(data_rows, 1):
                    if len(data_rows) > 1:
                        result.append(f"**{i}.** ")
                    for j, header in enumerate(headers):
                        if j < len(row):
                            cell_content = row[j]
                            # Handle links in cells
                            cell_content = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'[\1](<\2>)', cell_content)
                            result.append(f"**{header}:** {cell_content}\n")
                    if i < len(data_rows):
                        result.append("\n")  # Add spacing between rows
                
                return ''.join(result)
            else:
                # For simple tables, use code block format
                # Calculate column widths
                col_widths = [len(h) for h in headers]
                for row in data_rows:
                    for i, cell in enumerate(row):
                        if i < len(col_widths):
                            # Limit cell width for code blocks
                            cell_text = cell[:40] + '...' if len(cell) > 40 else cell
                            col_widths[i] = max(col_widths[i], len(cell_text))
                
                # Build formatted table
                table_lines = []
                
                # Header
                header_line = " | ".join([h.ljust(col_widths[i]) for i, h in enumerate(headers)])
                table_lines.append(header_line)
                
                # Separator
                separator = "-+-".join(["-" * w for w in col_widths])
                table_lines.append(separator)
                
                # Rows
                for row in data_rows:
                    formatted_cells = []
                    for i, cell in enumerate(row):
                        if i < len(col_widths):
                            # Truncate long cells
                            cell_text = cell[:40] + '...' if len(cell) > 40 else cell
                            formatted_cells.append(cell_text.ljust(col_widths[i]))
                    row_line = " | ".join(formatted_cells)
                    table_lines.append(row_line)
                
                return "```\n" + "\n".join(table_lines) + "\n```\n"
        
        # Replace all tables in the content
        converted = re.sub(table_pattern, convert_table, content, flags=re.MULTILINE)
        
        # Also handle [Part X/Y] indicators for multi-part messages
        converted = re.sub(r'\[Part \d+/\d+\]', '', converted)
        
        return converted
    
    @staticmethod
    def format_bold(text: str) -> str:
        """
        Format text as bold using Discord markdown.
        
        Args:
            text: Text to make bold
            
        Returns:
            Bold formatted text
        """
        return f"**{text}**"
    
    @staticmethod
    def format_italic(text: str) -> str:
        """
        Format text as italic using Discord markdown.
        
        Args:
            text: Text to make italic
            
        Returns:
            Italic formatted text
        """
        return f"*{text}*"
    
    @staticmethod
    def format_bold_italic(text: str) -> str:
        """
        Format text as bold and italic using Discord markdown.
        
        Args:
            text: Text to make bold and italic
            
        Returns:
            Bold italic formatted text
        """
        return f"***{text}***"
    
    @staticmethod
    def format_underline(text: str) -> str:
        """
        Format text as underlined using Discord markdown.
        
        Args:
            text: Text to underline
            
        Returns:
            Underlined formatted text
        """
        return f"__{text}__"
    
    @staticmethod
    def format_strikethrough(text: str) -> str:
        """
        Format text as strikethrough using Discord markdown.
        
        Args:
            text: Text to strikethrough
            
        Returns:
            Strikethrough formatted text
        """
        return f"~~{text}~~"
    
    @staticmethod
    def format_spoiler(text: str) -> str:
        """
        Format text as spoiler using Discord markdown.
        
        Args:
            text: Text to hide as spoiler
            
        Returns:
            Spoiler formatted text
        """
        return f"||{text}||"
