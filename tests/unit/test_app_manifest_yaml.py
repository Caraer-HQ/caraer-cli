from __future__ import annotations

from pathlib import Path

from caraer_cli.local_app import load_local_app
from caraer_cli.project.app_manifest_template import render_app_manifest


def test_render_app_manifest_yaml_with_examples(tmp_path: Path) -> None:
    text = render_app_manifest(
        {
            "label": "Demo",
            "name": "demo",
            "authMethod": "OAUTH2",
            "oauthRedirectUris": ["http://localhost:3000/oauth/callback"],
            "requiredScopes": [],
            "settingsSchema": [],
            "pricingPlans": [],
            "appBars": [],
        },
        include_examples=True,
    )
    path = tmp_path / "app.caraer.yaml"
    path.write_text(text, encoding="utf-8")
    assert "# Edit pricingPlans above, or: caraer apps add-pricing-plan" in text
    assert "# Edit appBars above, or: caraer apps add-app-bar" in text
    loaded = load_local_app(path)
    assert loaded["name"] == "demo"
    assert loaded["pricingPlans"] == []
    assert loaded["appBars"] == []
