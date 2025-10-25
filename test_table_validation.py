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
    """Test the table validation with various sample tables."""

    renderer = ChartRenderer()

    # Test cases that should pass
    test_tables = [
        # Original sample table
        """| Month    | Savings ($) | Percentage (%) |
| -------- | ----------- | -------------- |
| January  | $250        | 50.0           |
| February | $100        | 20.0           |
| March    | $150        | 30.0           |""",

        # Table with different currency formats
        """| Product | Price | Quantity |
| ------- | ----- | -------- |
| Apple   | $1.50 | 10       |
| Banana  | $0.80 | 15       |
| Orange  | $2.00 | 8        |""",

        # Table with percentages and numbers
        """| Category | Sales | Growth |
| -------- | ----- | ------ |
| Q1       | 1000  | 15%    |
| Q2       | 1200  | 20%    |
| Q3       | 1150  | 12%    |""",

        # Table that should fail (generic headers)
        """| Item | Value | Data |
| ---- | ----- | ---- |
| A    | 1     | x    |
| B    | 2     | y    |""",

        # Table that should fail (no numeric data)
        """| Name | Description | Status |
| ---- | ----------- | ------ |
| Test | Some text  | Active |"""
    ]

    for i, table in enumerate(test_tables, 1):
        print(f"\n{'='*60}")
        print(f"TEST CASE {i}:")
        print(f"{'='*60}")
        print(table)
        print(f"{'-'*60}")

        result = renderer._is_valid_data_table(table)
        print(f"Validation result: {'✅ PASSED' if result else '❌ FAILED'}")

if __name__ == "__main__":
    test_table_validation()