async def split_long_message(message, max_length=1900):
    """
    Split a long message into multiple parts to avoid Discord's 2000 character limit

    Args:
        message (str): The message to split
        max_length (int): Maximum length of each part (default: 1900 to leave room for part indicators)

    Returns:
        list: List of message parts
    """
    # Quick return for messages that don't need splitting
    if len(message) <= max_length:
        return [message]

    parts = []
    remaining = message
    
    while remaining:
        # Check if the remaining text fits in one part
        if len(remaining) <= max_length:
            parts.append(remaining)
            break
            
        # Try to find a good split point
        # First try paragraph break
        paragraph_end = remaining.rfind("\n\n", 0, max_length)
        
        # If paragraph break is found and not too close to the beginning
        if paragraph_end > max_length // 2:
            split_at = paragraph_end + 2  # Include the double newline
        else:
            # Try sentence ending (period + space)
            sentence_end = remaining.rfind(". ", 0, max_length)
            if sentence_end > 0:
                split_at = sentence_end + 2  # Include the period and space
            else:
                # Try any space
                space = remaining.rfind(" ", max_length // 2, max_length)
                if space > 0:
                    split_at = space + 1  # Include the space
                else:
                    # Force split at max_length if no natural break point
                    split_at = max_length
        
        # Add the current part and continue with the rest
        parts.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    
    # Add part indicators if there are multiple parts
    if len(parts) > 1:
        total_parts = len(parts)
        for i in range(total_parts):
            parts[i] = f"[Part {i+1}/{total_parts}]\n{parts[i]}"
    
    return parts
