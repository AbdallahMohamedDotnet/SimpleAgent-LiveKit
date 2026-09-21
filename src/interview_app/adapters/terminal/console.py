"""Standard input/output implementation of the interactive console boundary."""

from __future__ import annotations


class OperatorCancelled(Exception):
    """Raised when the operator closes input or asks to leave the current question."""


class StdConsole:
    """Read operator answers from stdin and write reports to stdout."""

    def write(self, message: str) -> None:
        print(message, flush=True)

    def prompt(self, message: str) -> str:
        try:
            return input(message)
        except EOFError as error:
            raise OperatorCancelled("Input stream closed.") from error
