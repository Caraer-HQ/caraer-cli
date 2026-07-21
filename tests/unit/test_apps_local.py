from __future__ import annotations

from pathlib import Path

from caraer_cli.apps_local import resolve_pull_target_file, sanitize_remote_app_payload
from caraer_cli.project.scaffold import scaffold_app_project


def test_sanitize_remote_app_payload_strips_reviewer_notes() -> None:
    payload = sanitize_remote_app_payload(
        {
            "uuid": "app-1",
            "name": "demo",
            "label": "Demo",
            "privateApp": False,
            "authMethod": "OAUTH2",
            "oauthRedirectUris": ["http://localhost:3000/oauth/callback"],
            "requiredScopes": ["tools.forms.all"],
            "serverlessFunctions": [{"uuid": "fn-1"}],
            "appPublish": {
                "publishState": "CHANGES_REQUESTED",
                "feedback": "Please fix",
                "reviewerNotes": "secret admin note",
            },
            "hasApp": {"installed": True},
        }
    )
    assert payload["uuid"] == "app-1"
    assert payload["authMethod"] == "OAUTH2"
    assert payload["oauthRedirectUris"] == ["http://localhost:3000/oauth/callback"]
    assert payload["requiredScopes"] == ["tools.forms.all"]
    assert "serverlessFunctions" not in payload
    assert "hasApp" not in payload
    assert "appPublish" not in payload
    assert "privateApp" not in payload


def test_pull_target_creates_sibling_folder_for_different_app(
    tmp_path: Path, monkeypatch
) -> None:
    existing = tmp_path / "my_second_cli_public_app"
    scaffold_app_project(
        existing,
        app_payload={"uuid": "aaaa-1111", "name": "my_second", "label": "Second"},
        app_uuid="aaaa-1111",
        sample_function=None,
        force=True,
    )
    monkeypatch.chdir(existing)

    target = resolve_pull_target_file(
        {"uuid": "bbbb-2222", "name": "caraer_ai", "label": "Caraer AI"},
        existing_app_file=str(existing / "src" / "app" / "app.caraer.yaml"),
    )

    assert target == (tmp_path / "caraer_ai" / "src" / "app" / "app.caraer.yaml").resolve()
    assert existing.name == "my_second_cli_public_app"


def test_pull_target_reuses_folder_for_same_app(tmp_path: Path, monkeypatch) -> None:
    existing = tmp_path / "caraer_ai"
    scaffold_app_project(
        existing,
        app_payload={"uuid": "bbbb-2222", "name": "caraer_ai", "label": "Caraer AI"},
        app_uuid="bbbb-2222",
        sample_function=None,
        force=True,
    )
    monkeypatch.chdir(existing)
    existing_file = existing / "src" / "app" / "app.caraer.yaml"

    target = resolve_pull_target_file(
        {"uuid": "bbbb-2222", "name": "caraer_ai", "label": "Caraer AI"},
        existing_app_file=str(existing_file),
    )

    assert target == existing_file.resolve()
