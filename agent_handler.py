"""
Agent handler module for Claude Code SDK integration.
Allows users to request Claude agents to work on tasks and create PRs.
"""

import asyncio
import logging
import os
import uuid
from typing import Optional, Callable, Awaitable

import config
import database

logger = logging.getLogger('discord_bot.agent_handler')

# Track active agent sessions
_active_agents = {}


class AgentTaskError(Exception):
    """Custom exception for agent task errors."""
    pass


def is_agent_configured() -> bool:
    """
    Check if the agent feature is properly configured.

    Returns:
        True if all required configuration is present
    """
    return bool(
        config.anthropic_api_key and
        config.agent_github_token and
        config.agent_github_repo
    )


def get_missing_config() -> list[str]:
    """
    Get a list of missing configuration items.

    Returns:
        List of missing configuration variable names
    """
    missing = []
    if not config.anthropic_api_key:
        missing.append('ANTHROPIC_API_KEY')
    if not config.agent_github_token:
        missing.append('AGENT_GITHUB_TOKEN')
    if not config.agent_github_repo:
        missing.append('AGENT_GITHUB_REPO')
    return missing


async def run_agent_task(
    task_id: str,
    task_description: str,
    status_callback: Optional[Callable[[str, str], Awaitable[None]]] = None
) -> tuple[bool, Optional[str], Optional[str]]:
    """
    Run a Claude agent to complete a task and create a PR.

    Args:
        task_id: Unique identifier for this task
        task_description: What the agent should do
        status_callback: Optional async callback(task_id, message) for status updates

    Returns:
        Tuple of (success: bool, pr_url: Optional[str], error: Optional[str])
    """
    try:
        # Import the SDK here to avoid import errors if not installed
        from claude_code_sdk import query, ClaudeCodeOptions, Message
    except ImportError:
        logger.error("claude-code-sdk not installed")
        return False, None, "Claude Code SDK is not installed"

    if not is_agent_configured():
        missing = get_missing_config()
        return False, None, f"Missing configuration: {', '.join(missing)}"

    # Update task status to running
    database.update_agent_task_status(task_id, 'running')

    if status_callback:
        await status_callback(task_id, "Agent is starting...")

    # Store in active agents
    _active_agents[task_id] = {
        'status': 'running',
        'messages': []
    }

    try:
        # Set up environment for the agent
        os.environ['ANTHROPIC_API_KEY'] = config.anthropic_api_key

        # Build the prompt for the agent
        repo = config.agent_github_repo
        prompt = f"""You are working on the GitHub repository: {repo}

Task requested by a Discord user:
{task_description}

Instructions:
1. First, clone the repository if not already present, or pull latest changes
2. Create a new branch for this work with a descriptive name
3. Make the requested changes
4. Run any existing tests to ensure nothing is broken
5. Commit your changes with a clear commit message
6. Push the branch to the remote repository
7. Create a pull request with:
   - A clear, descriptive title
   - A detailed description of what was changed and why
   - Any relevant notes for reviewers

Important:
- Use the GitHub token from the AGENT_GITHUB_TOKEN environment variable for authentication
- The repository URL is: https://github.com/{repo}
- Make sure to create the PR and provide the PR URL at the end

After creating the PR, output the PR URL in this exact format on its own line:
PR_URL: https://github.com/{repo}/pull/XXX
"""

        # Configure the agent options
        options = ClaudeCodeOptions(
            allowed_tools=[
                "Bash",
                "Read",
                "Write",
                "Edit",
                "Glob",
                "Grep"
            ],
            permission_mode="acceptEdits"
        )

        pr_url = None
        last_message = ""

        # Run the agent
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, Message):
                # Handle different message types
                if hasattr(message, 'content'):
                    content = str(message.content) if message.content else ""
                    last_message = content

                    # Store message
                    if task_id in _active_agents:
                        _active_agents[task_id]['messages'].append(content)

                    # Check for PR URL in the output
                    if 'PR_URL:' in content:
                        # Extract PR URL
                        for line in content.split('\n'):
                            if line.strip().startswith('PR_URL:'):
                                pr_url = line.split('PR_URL:')[1].strip()
                                break

                    # Send status update
                    if status_callback and len(content) > 0:
                        # Truncate long messages
                        update_msg = content[:200] + "..." if len(content) > 200 else content
                        await status_callback(task_id, f"Agent working: {update_msg}")

        # Check if we got a PR URL
        if pr_url:
            database.update_agent_task_status(task_id, 'completed', pr_url=pr_url)
            if status_callback:
                await status_callback(task_id, f"Task completed! PR created: {pr_url}")
            return True, pr_url, None
        else:
            # Task completed but no PR URL found
            database.update_agent_task_status(
                task_id,
                'completed',
                error_message="Task completed but no PR URL was found in output"
            )
            if status_callback:
                await status_callback(task_id, "Task completed but no PR was created")
            return True, None, "No PR URL found in agent output"

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error running agent task {task_id}: {error_msg}", exc_info=True)
        database.update_agent_task_status(task_id, 'failed', error_message=error_msg)
        if status_callback:
            await status_callback(task_id, f"Task failed: {error_msg}")
        return False, None, error_msg

    finally:
        # Clean up
        if task_id in _active_agents:
            del _active_agents[task_id]


def generate_task_id(author_id: str) -> str:
    """
    Generate a unique task ID.

    Args:
        author_id: Discord user ID

    Returns:
        Unique task ID string
    """
    return f"agent-{author_id}-{uuid.uuid4().hex[:8]}"


def get_active_agent_count() -> int:
    """
    Get the count of currently active agent tasks.

    Returns:
        Number of active agents
    """
    return len(_active_agents)


def is_task_active(task_id: str) -> bool:
    """
    Check if a specific task is currently active.

    Args:
        task_id: Task ID to check

    Returns:
        True if task is active
    """
    return task_id in _active_agents


def get_task_messages(task_id: str) -> list[str]:
    """
    Get the messages from an active task.

    Args:
        task_id: Task ID

    Returns:
        List of message strings
    """
    if task_id in _active_agents:
        return _active_agents[task_id].get('messages', [])
    return []
