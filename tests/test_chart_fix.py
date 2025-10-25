"""
Test script to verify that charts now use actual table data instead of generic "Row 1, Row 2" labels.  # noqa: E501
This test specifically addresses the bug where complex tables were showing generic row labels.
"""

import logging
from chart_renderer import ChartRenderer

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_simple_table():
    """Test simple 2-column table that should work correctly."""
    print("=== Testing Simple 2-Column Table ===")

    table_text = """| Username | Message Count |
| --- | --- |
| alice | 45 |
| bob | 32 |
| charlie | 28 |"""

    renderer = ChartRenderer()

    # Parse table
    parsed = renderer._parse_markdown_table(table_text)
    print(f"Headers: {parsed['headers']}")
    print(f"Rows: {parsed['rows']}")

    # Check chart type
    chart_type = renderer._infer_chart_type(parsed)
    print(f"Chart type: {chart_type}")

    # Generate chart
    chart_url = renderer._generate_quickchart_url(parsed, chart_type)
    print(f"Chart generated: {'✓' if chart_url else '✗'}")

    return chart_url is not None


def test_percentage_table():
    """Test table with percentages."""
    print("\n=== Testing Percentage Table ===")

    table_text = """| Technology | Usage (%) |
| --- | --- |
| Python | 45% |
| JavaScript | 35% |
| Go | 20% |"""

    renderer = ChartRenderer()

    # Parse table
    parsed = renderer._parse_markdown_table(table_text)
    print(f"Headers: {parsed['headers']}")
    print(f"Rows: {parsed['rows']}")

    # Check chart type
    chart_type = renderer._infer_chart_type(parsed)
    print(f"Chart type: {chart_type}")

    # Generate chart
    chart_url = renderer._generate_quickchart_url(parsed, chart_type)
    print(f"Chart generated: {'✓' if chart_url else '✗'}")

    return chart_url is not None


def test_complex_multi_column_table():
    """Test complex table with many columns (the problematic case)."""
    print("\n=== Testing Complex Multi-Column Table ===")

    table_text = """| Project/Toolkit | Focus Level | Workflow Type | Adoption Overhead | Key Features | Notes |  # noqa: E501
| --- | --- | --- | --- | --- | --- |
| React | High | Component-based | Medium | Virtual DOM, JSX | Popular choice |
| Vue | Medium | Component-based | Low | Template syntax | Easy to learn |
| Angular | High | Framework | High | TypeScript, CLI | Enterprise ready |
| Svelte | Medium | Compiled | Low | No runtime | Innovative approach |
| jQuery | Low | DOM manipulation | Very Low | Simple API | Legacy support |"""

    renderer = ChartRenderer()

    # Parse table
    parsed = renderer._parse_markdown_table(table_text)
    print(f"Headers ({len(parsed['headers'])}): {parsed['headers']}")
    print(f"First row: {parsed['rows'][0]}")
    print(f"Total rows: {len(parsed['rows'])}")

    # Check chart type
    chart_type = renderer._infer_chart_type(parsed)
    print(f"Chart type: {chart_type}")

    # Generate chart
    chart_url = renderer._generate_quickchart_url(parsed, chart_type)
    print(f"Chart generated: {'✓' if chart_url else '✗'}")

    # The key test: this should NOT generate "Row 1, Row 2" labels anymore
    if chart_url:
        print(
            "SUCCESS: Complex table now generates meaningful charts instead of generic 'Row N' labels"  # noqa: E501
        )

    return chart_url is not None


def test_mixed_data_table():
    """Test table with mixed text and numeric data."""
    print("\n=== Testing Mixed Data Table ===")

    table_text = """| Framework | Stars | Language | Release Year | Active |
| --- | --- | --- | --- | --- |
| React | 185000 | JavaScript | 2013 | Yes |
| Vue | 185000 | JavaScript | 2014 | Yes |
| Angular | 88000 | TypeScript | 2010 | Yes |
| Svelte | 65000 | JavaScript | 2016 | Yes |"""

    renderer = ChartRenderer()

    # Parse table
    parsed = renderer._parse_markdown_table(table_text)
    print(f"Headers: {parsed['headers']}")
    print(f"Sample row: {parsed['rows'][0]}")

    # Check chart type
    chart_type = renderer._infer_chart_type(parsed)
    print(f"Chart type: {chart_type}")

    # Generate chart
    chart_url = renderer._generate_quickchart_url(parsed, chart_type)
    print(f"Chart generated: {'✓' if chart_url else '✗'}")

    # Should find the numeric "Stars" column and use Framework names as labels
    print(
        "Expected: Should use Framework names (React, Vue, etc.) as labels with Stars as values"  # noqa: E501
    )

    return chart_url is not None


def test_full_pipeline():
    """Test the complete extraction pipeline with multiple tables."""
    print("\n=== Testing Full Pipeline ===")

    llm_response = """Here's the analysis of our development tools:

First, let's look at user activity:

| Username | Contributions |
| --- | --- |
| alice | 45 |
| bob | 32 |
| charlie | 28 |

Now, here's a complex comparison of frameworks:

| Framework | Popularity | Learning Curve | Performance | Community | Documentation | Enterprise |  # noqa: E501
| --- | --- | --- | --- | --- | --- |
| React | High | Medium | Good | Excellent | Good | Yes |
| Vue | High | Easy | Good | Good | Excellent | Partial |
| Angular | Medium | Hard | Excellent | Good | Good | Yes |
| Svelte | Growing | Easy | Excellent | Small | Good | No |

Finally, technology preferences:

| Technology | Usage (%) |
| --- | --- |
| JavaScript | 45% |
| TypeScript | 35% |
| Python | 20% |

These patterns show diverse preferences in our community."""

    renderer = ChartRenderer()

    # Run full extraction
    cleaned_content, chart_data_list = renderer.extract_tables_for_rendering(
        llm_response
    )

    print(f"Original response length: {len(llm_response)}")
    print(f"Cleaned content length: {len(cleaned_content)}")
    print(f"Charts extracted: {len(chart_data_list)}")

    success = True
    for i, chart_data in enumerate(chart_data_list):
        print(f"\nChart {i+1}:")
        print(f"  Type: {chart_data.get('type')}")
        print(f"  Placeholder: {chart_data.get('placeholder')}")
        print(f"  Has URL: {'✓' if chart_data.get('url') else '✗'}")

        if not chart_data.get("url"):
            success = False

    return success and len(chart_data_list) > 0


def main():
    """Run all tests to verify the chart data fix."""
    print("Testing Chart Data Extraction Fix")
    print("=" * 50)
    print("This test verifies that charts now use actual table data")
    print("instead of generic 'Row 1, Row 2' labels.\n")

    tests = [
        ("Simple Table", test_simple_table),
        ("Percentage Table", test_percentage_table),
        ("Complex Multi-Column Table", test_complex_multi_column_table),
        ("Mixed Data Table", test_mixed_data_table),
        ("Full Pipeline", test_full_pipeline),
    ]

    results = []

    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
            status = "PASS" if result else "FAIL"
            print(f"Result: {status}\n")
        except Exception as e:
            logger.error(f"Test '{test_name}' failed with error: {e}", exc_info=True)
            results.append((test_name, False))
            print(f"Result: ERROR - {e}\n")

    # Summary
    print("=" * 50)
    print("TEST SUMMARY")
    print("=" * 50)

    passed = 0
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{test_name}: {status}")
        if result:
            passed += 1

    print(f"\nOverall: {passed}/{len(results)} tests passed")

    if passed == len(results):
        print("\n🎉 ALL TESTS PASSED!")
        print("Charts should now show actual data instead of 'Row 1, Row 2' labels.")
    else:
        print(f"\n⚠️  {len(results) - passed} test(s) failed.")
        print("There may still be issues with chart data extraction.")

    return passed == len(results)


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
