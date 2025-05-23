from openai import OpenAI
from logging_config import logger
import config # Assuming config.py is in the same directory or accessible
import json
from typing import Optional, Dict, List, Any

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
                    "content": "You are an assistant bot to the techfren community discord server. A community of AI coding, Open source and technology enthusiasts \
                    users can use the function /sum-day to summarize the messages received today. there will be more features coming in the future"
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
            if not msg.get('is_command', False) and  # Use .get for safety
               not (msg.get('content', '').startswith('/sum-day'))  # Explicitly filter out /sum-day commands
        ]

        if not filtered_messages:
            return f"No messages found in #{channel_name} for the past 24 hours."

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

            # Check if this message has scraped content from a URL
            scraped_url = msg.get('scraped_url')
            scraped_summary = msg.get('scraped_content_summary')
            scraped_key_points = msg.get('scraped_content_key_points')

            # Format the message with the basic content
            message_text = f"[{time_str}] {author_name}: {content}"

            # If there's scraped content, add it to the message
            if scraped_url and scraped_summary:
                message_text += f"\n\n[Link Content from {scraped_url}]:\n{scraped_summary}"

                # If there are key points, add them too
                if scraped_key_points:
                    try:
                        key_points = json.loads(scraped_key_points)
                        if key_points and isinstance(key_points, list):
                            message_text += "\n\nKey points:"
                            for point in key_points:
                                message_text += f"\n- {point}"
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse key points JSON: {scraped_key_points}")

            formatted_messages_text.append(message_text)

        # Join the messages with newlines
        messages_text = "\n".join(formatted_messages_text)

        # Create the prompt for the LLM
        prompt = f"""Please summarize the following conversation from the #{channel_name} channel for the past 24 hours:

{messages_text}

Provide a concise summary with short bullet points for main topics. Do not include an introductory paragraph.
Highlight all user names/aliases with backticks (e.g., `username`).
At the end, include a section with the top 3 most interesting or notable one-liner quotes from the conversation.
"""

        logger.info(f"Calling LLM API for channel summary: #{channel_name} for the past 24 hours")

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
                    "content": "You are a helpful assistant that summarizes Discord conversations. Create concise summaries with short bullet points. Highlight all user names with backticks. Do not include an introductory paragraph. End with the top 3 most interesting quotes from the conversation."
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
        final_summary = f"**Summary of #{channel_name} for the past 24 hours**\n\n{summary}"
        return final_summary

    except Exception as e:
        logger.error(f"Error calling LLM API for summary: {str(e)}", exc_info=True)
        return "Sorry, I encountered an error while generating the summary. Please try again later."

async def summarize_scraped_content(markdown_content: str, url: str) -> Optional[Dict[str, Any]]:
    """
    Call the LLM API to summarize scraped content from a URL and extract key points.

    Args:
        markdown_content (str): The scraped content in markdown format
        url (str): The URL that was scraped

    Returns:
        Optional[Dict[str, Any]]: A dictionary containing the summary and key points,
                                 or None if summarization failed
    """
    try:
        # Truncate content if it's too long (to avoid token limits)
        max_content_length = 15000  # Adjust based on model's context window
        truncated_content = markdown_content[:max_content_length]
        if len(markdown_content) > max_content_length:
            truncated_content += "\n\n[Content truncated due to length...]"

        logger.info(f"Summarizing content from URL: {url}")

        # Check if OpenRouter API key exists
        if not hasattr(config, 'openrouter') or not config.openrouter:
            logger.error("OpenRouter API key not found in config.py or is empty")
            return None

        # Initialize the OpenAI client with OpenRouter base URL
        openai_client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=config.openrouter
        )

        # Get the model from config or use default
        model = getattr(config, 'llm_model', "x-ai/grok-3-mini-beta")

        # Create the prompt for the LLM
        prompt = f"""Please analyze the following content from the URL: {url}

{truncated_content}

Provide:
1. A concise summary (2-3 paragraphs) of the main content.
2. 3-5 key bullet points highlighting the most important information.

Format your response exactly as follows:
```json
{{
  "summary": "Your summary text here...",
  "key_points": [
    "First key point",
    "Second key point",
    "Third key point",
    "Fourth key point (if applicable)",
    "Fifth key point (if applicable)"
  ]
}}
```
"""

        # Make the API request
        completion = openai_client.chat.completions.create(
            extra_headers={
                "HTTP-Referer": "https://techfren.net",
                "X-Title": "TechFren Discord Bot",
            },
            model=model,  # Use the model from config
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert assistant that summarizes web content and extracts key points. You always respond in the exact JSON format requested."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            max_tokens=1500,  # Increased token limit for summaries
            temperature=0.3   # Lower temperature for more focused and consistent summaries
        )

        # Extract the response
        response_text = completion.choices[0].message.content
        logger.info(f"LLM API summary received successfully: {response_text[:50]}{'...' if len(response_text) > 50 else ''}")

        # Extract the JSON part from the response
        try:
            # Find JSON between triple backticks if present
            if "```json" in response_text and "```" in response_text.split("```json", 1)[1]:
                json_str = response_text.split("```json", 1)[1].split("```", 1)[0].strip()
            elif "```" in response_text and "```" in response_text.split("```", 1)[1]:
                json_str = response_text.split("```", 1)[1].split("```", 1)[0].strip()
            else:
                # If no backticks, try to parse the whole response
                json_str = response_text.strip()

            # Parse the JSON
            result = json.loads(json_str)

            # Validate the expected structure
            if "summary" not in result or "key_points" not in result:
                logger.warning(f"LLM response missing required fields: {result}")
                # Create a fallback structure
                if "summary" not in result:
                    result["summary"] = "Summary could not be extracted from the content."
                if "key_points" not in result:
                    result["key_points"] = ["Key points could not be extracted from the content."]

            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from LLM response: {e}", exc_info=True)
            logger.error(f"Raw response: {response_text}")

            # Create a fallback response
            return {
                "summary": "Failed to generate a proper summary from the content.",
                "key_points": ["The content could not be properly summarized due to a processing error."]
            }

    except Exception as e:
        logger.error(f"Error summarizing content from URL {url}: {str(e)}", exc_info=True)
        return None
