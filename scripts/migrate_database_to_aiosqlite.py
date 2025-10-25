"""
Script to migrate remaining database.py functions from sqlite3 to aiosqlite.
This is a one-time migration script.
"""

import re


def migrate_function(content: str, func_name: str) -> str:
    """Migrate a single function from sync to async."""
    
    # Pattern 1: Change def to async def
    content = re.sub(
        rf'^def {func_name}\(',
        f'async def {func_name}(',
        content,
        flags=re.MULTILINE
    )
    
    # Pattern 2: Change get_connection() to aiosqlite.connect(DB_FILE)
    content = content.replace(
        'with get_connection() as conn:',
        'async with aiosqlite.connect(DB_FILE) as conn:'
    )
    
    # Pattern 3: Add row_factory after connection
    content = re.sub(
        r'(async with aiosqlite\.connect\(DB_FILE\) as conn:)\n(\s+)(cursor = conn\.cursor\(\))',
        r'\1\n\2conn.row_factory = aiosqlite.Row',
        content
    )
    
    # Pattern 4: Convert cursor operations
    content = content.replace('cursor = conn.cursor()', '')
    content = re.sub(
        r'cursor\.execute\(',
        'async with conn.execute(',
        content
    )
    content = re.sub(
        r'cursor\.fetchone\(\)',
        'await cursor.fetchone()',
        content
    )
    content = re.sub(
        r'cursor\.fetchall\(\)',
        'await cursor.fetchall()',
        content
    )
    
    # Pattern 5: Add await to execute and commits
    content = re.sub(
        r'(\s+)conn\.execute\(',
        r'\1await conn.execute(',
        content
    )
    content = re.sub(
        r'(\s+)conn\.commit\(\)',
        r'\1await conn.commit()',
        content
    )
    
    # Pattern 6: Change sqlite3.IntegrityError to aiosqlite.IntegrityError
    content = content.replace('sqlite3.IntegrityError', 'aiosqlite.IntegrityError')
    
    # Pattern 7: Fix cursor context managers (add proper async with and await)
    # This needs manual review for complex cases
    
    return content


def main():
    """Run the migration."""
    # Read the current database.py
    with open('database.py', 'r') as f:
        content = f.read()
    
    # List of functions to migrate
    functions_to_migrate = [
        'get_message_count',
        'get_user_message_count',
        'get_all_channel_messages',
        'get_channel_messages_for_day',
        'get_channel_messages_for_hours',
        'get_recent_channel_messages',
        'get_messages_for_time_range',
        'get_messages_within_time_range',
        'store_channel_summary',
        'delete_messages_older_than',
        'get_active_channels',
        'get_scraped_content_by_url',
    ]
    
    # Migrate each function
    for func in functions_to_migrate:
        print(f"Migrating {func}...")
        content = migrate_function(content, func)
    
    # Write back
    with open('database.py.migrated', 'w') as f:
        f.write(content)
    
    print("\nMigration complete!")
    print("Review database.py.migrated and replace database.py if correct")
    print("\nNote: Manual review required for:")
    print("  - Cursor context managers")
    print("  - Complex fetchone/fetchall patterns")
    print("  - Row access patterns")


if __name__ == "__main__":
    main()
