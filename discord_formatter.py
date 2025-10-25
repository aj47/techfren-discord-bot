"""
Discord Response Formatter Module

This module provides utilities for formatting bot responses with rich Discord markdown,
including bold, italics, code blocks, quotes, embeds, and more.
"""

import re
from typing import List, Optional, Dict, Any, Tuple
import logging
from chart_renderer import extract_tables_for_rendering

logger = logging.getLogger(__name__)


class DiscordFormatter:
    """Enhanced Discord message formatter with rich markdown support."""

    @staticmethod
    def format_llm_response(
        content: str, citations: Optional[List[str]] = None, user_query: str = ""
    ) -> Tuple[str, List[Dict]]:
        """
        Format an LLM response with enhanced Discord markdown and extract charts.

        Args:
            content: The raw LLM response content
            citations: Optional list of citation URLs
            user_query: The user's original query (for detecting explicit chart types)

        Returns:
            Tuple of (formatted_string, chart_data_list)
            - formatted_string: Content with Discord markdown
            - chart_data_list: List of chart data dicts with 'file', 'type', 'placeholder' keys  # noqa: E501
        """
        formatted = content
        chart_data_list = []

        # Extract tables for chart rendering BEFORE converting to ASCII
        # This allows us to render nice chart images instead of messy ASCII tables
        try:
            logger.debug(f"🔍 Starting chart extraction with user_query: '{user_query[:50]}{'...' if len(user_query) > 50 else ''}'")
            formatted, chart_data_list = extract_tables_for_rendering(formatted, user_query)
            if chart_data_list:
                logger.info("📊 Extracted %d chart(s) from response", len(chart_data_list))
                for i, chart in enumerate(chart_data_list):
                    logger.debug(f"   Chart {i+1}: type={chart.get('type')}, placeholder='{chart.get('placeholder')[:30]}...'")
            else:
                logger.debug("📊 No charts found in response")
        except Exception as e:
            logger.error("Error extracting charts: %s", e, exc_info=True)
            # Continue with normal processing if chart extraction fails

        # Convert any remaining markdown tables to ASCII tables
        formatted = DiscordFormatter._convert_markdown_tables_to_ascii(formatted)

        # Replace Perplexity-style citations [1], [2] with clickable links if
        # citations provided
        if citations:
            for i, url in enumerate(citations, 1):
                # Make citation numbers into clickable superscript-like links
                formatted = formatted.replace(f"[{i}]", f"[`[{i}]`]({url})")

        # Enhanced formatting patterns
        formatting_rules = [
            # Headers - Convert markdown headers to Discord formatting
            (
                r"^#{1}\s+(.+)$",
                r"__**\1**__",
                re.MULTILINE,
            ),  # # Header -> bold underline
            (r"^#{2}\s+(.+)$", r"**\1**", re.MULTILINE),  # ## Header -> bold
            (r"^#{3,}\s+(.+)$", r"__\1__", re.MULTILINE),  # ### Header -> underline
            # Lists - Enhance bullet points and numbered lists
            (r"^\*\s+(.+)$", r"• \1", re.MULTILINE),  # * item -> • item
            (r"^-\s+(.+)$", r"• \1", re.MULTILINE),  # - item -> • item
            (
                r"^(\d+)\.\s+(.+)$",
                r"**\1.** \2",
                re.MULTILINE,
            ),  # 1. item -> bold number
            # Emphasis patterns already in the text
            # (Leave existing **bold** and *italic* as is, they work in Discord)
            # Code - Ensure inline code uses backticks properly
            (r"`([^`]+)`", r"`\1`", 0),  # Keep inline code as is
            # Quotes - Convert quote markers to Discord quote blocks
            (r"^>\s+(.+)$", r"> \1", re.MULTILINE),  # > quote -> Discord quote
            # Horizontal rules
            (r"^---+$", r"━━━━━━━━━━━━━━━", re.MULTILINE),
            (r"^\*\*\*+$", r"━━━━━━━━━━━━━━━", re.MULTILINE),
        ]

        # Apply formatting rules
        for pattern, replacement, flags in formatting_rules:
            if flags:
                formatted = re.sub(pattern, replacement, formatted, flags=flags)
            else:
                formatted = re.sub(pattern, replacement, formatted)

        return formatted, chart_data_list

    @staticmethod
    def format_summary_response(
        summary: str, channel_name: str, hours: int
    ) -> Tuple[str, List[Dict]]:
        """
        Format a channel summary response with enhanced styling.

        Args:
            summary: The raw summary text
            channel_name: Name of the channel
            hours: Number of hours summarized

        Returns:
            Tuple of (formatted_summary, chart_data_list)
        """
        time_period = f"{hours} hour{'s' if hours != 1 else ''}"

        # Add a styled header
        header = (
            f"📊 **Summary of #{channel_name}** *(past {time_period})*\n{'━' * 30}\n\n"
        )

        # Process the summary content
        formatted_summary, chart_data_list = DiscordFormatter.format_llm_response(
            summary
        )

        # Enhance specific patterns in summaries
        formatted_summary = DiscordFormatter._enhance_summary_sections(
            formatted_summary
        )

        return header + formatted_summary, chart_data_list

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
            r"^(Key Topics?|Main Topics?|Topics? Discussed):?\s*$",
            r"🔑 **\1:**",
            content,
            flags=re.MULTILINE | re.IGNORECASE,
        )

        # Format "Notable Quotes" section
        content = re.sub(
            r"^(Notable Quotes?|Top Quotes?|Interesting Quotes?):?\s*$",
            r"💬 **\1:**",
            content,
            flags=re.MULTILINE | re.IGNORECASE,
        )

        # Format "Sources" section
        content = re.sub(
            r"^(Sources?|References?):?\s*$",
            r"📚 **\1:**",
            content,
            flags=re.MULTILINE | re.IGNORECASE,
        )

        # Add emphasis to usernames (already backticked)
        # Usernames are typically in backticks like `username`
        # We'll make them bold as well
        content = re.sub(r"`([^`]+)`", r"**`\1`**", content)

        # Format URLs to be more compact
        # Look for [text](url) patterns and ensure they're formatted nicely
        content = re.sub(
            r"\[([^\]]+)\]\(([^)]+)\)",
            lambda m: f"[{m.group(1)}](<{m.group(2)}>)",
            content,
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
    def format_embed_field(
        name: str, value: str, inline: bool = False
    ) -> Dict[str, Any]:
        """
        Format a field for a Discord embed.

        Args:
            name: Field name
            value: Field value
            inline: Whether the field should be inline

        Returns:
            Formatted field dictionary
        """
        return {"name": name, "value": value, "inline": inline}

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
        author_icon_url: Optional[str] = None,
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
    def format_list(
        items: List[str], ordered: bool = False, bold_numbers: bool = True
    ) -> str:
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
                return "\n".join(
                    [f"**{i}.** {item}" for i, item in enumerate(items, 1)]
                )
            else:
                return "\n".join([f"{i}. {item}" for i, item in enumerate(items, 1)])
        else:
            return "\n".join([f"• {item}" for item in items])

    @staticmethod
    def format_table(headers: List[str], rows: List[List[str]]) -> str:
        """
        Format a table using simple key-value pairs (mobile-friendly).
        Works well on all screen sizes without wrapping issues.

        Args:
            headers: List of header strings
            rows: List of row data

        Returns:
            Formatted table in code block
        """
        # For tables with many columns or long content, use key-value format
        num_cols = len(headers)
        max_cell_length = max(
            [len(str(h)) for h in headers]
            + [len(str(cell)) for row in rows for cell in row]
        )

        # Use key-value format for better mobile compatibility
        if num_cols > 2 or max_cell_length > 30:
            return DiscordFormatter._format_table_keyvalue(headers, rows)

        # Simple 2-column table - use pipe format
        output_lines = []
        for row in rows:
            for header, cell in zip(headers, row):
                output_lines.append(f"{header}: {cell}")
            output_lines.append("")  # Blank line between rows

        return "```\n" + "\n".join(output_lines).strip() + "\n```"

    @staticmethod
    def _format_table_keyvalue(headers: List[str], rows: List[List[str]]) -> str:
        """
        Format a table as key-value pairs (mobile-friendly, no wrapping issues).

        Args:
            headers: List of header strings
            rows: List of row data

        Returns:
            Formatted table in code block
        """
        output_lines = []

        for idx, row in enumerate(rows, 1):
            if idx > 1:
                output_lines.append("")  # Blank line between entries

            for header, cell in zip(headers, row):
                output_lines.append(f"{header}: {cell}")

        return "```\n" + "\n".join(output_lines) + "\n```"

    @staticmethod
    def _convert_markdown_tables_to_ascii(content: str) -> str:
        """
        Convert markdown tables in content to ASCII tables.

        Args:
            content: Content that may contain markdown tables

        Returns:
            Content with markdown tables converted to ASCII tables
        """
        # Pattern to match markdown tables
        # Matches: | header | header |
        #          |--------|--------|
        #          | cell   | cell   |
        table_pattern = r"(\|[^\n]+\|\n\|[-:\s|]+\|\n(?:\|[^\n]+\|\n?)+)"

        def replace_table(match):
            table_text = match.group(1)
            try:
                # Parse the markdown table
                lines = [line.strip() for line in table_text.strip().split("\n")]
                if len(lines) < 3:  # Need at least header, separator, and one row
                    return table_text

                # Extract headers
                header_line = lines[0]
                headers = [cell.strip() for cell in header_line.split("|")[1:-1]]

                # Extract rows (skip separator line at index 1)
                rows = []
                for line in lines[2:]:
                    if line.strip():
                        cells = [cell.strip() for cell in line.split("|")[1:-1]]
                        if cells:  # Only add non-empty rows
                            rows.append(cells)

                # Format as ASCII table
                if headers and rows:
                    return DiscordFormatter.format_table(headers, rows)
                else:
                    return table_text
            except Exception as e:
                logger.warning("Failed to convert markdown table to ASCII: %s", e)
                return table_text

        # Replace all markdown tables with ASCII tables
        return re.sub(table_pattern, replace_table, content, flags=re.MULTILINE)
