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
    def _normalize_citations(citations: Any) -> List[Dict[str, Any]]:
        """
        Normalize citations from different API formats into a unified format.

        Handles:
        - Perplexity format: List of URL strings
        - Perplexity nested format: {"citations": [{"url": "..."}]}
        - Perplexity double-nested format: {"citations": [{"url": "...", "citations": [...]}]}
        - Exa format: List of objects with url, title, publishedDate, author, etc.
        - Dict-wrapped citations: {"items": [...]} or other wrapper keys
        - Citations with alternate url field names: link, source_url, href

        Args:
            citations: Citations in either format

        Returns:
            List of citation dictionaries with at least 'url' key
        """
        if not citations:
            return []

        # Handle various dict wrapper formats
        if isinstance(citations, dict):
            # Try common wrapper keys
            for wrapper_key in ['citations', 'items', 'sources', 'results', 'data']:
                if wrapper_key in citations and isinstance(citations[wrapper_key], list):
                    citations = citations[wrapper_key]
                    break
            else:
                # Dict but no recognized wrapper - try to extract url if present
                if 'url' in citations:
                    return [citations]
                logger.warning(f"Unrecognized citation dict format: {citations}")
                return []

        # Handle list of lists (nested citations)
        if isinstance(citations, list) and len(citations) > 0:
            # Check if all elements are lists (nested citations)
            if all(isinstance(item, list) for item in citations):
                # Flatten nested lists
                citations = [item for sublist in citations for item in sublist]

        normalized = []
        for citation in citations:
            normalized_citation = DiscordFormatter._normalize_single_citation(citation)
            if normalized_citation:
                normalized.append(normalized_citation)

        return normalized

    @staticmethod
    def _normalize_single_citation(citation: Any) -> Optional[Dict[str, Any]]:
        """
        Normalize a single citation from any format.

        Args:
            citation: Single citation in any format

        Returns:
            Citation dictionary with 'url' key, or None if invalid
        """
        if isinstance(citation, str):
            # Perplexity format: simple URL string
            return {'url': citation}
        elif isinstance(citation, dict):
            # Exa format: object with url and other metadata
            # Try to find URL in common fields
            url = None
            for url_field in ['url', 'link', 'source_url', 'href', 'source']:
                if url_field in citation:
                    url = citation[url_field]
                    break

            if url:
                # Build normalized citation, preserving all metadata
                normalized = {'url': url}
                # Copy other fields except wrapper keys
                for key, value in citation.items():
                    if key not in ['url', 'link', 'source_url', 'href', 'source', 'citations', 'items']:
                        normalized[key] = value
                return normalized
            else:
                logger.warning(f"Citation object missing URL field: {citation}")
                return None
        else:
            logger.warning(f"Unknown citation format: {type(citation)} - {citation}")
            return None

    @staticmethod
    def _format_citation_link(index: int, citation: Dict[str, Any]) -> str:
        """
        Format a single citation as a clickable Discord link.

        Args:
            index: The citation number (1-based)
            citation: Citation dictionary with url and optional metadata

        Returns:
            Formatted citation link
        """
        url = citation.get('url', '')
        return f"[`[{index}]`]({url})"

    @staticmethod
    def _format_sources_section(citations: List[Dict[str, Any]]) -> str:
        """
        Format a sources section with citation metadata for Exa-style citations.

        Args:
            citations: List of citation dictionaries with metadata

        Returns:
            Formatted sources section string
        """
        if not citations:
            return ""

        # Check if any citations have metadata beyond just URL
        has_metadata = any(
            citation.get('title') or citation.get('author') or citation.get('publishedDate')
            for citation in citations
        )

        if not has_metadata:
            return ""

        lines = ["\n\n📚 **Sources:**"]
        for i, citation in enumerate(citations, 1):
            url = citation.get('url', '')
            title = citation.get('title', '')
            author = citation.get('author', '')
            published_date = citation.get('publishedDate', '')

            # Build the source line
            if title:
                line = f"**{i}.** [{title}](<{url}>)"
            else:
                line = f"**{i}.** [Source {i}](<{url}>)"

            # Add metadata if available
            metadata_parts = []
            if author:
                metadata_parts.append(f"by {author}")
            if published_date:
                # Format date if it's in ISO format
                try:
                    from datetime import datetime
                    if 'T' in published_date:
                        date_obj = datetime.fromisoformat(published_date.replace('Z', '+00:00'))
                        formatted_date = date_obj.strftime('%b %d, %Y')
                        metadata_parts.append(formatted_date)
                    else:
                        metadata_parts.append(published_date)
                except (ValueError, TypeError):
                    metadata_parts.append(published_date)

            if metadata_parts:
                line += f" — *{', '.join(metadata_parts)}*"

            lines.append(line)

        return "\n".join(lines)

    @staticmethod
    def format_llm_response(content: str, citations: Optional[List[Any]] = None) -> str:
        """
        Format an LLM response with enhanced Discord markdown.

        Args:
            content: The raw LLM response content
            citations: Optional list of citations (supports both Perplexity URL strings
                      and Exa citation objects with url, title, author, etc.)

        Returns:
            Formatted string with Discord markdown
        """
        formatted = content

        # Convert markdown tables to ASCII tables before other formatting
        formatted = DiscordFormatter._convert_markdown_tables_to_ascii(formatted)

        # Normalize citations to a unified format
        normalized_citations = DiscordFormatter._normalize_citations(citations)

        # Replace [1], [2] style citations with clickable links
        if normalized_citations:
            for i, citation in enumerate(normalized_citations, 1):
                citation_link = DiscordFormatter._format_citation_link(i, citation)
                formatted = formatted.replace(f"[{i}]", citation_link)

        # Enhanced formatting patterns
        formatting_rules = [
            # Headers - Convert markdown headers to Discord formatting
            (r'^#{1}\s+(.+)$', r'__**\1**__', re.MULTILINE),  # # Header -> bold underline
            (r'^#{2}\s+(.+)$', r'**\1**\n', re.MULTILINE),      # ## Header -> bold with newline for spacing
            (r'^#{3,}\s+(.+)$', r'__\1__', re.MULTILINE),     # ### Header -> underline

            # Lists - Enhance bullet points and numbered lists
            (r'^\*\s+(.+)$', r'• \1', re.MULTILINE),          # * item -> • item
            (r'^-\s+(.+)$', r'• \1', re.MULTILINE),           # - item -> • item
            (r'^(\d+)\.\s+(.+)$', r'**\1.** \2', re.MULTILINE), # 1. item -> bold number

            # Emphasis patterns already in the text
            # (Leave existing **bold** and *italic* as is, they work in Discord)

            # Code - Ensure inline code uses backticks properly
            (r'`([^`]+)`', r'`\1`', 0),  # Keep inline code as is

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

        # Add sources section for Exa-style citations with metadata
        if normalized_citations:
            sources_section = DiscordFormatter._format_sources_section(normalized_citations)
            if sources_section:
                formatted += sources_section

        return formatted

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
        # We'll make them bold as well
        content = re.sub(r'`([^`]+)`', r'**`\1`**', content)
        
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
        max_cell_length = max([len(str(h)) for h in headers] +
                              [len(str(cell)) for row in rows for cell in row])

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
        table_pattern = r'(\|[^\n]+\|\n\|[-:\s|]+\|\n(?:\|[^\n]+\|\n?)+)'

        def replace_table(match):
            table_text = match.group(1)
            try:
                # Parse the markdown table
                lines = [line.strip() for line in table_text.strip().split('\n')]
                if len(lines) < 3:  # Need at least header, separator, and one row
                    return table_text

                # Extract headers
                header_line = lines[0]
                headers = [cell.strip() for cell in header_line.split('|')[1:-1]]

                # Extract rows (skip separator line at index 1)
                rows = []
                for line in lines[2:]:
                    if line.strip():
                        cells = [cell.strip() for cell in line.split('|')[1:-1]]
                        if cells:  # Only add non-empty rows
                            rows.append(cells)

                # Format as ASCII table
                if headers and rows:
                    return DiscordFormatter.format_table(headers, rows)
                else:
                    return table_text
            except Exception as e:
                logger.warning(f"Failed to convert markdown table to ASCII: {e}")
                return table_text

        # Replace all markdown tables with ASCII tables
        return re.sub(table_pattern, replace_table, content, flags=re.MULTILINE)

