"""Read a module's manifest out of its Astro component.

A module is one file. ``index.astro`` carries both the markup and an
``export const manifest`` describing the fields the builder shows. Astro hoists
top-level exports out of the render function into module scope, so the website
build and the preview import that object directly. The CLI has no JavaScript
runtime, so it reads the same declaration by slicing the object literal out of
the frontmatter.

That means the manifest has to be a literal, not something computed at runtime.
Anything else is rejected with a message saying so, rather than being silently
skipped.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

#: The export the manifest must be bound to.
MANIFEST_EXPORT = "manifest"

_FRONTMATTER = re.compile(r"^\s*---\r?\n(.*?)\r?\n\s*---", re.DOTALL)
_EXPORT = re.compile(
    r"export\s+const\s+" + MANIFEST_EXPORT + r"\s*(?::[^=]*?)?=\s*",
    re.DOTALL,
)


class ManifestError(ValueError):
    """A module's manifest is missing or cannot be read."""


def frontmatter(source: str) -> str | None:
    """The component script between the leading `---` fences."""
    match = _FRONTMATTER.match(source)
    return match.group(1) if match else None


def _object_literal(text: str, start: int) -> str:
    """Slice a balanced ``{...}`` starting at ``start``.

    Counts braces while stepping over strings, template literals and comments,
    so a `}` inside `"a}b"` or a comment does not end the object early. This
    also drops any `satisfies ModuleManifest` suffix for free, since the slice
    stops at the closing brace.
    """
    depth = 0
    index = start
    end = len(text)

    while index < end:
        char = text[index]

        if char in "\"'`":
            quote = char
            index += 1
            while index < end:
                if text[index] == "\\":
                    index += 2
                    continue
                if text[index] == quote:
                    break
                index += 1
            index += 1
            continue

        if char == "/" and index + 1 < end:
            following = text[index + 1]
            if following == "/":
                newline = text.find("\n", index)
                index = end if newline == -1 else newline + 1
                continue
            if following == "*":
                close = text.find("*/", index + 2)
                index = end if close == -1 else close + 2
                continue

        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]

        index += 1

    raise ManifestError(
        f"The `{MANIFEST_EXPORT}` object is never closed. Check for a missing `}}`."
    )


_IDENT = re.compile(r"[A-Za-z_$][\w$]*")
_NUMBER = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?")


class _LiteralParser:
    """Read the subset of JS object literals a module manifest is allowed to be.

    Prettier writes single quotes, unquoted keys and trailing commas. Those are
    not JSON, and pulling in a third-party parser just to accept them would
    leave every existing `caraer` install broken until it was reinstalled.
    """

    def __init__(self, text: str) -> None:
        self.text = text
        self.index = 0

    def parse(self) -> Any:
        value = self._value()
        self._skip()
        if self.index < len(self.text):
            raise ValueError(f"Unexpected {self.text[self.index]!r} after the object.")
        return value

    def _skip(self) -> None:
        text = self.text
        end = len(text)
        while self.index < end:
            char = text[self.index]
            if char.isspace():
                self.index += 1
                continue
            if char == "/" and self.index + 1 < end:
                following = text[self.index + 1]
                if following == "/":
                    newline = text.find("\n", self.index)
                    self.index = end if newline == -1 else newline + 1
                    continue
                if following == "*":
                    close = text.find("*/", self.index + 2)
                    if close == -1:
                        raise ValueError("Unclosed comment.")
                    self.index = close + 2
                    continue
            break

    def _peek(self) -> str:
        self._skip()
        return self.text[self.index] if self.index < len(self.text) else ""

    def _value(self) -> Any:
        char = self._peek()
        if char == "{":
            return self._object()
        if char == "[":
            return self._array()
        if char in "\"'":
            return self._string()
        if char == "`":
            raise ValueError("Template literals are not a plain value.")
        matched, keyword = self._keyword()
        if matched:
            return keyword
        number = _NUMBER.match(self.text, self.index)
        if number:
            self.index = number.end()
            raw = number.group()
            return float(raw) if any(c in raw for c in ".eE") else int(raw)
        raise ValueError(
            "Expected a plain value. Variables, spreads and function calls are not allowed."
        )

    def _object(self) -> dict[str, Any]:
        self.index += 1
        out: dict[str, Any] = {}
        while True:
            char = self._peek()
            if char == "}":
                self.index += 1
                return out
            key = self._key()
            if self._peek() != ":":
                raise ValueError(f"Expected ':' after {key!r}.")
            self.index += 1
            out[key] = self._value()
            char = self._peek()
            if char == ",":
                self.index += 1
                continue
            if char == "}":
                self.index += 1
                return out
            raise ValueError("Expected ',' or '}' in the object.")

    def _array(self) -> list[Any]:
        self.index += 1
        out: list[Any] = []
        while True:
            char = self._peek()
            if char == "]":
                self.index += 1
                return out
            out.append(self._value())
            char = self._peek()
            if char == ",":
                self.index += 1
                continue
            if char == "]":
                self.index += 1
                return out
            raise ValueError("Expected ',' or ']' in the array.")

    def _keyword(self) -> tuple[bool, Any]:
        for word, value in (("true", True), ("false", False), ("null", None)):
            if not self.text.startswith(word, self.index):
                continue
            after = self.index + len(word)
            if after < len(self.text) and (self.text[after].isalnum() or self.text[after] == "_"):
                continue
            self.index = after
            return True, value
        return False, None

    def _key(self) -> str:
        char = self._peek()
        if char in "\"'":
            return self._string()
        match = _IDENT.match(self.text, self.index)
        if not match:
            raise ValueError("Expected an object key.")
        self.index = match.end()
        return match.group()

    def _string(self) -> str:
        quote = self.text[self.index]
        self.index += 1
        chars: list[str] = []
        text = self.text
        end = len(text)
        while self.index < end:
            char = text[self.index]
            if char == "\\":
                if self.index + 1 >= end:
                    raise ValueError("Unterminated string.")
                nxt = text[self.index + 1]
                if nxt == "u" and self.index + 5 < end:
                    hex_digits = text[self.index + 2 : self.index + 6]
                    if re.fullmatch(r"[0-9a-fA-F]{4}", hex_digits):
                        chars.append(chr(int(hex_digits, 16)))
                        self.index += 6
                        continue
                chars.append(
                    {"n": "\n", "t": "\t", "r": "\r"}.get(nxt, nxt)
                )
                self.index += 2
                continue
            if char == quote:
                self.index += 1
                return "".join(chars)
            if char == "\n":
                raise ValueError("Unterminated string.")
            chars.append(char)
            self.index += 1
        raise ValueError("Unterminated string.")


def _loads_literal(text: str) -> Any:
    return _LiteralParser(text).parse()


def parse_manifest_source(source: str) -> dict[str, Any]:
    """Read the manifest out of one Astro component's source."""
    script = frontmatter(source)
    if script is None:
        raise ManifestError(
            "No `---` frontmatter block. A module declares its fields with "
            f"`export const {MANIFEST_EXPORT} = {{...}}` at the top of index.astro."
        )

    match = _EXPORT.search(script)
    if not match:
        raise ManifestError(
            f"No `export const {MANIFEST_EXPORT}` in the frontmatter. "
            "That export is how the builder learns which fields to show."
        )

    # Bound to something other than an object literal, such as a function call.
    if not script[match.end() :].lstrip().startswith("{"):
        raise ManifestError(
            f"`{MANIFEST_EXPORT}` must be a plain literal the CLI can read without "
            "running your code, so no variables, spreads or function calls."
        )

    literal = _object_literal(script, script.index("{", match.end()))

    try:
        parsed = _loads_literal(literal)
    except ValueError as exc:
        raise ManifestError(
            f"Could not read the `{MANIFEST_EXPORT}` object: {exc}. It has to be a "
            "plain literal the CLI can read without running your code, so no "
            "variables, spreads or function calls."
        ) from exc

    if not isinstance(parsed, dict):
        raise ManifestError(f"`{MANIFEST_EXPORT}` must be an object, got {type(parsed).__name__}.")
    return parsed


def parse_manifest_file(entry: Path) -> dict[str, Any]:
    """Read the manifest from a module's ``index.astro``."""
    try:
        source = entry.read_text(encoding="utf-8")
    except OSError as exc:
        raise ManifestError(f"Could not read {entry}: {exc}") from exc
    return parse_manifest_source(source)
