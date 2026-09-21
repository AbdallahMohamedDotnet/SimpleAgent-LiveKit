#!/usr/bin/env python3
"""Single entry point for the local voice interview application.

Run `./run.sh` (or `uv run python main.py`) to open the operator menu; every command the
application provides is also available individually through the `interview` CLI.
"""

from interview_app.entrypoints.menu import main

if __name__ == "__main__":
    raise SystemExit(main())
