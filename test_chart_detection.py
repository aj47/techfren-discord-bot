#!/usr/bin/env python3
"""
Test script to verify explicit chart type detection works correctly.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from chart_renderer import ChartRenderer

def test_chart_type_detection():
    """Test the chart type detection functionality."""

    renderer = ChartRenderer()

    # Test cases for different chart type requests
    test_cases = [
        ("create a pie chart showing user distribution", "pie"),
        ("make a bar chart of message counts", "bar"),
        ("generate a line graph of activity over time", "line"),
        ("show a scatter plot of correlation", "scatter"),
        ("create a heatmap of usage patterns", "heatmap"),
        ("make a box plot of response times", "box"),
        ("show a histogram of message lengths", "histogram"),
        ("generate an area chart of growth", "area"),
        ("analyze this data for me", None),  # No explicit chart type
        ("show me some statistics", None),  # No explicit chart type
    ]

    print("Testing chart type detection:")
    print("=" * 50)

    for query, expected in test_cases:
        detected = renderer._detect_requested_chart_type(query)
        status = "✅" if detected == expected else "❌"
        print(f"{status} Query: '{query}'")
        print(f"   Expected: {expected}, Detected: {detected}")
        print()

if __name__ == "__main__":
    test_chart_type_detection()
