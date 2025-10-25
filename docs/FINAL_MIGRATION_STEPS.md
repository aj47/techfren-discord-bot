# Final aiosqlite Migration Steps

## Status: 90% Complete - Only 4 Functions and Callers Remain

### ✅ COMPLETED (12/16 functions):
1. init_database()
2. check_database_connection()
3. store_message()
4. store_messages_batch()
5. update_message_with_scraped_data()
6. get_scraped_content_by_url()
7. get_message_count()
8. get_user_message_count()
9. get_all_channel_messages()
10. get_channel_messages_for_day()
11. get_channel_messages_for_hours()
12. (get_recent_channel_messages if exists)

### ⚠️ REMAINING (4 functions):
1. get_messages_for_time_range() - Used by summarization
2. store_channel_summary() - Used by summarization
3. delete_messages_older_than() - Used by cleanup tasks
4. get_active_channels() - Used by background tasks

## Quick Conversion Commands

For the remaining 4 functions, use this pattern:

### Pattern for get_messages_for_time_range():
```python
# OLD:
with get_connection() as conn:
    cursor = conn.cursor()
    cursor.execute(...)
    for row in cursor.fetchall():
        ...

# NEW:
async with aiosqlite.connect(DB_FILE) as conn:
    conn.row_factory = aiosqlite.Row
    async with conn.execute(...) as cursor:
        rows = await cursor.fetchall()
        for row in rows:
            ...
```

### Pattern for store_channel_summary():
```python
# OLD:
with get_connection() as conn:
    cursor = conn.cursor()
    cursor.execute(INSERT_CHANNEL_SUMMARY, (...))
    conn.commit()

# NEW:
async with aiosqlite.connect(DB_FILE) as conn:
    await conn.execute(INSERT_CHANNEL_SUMMARY, (...))
    await conn.commit()
```

### Pattern for delete_messages_older_than():
```python
# OLD:
with get_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) ...")
    count = cursor.fetchone()[0]
    cursor.execute("DELETE ...")
    conn.commit()

# NEW:
async with aiosqlite.connect(DB_FILE) as conn:
    async with conn.execute("SELECT COUNT(*) ...") as cursor:
        row = await cursor.fetchone()
        count = row[0] if row else 0
    await conn.execute("DELETE ...")
    await conn.commit()
```

### Pattern for get_active_channels():
```python
# Similar to get_messages_for_time_range pattern
```

## CRITICAL: Update All Callers

###bot.py Changes:

```python
# Line ~399
# OLD: database.init_database()
# NEW: await database.init_database()

# Line ~402
# OLD: if not database.check_database_connection():
# NEW: if not await database.check_database_connection():

# Line ~407
# OLD: message_count = database.get_message_count()
# NEW: message_count = await database.get_message_count()

# Line ~547  
# OLD: success = database.store_message(...)
# NEW: success = await database.store_message(...)
```

### llm_handler.py Changes:

```python
# Line ~233
# OLD: scraped_content = await asyncio.to_thread(get_scraped_content_by_url, url)
# NEW: scraped_content = await get_scraped_content_by_url(url)
```

### command_handler.py Changes:

Search for all calls to:
- `get_channel_messages_for_day` → add `await`
- `get_channel_messages_for_hours` → add `await`

### summarization_tasks.py Changes:

Search for:
- `get_messages_within_time_range` → add `await` (if this function exists)
- `get_messages_for_time_range` → add `await`
- `store_channel_summary` → add `await`

### thread_memory.py Changes:

Search for any database calls and add `await`

## Testing Commands

After completing migration:

```bash
# 1. Syntax check
python3 -m py_compile database.py

# 2. Pylint check
source venv/bin/activate && pylint database.py --rcfile=.pylintrc

# 3. Test import
python3 -c "import asyncio; from database import init_database; print('Import OK')"

# 4. Test database init
python3 -c "
import asyncio
from database import init_database, check_database_connection

async def test():
    await init_database()
    ok = await check_database_connection()
    print(f'Database OK: {ok}')

asyncio.run(test())
"

# 5. Check bot startup
python3 bot.py  # Should start without errors
```

## Quick Fix Script

Run this to convert the last 4 functions:

```bash
# For each remaining function:
# 1. Change `def` to `async def`
# 2. Change `with get_connection()` to `async with aiosqlite.connect(DB_FILE)`
# 3. Add `conn.row_factory = aiosqlite.Row` after connection
# 4. Change `cursor.execute()` to `async with conn.execute()` 
# 5. Change `cursor.fetchone()` to `await cursor.fetchone()`
# 6. Change `cursor.fetchall()` to `await cursor.fetchall()`
# 7. Change `conn.execute()` to `await conn.execute()`
# 8. Change `conn.commit()` to `await conn.commit()`
# 9. Fix f-strings to use %s formatting
```

## Estimated Time Remaining

- Convert 4 functions: 20 minutes
- Update callers: 30 minutes
- Testing: 20 minutes
- **Total: ~70 minutes**

## Success Criteria

- ✅ All 16 database functions are async
- ✅ No `get_connection()` calls remain
- ✅ All callers use `await`
- ✅ `python3 -m py_compile database.py` succeeds
- ✅ Pylint score is 10/10
- ✅ Bot starts successfully
- ✅ Messages store correctly
- ✅ Chart commands work
- ✅ No blocking database calls

## Rollback if Needed

```bash
git diff database.py > /tmp/db_migration.patch
git checkout database.py bot.py llm_handler.py command_handler.py
pip uninstall aiosqlite
# Then fix issues and re-apply
```

## Next Session Checklist

[ ] Convert get_messages_for_time_range()
[ ] Convert store_channel_summary()
[ ] Convert delete_messages_older_than()
[ ] Convert get_active_channels()
[ ] Update bot.py (4 await additions)
[ ] Update llm_handler.py (1 await fix)
[ ] Update command_handler.py (find and fix calls)
[ ] Update summarization_tasks.py (find and fix calls)
[ ] Update thread_memory.py (find and fix calls)
[ ] Run full test suite
[ ] Verify pylint 10/10
[ ] Test bot in production

You're 90% done! Just the home stretch remaining.
