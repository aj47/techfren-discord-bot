"""
Chart rendering module for Discord bot using Seaborn Objects interface.
Detects markdown tables in LLM responses and converts them to chart images.
"""

import re
import logging
import io
import os
import glob
from typing import List, Dict, Tuple, Optional
import pandas as pd
import seaborn as sns
import seaborn.objects as so
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import warnings

logger = logging.getLogger(__name__)

# Set matplotlib to use non-interactive backend
plt.switch_backend('Agg')

# Suppress matplotlib categorical units warning
warnings.filterwarnings('ignore', category=UserWarning, module='matplotlib.category')

# Register local fonts from the fonts directory
def _register_local_fonts():
    """Register fonts from the local fonts directory."""
    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    fonts_dir = os.path.join(script_dir, 'fonts')

    if not os.path.exists(fonts_dir):
        logger.warning("Local fonts directory not found at %s", fonts_dir)
        return

    # Find all font files in the fonts directory
    font_files = glob.glob(os.path.join(fonts_dir, '*.otf')) + glob.glob(os.path.join(fonts_dir, '*.ttf'))

    if not font_files:
        logger.warning("No font files found in %s", fonts_dir)
        return

    # Register each font file
    for font_file in font_files:
        try:
            fm.fontManager.addfont(font_file)
            logger.info("Registered local font: %s", os.path.basename(font_file))
        except Exception as e:
            logger.warning("Failed to register font %s: %s", font_file, e)

    logger.info("Registered %d local font(s) from %s", len(font_files), fonts_dir)

# Register fonts on module load
_register_local_fonts()


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

                value = ChartDataValidator._try_direct_conversion(numeric_str)
                if value is not None:
                    cleaned_values.append(value)
                    continue

                value = ChartDataValidator._extract_number_from_text(numeric_str)
                if value is not None:
                    cleaned_values.append(value)
                    continue

                value = ChartDataValidator._map_text_to_number(clean_str)
                cleaned_values.append(value)

            except (ValueError, AttributeError, TypeError):
                cleaned_values.append(0.0)

        return cleaned_values, has_percentages


class ChartRenderer:
    """Handles detection and rendering of tables/charts from LLM responses."""

    TABLE_PATTERN = re.compile(
        r"(\|[^|\n]+\|[\r\n]+\|[\s\-:|]+\|[\r\n]+(?:\|[^|\n]+\|[\r\n]*)+)", re.MULTILINE
    )

    # Custom color scheme (0x96f theme)
    COLORS = {
        'background': '#000000',  # Pure black
        'foreground': '#FCFCFA',
        'border': '#666666',      # Grey for borders
        'blue': '#49CAE4',
        'bright_blue': '#64D2E8',
        'cyan': '#AEE8F4',
        'bright_cyan': '#BAEBF6',
        'green': '#BCDF59',
        'bright_green': '#C6E472',
        'purple': '#A093E2',
        'bright_purple': '#AEA3E6',
        'red': '#FF7272',
        'bright_red': '#FF8787',
        'yellow': '#FFCA58',
        'bright_yellow': '#FFD271',
        'white': '#FCFCFA',
    }

    # Chart color palette for bars/lines
    CHART_PALETTE = [
        '#49CAE4',  # blue
        '#BCDF59',  # green
        '#A093E2',  # purple
        '#FFCA58',  # yellow
        '#FF7272',  # red
        '#AEE8F4',  # cyan
        '#64D2E8',  # bright_blue
        '#C6E472',  # bright_green
    ]

    def __init__(self):
        """Initialize the chart renderer."""
        # Set dark theme with no grid
        sns.set_theme(style="dark")
        plt.rcParams.update({
            'figure.facecolor': self.COLORS['background'],
            'axes.facecolor': self.COLORS['background'],
            'axes.edgecolor': self.COLORS['foreground'],
            'axes.labelcolor': self.COLORS['foreground'],
            'text.color': self.COLORS['foreground'],
            'xtick.color': self.COLORS['foreground'],
            'ytick.color': self.COLORS['foreground'],
            'grid.color': self.COLORS['background'],  # Hide grid
            'grid.alpha': 0,  # Hide grid
            'font.family': 'monospace',  # Use monospace font
            'font.monospace': ['KH Interference TRIAL', 'IBM Plex Mono', 'DejaVu Sans Mono', 'Courier New', 'monospace'],
        })

    def _is_valid_data_table(self, table_text: str) -> bool:
        """
        Check if a table contains valid data for charting.

        Args:
            table_text: The markdown table text

        Returns:
            bool: True if this is a valid data table
        """
        lines = table_text.strip().split('\n')
        if len(lines) < 3:  # Need at least header, separator, and one data row
            return False

        # Parse the table to check its structure
        try:
            data = self._parse_markdown_table(table_text)
            if not data or not data.get('headers') or not data.get('rows'):
                return False

            headers = data['headers']
            rows = data['rows']

            # Rule 1: Must have meaningful headers (not generic placeholders)
            generic_headers = {'item', 'value', 'data', 'thing', 'stuff', 'info', 'detail', 'name', 'description'}
            header_lower = [h.lower().strip() for h in headers if h and h.strip()]

            # If all headers are too generic, it's probably not a data table
            if all(h in generic_headers or len(h) < 3 for h in header_lower):
                return False

            # Rule 2: Must have at least one column with quantifiable data
            has_quantifiable_data = False
            for row in rows:
                for i, cell in enumerate(row):
                    if cell and i < len(headers):
                        # Check if cell contains numbers, percentages, or quantifiable data
                        cell_clean = cell.replace('%', '').replace(',', '').replace('$', '').strip()
                        if cell_clean.replace('.', '').isdigit():
                            has_quantifiable_data = True
                            break
                        elif '%' in cell or '$' in cell or any(c.isdigit() for c in cell):
                            has_quantifiable_data = True
                            break
                if has_quantifiable_data:
                    break

            if not has_quantifiable_data:
                return False

            # Rule 3: Must have consistent column counts
            expected_cols = len(headers)
            for row in rows:
                if len(row) != expected_cols:
                    return False

            # Rule 4: Not all cells should be identical (avoid repetitive non-data tables)
            if len(rows) > 1:
                first_row_values = [cell.strip() for cell in rows[0] if cell]
                if all(len(set([row[i].strip() for row in rows if len(row) > i])) <= 1 for i in range(len(first_row_values))):
                    return False

            return True

        except Exception as e:
            logger.debug("Table validation error: %s", e)
            return False

    def _detect_requested_chart_type(self, user_query: str) -> Optional[str]:
        """
        Detect if user explicitly requested a specific chart type in their query.

        Returns chart type if found, None if user wants auto-detection.
        """
        if not user_query:
            return None

        query_lower = user_query.lower()

        # Map keywords to chart types
        chart_keywords = {
            'scatter': ['scatter', 'scatter plot', 'scatterplot', 'correlation plot'],
            'heatmap': ['heatmap', 'heat map', 'matrix'],
            'box': ['box', 'box plot', 'boxplot', 'distribution'],
            'histogram': ['histogram', 'frequency', 'hist'],
            'area': ['area', 'area chart', 'filled'],
            'pie': ['pie', 'pie chart'],
            'line': ['line', 'line chart', 'trend'],
            'bar': ['bar', 'bar chart', 'bar graph'],
        }

        # Check for explicit requests
        for chart_type, keywords in chart_keywords.items():
            for keyword in keywords:
                if keyword in query_lower:
                    logger.info("User explicitly requested '%s' chart type", chart_type)
                    return chart_type

        return None

    def extract_tables_for_rendering(self, content: str, user_query: str = "") -> Tuple[str, List[Dict]]:
        """
        Extract markdown tables from content and prepare them for rendering.

        Args:
            content: The LLM response text containing potential markdown tables
            user_query: The user's original query (to detect explicit chart type requests)

        Returns:
            Tuple of (cleaned_content, chart_data_list)
            - cleaned_content: Original content with tables replaced by placeholders
            - chart_data_list: List of dicts with 'file', 'type', 'placeholder' keys
        """
        tables = self.TABLE_PATTERN.findall(content)

        if not tables:
            # Log when no tables are found, especially if chart was requested
            if user_query and ("chart" in user_query.lower() or "graph" in user_query.lower()):
                logger.warning(f"No markdown tables found in response despite chart request. Response preview: {content[:200]}{'...' if len(content) > 200 else ''}")
            return content, []

        # Filter tables to only include valid data tables
        valid_tables = []
        for table in tables:
            if self._is_valid_data_table(table):
                valid_tables.append(table)
            else:
                logger.debug("Filtered out non-data table: %s", table[:100])

        tables = valid_tables

        if not tables:
            logger.info("No valid data tables found after filtering")
            return content, []

        logger.info("Found %d valid data table(s) in response", len(tables))

        # Check if user explicitly requested a chart type
        requested_type = self._detect_requested_chart_type(user_query)
        if requested_type:
            logger.info("Using user-requested chart type: %s", requested_type)

        chart_data_list = []
        cleaned_content = content

        for idx, table_text in enumerate(tables):
            try:
                table_data = self._parse_markdown_table(table_text)

                if not table_data:
                    logger.warning("Failed to parse table %s, skipping", idx + 1)
                    continue

                # Use requested type if specified, otherwise auto-detect
                chart_type = requested_type or self._infer_chart_type(table_data)

                chart_file = self._generate_chart_file(table_data, chart_type)

                if chart_file:
                    placeholder = f"[Chart {idx + 1}: {chart_type.title()}]"

                    cleaned_content = cleaned_content.replace(
                        table_text, placeholder, 1
                    )

                    chart_data_list.append(
                        {
                            "file": chart_file,
                            "type": chart_type,
                            "placeholder": placeholder,
                            "original_table": table_text,
                        }
                    )

                    logger.info("Generated %s chart for table %s", chart_type, idx + 1)
                else:
                    logger.warning("Failed to generate chart for table %s", idx + 1)

            except Exception as e:
                logger.error("Error processing table %s: %s", idx + 1, e, exc_info=True)
                continue

        return cleaned_content, chart_data_list

    def _parse_markdown_table(self, table_text: str) -> Optional[Dict]:
        """Parse a markdown table into structured data."""
        try:
            lines = [
                line.strip() for line in table_text.strip().split("\n") if line.strip()
            ]

            if len(lines) < 3:
                return None

            headers = [cell.strip() for cell in lines[0].split("|") if cell.strip()]

            rows = []
            for line in lines[2:]:
                cells = [cell.strip() for cell in line.split("|") if cell.strip()]
                if len(cells) == len(headers):
                    rows.append(cells)

            if not rows:
                return None

            return {"headers": headers, "rows": rows}

        except Exception as e:
            logger.error("Error parsing markdown table: %s", e)
            return None

    def _infer_chart_type(self, table_data: Dict) -> str:
        """
        Analyze table data to determine the best chart type.

        Supports: bar, pie, line, scatter, heatmap, box, histogram, area
        """
        headers = table_data["headers"]
        rows = table_data["rows"]

        # Check for heatmap: matrix of numeric data (3+ cols, 3+ rows, mostly numeric)
        if len(headers) >= 3 and len(rows) >= 3:
            if self._check_heatmap_suitability(headers, rows):
                return "heatmap"

        # Check for scatter: 2 numeric columns with correlation pattern
        if len(headers) == 2:
            patterns = self._analyze_data_patterns(rows)

            if patterns["both_numeric"] and len(rows) >= 5:
                return "scatter"

            if patterns["numeric_count"] / patterns["total_rows"] > 0.3:
                if self._check_pie_chart_suitability(rows, patterns["has_percentages"]):
                    return "pie"
                if patterns["has_time_data"] and len(rows) >= 3:
                    return "line"
                # Check for histogram: single value column with frequency data
                if self._check_histogram_suitability(rows):
                    return "histogram"
                return "bar"

        # Check for box plot: categorical + numeric data with distribution
        if len(headers) == 2 and len(rows) >= 5:
            if self._check_box_plot_suitability(headers, rows):
                return "box"

        # Multi-column data analysis
        if len(headers) >= 3:
            multi_data = self._analyze_multicolumn_data(headers, rows)

            if multi_data["first_col_time"] and len(multi_data["numeric_cols"]) >= 2:
                # Could be area chart if showing cumulative/filled data
                if self._check_area_chart_suitability(headers, rows):
                    return "area"
                return "line"
            elif len(multi_data["numeric_cols"]) >= 2:
                return "line"
            elif len(multi_data["numeric_cols"]) == 1:
                return "bar"

        if self._find_any_numeric_column(headers, rows):
            return "bar"

        if len(headers) >= 2 and len(rows) > 1:
            unique_values = set(str(row[0]) for row in rows if len(row) > 0)
            if len(unique_values) > 1 and len(unique_values) <= 10:
                return "bar"

        return "bar"

    def _analyze_data_patterns(self, rows: List[List[str]]) -> Dict[str, any]:
        """Analyze data patterns in table rows."""
        numeric_count = 0
        total_rows = len(rows)
        has_percentages = False
        has_time_data = False
        both_numeric = False

        # Check if both columns are numeric (for scatter plots)
        if len(rows) > 0 and len(rows[0]) >= 2:
            col1_numeric_count = 0
            col2_numeric_count = 0

            for row in rows:
                if len(row) >= 2:
                    # Check column 1
                    try:
                        clean_val1 = row[0].strip().replace(",", "").replace("$", "")
                        float(clean_val1)
                        col1_numeric_count += 1
                    except ValueError:
                        pass

                    # Check column 2
                    try:
                        clean_val2 = row[1].strip().replace("%", "").replace(",", "").replace("$", "")
                        float(clean_val2)
                        col2_numeric_count += 1
                    except ValueError:
                        pass

            # Both columns mostly numeric
            if col1_numeric_count >= total_rows * 0.8 and col2_numeric_count >= total_rows * 0.8:
                both_numeric = True

        for row in rows:
            if len(row) >= 2:
                value_str = row[1].strip()

                if "%" in value_str:
                    has_percentages = True

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
            "both_numeric": both_numeric,
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

    def _check_heatmap_suitability(self, headers: List[str], rows: List[List[str]]) -> bool:
        """Check if data is suitable for heatmap (matrix of numeric data)."""
        if len(headers) < 3 or len(rows) < 3:
            return False

        # Count numeric cells
        numeric_cells = 0
        total_cells = 0

        for row in rows:
            for cell_idx in range(1, min(len(row), len(headers))):  # Skip first column (labels)
                total_cells += 1
                try:
                    clean_val = str(row[cell_idx]).replace(",", "").replace("$", "").strip()
                    float(clean_val)
                    numeric_cells += 1
                except (ValueError, AttributeError):
                    pass

        # At least 70% of cells should be numeric
        return numeric_cells / max(total_cells, 1) >= 0.7

    def _check_box_plot_suitability(self, headers: List[str], rows: List[List[str]]) -> bool:
        """Check if data is suitable for box plot (categorical with numeric distribution)."""
        if len(headers) != 2 or len(rows) < 5:
            return False

        # First column should have repeated categories
        categories = {}
        for row in rows:
            if len(row) >= 2:
                category = str(row[0]).strip()
                categories[category] = categories.get(category, 0) + 1

        # Need multiple values per category for distribution
        has_distribution = any(count >= 3 for count in categories.values())

        # Second column should be numeric
        numeric_count = 0
        for row in rows:
            if len(row) >= 2:
                try:
                    clean_val = str(row[1]).replace(",", "").replace("$", "").strip()
                    float(clean_val)
                    numeric_count += 1
                except (ValueError, AttributeError):
                    pass

        return has_distribution and numeric_count / len(rows) >= 0.8

    def _check_histogram_suitability(self, rows: List[List[str]]) -> bool:
        """Check if data is suitable for histogram (frequency distribution)."""
        # Look for patterns like "Value | Frequency" or "Range | Count"
        if len(rows) < 3:
            return False

        # Second column should be all numeric (counts/frequencies)
        numeric_count = 0
        for row in rows:
            if len(row) >= 2:
                try:
                    clean_val = str(row[1]).replace(",", "").strip()
                    float(clean_val)
                    numeric_count += 1
                except (ValueError, AttributeError):
                    pass

        # First column might have ranges like "0-10", "10-20"
        has_ranges = any("-" in str(row[0]) for row in rows if len(row) > 0)

        return numeric_count / len(rows) >= 0.9 and (has_ranges or len(rows) >= 5)

    def _check_area_chart_suitability(self, headers: List[str], rows: List[List[str]]) -> bool:
        """Check if data is suitable for area chart (cumulative/stacked data)."""
        # Look for keywords suggesting cumulative or stacked data
        cumulative_keywords = ["cumulative", "total", "sum", "aggregate", "running"]

        for header in headers:
            if any(keyword in header.lower() for keyword in cumulative_keywords):
                return True

        return False

    def _analyze_multicolumn_data(
        self, headers: List[str], rows: List[List[str]]
    ) -> Dict[str, any]:
        """Analyze multi-column data for chart type determination."""
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

    def _generate_chart_file(
        self, table_data: Dict, chart_type: str
    ) -> Optional[io.BytesIO]:
        """
        Generate a chart image file for the given table data and chart type.

        Supported chart types:
        - bar: Bar chart
        - pie: Pie chart
        - line: Line chart
        - scatter: Scatter plot
        - heatmap: Heatmap matrix
        - box: Box plot
        - histogram: Histogram
        - area: Area chart
        """
        try:
            if chart_type == "bar":
                return self._generate_bar_chart(table_data)
            elif chart_type == "pie":
                return self._generate_pie_chart(table_data)
            elif chart_type == "line":
                return self._generate_line_chart(table_data)
            elif chart_type == "scatter":
                return self._generate_scatter_plot(table_data)
            elif chart_type == "heatmap":
                return self._generate_heatmap(table_data)
            elif chart_type == "box":
                return self._generate_box_plot(table_data)
            elif chart_type == "histogram":
                return self._generate_histogram(table_data)
            elif chart_type == "area":
                return self._generate_area_chart(table_data)
            else:
                logger.warning("Unknown chart type: %s", chart_type)
                return None

        except Exception as e:
            logger.error("Error generating %s chart: %s", chart_type, e, exc_info=True)
            return None

    def _generate_bar_chart(self, table_data: Dict) -> Optional[io.BytesIO]:
        """Generate a bar chart using Seaborn Objects interface."""
        headers = table_data["headers"]
        rows = table_data["rows"]

        label_col_idx = 0
        value_col_idx = 1

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

                if numeric_count / len(rows) > 0.3:
                    value_col_idx = col_idx
                    break

        labels = [
            str(row[label_col_idx]) if len(row) > label_col_idx else f"Item {i + 1}"
            for i, row in enumerate(rows)
        ]
        raw_values = []

        for row in rows:
            if len(row) > value_col_idx:
                value_str = str(row[value_col_idx])
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

        values, has_percentages = ChartDataValidator.validate_numeric_data(raw_values)

        df = pd.DataFrame({
            headers[label_col_idx]: labels,
            headers[value_col_idx]: values
        })

        title = self._generate_chart_title(
            [headers[label_col_idx], headers[value_col_idx]], "bar"
        )

        fig, ax = plt.subplots(figsize=(10, 6))
        fig.patch.set_facecolor(self.COLORS['background'])
        ax.set_facecolor(self.COLORS['background'])

        # Use custom color palette
        colors = self.CHART_PALETTE[:len(labels)]
        if len(labels) > len(self.CHART_PALETTE):
            colors = colors * (len(labels) // len(self.CHART_PALETTE) + 1)
            colors = colors[:len(labels)]

        # Create bar chart with rounded corners
        from matplotlib.patches import FancyBboxPatch

        bars = []
        bar_width = 0.6
        x_positions = range(len(labels))

        for i, (x_pos, value, color) in enumerate(zip(x_positions, values, colors)):
            # Create rounded rectangle for each bar
            rounded_bar = FancyBboxPatch(
                (x_pos - bar_width/2, 0),
                bar_width,
                value,
                boxstyle="round,pad=0.02",
                linewidth=1.5,
                edgecolor=self.COLORS['border'],
                facecolor=color,
                transform=ax.transData
            )
            ax.add_patch(rounded_bar)

            # Create a fake bar object for text positioning
            class FakeBar:  # pylint: disable=too-few-public-methods
                """Helper class for text positioning on charts."""
                def __init__(self, x, width, height):
                    self._x = x
                    self._width = width
                    self._height = height
                def get_x(self):
                    return self._x
                def get_width(self):
                    return self._width
                def get_height(self):
                    return self._height

            bars.append(FakeBar(x_pos - bar_width/2, bar_width, value))

        # Set title with custom color
        ax.set_title(title, fontsize=18, fontweight='bold', color=self.COLORS['foreground'], pad=20)

        # Remove y-axis
        ax.set_yticks([])
        ax.spines['left'].set_visible(False)

        # Style remaining spines
        ax.spines['bottom'].set_color(self.COLORS['foreground'])
        ax.spines['right'].set_visible(False)
        ax.spines['top'].set_visible(False)

        # Add value labels on top of bars
        for bar_rect in bars:
            height = bar_rect.get_height()
            ax.text(
                bar_rect.get_x() + bar_rect.get_width() / 2.,
                height + (max(values) * 0.02),  # Add tiny margin
                f'{height:.0f}',
                ha='center', va='bottom',
                color=self.COLORS['foreground'],
                fontsize=28,
                fontweight='bold'
            )

        # Set x-axis ticks and labels
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=45, ha='right', color=self.COLORS['foreground'], fontsize=20)

        # Set axis limits
        ax.set_xlim(-0.5, len(labels) - 0.5)  # Center bars on tick marks
        ax.set_ylim(0, max(values) * 1.1)  # Add padding at the top

        plt.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor=self.COLORS['background'])
        buf.seek(0)
        plt.close(fig)

        return buf

    def _generate_pie_chart(self, table_data: Dict) -> Optional[io.BytesIO]:
        """Generate a pie chart using matplotlib (Seaborn doesn't have pie charts)."""
        headers = table_data["headers"]
        rows = table_data["rows"]

        labels = [row[0] for row in rows]
        raw_values = [row[1] if len(row) >= 2 else "0" for row in rows]

        values, has_percentages = ChartDataValidator.validate_numeric_data(raw_values)

        title = self._generate_chart_title(headers, "pie")

        fig, ax = plt.subplots(figsize=(10, 8))
        fig.patch.set_facecolor(self.COLORS['background'])
        ax.set_facecolor(self.COLORS['background'])

        # Use custom color palette
        colors = self.CHART_PALETTE[:len(values)]
        if len(values) > len(self.CHART_PALETTE):
            colors = colors * (len(values) // len(self.CHART_PALETTE) + 1)
            colors = colors[:len(values)]

        wedges, texts, autotexts = ax.pie(
            values,
            labels=labels,
            autopct='%1.1f%%',
            startangle=90,
            colors=colors,
            textprops={'color': self.COLORS['foreground'], 'fontsize': 24}
        )

        # Style percentage labels
        for autotext in autotexts:
            autotext.set_color(self.COLORS['background'])
            autotext.set_fontweight('bold')
            autotext.set_fontsize(26)

        ax.set_title(title, fontsize=18, fontweight='bold', color=self.COLORS['foreground'], pad=20)

        plt.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor=self.COLORS['background'])
        buf.seek(0)
        plt.close(fig)

        return buf

    def _generate_line_chart(self, table_data: Dict) -> Optional[io.BytesIO]:
        """Generate a line chart using Seaborn Objects interface."""
        headers = table_data["headers"]
        rows = table_data["rows"]

        labels = [row[0] for row in rows]

        data_dict = {headers[0]: labels}
        for col_idx in range(1, len(headers)):
            raw_values = [row[col_idx] if len(row) > col_idx else "0" for row in rows]
            values, _ = ChartDataValidator.validate_numeric_data(raw_values)
            data_dict[headers[col_idx]] = values

        df = pd.DataFrame(data_dict)

        df_melted = df.melt(
            id_vars=[headers[0]],
            var_name='Series',
            value_name='Value'
        )

        title = self._generate_chart_title(headers, "line")

        fig, ax = plt.subplots(figsize=(10, 6))
        fig.patch.set_facecolor(self.COLORS['background'])
        ax.set_facecolor(self.COLORS['background'])

        # Get unique series
        series_list = df_melted['Series'].unique()

        # Plot each series with custom colors
        for idx, series in enumerate(series_list):
            series_data = df_melted[df_melted['Series'] == series]
            color = self.CHART_PALETTE[idx % len(self.CHART_PALETTE)]

            ax.plot(
                series_data[headers[0]],
                series_data['Value'],
                color=color,
                linewidth=2.5,
                marker='o',
                markersize=8,
                label=series,
                markeredgecolor=self.COLORS['foreground'],
                markeredgewidth=1
            )

        # Set title and labels
        ax.set_title(title, fontsize=18, fontweight='bold', color=self.COLORS['foreground'], pad=20)
        ax.set_xlabel(headers[0], fontsize=24, color=self.COLORS['foreground'])

        # Remove y-axis
        ax.set_yticks([])
        ax.spines['left'].set_visible(False)

        # Style remaining spines
        ax.spines['bottom'].set_color(self.COLORS['foreground'])
        ax.spines['right'].set_visible(False)
        ax.spines['top'].set_visible(False)

        # Add legend if multiple series
        if len(series_list) > 1:
            legend = ax.legend(
                facecolor=self.COLORS['background'],
                edgecolor=self.COLORS['foreground'],
                labelcolor=self.COLORS['foreground'],
                fontsize=22
            )
            legend.get_frame().set_linewidth(1.5)

        plt.xticks(rotation=45, ha='right', color=self.COLORS['foreground'], fontsize=20)
        plt.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor=self.COLORS['background'])
        buf.seek(0)
        plt.close(fig)

        return buf

    def _generate_scatter_plot(self, table_data: Dict) -> Optional[io.BytesIO]:
        """Generate a scatter plot for two numeric variables."""
        headers = table_data["headers"]
        rows = table_data["rows"]

        # Extract X and Y values
        x_values = []
        y_values = []

        for row in rows:
            if len(row) >= 2:
                try:
                    x_val = float(str(row[0]).replace(",", "").replace("$", "").strip())
                    y_val = float(str(row[1]).replace(",", "").replace("$", "").strip())
                    x_values.append(x_val)
                    y_values.append(y_val)
                except (ValueError, AttributeError):
                    continue

        if not x_values or not y_values:
            return None

        df = pd.DataFrame({headers[0]: x_values, headers[1]: y_values})

        title = f"{headers[0]} vs {headers[1]} Correlation"

        fig, ax = plt.subplots(figsize=(14, 10))

        # Create scatter plot
        ax.scatter(df[headers[0]], df[headers[1]],
                  color=self.COLORS['primary'],
                  s=200,  # Point size
                  alpha=0.7,
                  edgecolors=self.COLORS['foreground'],
                  linewidths=2)

        ax.set_title(title, fontsize=18, fontweight='bold', color=self.COLORS['foreground'], pad=20)
        ax.set_xlabel(headers[0], fontsize=24, color=self.COLORS['foreground'])
        ax.set_ylabel(headers[1], fontsize=24, color=self.COLORS['foreground'])

        ax.set_facecolor(self.COLORS['background'])
        fig.patch.set_facecolor(self.COLORS['background'])

        ax.tick_params(colors=self.COLORS['foreground'], labelsize=20)
        ax.spines['bottom'].set_color(self.COLORS['foreground'])
        ax.spines['left'].set_color(self.COLORS['foreground'])
        ax.spines['right'].set_visible(False)
        ax.spines['top'].set_visible(False)

        plt.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor=self.COLORS['background'])
        buf.seek(0)
        plt.close(fig)

        return buf

    def _generate_heatmap(self, table_data: Dict) -> Optional[io.BytesIO]:
        """Generate a heatmap for matrix data."""
        headers = table_data["headers"]
        rows = table_data["rows"]

        # Build numeric matrix
        row_labels = [row[0] for row in rows]
        data_matrix = []

        for row in rows:
            row_values = []
            for col_idx in range(1, len(headers)):
                if len(row) > col_idx:
                    try:
                        val = float(str(row[col_idx]).replace(",", "").replace("$", "").strip())
                        row_values.append(val)
                    except (ValueError, AttributeError):
                        row_values.append(0)
                else:
                    row_values.append(0)
            data_matrix.append(row_values)

        df = pd.DataFrame(data_matrix, columns=headers[1:], index=row_labels)

        title = f"{headers[0]} Heatmap Analysis"

        fig, ax = plt.subplots(figsize=(14, 10))

        # Create heatmap with custom colors
        sns.heatmap(df,
                   annot=True,
                   fmt='.1f',
                   cmap='YlOrRd',
                   cbar_kws={'label': 'Value'},
                   linewidths=1,
                   linecolor=self.COLORS['background'],
                   ax=ax,
                   annot_kws={'size': 16, 'color': self.COLORS['background']})

        ax.set_title(title, fontsize=18, fontweight='bold', color=self.COLORS['foreground'], pad=20)
        ax.set_xlabel('', fontsize=20)
        ax.set_ylabel('', fontsize=20)

        fig.patch.set_facecolor(self.COLORS['background'])
        ax.set_facecolor(self.COLORS['background'])

        plt.xticks(color=self.COLORS['foreground'], fontsize=18, rotation=45, ha='right')
        plt.yticks(color=self.COLORS['foreground'], fontsize=18, rotation=0)

        plt.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor=self.COLORS['background'])
        buf.seek(0)
        plt.close(fig)

        return buf

    def _generate_box_plot(self, table_data: Dict) -> Optional[io.BytesIO]:
        """Generate a box plot for categorical distributions."""
        headers = table_data["headers"]
        rows = table_data["rows"]

        # Organize data by category
        categories = []
        values = []

        for row in rows:
            if len(row) >= 2:
                try:
                    category = str(row[0]).strip()
                    value = float(str(row[1]).replace(",", "").replace("$", "").strip())
                    categories.append(category)
                    values.append(value)
                except (ValueError, AttributeError):
                    continue

        if not categories or not values:
            return None

        df = pd.DataFrame({headers[0]: categories, headers[1]: values})

        title = f"{headers[1]} Distribution by {headers[0]}"

        fig, ax = plt.subplots(figsize=(14, 10))

        # Create box plot
        sns.boxplot(data=df, x=headers[0], y=headers[1],
                   color=self.COLORS['primary'],
                   ax=ax,
                   linewidth=2)

        ax.set_title(title, fontsize=18, fontweight='bold', color=self.COLORS['foreground'], pad=20)
        ax.set_xlabel(headers[0], fontsize=24, color=self.COLORS['foreground'])
        ax.set_ylabel(headers[1], fontsize=24, color=self.COLORS['foreground'])

        ax.set_facecolor(self.COLORS['background'])
        fig.patch.set_facecolor(self.COLORS['background'])

        ax.tick_params(colors=self.COLORS['foreground'], labelsize=20)
        plt.xticks(rotation=45, ha='right')

        ax.spines['bottom'].set_color(self.COLORS['foreground'])
        ax.spines['left'].set_color(self.COLORS['foreground'])
        ax.spines['right'].set_visible(False)
        ax.spines['top'].set_visible(False)

        plt.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor=self.COLORS['background'])
        buf.seek(0)
        plt.close(fig)

        return buf

    def _generate_histogram(self, table_data: Dict) -> Optional[io.BytesIO]:
        """Generate a histogram for frequency distribution."""
        headers = table_data["headers"]
        rows = table_data["rows"]

        labels = [str(row[0]).strip() for row in rows]
        raw_values = [row[1] if len(row) > 1 else "0" for row in rows]
        values, _ = ChartDataValidator.validate_numeric_data(raw_values)

        title = f"{headers[1]} Frequency Distribution"

        fig, ax = plt.subplots(figsize=(14, 10))

        # Create histogram-style bar chart
        ax.bar(labels, values,
              color=self.COLORS['primary'],
              edgecolor=self.COLORS['foreground'],
              linewidth=2)

        ax.set_title(title, fontsize=18, fontweight='bold', color=self.COLORS['foreground'], pad=20)
        ax.set_xlabel(headers[0], fontsize=24, color=self.COLORS['foreground'])
        ax.set_ylabel(headers[1], fontsize=24, color=self.COLORS['foreground'])

        ax.set_facecolor(self.COLORS['background'])
        fig.patch.set_facecolor(self.COLORS['background'])

        ax.tick_params(colors=self.COLORS['foreground'], labelsize=20)
        plt.xticks(rotation=45, ha='right')

        ax.spines['bottom'].set_color(self.COLORS['foreground'])
        ax.spines['left'].set_color(self.COLORS['foreground'])
        ax.spines['right'].set_visible(False)
        ax.spines['top'].set_visible(False)

        plt.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor=self.COLORS['background'])
        buf.seek(0)
        plt.close(fig)

        return buf

    def _generate_area_chart(self, table_data: Dict) -> Optional[io.BytesIO]:
        """Generate an area chart (filled line chart)."""
        headers = table_data["headers"]
        rows = table_data["rows"]

        labels = [row[0] for row in rows]

        data_dict = {headers[0]: labels}
        for col_idx in range(1, len(headers)):
            raw_values = [row[col_idx] if len(row) > col_idx else "0" for row in rows]
            values, _ = ChartDataValidator.validate_numeric_data(raw_values)
            data_dict[headers[col_idx]] = values

        df = pd.DataFrame(data_dict)

        title = self._generate_chart_title(headers, "area")

        fig, ax = plt.subplots(figsize=(14, 10))

        # Create filled area chart
        x_positions = range(len(labels))

        # Plot each series
        for col_idx in range(1, len(headers)):
            ax.fill_between(x_positions, df[headers[col_idx]],
                           alpha=0.5,
                           label=headers[col_idx],
                           linewidth=3)
            ax.plot(x_positions, df[headers[col_idx]],
                   linewidth=3,
                   marker='o',
                   markersize=10)

        ax.set_xticks(x_positions)
        ax.set_xticklabels(labels)

        ax.set_title(title, fontsize=18, fontweight='bold', color=self.COLORS['foreground'], pad=20)
        ax.set_xlabel(headers[0], fontsize=24, color=self.COLORS['foreground'])
        ax.set_ylabel('Value', fontsize=24, color=self.COLORS['foreground'])

        ax.set_facecolor(self.COLORS['background'])
        fig.patch.set_facecolor(self.COLORS['background'])

        ax.tick_params(colors=self.COLORS['foreground'], labelsize=20)
        ax.spines['bottom'].set_color(self.COLORS['foreground'])
        ax.spines['left'].set_color(self.COLORS['foreground'])
        ax.spines['right'].set_visible(False)
        ax.spines['top'].set_visible(False)

        # Add legend if multiple series
        if len(headers) > 2:
            legend = ax.legend(
                facecolor=self.COLORS['background'],
                edgecolor=self.COLORS['foreground'],
                labelcolor=self.COLORS['foreground'],
                fontsize=22
            )
            legend.get_frame().set_linewidth(1.5)

        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor=self.COLORS['background'])
        buf.seek(0)
        plt.close(fig)

        return buf

    def _generate_chart_title(self, headers: List[str], chart_type: str) -> str:
        """Generate a meaningful chart title based on headers and chart type."""
        if not headers:
            return f"{chart_type.title()} Chart Analysis"

        if len(headers) == 1:
            return self._get_single_header_title(headers[0], chart_type)

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

        category_header = headers[0]
        if chart_type == "line":
            return f"Multi-Metric Trends Over {category_header}"
        else:
            return f"Comprehensive {category_header} Analysis"

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


_chart_renderer = ChartRenderer()


def extract_tables_for_rendering(content: str, user_query: str = "") -> Tuple[str, List[Dict]]:
    """
    Convenience function to extract and render tables from content.

    Args:
        content: LLM response text
        user_query: The user's original query (to detect explicit chart type requests)

    Returns:
        Tuple of (cleaned_content, chart_data_list)
    """
    return _chart_renderer.extract_tables_for_rendering(content, user_query)
