# Deployment Checklist - October 24, 2025

## Pre-Deployment Checks

### 1. Verify Dependencies
```bash
# Check if new packages are installed
python -c "import seaborn; import matplotlib; import pandas; print('✅ All packages available')"

# Check versions
pip list | grep -E "(seaborn|matplotlib|pandas)"
```

**Expected Output**:
```
matplotlib    3.10.7
pandas        2.3.3
seaborn       0.13.2
```

### 2. Review Code Changes
```bash
# Check modified files
git status

# Review chart renderer changes
git diff chart_renderer.py | head -50

# Review command_abstraction changes  
git diff command_abstraction.py | head -50
```

### 3. Run Quick Tests

#### Test Chart Generation
```bash
python3 << 'EOF'
from chart_renderer import ChartRenderer

renderer = ChartRenderer()
content = """
| Product | Sales |
|---------|-------|
| A       | 100   |
| B       | 200   |
"""

_, charts = renderer.extract_tables_for_rendering(content)
print(f"✅ Generated {len(charts)} chart(s)")
assert len(charts) == 1
assert charts[0]['file'] is not None
print(f"✅ Chart file size: {len(charts[0]['file'].getvalue())} bytes")
EOF
```

**Expected**: Chart generated successfully with file size ~30-50KB

#### Test Integration
```bash
python3 << 'EOF'
from discord_formatter import DiscordFormatter

content = """
| User | Count |
|------|-------|
| A    | 10    |
| B    | 20    |
"""

formatted, charts = DiscordFormatter.format_llm_response(content)
print(f"✅ Extracted {len(charts)} chart(s)")
print(f"✅ Placeholder found: {'[Chart 1:' in formatted}")
EOF
```

**Expected**: 1 chart extracted, placeholder in formatted content

---

## Deployment Steps

### Step 1: Backup Current Version
```bash
# In case rollback is needed
cp -r /path/to/bot /path/to/bot.backup.$(date +%Y%m%d)
```

### Step 2: Install Dependencies
```bash
# Activate virtual environment
source venv/bin/activate  # or: venv/bin/activate

# Install new packages
pip install seaborn matplotlib pandas

# Remove old package (optional, won't break anything if left)
pip uninstall quickchart-io -y
```

### Step 3: Update Code
```bash
# Pull latest changes or copy files
git pull  # or manually copy updated files

# Verify main files exist
ls -lh chart_renderer.py command_abstraction.py discord_formatter.py requirements.txt
```

### Step 4: Restart Bot
```bash
# Stop current bot process
# Method depends on your setup:
# - systemctl stop bot
# - pkill -f bot.py
# - supervisorctl stop bot
# etc.

# Start bot with new code
# - systemctl start bot  
# - python bot.py
# - supervisorctl start bot
# etc.
```

---

## Post-Deployment Verification

### 1. Check Bot Startup
Monitor logs for errors:
```bash
# Replace with your log location
tail -f bot.log

# Or systemd logs:
journalctl -u bot -f
```

**Look for**:
- ✅ Bot connected successfully
- ❌ No import errors for seaborn/matplotlib/pandas
- ❌ No chart_renderer errors

### 2. Test Chart Generation

Send a test message in Discord:
```
@bot analyze this data:

| Product | Sales |
|---------|-------|  
| Widget  | 150   |
| Gadget  | 230   |
| Doohickey | 180 |
```

**Expected**:
- Bot responds with analysis
- Chart image attached to message
- Chart looks professional (Seaborn styling)

**Check Logs**:
```
INFO - Found 1 markdown table(s) in response
INFO - Generated bar chart for table 1
INFO - Prepared chart 1: bar
```

### 3. Test Thread Handling

#### Test 3a: Normal Message
```
@bot hello
```

**Expected**:
- Bot creates ONE thread
- No duplicate threads

**Check Logs**:
```
INFO - Creating bot thread
INFO - ✅ PATH 3: Created bot thread 'Bot Response - Username'
```

#### Test 3b: Message with Attachment
```
@bot what's in this image? [attach image]
```

**Expected**:
- Discord may auto-create thread OR bot creates thread
- Only ONE thread exists
- No duplicate threads

**Check Logs** (one of these):
```
# If Discord created it:
INFO - ✅ PATH 2: Found Discord auto-thread

# If bot created it:
INFO - ✅ PATH 3: Created bot thread

# Should NOT see:
INFO - Message already has a thread, creating standalone thread  ❌ (old behavior)

# Should see instead:
INFO - Successfully fetched existing thread  ✅ (new behavior)
```

### 4. Monitor for Issues

Watch logs for 10-15 minutes:
```bash
tail -f bot.log | grep -E "(ERROR|WARNING|chart|thread)"
```

**Green flags** ✅:
- "Generated [type] chart for table X"
- "Prepared chart X: [type]"
- "Successfully fetched existing thread"
- "Created bot thread" (singular, not duplicate)

**Red flags** ❌:
- "Error generating chart"
- "Failed to download chart" (shouldn't happen with local files)
- Multiple "Created bot thread" for same message
- Import errors for seaborn/matplotlib

---

## Rollback Procedure

### If Charts Break

1. **Quick Fix**: Restore old chart renderer
   ```bash
   cd /path/to/bot
   mv chart_renderer_old.py.bak chart_renderer.py
   systemctl restart bot
   ```

2. **Full Rollback**:
   ```bash
   cd /path/to/bot
   git checkout HEAD~1 chart_renderer.py requirements.txt
   pip uninstall seaborn matplotlib pandas -y
   pip install quickchart-io
   systemctl restart bot
   ```

### If Threads Break

1. **Quick Fix**: Revert command_abstraction.py
   ```bash
   git checkout HEAD~1 command_abstraction.py
   systemctl restart bot
   ```

### If Everything Breaks

```bash
# Restore full backup
systemctl stop bot
rm -rf /path/to/bot
mv /path/to/bot.backup.YYYYMMDD /path/to/bot
systemctl start bot
```

---

## Success Criteria

### ✅ Deployment is successful if:

1. **Bot starts without errors**
   - No import errors
   - Connects to Discord

2. **Charts work**
   - Tables in LLM responses generate charts
   - Charts are embedded in Discord messages
   - Charts look professional

3. **Threads work correctly**
   - Only ONE thread created per message
   - Existing threads are reused
   - No duplicate threads

4. **Performance is acceptable**
   - Chart generation < 1 second
   - No timeout errors
   - Memory usage stable

### ❌ Rollback if:

1. Bot crashes on startup
2. Chart generation consistently fails
3. Multiple duplicate threads appear
4. Memory usage increases significantly
5. Response times are much slower

---

## Support Information

### Logs to Collect for Issues

```bash
# Recent logs
tail -n 500 bot.log > issue_logs.txt

# Chart-related logs
grep -A 5 "chart" bot.log > chart_logs.txt

# Thread-related logs
grep -A 5 "thread" bot.log > thread_logs.txt

# Error logs
grep -E "(ERROR|CRITICAL)" bot.log > error_logs.txt
```

### Key Files to Check

1. `chart_renderer.py` - Chart generation
2. `command_abstraction.py` - Thread handling  
3. `requirements.txt` - Dependencies
4. `bot.log` - Runtime logs

### Documentation

- `SEABORN_MIGRATION.md` - Chart migration details
- `DUPLICATE_THREAD_FIX_V2.md` - Thread fix details
- `SESSION_SUMMARY_2025_10_24.md` - Complete overview

---

## Timeline Estimate

- **Pre-deployment checks**: 5-10 minutes
- **Deployment**: 5-10 minutes
- **Post-deployment verification**: 15-20 minutes
- **Total**: 25-40 minutes

## Risk Assessment

- **Overall Risk**: Low
- **Rollback Difficulty**: Easy (backed up files)
- **Impact of Failure**: Low (bot can be quickly restored)
- **Testing Coverage**: High (multiple tests created)

---

## Sign-off

- [ ] Pre-deployment checks completed
- [ ] Backup created
- [ ] Dependencies installed
- [ ] Code deployed
- [ ] Bot restarted successfully
- [ ] Charts tested and working
- [ ] Threads tested and working
- [ ] Logs monitored for 15+ minutes
- [ ] No errors or warnings
- [ ] Deployment successful ✅

**Deployed by**: _____________  
**Date**: _____________  
**Time**: _____________  
