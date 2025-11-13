#!/usr/bin/env python3
"""
Simple launcher for the Discord bot debug CLI.
Run this to start debugging your bot via command line.
"""

import sys
import os

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import and run the debug CLI
from debug_cli import main
import asyncio

if __name__ == "__main__":
    print("🚀 Starting Discord Bot Debug CLI...")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Debug session ended.")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Error starting debug CLI: {e}")
        sys.exit(1)
