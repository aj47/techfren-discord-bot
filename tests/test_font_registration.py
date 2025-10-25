#!/usr/bin/env python3
"""
Test script to verify that local fonts are properly registered.

Run this script to check if the KH Interference TRIAL fonts are loaded:
    python3 test_font_registration.py

Expected output:
    ✅ Found 3 KH Interference fonts
    - Font: KH Interference TRIAL (Bold)
    - Font: KH Interference TRIAL (Light)
    - Font: KH Interference TRIAL (Regular)
"""

import sys
import os

# Add the current directory to the path so we can import chart_renderer
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_font_registration():
    """Test that fonts are registered correctly."""
    print("Testing font registration...")
    print("-" * 50)

    try:
        # Import chart_renderer which registers fonts on load
        import chart_renderer
        print("✅ chart_renderer module loaded successfully")
    except Exception as e:
        print(f"❌ Failed to load chart_renderer: {e}")
        return False

    try:
        import matplotlib.font_manager as fm
        print("✅ matplotlib.font_manager imported")
    except Exception as e:
        print(f"❌ Failed to import matplotlib.font_manager: {e}")
        return False

    # Find all fonts with 'KH' or 'Interference' in the name
    kh_fonts = [
        f for f in fm.fontManager.ttflist
        if 'KH' in f.name or 'Interference' in f.name
    ]

    if not kh_fonts:
        print("❌ No KH Interference fonts found!")
        print("\nTroubleshooting:")
        print("1. Check that fonts/ directory exists")
        print("2. Verify .otf files are in fonts/ directory")
        print("3. Check chart_renderer.py logs for registration errors")
        return False

    print(f"\n✅ Found {len(kh_fonts)} KH Interference font variant(s):")
    print("-" * 50)

    for font in kh_fonts:
        style = font.style if hasattr(font, 'style') else 'Unknown'
        weight = font.weight if hasattr(font, 'weight') else 'Unknown'
        print(f"  • Name: {font.name}")
        print(f"    Style: {style}, Weight: {weight}")
        print(f"    File: {os.path.basename(font.fname)}")
        print()

    # Verify the fonts directory
    fonts_dir = os.path.join(os.path.dirname(__file__), 'fonts')
    print(f"Fonts directory: {fonts_dir}")

    if os.path.exists(fonts_dir):
        font_files = [f for f in os.listdir(fonts_dir) if f.endswith(('.otf', '.ttf'))]
        print(f"✅ Found {len(font_files)} font file(s) in fonts/ directory:")
        for font_file in sorted(font_files):
            print(f"  • {font_file}")
    else:
        print("❌ Fonts directory not found!")
        return False

    print("\n" + "=" * 50)
    print("✅ Font registration test PASSED!")
    print("=" * 50)
    return True


if __name__ == "__main__":
    success = test_font_registration()
    sys.exit(0 if success else 1)
