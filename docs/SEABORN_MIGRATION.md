# Seaborn Chart Renderer Migration

## Summary

Successfully migrated the chart rendering system from QuickChart.io API to Seaborn's Objects interface for local chart generation.

## Changes Made

### 1. Package Dependencies
- **Removed**: `quickchart-io`
- **Added**: `seaborn`, `matplotlib`, `pandas`
- Updated `requirements.txt` with new dependencies

### 2. Chart Renderer (`chart_renderer.py`)

#### Previous Implementation (QuickChart)
- Generated Chart.js configuration JSON
- Used QuickChart.io API to render charts
- Returned chart URLs that needed to be downloaded

#### New Implementation (Seaborn)
```python
# Key changes:
- Uses Seaborn Objects interface (so.Plot)
- Generates charts locally using matplotlib backend
- Returns BytesIO objects containing PNG images
- No external API dependency
```

#### Chart Types Supported
1. **Bar Charts**: Using `so.Bar()` mark
2. **Pie Charts**: Using matplotlib's `ax.pie()` (Seaborn doesn't have pie charts)
3. **Line Charts**: Using `so.Line()` and `so.Dot()` marks

#### Example Usage
```python
# Bar chart with Seaborn Objects
df = pd.DataFrame({'Category': labels, 'Value': values})
fig, ax = plt.subplots(figsize=(10, 6))
(
    so.Plot(df, x='Category', y='Value')
    .add(so.Bar(), so.Agg())
    .label(title=title)
    .on(ax)
    .plot()
)
```

### 3. Command Abstraction (`command_abstraction.py`)

#### Changed Methods
- `_download_chart_files()`: No longer downloads from URLs
  - Now extracts BytesIO data from chart_data
  - Creates Discord File objects directly from memory

#### Before:
```python
async def _download_chart_files(self, chart_data: List[Dict]) -> List[discord.File]:
    # Downloaded images from chart URLs using aiohttp
    chart_url = chart.get("url")
    async with session.get(chart_url) as response:
        image_data = await response.read()
```

#### After:
```python
async def _download_chart_files(self, chart_data: List[Dict]) -> List[discord.File]:
    # Extracts image data from BytesIO objects
    chart_file = chart.get("file")
    image_file = io.BytesIO(chart_file.getvalue())
```

### 4. Discord Formatter (`discord_formatter.py`)
- Updated import from `chart_renderer_seaborn` to `chart_renderer`
- Updated documentation to reflect 'file' key instead of 'url' key

## Benefits

1. **No External Dependencies**: Charts are generated locally without API calls
2. **Better Performance**: No network latency for chart generation
3. **More Control**: Full customization of chart appearance and styling
4. **Cost Savings**: No API rate limits or costs
5. **Privacy**: Data never leaves the server

## Testing

Created comprehensive tests:
- `test_seaborn_charts.py`: Unit tests for bar, pie, and line charts
- `test_save_chart.py`: Visual verification of generated charts
- `test_integration_seaborn.py`: Integration test with discord_formatter

### Test Results
```
✅ Bar chart generation: PASSED
✅ Pie chart generation: PASSED  
✅ Line chart generation: PASSED
✅ Integration with discord_formatter: PASSED
✅ File sizes: 35-60 KB per chart (reasonable)
```

## API Changes

### Chart Data Structure

#### Before:
```python
{
    "url": "https://quickchart.io/chart?...",
    "type": "bar",
    "placeholder": "[Chart 1: Bar]",
    "original_table": "| ... |"
}
```

#### After:
```python
{
    "file": <BytesIO object>,  # Contains PNG image data
    "type": "bar",
    "placeholder": "[Chart 1: Bar]",
    "original_table": "| ... |"
}
```

## Backward Compatibility

The external API remains the same:
```python
# Still works the same way
from chart_renderer import extract_tables_for_rendering
cleaned_content, chart_data = extract_tables_for_rendering(content)
```

## Files Modified

1. `chart_renderer.py` - Complete rewrite using Seaborn
2. `command_abstraction.py` - Updated `_download_chart_files()` method (2 occurrences)
3. `discord_formatter.py` - Updated documentation
4. `requirements.txt` - Updated dependencies

## Files Backed Up

- `chart_renderer_old.py.bak` - Original QuickChart implementation

## Configuration

### Matplotlib Backend
Set to 'Agg' (non-interactive) for server environments:
```python
import matplotlib.pyplot as plt
plt.switch_backend('Agg')
```

### Seaborn Theme
Default theme set to 'whitegrid':
```python
sns.set_theme(style="whitegrid")
```

## Future Enhancements

Potential improvements for the Seaborn implementation:

1. **Additional Chart Types**
   - Scatter plots using `so.Dot()`
   - Box plots using matplotlib
   - Violin plots using seaborn function interface

2. **Customization Options**
   - Color palettes based on content theme
   - Font size adjustments for different data sizes
   - Legend positioning optimization

3. **Performance Optimization**
   - Cache frequently generated charts
   - Async chart generation for multiple charts

4. **Enhanced Styling**
   - Custom color schemes matching Discord theme
   - Better label rotation and formatting
   - Dynamic sizing based on data volume

## Notes

- Chart generation is synchronous but fast (< 1 second per chart)
- PNG format chosen for best compatibility with Discord
- DPI set to 150 for good quality without excessive file size
- Figures are properly closed to prevent memory leaks

## Migration Date

2025-10-25
