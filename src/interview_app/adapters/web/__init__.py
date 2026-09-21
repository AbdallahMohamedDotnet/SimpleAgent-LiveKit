"""Server-side presentation adapter for local results."""

from interview_app.adapters.web.control import (
    ControlHttpApplication,
    ControlHttpServer,
    create_control_server,
)
from interview_app.adapters.web.results import (
    ResultsHttpApplication,
    ResultsHttpServer,
    create_results_server,
)

__all__ = ["ResultsHttpApplication", "ResultsHttpServer", "create_results_server"]
__all__ = [
    "ControlHttpApplication",
    "ControlHttpServer",
    "ResultsHttpApplication",
    "ResultsHttpServer",
    "create_control_server",
    "create_results_server",
]
