"""Localhost operator console process boundary."""

import asyncio

from interview_app.adapters.web import create_control_server
from interview_app.bootstrap import build_control_application
from interview_app.settings import ControlSettings


def run_control(settings: ControlSettings) -> None:
    database, application = build_control_application(settings)
    asyncio.run(database.migrate())
    server = create_control_server(application, host=settings.host, port=settings.port)
    actual_host, actual_port = server.server_address[:2]
    if isinstance(actual_host, bytes):
        actual_host = actual_host.decode("ascii")
    print(f"control_url=http://{actual_host}:{actual_port}/interviews/new", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
