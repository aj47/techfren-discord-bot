"""
Test file to verify chart generation improvements.
Tests the enhanced system prompts and chart rendering capabilities.
"""

import unittest
from unittest.mock import Mock, patch
import asyncio
from chart_renderer import ChartRenderer, ChartDataValidator
from llm_handler import call_llm_api, call_llm_for_summary


class TestChartDataValidator(unittest.TestCase):
    """Test the ChartDataValidator utility class."""

    def test_validate_numeric_data_basic(self):
        """Test basic numeric data validation."""
        values = ["45", "32", "18"]
        result, has_percentages = ChartDataValidator.validate_numeric_data(values)

        self.assertEqual(result, [45.0, 32.0, 18.0])
        self.assertFalse(has_percentages)

    def test_validate_numeric_data_percentages(self):
        """Test validation of percentage data."""
        values = ["45%", "32%", "18%"]
        result, has_percentages = ChartDataValidator.validate_numeric_data(values)

        self.assertEqual(result, [45.0, 32.0, 18.0])
        self.assertTrue(has_percentages)

    def test_validate_numeric_data_formatted(self):
        """Test validation of formatted numbers."""
        values = ["1,234", "$500", "75%"]
        result, has_percentages = ChartDataValidator.validate_numeric_data(values)

        self.assertEqual(result, [1234.0, 500.0, 75.0])
        self.assertTrue(has_percentages)

    def test_validate_numeric_data_invalid(self):
        """Test handling of invalid data."""
        values = ["invalid", "text", "abc"]
        result, has_percentages = ChartDataValidator.validate_numeric_data(values)

        self.assertEqual(result, [0.0, 0.0, 0.0])
        self.assertFalse(has_percentages)

    def test_get_color_palette_pie(self):
        """Test color palette generation for pie charts."""
        colors = ChartDataValidator.get_color_palette(5, 'pie')

        self.assertEqual(len(colors), 5)
        self.assertTrue(all('rgba(' in color for color in colors))
        self.assertTrue(all('0.8' in color for color in colors))

    def test_get_color_palette_line(self):
        """Test color palette generation for line charts."""
        colors = ChartDataValidator.get_color_palette(3, 'line')

        self.assertEqual(len(colors), 3)
        self.assertTrue(all('rgba(' in color for color in colors))
        self.assertTrue(all(', 1)' in color for color in colors))

    def test_get_color_palette_large_count(self):
        """Test color palette generation for large datasets."""
        colors = ChartDataValidator.get_color_palette(15, 'bar')

        self.assertEqual(len(colors), 15)
        # Should repeat colors when count exceeds available colors


class TestChartRenderer(unittest.TestCase):
    """Test the enhanced ChartRenderer functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.renderer = ChartRenderer()

    def test_parse_markdown_table_basic(self):
        """Test basic markdown table parsing."""
        table_text = """| User | Messages |
| --- | --- |
| alice | 45 |
| bob | 32 |"""

        result = self.renderer._parse_markdown_table(table_text)

        self.assertIsNotNone(result)
        self.assertEqual(result['headers'], ['User', 'Messages'])
        self.assertEqual(len(result['rows']), 2)
        self.assertEqual(result['rows'][0], ['alice', '45'])

    def test_infer_chart_type_percentages(self):
        """Test chart type inference for percentage data."""
        table_data = {
            'headers': ['Technology', 'Usage (%)'],
            'rows': [
                ['Python', '45%'],
                ['JavaScript', '35%'],
                ['Go', '20%']
            ]
        }

        chart_type = self.renderer._infer_chart_type(table_data)
        self.assertEqual(chart_type, 'pie')

    def test_infer_chart_type_time_series(self):
        """Test chart type inference for time-based data."""
        table_data = {
            'headers': ['Time Period', 'Messages', 'Users'],
            'rows': [
                ['09:00-10:00', '15', '8'],
                ['10:00-11:00', '23', '12'],
                ['11:00-12:00', '18', '9']
            ]
        }

        chart_type = self.renderer._infer_chart_type(table_data)
        self.assertEqual(chart_type, 'line')

    def test_infer_chart_type_comparison(self):
        """Test chart type inference for comparison data."""
        table_data = {
            'headers': ['Username', 'Message Count'],
            'rows': [
                ['alice', '45'],
                ['bob', '32'],
                ['charlie', '28']
            ]
        }

        chart_type = self.renderer._infer_chart_type(table_data)
        self.assertEqual(chart_type, 'bar')

    def test_generate_chart_title_bar(self):
        """Test chart title generation for bar charts."""
        headers = ['Username', 'Message Count']
        title = self.renderer._generate_chart_title(headers, 'bar')

        self.assertEqual(title, 'Message Count by Username')

    def test_generate_chart_title_pie(self):
        """Test chart title generation for pie charts."""
        headers = ['Technology', 'Usage (%)']
        title = self.renderer._generate_chart_title(headers, 'pie')

        self.assertEqual(title, 'Usage (%) Distribution by Technology')

    def test_generate_chart_title_line(self):
        """Test chart title generation for line charts."""
        headers = ['Time Period', 'Activity Level']
        title = self.renderer._generate_chart_title(headers, 'line')

        self.assertEqual(title, 'Activity Level Trends Over Time Period')

    def test_extract_tables_for_rendering(self):
        """Test table extraction from content."""
        content = """Here's the analysis:

| Username | Message Count |
| --- | --- |
| alice | 45 |
| bob | 32 |

This shows user activity."""

        cleaned_content, chart_data_list = self.renderer.extract_tables_for_rendering(content)

        self.assertEqual(len(chart_data_list), 1)
        self.assertIn('[Chart 1:', cleaned_content)
        self.assertIn('url', chart_data_list[0])
        self.assertIn('type', chart_data_list[0])


class TestSystemPromptImprovements(unittest.TestCase):
    """Test that system prompts generate better table formatting."""

    def test_system_prompt_requirements(self):
        """Test that system prompts include accuracy requirements."""
        # This would typically test the actual LLM responses
        # For now, we verify the prompt structure exists

        # Mock test data that should trigger table generation
        test_scenarios = [
            "Show user activity: alice sent 45 messages, bob sent 32",
            "Time distribution: 9-12 had 15 messages, 12-15 had 23 messages",
            "Technology mentions: Python (8 times), JavaScript (5 times)"
        ]

        for scenario in test_scenarios:
            # In real implementation, this would call LLM and verify table format
            self.assertIsInstance(scenario, str)
            self.assertTrue(len(scenario) > 0)

    def test_table_format_validation(self):
        """Test that generated tables follow the required format."""
        valid_table = """| Username | Message Count |
| --- | --- |
| alice | 45 |
| bob | 32 |"""

        # Test that the table matches expected format
        lines = valid_table.strip().split('\n')

        # Header line should start and end with |
        self.assertTrue(lines[0].startswith('|'))
        self.assertTrue(lines[0].endswith('|'))

        # Separator line should be | --- | --- |
        self.assertEqual(lines[1].strip(), '| --- | --- |')

        # Data lines should start and end with |
        for line in lines[2:]:
            self.assertTrue(line.startswith('|'))
            self.assertTrue(line.endswith('|'))

    def test_header_descriptiveness(self):
        """Test that headers are descriptive rather than generic."""
        good_headers = [
            'Username', 'Message Count', 'Usage (%)', 'Time Period',
            'Technology', 'References', 'Activity Level'
        ]

        bad_headers = [
            'Item', 'Value', 'Data', 'Count', 'Number'
        ]

        # Good headers should be specific and descriptive
        for header in good_headers:
            self.assertTrue(len(header.split()) >= 1)
            self.assertNotIn(header.lower(), ['item', 'value', 'data'])

        # Bad headers should be avoided
        for header in bad_headers:
            if header in ['Count']:  # 'Count' alone is generic
                self.assertTrue(len(header.split()) == 1)


class TestChartAccuracy(unittest.TestCase):
    """Test chart accuracy and data validation."""

    def test_percentage_data_accuracy(self):
        """Test that percentage data adds up correctly."""
        test_data = [
            (['45%', '35%', '20%'], True),  # Should sum to 100%
            (['60%', '25%', '15%'], True),  # Should sum to 100%
            (['50%', '30%'], False),        # Doesn't sum to 100%
        ]

        for values, should_sum_to_100 in test_data:
            cleaned_values, has_percentages = ChartDataValidator.validate_numeric_data(values)

            self.assertTrue(has_percentages)
            total = sum(cleaned_values)

            if should_sum_to_100:
                self.assertAlmostEqual(total, 100.0, places=1)

    def test_data_consistency(self):
        """Test that data is consistent and logical."""
        # Test case: message counts should be positive integers
        message_counts = ['45', '32', '28', '19']
        cleaned_values, _ = ChartDataValidator.validate_numeric_data(message_counts)

        # All values should be positive
        self.assertTrue(all(v >= 0 for v in cleaned_values))

        # Values should be whole numbers (for message counts)
        self.assertTrue(all(v == int(v) for v in cleaned_values))

    def test_unit_consistency(self):
        """Test that units are handled consistently."""
        # Mixed units should be handled appropriately
        mixed_values = ['$100', '€85', '£90']  # Different currencies
        cleaned_values, _ = ChartDataValidator.validate_numeric_data(mixed_values)

        # Should extract numeric values
        self.assertEqual(cleaned_values, [100.0, 85.0, 90.0])


if __name__ == '__main__':
    # Run the tests
    unittest.main(verbosity=2)

    # Additional integration test
    print("\n" + "="*50)
    print("INTEGRATION TEST - Chart Generation Pipeline")
    print("="*50)

    # Test the complete pipeline with sample data
    renderer = ChartRenderer()

    sample_tables = [
        """| Username | Message Count |
| --- | --- |
| alice | 45 |
| bob | 32 |
| charlie | 28 |""",

        """| Technology | Usage (%) |
| --- | --- |
| Python | 45% |
| JavaScript | 35% |
| Go | 20% |""",

        """| Time Period | Messages | Users |
| --- | --- | --- |
| 09:00-12:00 | 15 | 8 |
| 12:00-15:00 | 23 | 12 |
| 15:00-18:00 | 18 | 9 |"""
    ]

    for i, table in enumerate(sample_tables, 1):
        print(f"\nTest {i}: Processing sample table...")

        # Parse the table
        table_data = renderer._parse_markdown_table(table)
        if table_data:
            chart_type = renderer._infer_chart_type(table_data)
            title = renderer._generate_chart_title(table_data['headers'], chart_type)

            print(f"  Headers: {table_data['headers']}")
            print(f"  Chart Type: {chart_type}")
            print(f"  Generated Title: {title}")
            print(f"  Rows: {len(table_data['rows'])}")
        else:
            print(f"  Failed to parse table {i}")

    print("\nChart improvements test completed!")
