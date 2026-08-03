"""Presentation layer: timestamped HTML and CSV renderers."""

from .model import PipelineResult
from .render import (
    CSV_COLUMNS,
    build_csv_rows,
    build_missing_data_rows,
    build_ranked_rows,
    build_summary,
    render_csv,
    render_html,
    write_report_and_csv,
)

__all__ = [
    "PipelineResult",
    "CSV_COLUMNS",
    "build_csv_rows",
    "build_missing_data_rows",
    "build_ranked_rows",
    "build_summary",
    "render_csv",
    "render_html",
    "write_report_and_csv",
]
