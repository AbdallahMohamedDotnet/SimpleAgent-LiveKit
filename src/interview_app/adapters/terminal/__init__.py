"""Terminal presentation adapter for the read-only results and status commands."""

from interview_app.adapters.terminal import results_json, results_text
from interview_app.adapters.terminal.sanitize import sanitize_block, sanitize_line

__all__ = ["results_json", "results_text", "sanitize_block", "sanitize_line"]
