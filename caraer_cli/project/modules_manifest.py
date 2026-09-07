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

import json5

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
        parsed = json5.loads(literal)
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
