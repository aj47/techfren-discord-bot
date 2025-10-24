"""
Chart rendering module for Discord bot.
Detects markdown tables in LLM responses and converts them to chart images using QuickChart API.
"""

import re
import logging
from typing import List, Dict, Tuple, Optional
from quickchart import QuickChart

logger = logging.getLogger(__name__)


class ChartRenderer:
    """Handles detection and rendering of tables/charts from LLM responses."""

    # Regex pattern to detect markdown tables
    TABLE_PATTERN = re.compile(
        r'(\|.+\|[\r\n]+\|[\s\-:|]+\|[\r\n]+(?:\|.+\|[\r\n]*)+)',
        re.MULTILINE
    )

    def __init__(self):
        """Initialize the chart renderer."""
        pass

    def extract_tables_for_rendering(self, content: str) -> Tuple[str, List[Dict]]:
        """
        Extract markdown tables from content and prepare them for rendering.

        Args:
            content: The LLM response text containing potential markdown tables

        Returns:
            Tuple of (cleaned_content, chart_data_list)
            - cleaned_content: Original content with tables replaced by placeholders
            - chart_data_list: List of dicts with 'url', 'type', 'placeholder' keys
        """
        tables = self.TABLE_PATTERN.findall(content)

        if not tables:
            return content, []

        logger.info(f"Found {len(tables)} markdown table(s) in response")

        chart_data_list = []
        cleaned_content = content

        for idx, table_text in enumerate(tables):
            try:
                # Parse the table
                table_data = self._parse_markdown_table(table_text)

                if not table_data:
                    logger.warning(f"Failed to parse table {idx + 1}, skipping")
                    continue

                # Determine the best chart type
                chart_type = self._infer_chart_type(table_data)

                # Generate QuickChart URL
                chart_url = self._generate_quickchart_url(table_data, chart_type)

                if chart_url:
                    # Create placeholder text
                    placeholder = f"[Chart {idx + 1}: {chart_type.title()}]"

                    # Replace table with placeholder in content
                    cleaned_content = cleaned_content.replace(table_text, placeholder, 1)

                    chart_data_list.append({
                        'url': chart_url,
                        'type': chart_type,
                        'placeholder': placeholder,
                        'original_table': table_text
                    })

                    logger.info(f"Generated {chart_type} chart for table {idx + 1}")
                else:
                    logger.warning(f"Failed to generate chart URL for table {idx + 1}")

            except Exception as e:
                logger.error(f"Error processing table {idx + 1}: {e}", exc_info=True)
                continue

        return cleaned_content, chart_data_list

    def _parse_markdown_table(self, table_text: str) -> Optional[Dict]:
        """
        Parse a markdown table into structured data.

        Args:
            table_text: Raw markdown table text

        Returns:
            Dict with 'headers' and 'rows' keys, or None if parsing fails
        """
        try:
            lines = [line.strip() for line in table_text.strip().split('\n') if line.strip()]

            if len(lines) < 3:  # Need at least header, separator, and one data row
                return None

            # Parse header row
            headers = [cell.strip() for cell in lines[0].split('|') if cell.strip()]

            # Skip separator row (line[1])

            # Parse data rows
            rows = []
            for line in lines[2:]:
                cells = [cell.strip() for cell in line.split('|') if cell.strip()]
                if len(cells) == len(headers):
                    rows.append(cells)

            if not rows:
                return None

            return {
                'headers': headers,
                'rows': rows
            }

        except Exception as e:
            logger.error(f"Error parsing markdown table: {e}")
            return None

    def _infer_chart_type(self, table_data: Dict) -> str:
        """
        Analyze table data to determine the best chart type.

        Args:
            table_data: Parsed table with 'headers' and 'rows'

        Returns:
            Chart type: 'bar', 'line', 'pie', or 'table'
        """
        headers = table_data['headers']
        rows = table_data['rows']

        # If only 2 columns and second column is numeric, could be bar/pie
        if len(headers) == 2:
            # Check if second column is mostly numeric
            numeric_count = 0
            total_rows = len(rows)

            for row in rows:
                if len(row) >= 2:
                    try:
                        # Try to parse as number (removing % signs and commas)
                        value = row[1].replace('%', '').replace(',', '').strip()
                        float(value)
                        numeric_count += 1
                    except ValueError:
                        pass

            # If more than 70% numeric, use chart
            if numeric_count / total_rows > 0.7:
                # Check if values are percentages or sum to ~100
                try:
                    values = [float(row[1].replace('%', '').replace(',', '').strip()) for row in rows]
                    total = sum(values)

                    # If values sum to roughly 100, use pie chart
                    if 95 <= total <= 105 or any('%' in row[1] for row in rows):
                        return 'pie'
                except:
                    pass

                # Default to bar chart for numeric data
                return 'bar'

        # If 3+ columns with numeric data, could be line chart (time series)
        if len(headers) >= 3:
            # Check if we have numeric columns
            numeric_cols = []
            for col_idx in range(1, len(headers)):
                numeric_count = 0
                for row in rows:
                    if len(row) > col_idx:
                        try:
                            value = row[col_idx].replace('%', '').replace(',', '').strip()
                            float(value)
                            numeric_count += 1
                        except ValueError:
                            pass

                if numeric_count / len(rows) > 0.7:
                    numeric_cols.append(col_idx)

            # If we have multiple numeric columns, use line chart
            if len(numeric_cols) >= 2:
                return 'line'
            elif len(numeric_cols) == 1:
                return 'bar'

        # Default to table image for complex/text data
        return 'table'

    def _generate_quickchart_url(self, table_data: Dict, chart_type: str) -> Optional[str]:
        """
        Generate a QuickChart URL for the given table data and chart type.

        Args:
            table_data: Parsed table with 'headers' and 'rows'
            chart_type: Type of chart to generate

        Returns:
            QuickChart URL string, or None if generation fails
        """
        try:
            if chart_type == 'table':
                return self._generate_table_chart(table_data)
            elif chart_type == 'bar':
                return self._generate_bar_chart(table_data)
            elif chart_type == 'pie':
                return self._generate_pie_chart(table_data)
            elif chart_type == 'line':
                return self._generate_line_chart(table_data)
            else:
                logger.warning(f"Unknown chart type: {chart_type}")
                return None

        except Exception as e:
            logger.error(f"Error generating {chart_type} chart: {e}", exc_info=True)
            return None

    def _generate_table_chart(self, table_data: Dict) -> Optional[str]:
        """Generate a formatted table image using QuickChart."""
        qc = QuickChart()
        qc.width = 800
        qc.height = 400
        qc.device_pixel_ratio = 2.0

        headers = table_data['headers']
        rows = table_data['rows']

        # Create a simple table visualization using Chart.js table plugin
        # For now, we'll create a simple bar chart to represent the table
        # A true table rendering would require custom HTML or a different approach

        # Alternative: Use a simple visual representation
        config = {
            'type': 'bar',
            'data': {
                'labels': [f"Row {i+1}" for i in range(len(rows))],
                'datasets': [{
                    'label': 'Table Data (visual representation)',
                    'data': [i+1 for i in range(len(rows))]
                }]
            },
            'options': {
                'title': {
                    'display': True,
                    'text': f"Table: {' | '.join(headers)}"
                },
                'plugins': {
                    'datalabels': {
                        'display': False
                    }
                }
            }
        }

        qc.config = config
        return qc.get_url()

    def _generate_bar_chart(self, table_data: Dict) -> Optional[str]:
        """Generate a bar chart using QuickChart."""
        qc = QuickChart()
        qc.width = 800
        qc.height = 500
        qc.device_pixel_ratio = 2.0

        headers = table_data['headers']
        rows = table_data['rows']

        # Extract labels and values
        labels = [row[0] for row in rows]
        values = []

        for row in rows:
            if len(row) >= 2:
                try:
                    value = row[1].replace('%', '').replace(',', '').strip()
                    values.append(float(value))
                except ValueError:
                    values.append(0)

        config = {
            'type': 'bar',
            'data': {
                'labels': labels,
                'datasets': [{
                    'label': headers[1] if len(headers) > 1 else 'Value',
                    'data': values,
                    'backgroundColor': 'rgba(54, 162, 235, 0.8)',
                    'borderColor': 'rgba(54, 162, 235, 1)',
                    'borderWidth': 1
                }]
            },
            'options': {
                'title': {
                    'display': True,
                    'text': f"{headers[0]} vs {headers[1]}" if len(headers) > 1 else 'Data Comparison',
                    'fontSize': 16
                },
                'legend': {
                    'display': True
                },
                'scales': {
                    'yAxes': [{
                        'ticks': {
                            'beginAtZero': True
                        }
                    }]
                },
                'plugins': {
                    'datalabels': {
                        'anchor': 'end',
                        'align': 'top',
                        'formatter': '(value) => value'
                    }
                }
            }
        }

        qc.config = config
        return qc.get_url()

    def _generate_pie_chart(self, table_data: Dict) -> Optional[str]:
        """Generate a pie chart using QuickChart."""
        qc = QuickChart()
        qc.width = 600
        qc.height = 600
        qc.device_pixel_ratio = 2.0

        headers = table_data['headers']
        rows = table_data['rows']

        # Extract labels and values
        labels = [row[0] for row in rows]
        values = []

        for row in rows:
            if len(row) >= 2:
                try:
                    value = row[1].replace('%', '').replace(',', '').strip()
                    values.append(float(value))
                except ValueError:
                    values.append(0)

        # Generate colors
        colors = [
            'rgba(255, 99, 132, 0.8)',
            'rgba(54, 162, 235, 0.8)',
            'rgba(255, 206, 86, 0.8)',
            'rgba(75, 192, 192, 0.8)',
            'rgba(153, 102, 255, 0.8)',
            'rgba(255, 159, 64, 0.8)',
            'rgba(199, 199, 199, 0.8)',
            'rgba(83, 102, 255, 0.8)',
        ]

        config = {
            'type': 'pie',
            'data': {
                'labels': labels,
                'datasets': [{
                    'data': values,
                    'backgroundColor': colors[:len(values)]
                }]
            },
            'options': {
                'title': {
                    'display': True,
                    'text': headers[1] if len(headers) > 1 else 'Distribution',
                    'fontSize': 16
                },
                'legend': {
                    'display': True,
                    'position': 'right'
                },
                'plugins': {
                    'datalabels': {
                        'color': '#fff',
                        'font': {
                            'weight': 'bold',
                            'size': 14
                        },
                        'formatter': '(value, ctx) => { const label = ctx.chart.data.labels[ctx.dataIndex]; return label + ": " + value + "%"; }'
                    }
                }
            }
        }

        qc.config = config
        return qc.get_url()

    def _generate_line_chart(self, table_data: Dict) -> Optional[str]:
        """Generate a line chart using QuickChart."""
        qc = QuickChart()
        qc.width = 800
        qc.height = 500
        qc.device_pixel_ratio = 2.0

        headers = table_data['headers']
        rows = table_data['rows']

        # Extract labels (first column)
        labels = [row[0] for row in rows]

        # Extract datasets (remaining columns)
        datasets = []
        colors = [
            'rgba(255, 99, 132, 1)',
            'rgba(54, 162, 235, 1)',
            'rgba(255, 206, 86, 1)',
            'rgba(75, 192, 192, 1)',
            'rgba(153, 102, 255, 1)',
        ]

        for col_idx in range(1, len(headers)):
            values = []
            for row in rows:
                if len(row) > col_idx:
                    try:
                        value = row[col_idx].replace('%', '').replace(',', '').strip()
                        values.append(float(value))
                    except ValueError:
                        values.append(0)

            datasets.append({
                'label': headers[col_idx],
                'data': values,
                'borderColor': colors[(col_idx - 1) % len(colors)],
                'backgroundColor': colors[(col_idx - 1) % len(colors)].replace('1)', '0.2)'),
                'fill': False,
                'tension': 0.1
            })

        config = {
            'type': 'line',
            'data': {
                'labels': labels,
                'datasets': datasets
            },
            'options': {
                'title': {
                    'display': True,
                    'text': f"{headers[0]} Trends",
                    'fontSize': 16
                },
                'legend': {
                    'display': True
                },
                'scales': {
                    'yAxes': [{
                        'ticks': {
                            'beginAtZero': True
                        }
                    }]
                },
                'plugins': {
                    'datalabels': {
                        'display': False
                    }
                }
            }
        }

        qc.config = config
        return qc.get_url()


# Singleton instance
_chart_renderer = ChartRenderer()


def extract_tables_for_rendering(content: str) -> Tuple[str, List[Dict]]:
    """
    Convenience function to extract and render tables from content.

    Args:
        content: LLM response text

    Returns:
        Tuple of (cleaned_content, chart_data_list)
    """
    return _chart_renderer.extract_tables_for_rendering(content)
