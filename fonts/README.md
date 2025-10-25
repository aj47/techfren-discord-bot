# Fonts Directory

This directory contains local fonts used by the Discord bot for chart rendering.

## KH Interference TRIAL

**Font Family**: KH Interference TRIAL
**Designer**: Hanken Design Co.
**License**: Trial version (for testing purposes)
**Format**: OpenType (.otf)

### Files:
- `KHInterferenceTRIAL-Regular.otf` - Regular weight
- `KHInterferenceTRIAL-Light.otf` - Light weight
- `KHInterferenceTRIAL-Bold.otf` - Bold weight

### Usage:

These fonts are automatically registered when the `chart_renderer.py` module is loaded. The fonts are used for chart rendering to maintain a consistent, modern monospace aesthetic.

### Font Registration:

The fonts are registered programmatically in `chart_renderer.py` using matplotlib's font manager:

```python
import matplotlib.font_manager as fm

# Fonts are registered from this directory on module load
fm.fontManager.addfont('fonts/KHInterferenceTRIAL-Regular.otf')
```

### Why Local Fonts?

By including fonts in the project directory, we:
- **Ensure portability**: No dependency on system-installed fonts
- **Guarantee consistency**: Same rendering on all systems
- **Simplify deployment**: No need to install fonts globally
- **Support containers**: Works in Docker/containerized environments

### Fallback Fonts:

If KH Interference TRIAL fails to load, matplotlib will fall back to:
1. IBM Plex Mono
2. DejaVu Sans Mono
3. Courier New
4. System monospace

See `chart_renderer.py` line ~170 for the full font stack configuration.
