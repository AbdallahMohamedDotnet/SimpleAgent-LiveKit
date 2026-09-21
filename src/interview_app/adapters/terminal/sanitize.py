"""Neutralize untrusted text before it reaches an operator terminal.

Candidate speech, model responses and stored names are untrusted input. Written verbatim to a
terminal they could emit ANSI escape sequences that rewrite earlier output, hide text, or spoof
command results. Every untrusted value is therefore escaped here before rendering. The escapes are
readable rather than reversible: `\\x1b` in rendered output means the source contained that control
character, not that it contained those four literal characters.
"""

import unicodedata
from typing import Final

_UNSAFE_CATEGORIES: Final = frozenset({"Cc", "Cf", "Co", "Cs", "Cn"})


def sanitize_line(value: str) -> str:
    """Return the value as one terminal-safe line, escaping newlines as well."""
    return "".join(_safe(character, keep_newline=False) for character in value)


def sanitize_block(value: str) -> str:
    """Return terminal-safe multi-line text; only the line feed survives unescaped."""
    return "".join(_safe(character, keep_newline=True) for character in value)


def _safe(character: str, *, keep_newline: bool) -> str:
    if character == "\n":
        return "\n" if keep_newline else "\\n"
    if unicodedata.category(character) not in _UNSAFE_CATEGORIES:
        return character
    codepoint = ord(character)
    return f"\\x{codepoint:02x}" if codepoint < 0x100 else f"\\u{codepoint:04x}"
