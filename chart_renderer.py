"""
Chart rendering module for Discord bot.
Detects markdown tables in LLM responses and converts them to chart images using QuickChart API.  # noqa: E501
"""

import re
import logging
from typing import List, Dict, Tuple, Optional
from quickchart import QuickChart

logger = logging.getLogger(__name__)


class ChartDataValidator:
    """Utility class for validating and normalizing chart data."""

    @staticmethod
    def _clean_numeric_string(clean_str: str) -> Tuple[str, bool]:
        """Remove formatting characters from numeric string."""
        has_percentages = "%" in clean_str
        numeric_str = (
            clean_str.replace("%", "")
            .replace(",", "")
            .replace("$", "")
            .replace("€", "")
            .replace("£", "")
            .strip()
        )
        return numeric_str, has_percentages

    @staticmethod
    def _try_direct_conversion(numeric_str: str) -> float:
        """Try direct conversion to float."""
        try:
            return float(numeric_str)
        except ValueError:
            return None

    @staticmethod
    def _extract_number_from_text(numeric_str: str) -> float:
        """Extract first number from text like 'High (85)' or 'Score: 92'."""
        import re

        number_match = re.search(r"(\d+(?:\.\d+)?)", numeric_str)
        if number_match:
            return float(number_match.group(1))
        return None

    @staticmethod
    def _map_text_to_number(clean_str: str) -> float:
        """Map text descriptions to numeric values."""
        text_lower = clean_str.lower()
        if "high" in text_lower or "excellent" in text_lower:
            return 3.0
        elif "medium" in text_lower or "good" in text_lower:
            return 2.0
        elif "low" in text_lower or "poor" in text_lower:
            return 1.0
        elif "yes" in text_lower or "true" in text_lower or "active" in text_lower:
            return 1.0
        elif "no" in text_lower or "false" in text_lower or "inactive" in text_lower:
            return 0.0
        else:
            # Last resort: use string length as a proxy
            return float(len(clean_str))

    @staticmethod
    def validate_numeric_data(values: List[str]) -> Tuple[List[float], bool]:
        """
        Validate and convert string values to numeric data with aggressive extraction.

        Args:
            values: List of string values to validate

        Returns:
            Tuple of (cleaned_values, has_percentages)
        """
        cleaned_values = []
        has_percentages = False

        for value_str in values:
            try:
                clean_str = str(value_str).strip()
                numeric_str, has_pct = ChartDataValidator._clean_numeric_string(
                    clean_str
                )
                has_percentages = has_percentages or has_pct

                # Try direct conversion first
                value = ChartDataValidator._try_direct_conversion(numeric_str)
                if value is not None:
                    cleaned_values.append(value)
                    continue

                # Try extracting number from text
                value = ChartDataValidator._extract_number_from_text(numeric_str)
                if value is not None:
                    cleaned_values.append(value)
                    continue

                # Map text to numbers
                value = ChartDataValidator._map_text_to_number(clean_str)
                cleaned_values.append(value)

            except (ValueError, AttributeError, TypeError):
                cleaned_values.append(0.0)

        return cleaned_values, has_percentages

    @staticmethod
    def get_color_palette(count: int, chart_type: str = "default") -> List[str]:
        """
        Get an appropriate color palette for the given number of data points.

        Args:
            count: Number of colors needed
            chart_type: Type of chart ('pie', 'bar', 'line', 'default')

        Returns:
            List of color strings
        """
        # Enhanced color palettes for different chart types
        if chart_type == "pie":
            colors = [
                "rgba(255, 99, 132, 0.8)",  # Red
                "rgba(54, 162, 235, 0.8)",  # Blue
                "rgba(255, 206, 86, 0.8)",  # Yellow
                "rgba(75, 192, 192, 0.8)",  # Teal
                "rgba(153, 102, 255, 0.8)",  # Purple
                "rgba(255, 159, 64, 0.8)",  # Orange
                "rgba(199, 199, 199, 0.8)",  # Grey
                "rgba(83, 102, 255, 0.8)",  # Indigo
                "rgba(255, 192, 203, 0.8)",  # Pink
                "rgba(144, 238, 144, 0.8)",  # Light Green
                "rgba(255, 182, 193, 0.8)",  # Light Pink
                "rgba(173, 216, 230, 0.8)",  # Light Blue
            ]
        elif chart_type == "bar":
            colors = [
                "rgba(54, 162, 235, 0.8)",  # Blue
                "rgba(255, 99, 132, 0.8)",  # Red
                "rgba(75, 192, 192, 0.8)",  # Teal
                "rgba(153, 102, 255, 0.8)",  # Purple
                "rgba(255, 206, 86, 0.8)",  # Yellow
                "rgba(255, 159, 64, 0.8)",  # Orange
                "rgba(199, 199, 199, 0.8)",  # Grey
                "rgba(83, 102, 255, 0.8)",  # Indigo
            ]
        elif chart_type == "line":
            colors = [
                "rgba(255, 99, 132, 1)",  # Red
                "rgba(54, 162, 235, 1)",  # Blue
                "rgba(75, 192, 192, 1)",  # Teal
                "rgba(153, 102, 255, 1)",  # Purple
                "rgba(255, 206, 86, 1)",  # Yellow
                "rgba(255, 159, 64, 1)",  # Orange
                "rgba(199, 199, 199, 1)",  # Grey
                "rgba(83, 102, 255, 1)",  # Indigo
            ]
        else:
            colors = [
                "rgba(54, 162, 235, 0.8)",
                "rgba(255, 99, 132, 0.8)",
                "rgba(255, 206, 86, 0.8)",
                "rgba(75, 192, 192, 0.8)",
                "rgba(153, 102, 255, 0.8)",
                "rgba(255, 159, 64, 0.8)",
                "rgba(199, 199, 199, 0.8)",
                "rgba(83, 102, 255, 0.8)",
            ]

        # Repeat colors if we need more than available
        return (
            colors[:count]
            if count <= len(colors)
            else colors * ((count // len(colors)) + 1)
        )


class ChartRenderer:
    """Handles detection and rendering of tables/charts from LLM responses."""

    # Regex pattern to detect markdown tables
    TABLE_PATTERN = re.compile(
        r"(\|.+\|[\r\n]+\|[\s\-:|]+\|[\r\n]+(?:\|.+\|[\r\n]*)+)", re.MULTILINE
    )

    def __init__(self):
        """Initialize the chart renderer."""

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
                    cleaned_content = cleaned_content.replace(
                        table_text, placeholder, 1
                    )

                    chart_data_list.append(
                        {
                            "url": chart_url,
                            "type": chart_type,
                            "placeholder": placeholder,
                            "original_table": table_text,
                        }
                    )

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
            lines = [
                line.strip() for line in table_text.strip().split("\n") if line.strip()
            ]

            if len(lines) < 3:  # Need at least header, separator, and one data row
                return None

            # Parse header row
            headers = [cell.strip() for cell in lines[0].split("|") if cell.strip()]

            # Skip separator row (line[1])

            # Parse data rows
            rows = []
            for line in lines[2:]:
                cells = [cell.strip() for cell in line.split("|") if cell.strip()]
                if len(cells) == len(headers):
                    rows.append(cells)

            if not rows:
                return None

            return {"headers": headers, "rows": rows}

        except Exception as e:
            logger.error(f"Error parsing markdown table: {e}")
            return None

    def _analyze_data_patterns(self, rows: List[List[str]]) -> Dict[str, any]:
        """Analyze data patterns in table rows."""
        numeric_count = 0
        total_rows = len(rows)
        has_percentages = False
        has_time_data = False

        for row in rows:
            if len(row) >= 2:
                value_str = row[1].strip()

                # Check for percentage indicators
                if "%" in value_str:
                    has_percentages = True

                # Check for time patterns
                if any(
                    pattern in row[0].lower()
                    for pattern in ["time", "hour", "day", "date", ":"]
                ):
                    has_time_data = True

                try:
                    clean_value = value_str.replace("%", "").replace(",", "").strip()
                    float(clean_value)
                    numeric_count += 1
                except ValueError:
                    pass

        return {
            "numeric_count": numeric_count,
            "total_rows": total_rows,
            "has_percentages": has_percentages,
            "has_time_data": has_time_data,
        }

    def _check_pie_chart_suitability(
        self, rows: List[List[str]], has_percentages: bool
    ) -> bool:
        """Check if data is suitable for pie chart."""
        if not has_percentages:
            return False

        try:
            values = [
                float(row[1].replace("%", "").replace(",", "").strip()) for row in rows
            ]
            total = sum(values)
            return 95 <= total <= 105
        except (ValueError, TypeError, ZeroDivisionError):
            return False

    def _analyze_multicolumn_data(
        self, headers: List[str], rows: List[List[str]]
    ) -> Dict[str, any]:
        """Analyze multi-column data for chart type determination."""
        import re

        first_col_time = any(
            pattern in headers[0].lower()
            for pattern in ["time", "hour", "day", "date", "period"]
        )
        numeric_cols = []

        for col_idx in range(1, len(headers)):
            numeric_count = 0
            for row in rows:
                if len(row) > col_idx:
                    try:
                        value = (
                            str(row[col_idx])
                            .replace("%", "")
                            .replace(",", "")
                            .replace("$", "")
                            .replace("€", "")
                            .replace("£", "")
                            .strip()
                        )
                        number_match = re.search(r"(\d+(?:\.\d+)?)", value)
                        if number_match:
                            float(number_match.group(1))
                            numeric_count += 1
                        else:
                            float(value)
                            numeric_count += 1
                    except (ValueError, AttributeError):
                        pass

            if numeric_count / len(rows) > 0.3:
                numeric_cols.append(col_idx)

        return {"first_col_time": first_col_time, "numeric_cols": numeric_cols}

    def _find_any_numeric_column(
        self, headers: List[str], rows: List[List[str]]
    ) -> bool:
        """Find any numeric column with aggressive detection."""
        import re

        for col_idx in range(1, len(headers)):
            numeric_count = 0
            for row in rows:
                if len(row) > col_idx:
                    try:
                        value = (
                            str(row[col_idx])
                            .replace("%", "")
                            .replace(",", "")
                            .replace("$", "")
                            .replace("€", "")
                            .replace("£", "")
                            .strip()
                        )
                        number_match = re.search(r"(\d+(?:\.\d+)?)", value)
                        if number_match:
                            float(number_match.group(1))
                            numeric_count += 1
                        else:
                            float(value)
                            numeric_count += 1
                    except (ValueError, AttributeError):
                        pass

            if numeric_count / len(rows) > 0.2:
                return True
        return False

    def _infer_two_column_chart_type(self, rows: List[List[str]]) -> str:
        """Infer chart type for 2-column data."""
        patterns = self._analyze_data_patterns(rows)

        # If more than 30% numeric, choose appropriate chart type
        if patterns["numeric_count"] / patterns["total_rows"] > 0.3:
            if self._check_pie_chart_suitability(rows, patterns["has_percentages"]):
                return "pie"
            if patterns["has_time_data"] and len(rows) >= 3:
                return "line"
            return "bar"
        return None

    def _infer_multicolumn_chart_type(
        self, headers: List[str], rows: List[List[str]]
    ) -> str:
        """Infer chart type for 3+ columns."""
        multi_data = self._analyze_multicolumn_data(headers, rows)

        if multi_data["first_col_time"] and len(multi_data["numeric_cols"]) >= 2:
            return "line"
        elif len(multi_data["numeric_cols"]) >= 2:
            return "line"
        elif len(multi_data["numeric_cols"]) == 1:
            return "bar"
        return None

    def _infer_fallback_chart_type(
        self, headers: List[str], rows: List[List[str]]
    ) -> str:
        """Fallback logic for chart type inference."""
        # Try to find any visualizable data
        if self._find_any_numeric_column(headers, rows):
            return "bar"

        # Check for categorical data that varies
        if len(headers) >= 2 and len(rows) > 1:
            unique_values = set(str(row[0]) for row in rows if len(row) > 0)
            if len(unique_values) > 1 and len(unique_values) <= 10:
                return "bar"

        return "table"

    def _infer_chart_type(self, table_data: Dict) -> str:
        """
        Analyze table data to determine the best chart type based on content patterns.

        Args:
            table_data: Parsed table with 'headers' and 'rows'

        Returns:
            Chart type: 'bar', 'line', 'pie', or 'table'
        """
        headers = table_data["headers"]
        rows = table_data["rows"]

        # If only 2 columns, analyze the content type
        if len(headers) == 2:
            chart_type = self._infer_two_column_chart_type(rows)
            if chart_type:
                return chart_type

        # If 3+ columns with numeric data, analyze for time series
        if len(headers) >= 3:
            chart_type = self._infer_multicolumn_chart_type(headers, rows)
            if chart_type:
                return chart_type

        # Fallback logic
        return self._infer_fallback_chart_type(headers, rows)

    def _generate_quickchart_url(
        self, table_data: Dict, chart_type: str
    ) -> Optional[str]:
        """
        Generate a QuickChart URL for the given table data and chart type.

        Args:
            table_data: Parsed table with 'headers' and 'rows'
            chart_type: Type of chart to generate

        Returns:
            QuickChart URL string, or None if generation fails
        """
        try:
            if chart_type == "table":
                table_url = self._generate_table_chart(table_data)
                # If table chart returns None, try to generate a bar chart instead
                if table_url is None:
                    logger.info(
                        "Table chart generation returned None, attempting bar chart fallback"  # noqa: E501
                    )
                    return self._generate_bar_chart(table_data)
                return table_url
            elif chart_type == "bar":
                return self._generate_bar_chart(table_data)
            elif chart_type == "pie":
                return self._generate_pie_chart(table_data)
            elif chart_type == "line":
                return self._generate_line_chart(table_data)
            else:
                logger.warning(f"Unknown chart type: {chart_type}")
                return None

        except Exception as e:
            logger.error(f"Error generating {chart_type} chart: {e}", exc_info=True)
            return None

    def _find_best_numeric_column(
        self, headers: List[str], rows: List[List[str]]
    ) -> Optional[int]:
        """Find the column with the highest ratio of numeric values."""
        best_numeric_ratio = 0
        value_col_idx = None

        for col_idx in range(1, len(headers)):
            numeric_count = 0
            for row in rows:
                if len(row) > col_idx:
                    try:
                        value = (
                            str(row[col_idx])
                            .replace("%", "")
                            .replace(",", "")
                            .replace("$", "")
                            .replace("€", "")
                            .replace("£", "")
                            .strip()
                        )
                        import re

                        number_match = re.search(r"(\d+(?:\.\d+)?)", value)
                        if number_match:
                            float(number_match.group(1))
                            numeric_count += 1
                        else:
                            float(value)
                            numeric_count += 1
                    except (ValueError, AttributeError):
                        pass

            numeric_ratio = numeric_count / len(rows) if len(rows) > 0 else 0
            if numeric_ratio > 0.3 and numeric_ratio > best_numeric_ratio:
                value_col_idx = col_idx
                best_numeric_ratio = numeric_ratio

        return value_col_idx

    def _create_frequency_chart(self, rows: List[List[str]]) -> Optional[str]:
        """Create a frequency distribution chart from categorical data."""
        if len(rows) <= 1:
            return None

        from collections import Counter

        category_counts = Counter(
            [row[0] if len(row) > 0 else "Unknown" for row in rows]
        )

        if len(category_counts) > 1 and len(category_counts) <= 10:
            simplified_table = {
                "headers": ["Category", "Count"],
                "rows": [
                    [category, count] for category, count in category_counts.items()
                ],
            }
            return self._generate_bar_chart(simplified_table)

        return None

    def _generate_table_chart(self, table_data: Dict) -> Optional[str]:
        """Generate a formatted table image using QuickChart."""
        headers = table_data["headers"]
        rows = table_data["rows"]

        # For complex tables with many columns, try to find the best 2 columns to
        # visualize
        if len(headers) > 2:
            value_col_idx = self._find_best_numeric_column(headers, rows)

            if value_col_idx is not None:
                simplified_table = {
                    "headers": [headers[0], headers[value_col_idx]],
                    "rows": [
                        [row[0], row[value_col_idx]]
                        for row in rows
                        if len(row) > value_col_idx
                    ],
                }

                chart_type = self._infer_chart_type(simplified_table)
                if chart_type == "bar":
                    return self._generate_bar_chart(simplified_table)
                elif chart_type == "pie":
                    return self._generate_pie_chart(simplified_table)
                elif chart_type == "line":
                    return self._generate_line_chart(simplified_table)

            # Try frequency chart as fallback
            return self._create_frequency_chart(rows)

        # For 2-column tables, proceed with normal chart generation
        if len(headers) == 2:
            chart_type = self._infer_chart_type(table_data)
            if chart_type == "bar":
                return self._generate_bar_chart(table_data)
            elif chart_type == "pie":
                return self._generate_pie_chart(table_data)
            elif chart_type == "line":
                return self._generate_line_chart(table_data)

        # Fallback for all other cases
        return None

    def _generate_bar_chart(self, table_data: Dict) -> Optional[str]:
        """Generate a bar chart using QuickChart with enhanced labeling."""
        qc = QuickChart()
        qc.width = 800
        qc.height = 500
        qc.device_pixel_ratio = 2.0

        headers = table_data["headers"]
        rows = table_data["rows"]

        # For multi-column tables, find the best numeric column to chart
        label_col_idx = 0
        value_col_idx = 1

        # If table has more than 2 columns, find the first numeric column
        if len(headers) > 2:
            for col_idx in range(1, len(headers)):
                numeric_count = 0
                test_values = [
                    row[col_idx] if len(row) > col_idx else "0" for row in rows
                ]

                for val in test_values:
                    try:
                        clean_val = val.replace("%", "").replace(",", "").strip()
                        float(clean_val)
                        numeric_count += 1
                    except (ValueError, AttributeError):
                        pass

                # Use this column if >30% numeric (lowered threshold)
                if numeric_count / len(rows) > 0.3:
                    value_col_idx = col_idx
                    break

        # Extract labels and values using the determined columns
        labels = [
            str(row[label_col_idx]) if len(row) > label_col_idx else f"Item {i + 1}"
            for i, row in enumerate(rows)
        ]
        raw_values = []

        # Enhanced value extraction with better numeric parsing
        for row in rows:
            if len(row) > value_col_idx:
                value_str = str(row[value_col_idx])
                # Try to extract numeric value from text using regex
                import re

                number_match = re.search(
                    r"(\d+(?:\.\d+)?)",
                    value_str.replace("%", "")
                    .replace(",", "")
                    .replace("$", "")
                    .replace("€", "")
                    .replace("£", ""),
                )
                if number_match:
                    raw_values.append(number_match.group(1))
                else:
                    raw_values.append(value_str)
            else:
                raw_values.append("0")

        # Validate and clean numeric data
        values, has_percentages = ChartDataValidator.validate_numeric_data(raw_values)

        # Generate a more descriptive title using the selected columns
        selected_headers = (
            [headers[label_col_idx], headers[value_col_idx]]
            if len(headers) > value_col_idx
            else headers
        )
        title = self._generate_chart_title(selected_headers, "bar")

        # Get appropriate colors
        colors = ChartDataValidator.get_color_palette(len(values), "bar")

        # Determine if values should show percentages
        value_suffix = "%" if has_percentages else ""

        # Create more detailed axis labels and legend descriptions
        x_axis_label = self._enhance_axis_label(
            headers[label_col_idx] if len(headers) > label_col_idx else "Category", "x"
        )
        y_axis_label = self._enhance_axis_label(
            headers[value_col_idx] if len(headers) > value_col_idx else "Value",
            "y",
            value_suffix,
        )
        legend_label = self._enhance_legend_label(
            headers[value_col_idx] if len(headers) > value_col_idx else "Value",
            "bar",
            value_suffix,
        )

        config = {
            "type": "bar",
            "data": {
                "labels": labels,
                "datasets": [
                    {
                        "label": legend_label,
                        "data": values,
                        "backgroundColor": colors,
                        "borderColor": [color.replace("0.8", "1") for color in colors],
                        "borderWidth": 1,
                    }
                ],
            },
            "options": {
                "responsive": True,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": title,
                        "font": {"size": 16, "weight": "bold"},
                    },
                    "legend": {"display": len(selected_headers) > 2, "position": "top"},
                    "datalabels": {
                        "anchor": "end",
                        "align": "top",
                        "formatter": f'(value) => value + "{value_suffix}"',
                        "font": {"weight": "bold"},
                    },
                },
                "scales": {
                    "x": {
                        "title": {
                            "display": True,
                            "text": x_axis_label,
                            "font": {"size": 14, "weight": "bold"},
                        }
                    },
                    "y": {
                        "beginAtZero": True,
                        "title": {
                            "display": True,
                            "text": y_axis_label,
                            "font": {"size": 14, "weight": "bold"},
                        },
                        "ticks": {"callback": f'(value) => value + "{value_suffix}"'},
                    },
                },
            },
        }

        qc.config = config
        return qc.get_url()

    def _generate_pie_chart(self, table_data: Dict) -> Optional[str]:
        """Generate a pie chart using QuickChart with enhanced labeling."""
        qc = QuickChart()
        qc.width = 700
        qc.height = 500
        qc.device_pixel_ratio = 2.0

        headers = table_data["headers"]
        rows = table_data["rows"]

        # Extract labels and values using validation
        labels = [row[0] for row in rows]
        raw_values = [row[1] if len(row) >= 2 else "0" for row in rows]

        # Validate and clean numeric data
        values, has_percentages = ChartDataValidator.validate_numeric_data(raw_values)

        # Generate title
        title = self._generate_chart_title(headers, "pie")

        # Get appropriate colors for pie chart
        colors = ChartDataValidator.get_color_palette(len(values), "pie")

        # Determine if values should show percentages
        "%" if has_percentages else ""

        # Calculate percentages for display
        sum(values)

        config = {
            "type": "pie",
            "data": {
                "labels": labels,
                "datasets": [
                    {
                        "data": values,
                        "backgroundColor": colors,
                        "borderColor": "#fff",
                        "borderWidth": 2,
                    }
                ],
            },
            "options": {
                "responsive": True,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": title,
                        "font": {"size": 16, "weight": "bold"},
                    },
                    "legend": {
                        "display": True,
                        "position": "right",
                        "labels": {"padding": 20, "usePointStyle": True},
                    },
                    "datalabels": {
                        "color": "#fff",
                        "font": {"weight": "bold", "size": 12},
                        "formatter": '(value, ctx) => { const total = ctx.dataset.data.reduce((a, b) => a + b, 0); const percentage = Math.round((value / total) * 100); return percentage + "%"; }',  # noqa: E501
                        "display": "(ctx) => ctx.dataset.data[ctx.dataIndex] > 0",
                    },
                },
            },
        }

        qc.config = config
        return qc.get_url()

    def _generate_line_chart(self, table_data: Dict) -> Optional[str]:
        """Generate a line chart using QuickChart with enhanced labeling."""
        qc = QuickChart()
        qc.width = 800
        qc.height = 500
        qc.device_pixel_ratio = 2.0

        headers = table_data["headers"]
        rows = table_data["rows"]

        # Extract labels (first column)
        labels = [row[0] for row in rows]

        # Extract datasets (remaining columns) with validation
        datasets = []

        # Get colors for line chart
        colors = ChartDataValidator.get_color_palette(len(headers) - 1, "line")

        for col_idx in range(1, len(headers)):
            raw_values = [row[col_idx] if len(row) > col_idx else "0" for row in rows]
            values, _ = ChartDataValidator.validate_numeric_data(raw_values)

            color = colors[(col_idx - 1) % len(colors)]
            datasets.append(
                {
                    "label": headers[col_idx],
                    "data": values,
                    "borderColor": color,
                    "backgroundColor": color.replace("1)", "0.1)"),
                    "fill": False,
                    "tension": 0.3,
                    "pointRadius": 5,
                    "pointHoverRadius": 7,
                    "pointBackgroundColor": color,
                    "pointBorderColor": "#fff",
                    "pointBorderWidth": 2,
                }
            )

        # Generate a more descriptive title
        title = self._generate_chart_title(headers, "line")

        config = {
            "type": "line",
            "data": {"labels": labels, "datasets": datasets},
            "options": {
                "responsive": True,
                "plugins": {
                    "title": {
                        "display": True,
                        "text": title,
                        "font": {"size": 16, "weight": "bold"},
                    },
                    "legend": {"display": len(datasets) > 1, "position": "top"},
                    "datalabels": {"display": False},
                },
                "scales": {
                    "x": {
                        "title": {
                            "display": True,
                            "text": headers[0] if headers else "Time Period",
                        }
                    },
                    "y": {
                        "beginAtZero": True,
                        "title": {
                            "display": True,
                            "text": self._enhance_axis_label("Value", "y"),
                            "font": {"size": 14, "weight": "bold"},
                        },
                    },
                },
                "interaction": {"intersect": False, "mode": "index"},
            },
        }

        qc.config = config
        return qc.get_url()

    def _get_single_header_title(self, header: str, chart_type: str) -> str:
        """Generate title for single header charts."""
        if chart_type == "pie":
            return f"{header} Distribution Analysis"
        elif chart_type == "bar":
            return f"{header} Comparison Chart"
        elif chart_type == "line":
            return f"{header} Trend Analysis"
        else:
            return f"{header} Analysis"

    def _get_pie_chart_title(self, category_header: str, value_header: str) -> str:
        """Generate title for pie charts."""
        if "focus" in value_header.lower():
            return f"Focus Level Distribution Across {category_header}"
        elif "detail" in value_header.lower():
            return f"Detail Level Breakdown by {category_header}"
        elif "%" in value_header or "percent" in value_header.lower():
            return f"{value_header} Share by {category_header}"
        else:
            return f"{value_header} Distribution by {category_header}"

    def _get_bar_chart_title(self, category_header: str, value_header: str) -> str:
        """Generate title for bar charts."""
        if "focus" in value_header.lower():
            return f"Focus Score Comparison: {category_header} Analysis"
        elif "detail" in value_header.lower():
            return f"Detail Level Analysis by {category_header}"
        elif "score" in value_header.lower() or "rating" in value_header.lower():
            return f"{value_header} Ratings Across {category_header}"
        elif "count" in value_header.lower() or "number" in value_header.lower():
            return f"{value_header} by {category_header}"
        elif "year" in value_header.lower():
            return f"{category_header} Timeline: {value_header}"
        elif "goal" in value_header.lower():
            return f"{category_header} Target Goals: {value_header}"
        elif "power" in value_header.lower():
            return f"{category_header} Power Analysis: {value_header}"
        else:
            return f"{value_header} Analysis by {category_header}"

    def _get_line_chart_title(self, category_header: str, value_header: str) -> str:
        """Generate title for line charts."""
        if (
            "time" in category_header.lower()
            or "date" in category_header.lower()
            or "period" in category_header.lower()
        ):
            return f"{value_header} Trends Over {category_header}"
        else:
            return f"{value_header} Evolution Across {category_header}"

    def _generate_chart_title(self, headers: List[str], chart_type: str) -> str:
        """
        Generate a meaningful and detailed chart title based on headers and chart type.

        Args:
            headers: List of column headers
            chart_type: Type of chart being generated

        Returns:
            str: Descriptive chart title
        """
        if not headers:
            return f"{chart_type.title()} Chart Analysis"

        # For single header, make it more descriptive
        if len(headers) == 1:
            return self._get_single_header_title(headers[0], chart_type)

        # For two headers, create enhanced relationship titles
        if len(headers) == 2:
            category_header = headers[0]
            value_header = headers[1]

            if chart_type == "pie":
                return self._get_pie_chart_title(category_header, value_header)
            elif chart_type == "bar":
                return self._get_bar_chart_title(category_header, value_header)
            elif chart_type == "line":
                return self._get_line_chart_title(category_header, value_header)
            else:
                return f"{category_header} vs {value_header} Analysis"

        # For multiple headers, create context-aware titles
        category_header = headers[0]
        if chart_type == "line":
            return f"Multi-Metric Trends Over {category_header}"
        else:
            return f"Comprehensive {category_header} Analysis"

    def _enhance_x_axis_label(self, label: str) -> str:
        """Enhance X-axis labels (typically categories)."""
        if label.lower() in ["category", "item", "name"]:
            return "Categories"
        elif any(word in label.lower() for word in ["time", "date", "period"]):
            return f"Time Period ({label})"
        elif any(word in label.lower() for word in ["user", "author"]):
            return f"Users ({label})"
        elif any(word in label.lower() for word in ["technology", "tool", "framework"]):
            return f"Technologies ({label})"
        elif any(word in label.lower() for word in ["method", "approach"]):
            return f"Methodologies ({label})"
        else:
            return f"{label} (Categories)"

    def _enhance_y_axis_label(self, label: str, suffix: str = "") -> str:
        """Enhance Y-axis labels (typically values/measurements)."""
        if label.lower() in ["value", "count", "number"]:
            return f'Measurement Values{" (" + suffix + ")" if suffix else ""}'
        elif "focus" in label.lower():
            return f'Focus Level (Score){" " + suffix if suffix else ""}'
        elif "detail" in label.lower():
            return f'Detail Level (Quantity){" " + suffix if suffix else ""}'
        elif any(word in label.lower() for word in ["score", "rating"]):
            return f'{label} (Rating Scale){" " + suffix if suffix else ""}'
        elif any(word in label.lower() for word in ["count", "number"]):
            return f'{label} (Quantity){" " + suffix if suffix else ""}'
        elif "%" in label or "percent" in label.lower() or suffix == "%":
            return f'{label} (Percentage){" " + suffix if suffix else ""}'
        elif "year" in label.lower():
            return f"{label} (Year)"
        elif "goal" in label.lower():
            return f'{label} (Target Value){" " + suffix if suffix else ""}'
        elif "power" in label.lower():
            return f'{label} (Power Units){" " + suffix if suffix else ""}'
        else:
            return f'{label} (Value){" " + suffix if suffix else ""}'

    def _enhance_axis_label(
        self, original_label: str, axis_type: str, suffix: str = ""
    ) -> str:
        """
        Enhance axis labels to be more descriptive and informative.

        Args:
            original_label: The original column header
            axis_type: 'x' or 'y' to indicate axis type
            suffix: Optional suffix like '%' for the label

        Returns:
            Enhanced, more descriptive axis label
        """
        label = original_label.strip()

        if axis_type == "x":
            return self._enhance_x_axis_label(label)
        elif axis_type == "y":
            return self._enhance_y_axis_label(label, suffix)

        return label

    def _enhance_pie_legend_label(self, label: str, suffix: str = "") -> str:
        """Enhance legend labels for pie charts."""
        if "focus" in label.lower():
            return f'Focus Distribution{" (" + suffix + ")" if suffix else ""}'
        elif "detail" in label.lower():
            return f'Detail Breakdown{" (" + suffix + ")" if suffix else ""}'
        elif "%" in label or "percent" in label.lower() or suffix == "%":
            return f'{label} Share{" (" + suffix + ")" if suffix else ""}'
        else:
            return f'{label} Distribution{" (" + suffix + ")" if suffix else ""}'

    def _enhance_bar_legend_label(self, label: str, suffix: str = "") -> str:
        """Enhance legend labels for bar charts."""
        if "focus" in label.lower():
            return f'Focus Score{" (" + suffix + ")" if suffix else ""}'
        elif "detail" in label.lower():
            return f'Detail Level{" (" + suffix + ")" if suffix else ""}'
        elif any(word in label.lower() for word in ["count", "number"]):
            return f'{label}{" (" + suffix + ")" if suffix else ""}'
        elif any(word in label.lower() for word in ["score", "rating"]):
            return f'{label} Rating{" (" + suffix + ")" if suffix else ""}'
        elif "year" in label.lower():
            return f"{label} (Timeline)"
        elif "goal" in label.lower():
            return f'{label} Target{" (" + suffix + ")" if suffix else ""}'
        elif "power" in label.lower():
            return f'{label} Capacity{" (" + suffix + ")" if suffix else ""}'
        else:
            return f'{label} Measurement{" (" + suffix + ")" if suffix else ""}'

    def _enhance_line_legend_label(self, label: str, suffix: str = "") -> str:
        """Enhance legend labels for line charts."""
        if "focus" in label.lower():
            return f'Focus Trends{" (" + suffix + ")" if suffix else ""}'
        elif "detail" in label.lower():
            return f'Detail Evolution{" (" + suffix + ")" if suffix else ""}'
        else:
            return f'{label} Over Time{" (" + suffix + ")" if suffix else ""}'

    def _enhance_legend_label(
        self, original_label: str, chart_type: str, suffix: str = ""
    ) -> str:
        """
        Enhance legend labels to be more descriptive and informative.

        Args:
            original_label: The original column header
            chart_type: Type of chart ('bar', 'pie', 'line')
            suffix: Optional suffix like '%' for the label

        Returns:
            Enhanced, more descriptive legend label
        """
        label = original_label.strip()

        if chart_type == "pie":
            return self._enhance_pie_legend_label(label, suffix)
        elif chart_type == "bar":
            return self._enhance_bar_legend_label(label, suffix)
        elif chart_type == "line":
            return self._enhance_line_legend_label(label, suffix)

        # Fallback
        return f'{label}{" (" + suffix + ")" if suffix else ""}'


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
