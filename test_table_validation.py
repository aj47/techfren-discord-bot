#!/usr/bin/env python3
"""
Test script to debug table validation issues.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from chart_renderer import ChartRenderer
import logging

# Set up logging to see debug messages
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')

def test_table_validation():
    """Test the table validation with a sample table."""

    renderer = ChartRenderer()

    # Sample table similar to the one that failed
    sample_table = """| Month    | Savings ($) | Percentage (%) |
| -------- | ----------- | -------------- |
| January  | $250        | 50.0           |
| February | $100        | 20.0           |
| March    | $150        | 30.0           |"""

    print("Testing table validation with sample data:")
    print("=" * 50)
    print("Sample table:")
    print(sample_table)
    print("=" * 50)

    result = renderer._is_valid_data_table(sample_table)
    print(f"\nValidation result: {'PASSED' if result else 'FAILED'}")

if __name__ == "__main__":
    test_table_validation()