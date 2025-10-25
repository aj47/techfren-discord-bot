# aiosqlite Migration Plan

## Overview
Migrating from `sqlite3` (blocking) to `aiosqlite` (async) for proper async database operations.

## Benefits
- ✅ Non-blocking database I/O
- ✅ Better performance under load
- ✅ Proper async/await pattern throughout
- ✅ No event loop blocking

## Migration Strategy

### Phase 1: Core Infrastructure (Priority: CRITICAL)
- [x] Add `aiosqlite` to requirements.txt
- [x] Install aiosqlite
- [ ] Update `init_database()` → `async def init_database()`
- [ ] Update `get_connection()` → Remove (use `aiosqlite.connect()` directly)
- [ ] Update `check_database_connection()` → `async def check_database_connection()`

### Phase 2: Core Database Functions (Priority: HIGH)
- [ ] `store_message()` → `async def store_message()`
- [ ] `store_messages_batch()` → Already async, update internals
- [ ] `update_message_with_scraped_content()` → `async def update_message_with_scraped_content()`
- [ ] `get_message_count()` → `async def get_message_count()`
- [ ] `get_user_message_count()` → `async def get_user_message_count()`

### Phase 3: Query Functions (Priority: HIGH)
- [ ] `get_all_channel_messages()` → `async def get_all_channel_messages()`
- [ ] `get_recent_channel_messages()` → `async def get_recent_channel_messages()`
- [ ] `get_messages_within_time_range()` → `async def get_messages_within_time_range()`
- [ ] `get_active_channels()` → `async def get_active_channels()`
- [ ] `get_scraped_content_by_url()` → `async def get_scraped_content_by_url()`

### Phase 4: Summary Functions (Priority: MEDIUM)
- [ ] `store_channel_summary()` → `async def store_channel_summary()`
- [ ] `delete_messages_older_than()` → `async def delete_messages_older_than()`

### Phase 5: Update Callers (Priority: CRITICAL)
- [ ] bot.py - Update all database calls to use `await`
- [ ] command_handler.py - Update all database calls
- [ ] llm_handler.py - Update `get_scraped_content_by_url` calls
- [ ] thread_memory.py - Update all database calls
- [ ] summarization_tasks.py - Update all database calls

### Phase 6: Utility Files (Priority: LOW)
- [ ] db_utils.py - Update or mark as deprecated
- [ ] db_migration.py - Update migration functions

## Key Changes

### Pattern 1: Connection Management

**OLD (sqlite3):**
```python
def some_function():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM messages")
        return cursor.fetchall()
```

**NEW (aiosqlite):**
```python
async def some_function():
    async with aiosqlite.connect(DB_FILE) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM messages") as cursor:
            return await cursor.fetchall()
```

### Pattern 2: Execute and Fetch

**OLD:**
```python
cursor.execute("SELECT * FROM messages WHERE id = ?", (msg_id,))
row = cursor.fetchone()
```

**NEW:**
```python
async with conn.execute("SELECT * FROM messages WHERE id = ?", (msg_id,)) as cursor:
    row = await cursor.fetchone()
```

### Pattern 3: Insert/Update

**OLD:**
```python
cursor.execute("INSERT INTO messages VALUES (?, ?)", (id, content))
conn.commit()
```

**NEW:**
```python
await conn.execute("INSERT INTO messages VALUES (?, ?)", (id, content))
await conn.commit()
```

### Pattern 4: Exception Handling

**OLD:**
```python
except sqlite3.IntegrityError:
    pass
```

**NEW:**
```python
except aiosqlite.IntegrityError:
    pass
```

## Testing Plan

After each phase:
1. Run syntax check: `python3 -m py_compile database.py`
2. Run pylint: `pylint database.py --rcfile=.pylintrc`
3. Test database init: `python3 -c "import asyncio; from database import init_database; asyncio.run(init_database())"`
4. Test bot startup
5. Test message storage
6. Test queries

## Rollback Plan

If issues occur:
1. Git stash changes: `git stash`
2. Revert to sqlite3
3. Debug offline
4. Re-apply with fixes

## Estimated Time

- Phase 1-2: 30 minutes
- Phase 3-4: 30 minutes
- Phase 5: 45 minutes (many callers)
- Phase 6: 15 minutes
- Testing: 30 minutes
- **Total: ~2.5 hours**

## Breaking Changes

⚠️ **All database functions become async!**

Before:
```python
count = get_message_count()
```

After:
```python
count = await get_message_count()
```

Every caller must be updated to use `await`.

## Files Affected

### Core Files (Must Update):
- `database.py` - Main database module
- `bot.py` - Bot initialization and message handling
- `command_handler.py` - Command processing
- `llm_handler.py` - LLM API calls with database lookups
- `thread_memory.py` - Thread memory storage

### Utility Files (Can Update Later):
- `db_utils.py` - Database utilities
- `db_migration.py` - Migration scripts
- `summarization_tasks.py` - Background tasks

### Test Files (Update If Running Tests):
- All test files using database functions

## Success Criteria

- ✅ All database operations are async
- ✅ No blocking `sqlite3` calls remain
- ✅ Bot starts successfully
- ✅ Messages store correctly
- ✅ Queries work correctly
- ✅ Pylint score remains 10/10
- ✅ No performance regression
- ✅ No data loss

## Notes

- aiosqlite is a wrapper around sqlite3, not a replacement
- Same SQL syntax and features
- Thread-safe like sqlite3
- Compatible with existing database file
- No data migration needed!
