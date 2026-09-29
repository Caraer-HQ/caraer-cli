"""Read ``exports.manifest`` / ``manifest = {...}`` from a function file.

The CLI does not execute function source. It slices a literal object the same
way it reads a module's ``export const manifest``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from caraer_cli.project.modules_manifest import ManifestError, _loads_literal, _object_literal

_JS_MANIFEST = re.compile(
    r"(?:exports\.manifest|module\.exports\.manifest|export\s+const\s+manifest)\s*(?::[^=]*?)?=\s*",
    re.DOTALL,
)
_PY_MANIFEST = re.compile(r"^manifest\s*=\s*", re.MULTILINE)
_PY_KEYWORDS = re.compile(r"\b(True|False|None)\b")


def parse_code_manifest(source: str, *, path: Path | None = None) -> dict[str, Any]:
    """Parse a JS or Python manifest literal. Missing manifest is an empty dict."""
    suffix = path.suffix.lower() if path is not None else ""
    if suffix == ".py" or (_PY_MANIFEST.search(source) and "exports." not in source):
        return _parse_python_manifest(source)
    return _parse_js_manifest(source)


def upsert_code_manifest(source: str, payload: dict[str, Any], *, path: Path | None = None) -> str:
    """Replace or append a literal manifest object without executing the file."""
    literal = json.dumps(payload, indent=2)
    suffix = path.suffix.lower() if path is not None else ""
    if suffix == ".py":
        py_literal = (
            literal.replace("true", "True").replace("false", "False").replace("null", "None")
        )
        match = _PY_MANIFEST.search(source)
        if match:
            start = source.index("{", match.end())
            old = _object_literal(source, start)
            return source[:start] + py_literal + source[start + len(old) :]
        return f"manifest = {py_literal}\n\n{source.lstrip()}"
    match = _JS_MANIFEST.search(source)
    if match:
        start = source.index("{", match.end())
        old = _object_literal(source, start)
        return source[:start] + literal + source[start + len(old) :]
    return source.rstrip() + f"\n\nexports.manifest = {literal};\n"


def write_code_manifest(path: Path, payload: dict[str, Any]) -> None:
    source = path.read_text(encoding="utf-8") if path.is_file() else ""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(upsert_code_manifest(source, payload, path=path), encoding="utf-8")


def parse_code_manifest_file(path: Path) -> dict[str, Any]:
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ManifestError(f"Could not read {path}: {exc}") from exc
    return parse_code_manifest(source, path=path)


def _parse_object_after(source: str, start: int) -> dict[str, Any]:
    rest = source[start:].lstrip()
    if not rest.startswith("{"):
        raise ManifestError(
            "`manifest` must be a plain object literal the CLI can read without "
            "running your code."
        )
    literal = _object_literal(source, source.index("{", start))
    parsed = _loads_literal(literal, {})
    if not isinstance(parsed, dict):
        raise ManifestError(f"`manifest` must be an object, got {type(parsed).__name__}.")
    return parsed


def _parse_js_manifest(source: str) -> dict[str, Any]:
    match = _JS_MANIFEST.search(source)
    if match is None:
        return {}
    return _parse_object_after(source, match.end())


def _parse_python_manifest(source: str) -> dict[str, Any]:
    match = _PY_MANIFEST.search(source)
    if match is None:
        return {}
    normalized = _PY_KEYWORDS.sub(
        lambda item: {"True": "true", "False": "false", "None": "null"}[item.group(1)],
        source,
    )
    return _parse_object_after(normalized, match.end())
