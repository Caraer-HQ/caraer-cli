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
# Example installation settings (uncomment and edit):
# settingsSchema:
#   - name: api_base_url
#     label: API base URL
#     type: SINGLE_LINE
#     required: false
#     defaultValue: https://api.example.com
"""

_EXAMPLE_PRICING_PLANS = """\
# Example pricing (uncomment and edit):
# pricingPlans:
#   - title: Starter
#     description: Good for trying the app
#     pricingType: FLAT
#     pricePerUnit: "0.00"
#     unit: month
#     freeUnits: "100"
#     freeUnitsPeriod: month
"""

_EXAMPLE_APP_BARS = """\
# Example app bars (uncomment and edit):
# appBars:
#   - location: RECORD_PREVIEW
#     label: Run action
#     tooltipLabel: Trigger the app action
#     description: Sends the record to your serverless function
#     webhook:
#       topic: app.bar.triggered
#       deliveryMode: SERVERLESS
#       serverlessFunction:
#         name: hello-world
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
