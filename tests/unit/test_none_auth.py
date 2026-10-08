from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from caraer_cli.commands.apps import build_public_app_placeholder
from caraer_cli.completion_callbacks import complete_auth_method
from caraer_cli.local_app import load_local_app
from caraer_cli.project.scaffold import scaffold_app_project
from caraer_cli.project.validate_app import validate_local_app
from caraer_cli.wizard.public_app import build_public_app_payload_from_answers


def test_none_placeholder_has_no_oauth_callback() -> None:
    payload = build_public_app_placeholder(label="Hosted App", auth_method="none", private=True)
    assert payload["authMethod"] == "NONE"
    assert payload["oauthRedirectUris"] == []
    assert "oauthClientId" not in payload
    assert "oauthClientSecret" not in payload


def test_none_wizard_payload_has_no_oauth_callback() -> None:
    payload = build_public_app_payload_from_answers(
        label="Hosted App", name="hosted_app", details=None, brandmark=None,
        required_scopes=["records.candidate.read"], settings_schema=[], app_bars=[],
        webhook_controls={}, auth_method="NONE", private=True,
    )
    assert payload["authMethod"] == "NONE"
    assert payload["oauthRedirectUris"] == []
    assert payload["requiredScopes"] == ["records.candidate.read"]


def test_none_scaffold_validates_without_callbacks(tmp_path: Path) -> None:
    payload = build_public_app_placeholder(label="Hosted App", auth_method="NONE", private=True)
    payload.pop("oauthRedirectUris")
    scaffold_app_project(
        tmp_path, app_payload=payload, sample_function=None, sample_module=False,
        private_app=True, runtime="nodejs22",
    )
    manifest = load_local_app(tmp_path / "src/app/app.caraer.yaml")
    assert manifest["authMethod"] == "NONE"
    assert manifest["oauthRedirectUris"] == []
    report = validate_local_app(tmp_path)
    assert report.ok, report.issues


@pytest.mark.parametrize("method", ["NONE", "API_KEY", "OAUTH2"])
def test_schema_preserves_all_authentication_modes(method: str) -> None:
    schema = json.loads((Path(__file__).parents[2] / "schemas/app.caraer.schema.json").read_text())
    validator = Draft202012Validator(schema)
    manifest = {"name": "hosted_app", "label": "Hosted App", "authMethod": method}
    if method == "OAUTH2":
        assert list(validator.iter_errors(manifest))
        manifest["oauthRedirectUris"] = ["https://client.example/callback"]
    validator.validate(manifest)


def test_completion_includes_none() -> None:
    assert ("NONE", "Platform-managed installation tokens") in complete_auth_method(None, "N")
