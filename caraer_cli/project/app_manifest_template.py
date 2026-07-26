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
# Prefer modular files: src/app/settings/<name>.json
# (caraer apps add-setting <name>)
# Inline settingsSchema: [] is fine when using files.
"""

_EXAMPLE_PRICING_PLANS = """\
# Prefer modular files: src/app/pricing/<slug>.json
# (caraer apps add-pricing-plan "Starter")
"""

_EXAMPLE_APP_BARS = """\
# Prefer modular files: src/app/app-bars/<slug>.json
# (caraer apps add-app-bar "Run action" --location RECORD_PREVIEW --function hello-world)
# Lifecycle hooks are scaffolded on init under src/app/lifecycle/ + functions/on-*
# (see docs/app_lifecycle.md; recreate with: caraer apps add-lifecycle-hook install)
"""


def render_app_manifest(payload: dict[str, Any], *, include_examples: bool = True) -> str:
    """Serialize an app manifest as YAML, optionally with commented-out examples."""
    data = dict(payload)
    for key in ("requiredScopes", "settingsSchema", "pricingPlans", "appBars"):
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
        elif stripped == "pricingPlans: []":
            out.append(_EXAMPLE_PRICING_PLANS.rstrip("\n"))
        elif stripped == "appBars: []":
            out.append(_EXAMPLE_APP_BARS.rstrip("\n"))
    return "\n".join(out) + "\n"
