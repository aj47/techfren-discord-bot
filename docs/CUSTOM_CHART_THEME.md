# Custom Chart Theme - 0x96f

## Overview

Updated all chart types (bar, pie, line) to use a custom dark theme based on the 0x96f color scheme with:
- Dark background (#262427)
- Vibrant colors for data
- No y-axis on bar/line charts
- No background grids
- Clean, modern appearance

## Color Scheme

Based on the 0x96f terminal theme:

```python
COLORS = {
    'background': '#262427',    # Dark background
    'foreground': '#FCFCFA',    # White text
    'blue': '#49CAE4',          # Primary blue
    'bright_blue': '#64D2E8',   # Brighter blue
    'cyan': '#AEE8F4',          # Cyan
    'bright_cyan': '#BAEBF6',   # Bright cyan
    'green': '#BCDF59',         # Green
    'bright_green': '#C6E472',  # Bright green
    'purple': '#A093E2',        # Purple
    'bright_purple': '#AEA3E6', # Bright purple
    'red': '#FF7272',           # Red
    'bright_red': '#FF8787',    # Bright red
    'yellow': '#FFCA58',        # Yellow
    'bright_yellow': '#FFD271', # Bright yellow
}
```

### Chart Color Palette

Data is displayed using these colors in order:
1. Blue (#49CAE4)
2. Green (#BCDF59)
3. Purple (#A093E2)
4. Yellow (#FFCA58)
5. Red (#FF7272)
6. Cyan (#AEE8F4)
7. Bright Blue (#64D2E8)
8. Bright Green (#C6E472)

## Chart Styling

### Bar Charts
- **Background**: Dark (#262427)
- **Bars**: Colored with custom palette
- **Bar borders**: White outline (1.5px)
- **Y-axis**: Hidden (no axis, no ticks)
- **X-axis**: White color with 45° rotated labels
- **Value labels**: Displayed on top of each bar
- **Grid**: Completely hidden
- **Title**: White, bold, 16pt

### Pie Charts
- **Background**: Dark (#262427)
- **Slices**: Colored with custom palette
- **Labels**: White text
- **Percentages**: Dark text on colored slices (for contrast)
- **Title**: White, bold, 16pt

### Line Charts
- **Background**: Dark (#262427)
- **Lines**: Colored with custom palette (2.5px width)
- **Markers**: Circles with white outline
- **Y-axis**: Hidden (no axis, no ticks)
- **X-axis**: White color with 45° rotated labels
- **Legend**: Dark background with white border (if multiple series)
- **Grid**: Completely hidden
- **Title**: White, bold, 16pt

## Implementation Details

### Global Theme Settings

```python
def __init__(self):
    sns.set_theme(style="dark")
    plt.rcParams.update({
        'figure.facecolor': self.COLORS['background'],
        'axes.facecolor': self.COLORS['background'],
        'axes.edgecolor': self.COLORS['foreground'],
        'axes.labelcolor': self.COLORS['foreground'],
        'text.color': self.COLORS['foreground'],
        'xtick.color': self.COLORS['foreground'],
        'ytick.color': self.COLORS['foreground'],
        'grid.color': self.COLORS['background'],  # Hide grid
        'grid.alpha': 0,  # Hide grid
    })
```

### Bar Chart Specific

```python
# Remove y-axis
ax.set_yticks([])
ax.spines['left'].set_visible(False)

# Style remaining spines
ax.spines['bottom'].set_color(self.COLORS['foreground'])
ax.spines['right'].set_visible(False)
ax.spines['top'].set_visible(False)

# Add value labels on bars
for bar in bars:
    height = bar.get_height()
    ax.text(bar.get_x() + bar.get_width() / 2., height,
            f'{height:.0f}', ha='center', va='bottom',
            color=self.COLORS['foreground'])
```

### Line Chart Specific

```python
# Plot with custom styling
ax.plot(x, y, 
        color=color,
        linewidth=2.5,
        marker='o',
        markersize=8,
        markeredgecolor=self.COLORS['foreground'],
        markeredgewidth=1)

# Remove y-axis
ax.set_yticks([])
ax.spines['left'].set_visible(False)
```

### Pie Chart Specific

```python
# Style percentage labels to contrast with slice colors
wedges, texts, autotexts = ax.pie(values, ...)

for autotext in autotexts:
    autotext.set_color(self.COLORS['background'])  # Dark on light slices
    autotext.set_fontweight('bold')
```

## Changes Made

### File: `chart_renderer.py`

1. **Added color scheme constants** (lines 120-148)
   - `COLORS` dict with theme colors
   - `CHART_PALETTE` list for data colors

2. **Updated `__init__`** (lines 150-164)
   - Set dark theme
   - Configure matplotlib rcParams
   - Hide grids globally

3. **Rewrote `_generate_bar_chart`** (lines 490-538)
   - Use matplotlib directly instead of Seaborn Objects
   - Apply custom colors
   - Remove y-axis
   - Add value labels on bars

4. **Updated `_generate_pie_chart`** (lines 552-586)
   - Use custom color palette
   - Style percentage labels
   - Set dark background

5. **Rewrote `_generate_line_chart`** (lines 609-665)
   - Use matplotlib directly instead of Seaborn Objects
   - Apply custom colors per series
   - Remove y-axis
   - Style legend with custom colors

## Visual Examples

### Bar Chart Features
- ✅ Dark background (#262427)
- ✅ Colorful bars with white borders
- ✅ No y-axis or grid
- ✅ Value labels on top of bars
- ✅ Clean x-axis with rotated labels

### Pie Chart Features
- ✅ Dark background (#262427)
- ✅ Vibrant slice colors
- ✅ White labels around pie
- ✅ Bold percentages on slices
- ✅ Large, readable chart

### Line Chart Features
- ✅ Dark background (#262427)
- ✅ Thick colored lines (2.5px)
- ✅ Marker points with white outlines
- ✅ No y-axis or grid
- ✅ Legend with matching theme

## Testing

All three chart types tested successfully:

```
✅ Bar chart: 36,657 bytes (~36 KB)
✅ Pie chart: 83,458 bytes (~81 KB)
✅ Line chart: 68,717 bytes (~67 KB)
```

Charts are slightly smaller than before due to:
- No grid lines to render
- Simplified axis styling
- Optimized color usage

## Benefits

1. **Visual Consistency**: Matches the 0x96f terminal theme
2. **Better Readability**: High contrast on dark background
3. **Modern Look**: Clean, minimalist design
4. **Focus on Data**: No distracting gridlines or y-axis
5. **Value Visibility**: Direct labels on bars eliminate need for y-axis

## Integration

No changes needed in other files - the chart renderer API remains the same:

```python
from chart_renderer import extract_tables_for_rendering

cleaned_content, chart_data = extract_tables_for_rendering(content)
# chart_data[0]['file'] contains the styled chart
```

## Configuration

To modify colors, edit the `COLORS` and `CHART_PALETTE` constants in the `ChartRenderer` class.

To change styling (e.g., show y-axis), modify the chart generation methods:
- `_generate_bar_chart()`
- `_generate_pie_chart()`  
- `_generate_line_chart()`

## Rollback

If you need to revert to the previous styling:

```bash
git diff chart_renderer.py  # Review changes
git checkout HEAD~1 chart_renderer.py  # Revert if needed
```

## Date

2025-10-24
