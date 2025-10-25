#!/usr/bin/env python3
"""
Test edge cases for table validation.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from chart_renderer import ChartRenderer

def test_edge_cases():
    """Test edge cases for table validation."""

    renderer = ChartRenderer()

    # Edge case tables that might be problematic
    edge_cases = [
        # Table with mixed currency formats
        """| Month | Revenue |
| ----- | ------- |
| Jan   | $1,000  |
| Feb   | €900    |
| Mar   | £1,100  |""",

        # Table with scientific notation
        """| Measurement | Value |
| ----------- | ----- |
| Distance    | 1.5e3 |
| Time        | 2.4e-2|""",

        # Table with negative numbers
        """| Product | Profit |
| ------- | ------ |
| A       | -$50   |
| B       | $100   |
| C       | $25    |""",

        # Table with very specific headers that might be too generic
        """| Name | Amount | Type |
| ---- | ------ | ---- |
| John | $500   | A    |
| Jane | $750   | B    |""",

        # Table with minimal numeric data
        """| Category | Items | Has Value |
| -------- | ----- | --------- |
| A        | 5     | Yes      |
| B        | 3     | No       |""",
    ]

    for i, table in enumerate(edge_cases, 1):
        print(f"\n{'='*60}")
        print(f"EDGE CASE {i}:")
        print(f"{'='*60}")
        print(table)
        print(f"{'-'*60}")

        result = renderer._is_valid_data_table(table)
        print(f"Validation result: {'✅ PASSED' if result else '❌ FAILED'}")

        if not result:
            print("This case failed - checking if it should be passing...")
            # Brief analysis
            if "€" in table or "£" in table:
                print("  → Contains non-dollar currency symbols")
            if "e3" in table or "e-2" in table:
                print("  → Contains scientific notation")
            if "-$" in table:
                print("  → Contains negative currency values")
            if "Name" in table and "Type" in table:
                print("  → Has potentially generic headers")

if __name__ == "__main__":
    test_edge_cases()