#!/usr/bin/env python3
"""
Test the chart type detection logic without importing heavy dependencies.
"""

import re

def _detect_requested_chart_type(user_query: str) -> str:
    """
    Detect if user explicitly requests a specific chart type.

    Args:
        user_query: The user's original query

    Returns:
        str: Chart type if detected, None otherwise
    """
    if not user_query:
        return None

    query_lower = user_query.lower()

    # Chart type keywords mapping
    chart_keywords = {
        'pie': ['pie chart', 'piechart'],
        'bar': ['bar chart', 'bar chart', 'barchart'],
        'line': ['line chart', 'line graph', 'linechart', 'linegraph'],
        'scatter': ['scatter plot', 'scatterplot', 'scatter chart', 'scatterchart'],
        'heatmap': ['heatmap', 'heat map', 'heat map'],
        'box': ['box plot', 'boxplot', 'box plot', 'boxplot'],
        'histogram': ['histogram', 'histogram'],
        'area': ['area chart', 'area chart', 'areachart']
    }

    # Check for explicit chart type requests
    for chart_type, keywords in chart_keywords.items():
        for keyword in keywords:
            if keyword in query_lower:
                return chart_type

    return None

def test_chart_type_detection():
    """Test the chart type detection functionality."""

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
        ("can you create a piechart for me", "pie"),  # Test piechart variant
        ("I need a barchart", "bar"),  # Test barchart variant
        ("make me a linegraph", "line"),  # Test linegraph variant
    ]

    print("Testing chart type detection:")
    print("=" * 60)

    passed = 0
    total = len(test_cases)

    for query, expected in test_cases:
        detected = _detect_requested_chart_type(query)
        status = "✅" if detected == expected else "❌"
        if detected == expected:
            passed += 1
        print(f"{status} Query: '{query}'")
        print(f"   Expected: {expected}, Detected: {detected}")
        print()

    print(f"Results: {passed}/{total} tests passed ({passed/total*100:.1f}%)")

if __name__ == "__main__":
    test_chart_type_detection()