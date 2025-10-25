# Local Fonts Setup - KH Interference TRIAL

## Summary

Migrated the KH Interference TRIAL font from system-wide installation (`~/.fonts`) to a local project directory (`./fonts`). This makes the project self-contained and portable.

## Problem

Previously, the bot depended on the KH Interference TRIAL font being installed globally in `~/.fonts/`. This meant:
- ❌ Required manual font installation on every deployment
- ❌ Not portable (wouldn't work on new systems without setup)
- ❌ Difficult to containerize (Docker would need font installation steps)
- ❌ Inconsistent between development and production environments

## Solution

**Bundled the fonts directly in the project:**
- ✅ Fonts stored in `./fonts/` directory
- ✅ Automatically registered when chart_renderer.py loads
- ✅ No system-level installation required
- ✅ Works in any environment (dev, prod, Docker)
- ✅ Fully portable and self-contained

## Changes Made

### 1. Created Fonts Directory

```bash
mkdir fonts/
```

### 2. Copied Font Files

Copied KH Interference TRIAL fonts from the existing archive:

```bash
cp "KH-Interference-TRIAL/KH Interference TRIAL/OTF/"*.otf fonts/
```

**Result**: 3 font files in `fonts/`:
- `KHInterferenceTRIAL-Regular.otf` (38 KB)
- `KHInterferenceTRIAL-Light.otf` (39 KB)
- `KHInterferenceTRIAL-Bold.otf` (40 KB)

### 3. Updated chart_renderer.py

**Added imports** (lines 9-10, 16):
```python
import os
import glob
import matplotlib.font_manager as fm
```

**Added font registration function** (lines 28-56):
```python
def _register_local_fonts():
    """Register fonts from the local fonts directory."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    fonts_dir = os.path.join(script_dir, 'fonts')

    # Find and register all .otf and .ttf files
    font_files = glob.glob(os.path.join(fonts_dir, '*.otf')) + \
                 glob.glob(os.path.join(fonts_dir, '*.ttf'))

    for font_file in font_files:
        fm.fontManager.addfont(font_file)
        logger.info("Registered local font: %s", os.path.basename(font_file))

# Register fonts on module load
_register_local_fonts()
```

**How it works:**
1. When `chart_renderer.py` is imported, `_register_local_fonts()` runs automatically
2. Finds all `.otf` and `.ttf` files in the `fonts/` directory
3. Registers them with matplotlib's font manager
4. Logs each registered font for debugging

### 4. Updated .gitignore

Added entries to ignore the old font archive:
```gitignore
# Font archive files (fonts are in fonts/ directory now)
KH-Interference-TRIAL/
KH-Interference-TRIAL.zip
*.zip:Zone.Identifier
```

This keeps the repository clean while preserving the actual font files in `fonts/`.

### 5. Created Documentation

- `fonts/README.md`: Explains the fonts and their usage
- `LOCAL_FONTS_SETUP.md`: This file documenting the migration

## Testing

### Verify Font Registration

Check that fonts are registered when the module loads:

```python
python3 -c "import chart_renderer; import matplotlib.font_manager as fm; print([f.name for f in fm.fontManager.ttflist if 'KH' in f.name])"
```

**Expected output:**
```
['KH Interference TRIAL', 'KH Interference TRIAL', 'KH Interference TRIAL']
```

### Verify in Logs

When the bot starts, you should see in logs:
```
INFO - Registered local font: KHInterferenceTRIAL-Regular.otf
INFO - Registered local font: KHInterferenceTRIAL-Light.otf
INFO - Registered local font: KHInterferenceTRIAL-Bold.otf
INFO - Registered 3 local font(s) from /path/to/project/fonts
```

### Test Chart Generation

Generate a chart with the bot to verify the font is being used:
```
@bot /chart-day
```

The chart should render with the KH Interference TRIAL font.

## Deployment Checklist

When deploying to a new environment:

- ✅ No font installation required
- ✅ No `~/.fonts` setup needed
- ✅ No font cache refresh needed
- ✅ Just clone the repo and run!

## Directory Structure

```
techfren-discord-bot/
├── fonts/
│   ├── README.md
│   ├── KHInterferenceTRIAL-Regular.otf
│   ├── KHInterferenceTRIAL-Light.otf
│   └── KHInterferenceTRIAL-Bold.otf
├── chart_renderer.py  (with font registration code)
├── .gitignore  (ignores KH-Interference-TRIAL/ archive)
└── LOCAL_FONTS_SETUP.md  (this file)
```

## Benefits

1. **Portability**: Project works on any system without font setup
2. **Containerization**: Easy to Docker-ize (no extra font installation steps)
3. **Consistency**: Same fonts everywhere (dev, prod, CI/CD)
4. **Simplicity**: One less deployment step
5. **Version Control**: Fonts are versioned with the code

## Font Stack

The chart renderer uses this font fallback order (chart_renderer.py:170):

```python
'font.monospace': [
    'KH Interference TRIAL',  # Primary (now loaded from ./fonts/)
    'IBM Plex Mono',          # Fallback 1
    'DejaVu Sans Mono',       # Fallback 2
    'Courier New',            # Fallback 3
    'monospace'               # System default
]
```

## Cleanup (Optional)

You can now safely remove the old font archive if desired:

```bash
rm -rf KH-Interference-TRIAL/
rm KH-Interference-TRIAL.zip*
```

These are already in `.gitignore`, so they won't be committed.

## Related Files

- `chart_renderer.py`: Chart rendering with font registration
- `fonts/README.md`: Font documentation
- `.gitignore`: Excludes old font archive
- `IBM_PLEX_MONO_SETUP.md`: Previous font setup documentation

## Migration Complete! ✅

The bot now uses local fonts from `./fonts/` instead of relying on system-installed fonts.
