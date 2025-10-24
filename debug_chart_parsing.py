"""
Debug script to test table parsing and chart generation.
This will help identify why charts are showing "Row 1, Row 2" instead of actual data.
"""

from chart_renderer import ChartRenderer, ChartDataValidator
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def test_table_extraction():
    """Test the table extraction regex and parsing."""

    print("=== Testing Table Extraction ===")

    # Sample LLM response with table
    sample_response = """Here's the analysis of user activity:

| Username | Message Count |
| --- | --- |
| alice | 45 |
| bob | 32 |
| charlie | 28 |

Key insights:
- Alice leads with 42% of messages
- Activity peaked during evening hours"""

    print(f"Sample response:\n{sample_response}\n")

    # Test regex pattern
    renderer = ChartRenderer()

    # Extract tables using the regex
    tables = renderer.TABLE_PATTERN.findall(sample_response)
    print(f"Regex found {len(tables)} table(s)")

    for i, table in enumerate(tables):
        print(f"\nTable {i + 1} raw text:")
        print(repr(table))
        print(f"\nTable {i + 1} formatted:")
        print(table)

        # Parse the table
        parsed = renderer._parse_markdown_table(table)
        print(f"\nParsed table {i + 1}:")
        print(f"Headers: {parsed['headers'] if parsed else 'Failed to parse'}")
        print(f"Rows: {parsed['rows'] if parsed else 'Failed to parse'}")

        if parsed:
            # Test chart type inference
            chart_type = renderer._infer_chart_type(parsed)
            print(f"Inferred chart type: {chart_type}")

            # Test chart generation
            chart_url = renderer._generate_quickchart_url(parsed, chart_type)
            print(
                f"Generated chart URL: {chart_url[:100]}..."
                if chart_url
                else "Failed to generate chart"
            )


def test_table_variations():
    """Test different table formats that might cause issues."""

    print("\n=== Testing Table Variations ===")

    test_cases = [
        {
            "name": "Standard table",
            "table": """| Username | Message Count |
| --- | --- |
| alice | 45 |
| bob | 32 |""",
        },
        {
            "name": "Table with extra spaces",
            "table": """| Username    | Message Count |
|   ---       |      ---      |
| alice       |      45       |
| bob         |      32       |""",
        },
        {
            "name": "Table with percentages",
            "table": """| Technology | Usage (%) |
| --- | --- |
| Python | 45% |
| JavaScript | 35% |
| Go | 20% |""",
        },
        {
            "name": "Complex table",
            "table": """| Project/Toolkit | Focus Level | Workflow Type | Adoption Overhead | Key Features | Notes |  # noqa: E501
| --- | --- | --- | --- | --- | --- |
| React | High | Component-based | Medium | Virtual DOM, JSX | Popular choice |
| Vue | Medium | Component-based | Low | Template syntax | Easy to learn |
| Angular | High | Framework | High | TypeScript, CLI | Enterprise ready |""",
        },
    ]

    renderer = ChartRenderer()

    for case in test_cases:
        print(f"\n--- Testing: {case['name']} ---")

        # Parse the table
        parsed = renderer._parse_markdown_table(case["table"])

        if parsed:
            print("✓ Parsed successfully")
            print(f"  Headers ({len(parsed['headers'])}): {parsed['headers']}")
            print(
                f"  Rows ({len(parsed['rows'])}): {parsed['rows'][:2]}..."
            )  # Show first 2 rows

            # Test chart type
            chart_type = renderer._infer_chart_type(parsed)
            print(f"  Chart type: {chart_type}")

        else:
            print("✗ Failed to parse")


def test_data_validation():
    """Test the data validation for chart generation."""

    print("\n=== Testing Data Validation ===")

    test_data = [
        ["45", "32", "28"],
        ["45%", "35%", "20%"],
        ["1,234", "567", "89"],
        ["$100", "$250", "$75"],
        ["invalid", "text", "data"],
    ]

    for i, data in enumerate(test_data):
        print(f"\nTest {i + 1}: {data}")
        values, has_percentages = ChartDataValidator.validate_numeric_data(data)
        print(f"  Result: {values}")
        print(f"  Has percentages: {has_percentages}")


def test_chart_title_generation():
    """Test chart title generation."""

    print("\n=== Testing Chart Title Generation ===")

    test_cases = [
        (["Username", "Message Count"], "bar"),
        (["Technology", "Usage (%)"], "pie"),
        (["Time Period", "Activity Level"], "line"),
        (["Project/Toolkit", "Focus Level", "Workflow Type"], "bar"),
    ]

    renderer = ChartRenderer()

    for headers, chart_type in test_cases:
        title = renderer._generate_chart_title(headers, chart_type)
        print(f"Headers: {headers}")
        print(f"Chart type: {chart_type}")
        print(f"Generated title: '{title}'")
        print()


def test_full_pipeline():
    """Test the complete table extraction and chart generation pipeline."""

    print("\n=== Testing Full Pipeline ===")

    # Full LLM response with multiple elements
    full_response = """Based on the analysis of our Discord server activity, here are the key findings:  # noqa: E501

The community shows strong engagement across different time periods with clear patterns emerging.  # noqa: E501

| Username | Message Count |
| --- | --- |
| alice | 45 |
| bob | 32 |
| charlie | 28 |
| david | 19 |

Additionally, we can see technology preferences in discussions:

| Technology | Mentions |
| --- | --- |
| Python | 23 |
| JavaScript | 18 |
| TypeScript | 12 |
| Rust | 8 |

These patterns indicate a healthy, active community with diverse technical interests."""

    print("Full response test:")
    print(f"Response length: {len(full_response)} characters")

    renderer = ChartRenderer()

    # Run the complete extraction pipeline
    cleaned_content, chart_data_list = renderer.extract_tables_for_rendering(
        full_response
    )

    print(f"\nExtracted {len(chart_data_list)} chart(s)")
    print(f"Cleaned content length: {len(cleaned_content)} characters")

    for i, chart_data in enumerate(chart_data_list):
        print(f"\nChart {i + 1}:")
        print(f"  Type: {chart_data.get('type')}")
        print(f"  Placeholder: {chart_data.get('placeholder')}")
        print(f"  URL: {chart_data.get('url', '')[:50]}...")

        # Show original table
        print("  Original table:")
        original = chart_data.get("original_table", "")
        print(f"    {original[:100]}...")


def main():
    """Run all debug tests."""
    try:
        test_table_extraction()
        test_table_variations()
        test_data_validation()
        test_chart_title_generation()
        test_full_pipeline()

        print("\n" + "=" * 50)
        print("Debug testing completed!")
        print("Check the output above for any parsing issues.")

    except Exception as e:
        logger.error(f"Debug test error: {e}", exc_info=True)


if __name__ == "__main__":
    main()
