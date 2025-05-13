async def split_long_message(message, max_length=1900):
    """
    Split a long message into multiple parts to avoid Discord's 2000 character limit

    Args:
        message (str): The message to split
        max_length (int): Maximum length of each part (default: 1900 to leave room for part indicators)

    Returns:
        list: List of message parts
    """
    if len(message) <= max_length:
        return [message]

    parts = []
    current_part = ""

    # Split by paragraphs first (double newlines)
    paragraphs = message.split("\n\n")

    for paragraph in paragraphs:
        # If adding this paragraph would exceed max_length, start a new part
        if len(current_part) + len(paragraph) + 2 > max_length: # +2 for potential "\n\n"
            if current_part:
                parts.append(current_part.strip())
            current_part = paragraph
        else:
            if current_part:
                current_part += "\n\n" + paragraph
            else:
                current_part = paragraph
        
        # Inner loop to handle cases where a single paragraph (or the current_part) is too long
        while len(current_part) > max_length:
            # Find a good split point (prefer sentence, then word)
            split_at = -1
            # Try to split at the last sentence ending before max_length
            for i in range(min(len(current_part), max_length) -1, -1, -1):
                if current_part[i] == '.' and (i + 1 < len(current_part) and current_part[i+1] == ' '):
                    split_at = i + 1 # Include the period, split after space
                    break
            
            if split_at == -1: # If no sentence found, try to split at the last space
                for i in range(min(len(current_part), max_length) -1, -1, -1):
                    if current_part[i] == ' ':
                        split_at = i
                        break
            
            if split_at == -1: # If no space found, force split at max_length
                split_at = max_length

            parts.append(current_part[:split_at].strip())
            current_part = current_part[split_at:].strip()


    # Add the last part if it's not empty
    if current_part:
        parts.append(current_part.strip())

    # Add part indicators if there are multiple parts
    if len(parts) > 1:
        for i in range(len(parts)):
            parts[i] = f"[Part {i+1}/{len(parts)}]\n{parts[i]}"
    elif not parts and message: # Handle case where original message was <= max_length but split logic ran
        return [message]


    return parts
