"""
Utility script for interacting with the Discord bot database.
Provides command-line tools for querying and managing the database.
"""

import argparse
import sqlite3
import os
import sys
import json
from datetime import datetime
from tabulate import tabulate
from typing import List, Dict, Any, Optional

# Database constants
DB_DIRECTORY = "data"
DB_FILE = os.path.join(DB_DIRECTORY, "discord_messages.db")

def get_connection() -> sqlite3.Connection:
    """Get a connection to the SQLite database."""
    if not os.path.exists(DB_FILE):
        print(f"Error: Database file not found at {DB_FILE}")
        sys.exit(1)

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def list_recent_messages(limit: int = 10) -> None:
    """List the most recent messages in the database."""
    conn = get_connection()
    cursor = conn.cursor()

    query = """
    SELECT id, author_name, channel_name, guild_name,
           substr(content, 1, 50) as content_preview,
           created_at, is_command, command_type
    FROM messages
    ORDER BY created_at DESC
    LIMIT ?
    """

    cursor.execute(query, (limit,))
    rows = cursor.fetchall()

    if not rows:
        print("No messages found in the database.")
        return

    # Convert rows to list of dicts for tabulate
    data = []
    for row in rows:
        data.append({
            "ID": row['id'],
            "Author": row['author_name'],
            "Channel": row['channel_name'],
            "Guild": row['guild_name'] or 'DM',
            "Content": row['content_preview'] + ('...' if len(row['content_preview']) >= 50 else ''),
            "Created At": row['created_at'],
            "Command": f"{row['command_type'] if row['is_command'] else 'No'}"
        })

    print(tabulate(data, headers="keys", tablefmt="grid"))
    print(f"\nTotal messages shown: {len(rows)}")

    conn.close()

def get_message_stats() -> None:
    """Get statistics about messages in the database."""
    conn = get_connection()
    cursor = conn.cursor()

    # Total message count
    cursor.execute("SELECT COUNT(*) FROM messages")
    total_count = cursor.fetchone()[0]

    # Command count
    cursor.execute("SELECT COUNT(*) FROM messages WHERE is_command = 1")
    command_count = cursor.fetchone()[0]

    # Command type breakdown
    cursor.execute("""
    SELECT command_type, COUNT(*) as count
    FROM messages
    WHERE is_command = 1
    GROUP BY command_type
    """)
    command_types = cursor.fetchall()

    # User message count
    cursor.execute("""
    SELECT author_name, COUNT(*) as count
    FROM messages
    GROUP BY author_id
    ORDER BY count DESC
    LIMIT 10
    """)
    top_users = cursor.fetchall()

    # Channel message count
    cursor.execute("""
    SELECT channel_name, COUNT(*) as count
    FROM messages
    GROUP BY channel_id
    ORDER BY count DESC
    LIMIT 10
    """)
    top_channels = cursor.fetchall()

    # Print statistics
    print("\n=== Message Statistics ===")
    print(f"Total messages: {total_count}")
    print(f"Commands: {command_count} ({command_count/total_count*100:.1f}% of total)")

    print("\n--- Command Types ---")
    for cmd in command_types:
        print(f"{cmd['command_type']}: {cmd['count']} ({cmd['count']/command_count*100:.1f}% of commands)")

    print("\n--- Top Users ---")
    user_data = [{"User": row['author_name'], "Messages": row['count']} for row in top_users]
    print(tabulate(user_data, headers="keys", tablefmt="simple"))

    print("\n--- Top Channels ---")
    channel_data = [{"Channel": row['channel_name'], "Messages": row['count']} for row in top_channels]
    print(tabulate(channel_data, headers="keys", tablefmt="simple"))

    conn.close()

def list_summaries(limit: int = 10, channel: Optional[str] = None, date: Optional[str] = None) -> None:
    """
    List channel summaries from the database.

    Args:
        limit (int): Maximum number of summaries to show
        channel (Optional[str]): Filter by channel name
        date (Optional[str]): Filter by date (YYYY-MM-DD)
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Build the query based on filters
    query = """
    SELECT id, channel_name, guild_name, date,
           substr(summary_text, 1, 100) as summary_preview,
           message_count, active_users, created_at
    FROM channel_summaries
    """

    conditions = []
    params = []

    if channel:
        conditions.append("channel_name LIKE ?")
        params.append(f"%{channel}%")

    if date:
        conditions.append("date = ?")
        params.append(date)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()

    if not rows:
        print("No summaries found in the database.")
        return

    # Convert rows to list of dicts for tabulate
    data = []
    for row in rows:
        data.append({
            "ID": row['id'],
            "Channel": row['channel_name'],
            "Guild": row['guild_name'] or 'N/A',
            "Date": row['date'],
            "Messages": row['message_count'],
            "Users": row['active_users'],
            "Summary Preview": row['summary_preview'] + ('...' if len(row['summary_preview']) >= 100 else ''),
            "Created At": row['created_at']
        })

    print(tabulate(data, headers="keys", tablefmt="grid"))
    print(f"\nTotal summaries shown: {len(rows)}")

    conn.close()

def view_summary(summary_id: int) -> None:
    """
    View a specific channel summary in full.

    Args:
        summary_id (int): ID of the summary to view
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT channel_name, guild_name, date, summary_text,
               message_count, active_users, active_users_list, created_at, metadata
        FROM channel_summaries
        WHERE id = ?
        """,
        (summary_id,)
    )

    row = cursor.fetchone()

    if not row:
        print(f"No summary found with ID {summary_id}")
        return

    # Parse the active users list from JSON
    active_users = json.loads(row['active_users_list'])

    # Parse metadata if available
    metadata = json.loads(row['metadata']) if row['metadata'] else {}

    # Print the summary details
    print("\n" + "=" * 80)
    print(f"CHANNEL SUMMARY: {row['channel_name']} ({row['date']})")
    print("=" * 80)
    print(f"Guild: {row['guild_name'] or 'N/A'}")
    print(f"Messages: {row['message_count']}")
    print(f"Active Users: {row['active_users']}")
    print(f"Created At: {row['created_at']}")

    if metadata:
        print("\nMetadata:")
        for key, value in metadata.items():
            print(f"  {key}: {value}")

    print("\nActive Users List:")
    for user in active_users:
        print(f"  - {user}")

    print("\nSummary:")
    print("-" * 80)
    print(row['summary_text'])
    print("-" * 80)

    conn.close()

def main():
    parser = argparse.ArgumentParser(description="Discord Bot Database Utility")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # List recent messages command
    list_parser = subparsers.add_parser("list", help="List recent messages")
    list_parser.add_argument("-n", "--limit", type=int, default=10, help="Number of messages to show")

    # Stats command
    subparsers.add_parser("stats", help="Show message statistics")

    # List summaries command
    summaries_parser = subparsers.add_parser("summaries", help="List channel summaries")
    summaries_parser.add_argument("-n", "--limit", type=int, default=10, help="Number of summaries to show")
    summaries_parser.add_argument("-c", "--channel", type=str, help="Filter by channel name")
    summaries_parser.add_argument("-d", "--date", type=str, help="Filter by date (YYYY-MM-DD)")

    # View summary command
    view_parser = subparsers.add_parser("view-summary", help="View a specific channel summary")
    view_parser.add_argument("id", type=int, help="ID of the summary to view")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "list":
        list_recent_messages(args.limit)
    elif args.command == "stats":
        get_message_stats()
    elif args.command == "summaries":
        list_summaries(args.limit, args.channel, args.date)
    elif args.command == "view-summary":
        view_summary(args.id)

if __name__ == "__main__":
    main()
