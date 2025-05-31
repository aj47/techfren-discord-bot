def generate_discord_message_link(guild_id: str, channel_id: str, message_id: str) -> str:
    """
    Generate a Discord message link from guild ID, channel ID, and message ID.

    Args:
        guild_id (str): The Discord guild (server) ID
        channel_id (str): The Discord channel ID
        message_id (str): The Discord message ID

    Returns:
        str: The Discord message link
    """
    if guild_id:
        return f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"
    else:
        # For DMs, use @me instead of guild_id
        return f"https://discord.com/channels/@me/{channel_id}/{message_id}"

async def split_long_message(message, discord_limit=2000):
    """
    Split a long message into multiple parts to strictly avoid Discord's 2000 character limit.

    This function ensures that:
    1. Each final message part (including part indicators) is under the Discord limit
    2. Part indicators are accounted for in length calculations
    3. No content is lost during splitting
    4. Messages are split at natural boundaries when possible

    Args:
        message (str): The message to split
        discord_limit (int): Discord's character limit (default: 2000)

    Returns:
        list: List of message parts, each guaranteed to be under discord_limit
    """
    if not message or not message.strip():
        return [message] if message else []

    # If message is short enough, return as-is
    if len(message) <= discord_limit:
        return [message]

    def calculate_part_indicator_length(part_num, total_parts):
        """Calculate the length of part indicator like '[Part 1/3]\n'"""
        return len(f"[Part {part_num}/{total_parts}]\n")

    def estimate_max_part_indicator_length(estimated_parts):
        """Estimate the maximum length a part indicator could be"""
        # Account for potentially more parts than estimated
        safety_parts = max(estimated_parts * 2, 99)  # Up to 99 parts max
        return len(f"[Part {safety_parts}/{safety_parts}]\n")

    def find_split_point(text, max_length):
        """Find the best place to split text, preferring natural boundaries"""
        if len(text) <= max_length:
            return len(text)

        # Try to split at paragraph boundary (double newline)
        for i in range(max_length, max(0, max_length - 200), -1):
            if i < len(text) - 1 and text[i:i+2] == '\n\n':
                return i

        # Try to split at sentence ending
        for i in range(max_length, max(0, max_length - 100), -1):
            if i < len(text) and text[i] == '.' and (i + 1 >= len(text) or text[i+1] == ' '):
                return i + 1

        # Try to split at line break
        for i in range(max_length, max(0, max_length - 50), -1):
            if i < len(text) and text[i] == '\n':
                return i

        # Try to split at word boundary
        for i in range(max_length, max(0, max_length - 20), -1):
            if i < len(text) and text[i] == ' ':
                return i

        # Force split if no good boundary found
        return max_length

    # Estimate how many parts we might need for initial calculation
    estimated_parts = (len(message) // (discord_limit - 50)) + 1
    max_indicator_length = estimate_max_part_indicator_length(estimated_parts)

    # Calculate safe length for content (leaving room for part indicators)
    safe_content_length = discord_limit - max_indicator_length - 10  # Extra safety margin

    # Split the message into parts
    parts = []
    remaining_text = message

    while remaining_text:
        if len(remaining_text) <= safe_content_length:
            # Remaining text fits in one part
            parts.append(remaining_text.strip())
            break

        # Find the best split point
        split_point = find_split_point(remaining_text, safe_content_length)

        # Extract the part and clean it up
        part = remaining_text[:split_point].strip()
        if part:
            parts.append(part)

        # Move to the next section
        remaining_text = remaining_text[split_point:].strip()

    # Filter out empty parts
    parts = [part for part in parts if part.strip()]

    if not parts:
        return [message]  # Fallback to original if something went wrong

    # If only one part, return as-is
    if len(parts) == 1:
        return parts

    # Check if the original message starts with a title that should be handled separately
    title_part = None
    content_to_split = message

    if (message.startswith('**') and '\n' in message):
        lines = message.split('\n', 1)  # Split into first line and rest
        potential_title = lines[0]

        # Check if first line looks like a title
        if (potential_title.endswith('**') and
            len(potential_title) < 200 and
            len(lines) > 1):

            title_part = potential_title
            content_to_split = lines[1].strip()  # Rest of the content

            # Re-split just the content (without title)
            if content_to_split:
                content_parts = []
                remaining_content = content_to_split

                while remaining_content:
                    if len(remaining_content) <= safe_content_length:
                        content_parts.append(remaining_content.strip())
                        break

                    split_point = find_split_point(remaining_content, safe_content_length)
                    part = remaining_content[:split_point].strip()
                    if part:
                        content_parts.append(part)
                    remaining_content = remaining_content[split_point:].strip()

                # Filter out empty parts
                content_parts = [part for part in content_parts if part.strip()]

                if len(content_parts) == 0:
                    return [title_part]
                elif len(content_parts) == 1:
                    return [title_part, content_parts[0]]
                else:
                    # Add part indicators to content parts only
                    final_content_parts = []
                    for i, part in enumerate(content_parts):
                        indicator = f"[Part {i+1}/{len(content_parts)}]\n"
                        final_part = indicator + part

                        # Verify the final part doesn't exceed Discord limit
                        if len(final_part) > discord_limit:
                            # This part is still too long, need to re-split
                            sub_parts = await split_long_message(part, discord_limit)
                            final_content_parts.extend(sub_parts)
                        else:
                            final_content_parts.append(final_part)

                    return [title_part] + final_content_parts
            else:
                return [title_part]

    # Normal case: add part indicators to all parts
    final_parts = []
    for i, part in enumerate(parts):
        indicator = f"[Part {i+1}/{len(parts)}]\n"
        final_part = indicator + part

        # Verify the final part doesn't exceed Discord limit
        if len(final_part) > discord_limit:
            # This part is still too long, need to re-split
            sub_parts = await split_long_message(part, discord_limit)
            final_parts.extend(sub_parts)
        else:
            final_parts.append(final_part)

    return final_parts
