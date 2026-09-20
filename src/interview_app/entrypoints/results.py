"""Localhost results server process boundary."""

import asyncio

from interview_app.adapters.web import create_results_server
from interview_app.bootstrap import build_results_application
from interview_app.settings import ResultsSettings


def run_results(settings: ResultsSettings) -> None:
    database, application = build_results_application(settings)
    asyncio.run(database.migrate())
    server = create_results_server(application, host=settings.host, port=settings.port)
    actual_host, actual_port = server.server_address[:2]
    if isinstance(actual_host, bytes):
        actual_host = actual_host.decode("ascii")
    print(f"results_url=http://{actual_host}:{actual_port}/results", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
