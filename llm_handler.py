from openai import OpenAI
from logging_config import logger
import config # Assuming config.py is in the same directory or accessible

async def call_llm_api(query):
    """
    Call the LLM API with the user's query and return the response

    Args:
        query (str): The user's query text

    Returns:
        str: The LLM's response or an error message
    """
    try:
        logger.info(f"Calling LLM API with query: {query[:50]}{'...' if len(query) > 50 else ''}")

        # Check if OpenRouter API key exists
        if not hasattr(config, 'openrouter') or not config.openrouter:
            logger.error("OpenRouter API key not found in config.py or is empty")
            return "Error: OpenRouter API key is missing. Please contact the bot administrator."

        # Initialize the OpenAI client with OpenRouter base URL
        openai_client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=config.openrouter
        )

        # Get the model from config or use default
        model = getattr(config, 'llm_model', "x-ai/grok-3-mini-beta")

        # Make the API request
        completion = openai_client.chat.completions.create(
            extra_headers={
                "HTTP-Referer": "https://techfren.net",  # Optional site URL
                "X-Title": "TechFren Discord Bot",  # Optional site title
            },
            model=model,  # Use the model from config
            messages=[
                {
                    "role": "system",
                    "content": "You are an assistant bot to the techfren community discord server. A community of AI coding, Open source and technology enthusiasts"
                },
                {
                    "role": "user",
                    "content": query
                }
            ],
            max_tokens=1000,
            temperature=0.7
        )

        # Extract the response
        message = completion.choices[0].message.content
        logger.info(f"LLM API response received successfully: {message[:50]}{'...' if len(message) > 50 else ''}")
        return message

    except Exception as e:
        logger.error(f"Error calling LLM API: {str(e)}", exc_info=True)
        return "Sorry, I encountered an error while processing your request. Please try again later."

async def call_llm_for_summary(messages, channel_name, date):
    """
    Call the LLM API to summarize a list of messages from a channel

    Args:
        messages (list): List of message dictionaries
        channel_name (str): Name of the channel
        date (datetime): Date of the messages

    Returns:
        str: The LLM's summary or an error message
    """
    try:
        # Filter out command messages but include bot responses
        filtered_messages = [
            msg for msg in messages
            if not msg.get('is_command', False) # Use .get for safety
        ]

        if not filtered_messages:
            return f"No messages found in #{channel_name} for {date.strftime('%Y-%m-%d')}."

        # Prepare the messages for summarization
        formatted_messages_text = []
        for msg in filtered_messages:
            # Ensure created_at is a datetime object before calling strftime
            created_at_time = msg.get('created_at')
            if hasattr(created_at_time, 'strftime'):
                time_str = created_at_time.strftime('%H:%M:%S')
            else:
                time_str = "Unknown Time" # Fallback if created_at is not as expected
            
            author_name = msg.get('author_name', 'Unknown Author')
            content = msg.get('content', '')
            formatted_messages_text.append(f"[{time_str}] {author_name}: {content}")

        # Join the messages with newlines
        messages_text = "\n".join(formatted_messages_text)

        # Create the prompt for the LLM
        prompt = f"""Please summarize the following conversation from the #{channel_name} channel on {date.strftime('%Y-%m-%d')}:

{messages_text}

Provide a concise summary of the main topics discussed, key points made, and any conclusions reached.
Format the summary in a clear, readable way with bullet points for main topics.
"""

        logger.info(f"Calling LLM API for channel summary: #{channel_name} on {date.strftime('%Y-%m-%d')}")

        # Check if OpenRouter API key exists
        if not hasattr(config, 'openrouter') or not config.openrouter:
            logger.error("OpenRouter API key not found in config.py or is empty")
            return "Error: OpenRouter API key is missing. Please contact the bot administrator."

        # Initialize the OpenAI client with OpenRouter base URL
        openai_client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=config.openrouter
        )

        # Get the model from config or use default
        model = getattr(config, 'llm_model', "x-ai/grok-3-mini-beta")

        # Make the API request with a higher token limit for summaries
        completion = openai_client.chat.completions.create(
            extra_headers={
                "HTTP-Referer": "https://techfren.net",
                "X-Title": "TechFren Discord Bot",
            },
            model=model,  # Use the model from config
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant that summarizes Discord conversations. Provide clear, concise summaries that capture the main points of discussions."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            max_tokens=1500,  # Increased token limit for summaries
            temperature=0.5   # Lower temperature for more focused summaries
        )

        # Extract the response
        summary = completion.choices[0].message.content
        logger.info(f"LLM API summary received successfully: {summary[:50]}{'...' if len(summary) > 50 else ''}")

        # Add a header to the summary
        final_summary = f"**Summary of #{channel_name} on {date.strftime('%Y-%m-%d')}**\n\n{summary}"
        return final_summary

    except Exception as e:
        logger.error(f"Error calling LLM API for summary: {str(e)}", exc_info=True)
        return "Sorry, I encountered an error while generating the summary. Please try again later."
