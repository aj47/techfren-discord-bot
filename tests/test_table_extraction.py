#!/usr/bin/env python3
"""
Test the table extraction regex to ensure it captures complete tables.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from chart_renderer import ChartRenderer

def test_table_extraction():
    """Test table extraction with sample LLM responses."""

    renderer = ChartRenderer()

    # Test cases that should extract complete tables
    test_cases = [
        # Original sample response
        """Here is the pie chart data visualization based on your savings amounts:

| Month    | Savings ($) | Percentage (%) |
| -------- | ----------- | -------------- |
| January  | 251         | 33.82%         |
| February | 100         | 20.0%          |
| March    | 150         | 30.0%          |

This chart shows your savings distribution over the three months.""",

        # Response with multiple tables (should extract both)
        """Here are two charts for your data:

First chart - Sales by quarter:
| Quarter | Sales | Growth |
| ------- | ----- | ------ |
| Q1      | 1000  | 15%    |
| Q2      | 1200  | 20%    |
| Q3      | 1150  | 12%    |

Second chart - Product performance:
| Product | Units | Revenue |
| ------- | ----- | ------- |
| A       | 100   | $5000   |
| B       | 150   | $7500   |
| C       | 80    | $4000   |""",

        # Table with different formatting (extra spaces)
        """Data analysis results:

| Category    | Value    | Status  |
| ----------- | -------- | ------- |
| Processing  | 75.5%    | Good    |
| Completed   | 150      | Done    |
| Pending     | 25       | Waiting |

The analysis is complete.""",
    ]

    for i, response in enumerate(test_cases, 1):
        print(f"\n{'='*80}")
        print(f"TEST CASE {i}:")
        print(f"{'='*80}")
        print(response)
        print(f"{'-'*80}")

        # Test table extraction
        tables = renderer.TABLE_PATTERN.findall(response)

        print(f"Found {len(tables)} table(s) with regex:")
        for j, table in enumerate(tables, 1):
            print(f"\nTable {j}:")
            print(repr(table[:100] + "..." if len(table) > 100 else table))
            print("Formatted:")
            print(table)
            print("-" * 40)

        # Test validation for each table
        for j, table in enumerate(tables, 1):
            print(f"\nValidation for Table {j}:")
            is_valid = renderer._is_valid_data_table(table)
            print(f"Result: {'VALID' if is_valid else 'INVALID'}")
            if not is_valid:
                print("This table failed validation - checking if it should pass...")

if __name__ == "__main__":
    test_table_extraction()