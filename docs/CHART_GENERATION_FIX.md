# Chart Generation Fix - User Data Visualization

## Issue
When users provide data in a table format and ask "create a graph", the bot was explaining HOW to make graphs instead of actually creating them.

### Example that failed:
```
User: @bot 
| Month    | Savings |
|----------|---------|
| January  | $250    |
| February | $80     |
| March    | $420    |
create a graph something like this

Bot response: "To create a graph from your savings data, you can..."
Result: ❌ No chart generated (LLM gave instructions, didn't create table)
```

## Root Cause

The LLM was in "explainer mode" instead of "creator mode". The system prompt needed to be more explicit that:
1. The bot's job is to CREATE charts, not explain how
2. When users provide data, the bot should reformat it as a proper markdown table
3. The system automatically renders markdown tables as visual charts

## Solution

### 1. Enhanced Chart System Prompt

Added explicit instructions at the top:

```
YOUR JOB IS TO CREATE CHARTS, NOT EXPLAIN HOW:
When users provide data (in any format - table, list, text), you must:
1. Parse and understand the data
2. Create a properly formatted markdown table
3. The system will automatically render it as a visual chart
4. Add brief analysis below the table

DO NOT explain how to make charts - YOU make the chart by creating the table!
```

### 2. Added Example Section

Included a concrete example in the prompt:

```
EXAMPLE - User provides data:
User: "| Month | Savings | | Jan | $250 | | Feb | $80 |"
You MUST respond with: "Here's your savings visualization:

| Month    | Savings |
| -------- | ------- |
| January  | $250    |
| February | $80     |
| March    | $420    |

Your savings show a strong recovery in March after a dip in February."
```

### 3. Improved Chart Detection

Enhanced `_should_use_chart_system()` to:
- Detect table data in user input with regex: `\|.+\|.*\n\|[-:\s|]+\|`
- Added more chart-related keywords: "plot", "visualize", "visualization", "compare"
- Added more chart phrases: "create a graph", "make a chart", "generate a graph", "visualize this"

```python
# Now detects table data automatically
has_table_data = bool(re.search(r'\|.+\|.*\n\|[-:\s|]+\|', query + full_content))
if has_table_data:
    logger.info("Detected table data in query/content, using chart system")
    return True
```

### 4. Clarified Regular Mode Behavior

Updated regular system prompt to redirect users:

```
IF USER PROVIDES DATA TO VISUALIZE:
When users send you raw data and ask to "create a graph" or "make a chart":
  → Tell them: "I can help with that! Please use the mention with chart context, 
     or try the `/chart-day` or `/chart-hr` commands which are optimized for 
     data visualization..."
```

## Expected Behavior Now

### Scenario 1: User mentions bot with data
```
User: @bot 
| Month    | Savings |
|----------|---------|
| January  | $250    |
| February | $80     |
| March    | $420    |
create a graph

Detection: ✓ "create a graph" phrase found → CHART MODE
Bot response: 
"Here's your savings visualization:

| Month    | Savings |
| -------- | ------- |
| January  | $250    |
| February | $80     |
| March    | $420    |

[Chart 1: Bar]"

Result: ✅ Bar chart image automatically generated and attached
```

### Scenario 2: User asks about chat data
```
User: /chart-day

Detection: force_charts=True → CHART MODE
Bot analyzes conversation data, creates table
Result: ✅ Chart automatically generated
```

### Scenario 3: Regular question
```
User: @bot how do webhooks work?

Detection: No chart keywords → REGULAR MODE
Bot explains webhooks conversationally
Result: ✅ Text response, no charts
```

## Technical Flow

```
User Message with Data
    ↓
Bot detects "create a graph" OR table data in input
    ↓
_should_use_chart_system() → True
    ↓
Uses _get_chart_analysis_system_prompt()
    ↓
LLM reads new explicit instructions
    ↓
LLM creates properly formatted markdown table
    ↓
discord_formatter.format_llm_response() extracts table
    ↓
chart_renderer.extract_tables_for_rendering() parses table
    ↓
Chart image generated and attached
    ↓
User sees beautiful chart!
```

## Files Modified

1. **llm_handler.py**:
   - `_get_chart_analysis_system_prompt()` - Added explicit chart creation instructions
   - `_should_use_chart_system()` - Added table data detection
   - `_get_regular_system_prompt()` - Added user data redirect guidance

## Testing

To verify the fix works:

1. **Test with user-provided data**:
   ```
   @bot | Product | Sales | | Widget A | 150 | | Widget B | 230 | create a graph
   ```
   Expected: Bot creates properly formatted table, chart is generated

2. **Test with text request**:
   ```
   @bot create a graph showing: apples: 10, oranges: 15, bananas: 8
   ```
   Expected: Bot parses data, creates table, chart is generated

3. **Test with conversation data**:
   ```
   /chart-day
   ```
   Expected: Bot analyzes chat, creates table, chart is generated

## Key Takeaways

1. **LLM's job changed**: From "explainer" to "creator"
2. **Table detection**: Now automatically detects when user provides table data
3. **Clear instructions**: System prompt explicitly says "CREATE, don't explain"
4. **Better keywords**: More comprehensive detection of chart requests
5. **Mode clarity**: Chart mode creates tables, regular mode redirects

The bot will now actually CREATE the visualization instead of explaining how to make one!
