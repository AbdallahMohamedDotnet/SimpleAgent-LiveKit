"""Server-side presentation adapter for local results."""

from interview_app.adapters.web.results import (
    ResultsHttpApplication,
    ResultsHttpServer,
    create_results_server,
)

__all__ = ["ResultsHttpApplication", "ResultsHttpServer", "create_results_server"]
