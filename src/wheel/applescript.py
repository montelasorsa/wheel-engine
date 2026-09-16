"""AppleScript string quoting, shared by the two modules that drive osascript.

`deliver` composes a Mail message and `notify` posts a notification. Both build
AppleScript source by interpolating text nobody vetted -- a file path, a step
name, an error message from a failing command. Interpolating into a language is
where injection bugs live, and the fix is identical in both places, so it is
written once here rather than twice with one of them slightly wrong.
"""

from __future__ import annotations


def quote(value: str) -> str:
    """One AppleScript string literal, with the two characters that bite it.

    Backslash first, then the quote. Reversing the order would escape the
    backslashes the quote replacement just introduced, and a path containing a
    quote would end the literal early.
    """

    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
