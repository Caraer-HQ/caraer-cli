from __future__ import annotations

from caraer_cli.commands.apps import build_public_app_placeholder, normalize_app_name
from caraer_cli.wizard.catalog import find_main_category
from caraer_cli.wizard.public_app import build_public_app_payload_from_answers
from caraer_cli.wizard.scope_macros import find_preset, materialize_macro


def test_normalize_app_name() -> None:
    assert normalize_app_name("My Cool-App!") == "my_cool_app"


def test_build_public_app_placeholder() -> None:
    payload = build_public_app_placeholder(label="My App", name="My App")
    assert payload["label"] == "My App"
    assert payload["name"] == "my_app"
    assert "privateApp" not in payload
    assert payload["runtime"] == "nodejs22"
    assert payload["authMethod"] == "OAUTH2"
    assert payload["hideApiKeyField"] is True
    assert payload["oauthRedirectUris"] == ["http://localhost:3000/oauth/callback"]
    assert payload["details"]["category"] == "developer_tools"
    assert payload["brandmark"].endswith(".svg")
    assert payload["details"]["image"].endswith(".svg")
    assert payload["details"]["brandColor"].startswith("#")
    assert payload["appBars"] == []
    assert "pricingPlans" not in payload
    assert "billFailedWebhookRequests" not in payload


def test_category_catalog_matches_backend_keys() -> None:
    productivity = find_main_category("productivity")
    assert productivity is not None
    assert productivity.label == "Productivity"
    assert {s.key for s in productivity.subcategories} >= {"agenda", "tasks", "automation"}


def test_materialize_tool_macro() -> None:
    preset = find_preset("tools.tool.all")
    assert preset is not None
    assert materialize_macro(preset, tool="forms") == ["tools.forms.all"]


def test_materialize_setting_pack() -> None:
    preset = find_preset("records.setting.pack")
    assert preset is not None
    assert materialize_macro(preset, setting_field="attendee_object") == [
        "records.<setting:attendee_object>.all",
        "records.<setting:attendee_object>.properties_all",
        "records.<setting:attendee_object>.relations_all",
    ]


def test_materialize_trait_pack() -> None:
    preset = find_preset("records.trait.pack")
    assert preset is not None
    assert materialize_macro(preset, trait_name="user") == [
        "records.<trait:user>.all",
        "records.<trait:user>.properties_all",
    ]


def test_materialize_object_pack() -> None:
    preset = find_preset("records.object.pack")
    assert preset is not None
    assert materialize_macro(preset, object_name="candidate") == [
        "records.candidate.all",
        "records.candidate.properties_all",
        "records.candidate.relations_all",
    ]


def test_build_public_app_payload_from_answers() -> None:
    payload = build_public_app_payload_from_answers(
        label="My first CLI App",
        name="my_first_cli_app",
        details={
            "title": "Hello world",
            "category": "productivity",
            "subcategories": ["agenda", "tasks"],
            "image": "https://example.com/logo.svg",
            "brandColor": "#E74363",
            "textColor": "#FFFFFF",
        },
        brandmark="https://example.com/brandmark.svg",
        required_scopes=["tools.forms.all", "records.candidate.properties_all"],
        settings_schema=[
            {
                "name": "Hello",
                "label": "Hello",
                "type": "SINGLE_LINE",
                "required": False,
                "defaultValue": "hoi",
            }
        ],
        app_bars=[
            {
                "location": "RECORD_PREVIEW",
                "label": "Run",
                "webhook": {"url": "https://example.com/hook", "topic": "app.bar.triggered"},
            }
        ],
        webhook_controls={
            "webhookRateLimitPerMinute": 100,
        },
    )
    assert "privateApp" not in payload
    assert payload["runtime"] == "nodejs22"
    assert payload["authMethod"] == "OAUTH2"
    assert payload["hideApiKeyField"] is True
    assert payload["oauthRedirectUris"] == ["http://localhost:3000/oauth/callback"]
    assert payload["name"] == "my_first_cli_app"
    assert payload["requiredScopes"] == [
        "tools.forms.all",
        "records.candidate.properties_all",
    ]
    assert payload["settingsSchema"][0]["type"] == "SINGLE_LINE"
    assert "pricingPlans" not in payload
    assert payload["appBars"][0]["location"] == "RECORD_PREVIEW"
    assert payload["webhookRateLimitPerMinute"] == 100
    assert "billFailedWebhookRequests" not in payload


def test_build_private_app_placeholder() -> None:
    payload = build_public_app_placeholder(label="Internal", name="internal", private=True)
    assert payload["label"] == "Internal"
    assert payload["name"] == "internal"
    assert "brandmark" not in payload
    assert "details" not in payload
    assert payload["authMethod"] == "OAUTH2"
    assert "privateApp" not in payload


def test_build_private_app_payload_from_answers() -> None:
    payload = build_public_app_payload_from_answers(
        label="Internal",
        name="internal",
        details=None,
        brandmark=None,
        required_scopes=["tools.forms.all"],
        settings_schema=[],
        app_bars=[],
        webhook_controls={},
        private=True,
    )
    assert "brandmark" not in payload
    assert "details" not in payload
    assert payload["requiredScopes"] == ["tools.forms.all"]
