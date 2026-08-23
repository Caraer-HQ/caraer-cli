"""Render and locate local app manifests (YAML preferred)."""

from __future__ import annotations

from typing import Any

import yaml

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
# Optional modular files also work: src/app/settings/<name>.json (--modular)
# Group installer cards with settingsSections or src/app/settings-sections/*.json
"""

_EXAMPLE_APP_BARS = """\
# Edit appBars above when needed (record / tool / trait bars).
# Lifecycle hooks: src/app/lifecycle/ + functions/on-* (caraer apps add lifecycle-hook)
"""


def render_app_manifest(payload: dict[str, Any], *, include_examples: bool = True) -> str:
    """Serialize an app manifest as YAML, optionally with commented-out examples.

    No ``# yaml-language-server`` schema directive is emitted: the schemas live in
    a private repo, so editors could only ever report a load failure on it.
    ``caraer apps validate`` checks the manifest against the bundled schemas.
    """
    data = dict(payload)
    for key in ("requiredScopes", "settingsSchema", "appBars"):
        data.setdefault(key, [])

    body = yaml.safe_dump(
        data,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    ).rstrip() + "\n"
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
    return "\n".join(out) + "\n"
