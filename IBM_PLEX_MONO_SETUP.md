# IBM Plex Mono Font Setup

## Overview

All charts now use IBM Plex Mono as the primary font for:
- Titles
- Axis labels
- Value labels
- Legend text
- All other text elements

## Installation

IBM Plex Mono has been installed to the user fonts directory:

```bash
~/.fonts/
├── IBMPlexMono-Regular.otf
├── IBMPlexMono-Bold.otf
├── IBMPlexMono-Italic.otf
├── IBMPlexMono-Light.otf
├── IBMPlexMono-SemiBold.otf
└── ... (other variants)
```

### Font Source

Downloaded from: https://github.com/IBM/plex/releases/tag/v6.4.0

### Installation Commands

```bash
# Create fonts directory
mkdir -p ~/.fonts

# Download IBM Plex
cd ~/.fonts
wget https://github.com/IBM/plex/releases/download/v6.4.0/OpenType.zip

# Extract
unzip OpenType.zip
mv OpenType/IBM-Plex-Mono/*.otf .
rm -rf OpenType OpenType.zip

# Update font cache
fc-cache -f ~/.fonts
```

### Clear Matplotlib Cache

After installing new fonts, matplotlib's cache must be cleared:

```bash
rm -f ~/.cache/matplotlib/fontlist-*.json
```

## Configuration in Code

Updated `chart_renderer.py` to use IBM Plex Mono:

```python
plt.rcParams.update({
    'font.family': 'monospace',
    'font.monospace': ['IBM Plex Mono', 'DejaVu Sans Mono', 'Courier New', 'monospace'],
})
```

### Fallback Fonts

If IBM Plex Mono is not available, matplotlib will use fallbacks in order:
1. IBM Plex Mono (preferred)
2. DejaVu Sans Mono
3. Courier New
4. System default monospace

## Verification

To check if IBM Plex Mono is installed and recognized:

```bash
# Check system fonts
fc-list | grep -i "plex\|mono" | grep -i ibm

# Expected output:
# /home/user/.fonts/IBMPlexMono-Regular.otf: IBM Plex Mono:style=Regular
# ... (other variants)
```

### Python Check

```python
from matplotlib.font_manager import findSystemFonts

fonts = findSystemFonts()
ibm_fonts = [f for f in fonts if 'ibm' in f.lower() or 'plex' in f.lower()]

if ibm_fonts:
    print("✅ IBM Plex Mono found")
else:
    print("❌ IBM Plex Mono not found")
```

## Visual Characteristics

IBM Plex Mono provides:
- **Monospace**: All characters have equal width
- **Clean**: Modern, professional appearance
- **Readable**: Designed for code/data display
- **Consistent**: Works well at all sizes

### Compared to Default

**Before** (proportional font):
- Variable character widths
- Less technical appearance
- Numbers can appear cramped

**After** (IBM Plex Mono):
- Fixed character widths
- Technical, modern look
- Numbers clearly spaced
- Better alignment

## Chart Examples

All chart types now use IBM Plex Mono:

### Bar Charts
- Title: IBM Plex Mono
- X-axis labels: IBM Plex Mono
- Value labels on bars: IBM Plex Mono

### Pie Charts
- Title: IBM Plex Mono
- Slice labels: IBM Plex Mono
- Percentages: IBM Plex Mono

### Line Charts
- Title: IBM Plex Mono
- X-axis labels: IBM Plex Mono
- Legend: IBM Plex Mono

## File Changes

### Modified Files
1. `chart_renderer.py` - Added font configuration

### Font Files Added
- `~/.fonts/IBMPlexMono-*.otf` (multiple variants)

## Deployment Notes

### On New Systems

If deploying to a new system, install IBM Plex Mono:

```bash
# Install to user fonts
mkdir -p ~/.fonts
cd ~/.fonts
wget https://github.com/IBM/plex/releases/download/v6.4.0/OpenType.zip
unzip OpenType.zip
mv OpenType/IBM-Plex-Mono/*.otf .
rm -rf OpenType OpenType.zip
fc-cache -f ~/.fonts

# Clear matplotlib cache
rm -f ~/.cache/matplotlib/fontlist-*.json
```

### Docker/Container Deployment

For Docker containers, add to Dockerfile:

```dockerfile
# Install IBM Plex Mono
RUN mkdir -p /usr/share/fonts/truetype/ibm-plex && \
    wget -O /tmp/ibm-plex.zip https://github.com/IBM/plex/releases/download/v6.4.0/OpenType.zip && \
    unzip /tmp/ibm-plex.zip -d /tmp/ibm-plex && \
    cp /tmp/ibm-plex/OpenType/IBM-Plex-Mono/*.otf /usr/share/fonts/truetype/ibm-plex/ && \
    rm -rf /tmp/ibm-plex /tmp/ibm-plex.zip && \
    fc-cache -f -v
```

## Troubleshooting

### Font Not Appearing

1. **Check font is installed**:
   ```bash
   fc-list | grep -i plex
   ```

2. **Clear matplotlib cache**:
   ```bash
   rm -f ~/.cache/matplotlib/fontlist-*.json
   ```

3. **Restart Python process**:
   - Matplotlib caches fonts at startup
   - Must restart bot after font installation

4. **Check matplotlib config**:
   ```python
   import matplotlib.pyplot as plt
   print(plt.rcParams['font.monospace'])
   # Should include 'IBM Plex Mono'
   ```

### Fallback Font Being Used

If charts show a different monospace font:
- IBM Plex Mono not found by matplotlib
- Check installation location
- Verify font cache was cleared
- Restart the bot process

## License

IBM Plex is licensed under the SIL Open Font License 1.1
- Free for personal and commercial use
- Can be bundled with applications
- No restrictions on modification

Source: https://github.com/IBM/plex

## Benefits

1. **Consistency**: Matches modern technical aesthetic
2. **Readability**: Designed for code/data display
3. **Professional**: Clean, modern appearance
4. **Free**: Open source, no licensing costs
5. **Complete**: Includes all weights and styles

## Date

2025-10-24
