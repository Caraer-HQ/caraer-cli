"""Render and locate local app manifests (YAML preferred)."""

from __future__ import annotations

from typing import Any

import yaml

from caraer_cli.project.json_schemas import APP_MANIFEST_SCHEMA_URL

APP_MANIFEST_YAML = "app.caraer.yaml"
APP_MANIFEST_JSON = "app.caraer.json"  # legacy; still loaded if present
APP_MANIFEST_NAMES = (APP_MANIFEST_YAML, APP_MANIFEST_JSON, "app.yaml", "app.yml", "app.json")

_EXAMPLE_REQUIRED_SCOPES = """\
# Example scopes (uncomment and edit):
# requiredScopes:
#   - tools.forms.all
#   - records.candidate.properties_all
"""

_EXAMPLE_SETTINGS_SCHEMA = """\
# Edit settingsSchema above, or: caraer apps add setting
# On 2026.2.1 settings live in src/app/settings.yaml instead of this file.
"""

_EXAMPLE_APP_BARS = """\
# Edit appBars above when needed (record / tool / trait bars).
# On 2026.2.1 declare the bar in src/app/appbars/<name>.js: exports.manifest.appBars.
# Lifecycle hooks: src/app/lifecycle/<event>.js (caraer apps add lifecycle-hook)
"""


def render_app_manifest(payload: dict[str, Any], *, include_examples: bool = True) -> str:
    """Serialize an app manifest as YAML, optionally with commented-out examples.

    Prefixes a public ``# yaml-language-server: $schema=…`` line so editors can
    load the schema from Caraer-HQ/caraer-app-schemas. ``caraer apps validate``
    still checks against the schemas bundled with the CLI.
    """
    data = dict(payload)
    data.setdefault("requiredScopes", [])
    if "settingsSchema" in data:
        data.setdefault("settingsSchema", [])
    if "appBars" in data:
        data.setdefault("appBars", [])

    body = (
        f"# yaml-language-server: $schema={APP_MANIFEST_SCHEMA_URL}\n"
        + yaml.safe_dump(
            data,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        ).rstrip()
        + "\n"
    )
    if not include_examples:
        return body

    lines = body.splitlines()
    out: list[str] = []
    for line in lines:
        out.append(line)
        stripped = line.strip()
        if stripped == "requiredScopes: []":
            out.append(_EXAMPLE_REQUIRED_SCOPES.rstrip("\n"))
        elif stripped == "settingsSchema: []":
            out.append(_EXAMPLE_SETTINGS_SCHEMA.rstrip("\n"))
        elif stripped == "appBars: []":
            out.append(_EXAMPLE_APP_BARS.rstrip("\n"))
    if "settingsSchema" not in data:
        out.append(_EXAMPLE_SETTINGS_SCHEMA.rstrip("\n"))
    if "appBars" not in data:
        out.append(_EXAMPLE_APP_BARS.rstrip("\n"))
    return "\n".join(out) + "\n"
