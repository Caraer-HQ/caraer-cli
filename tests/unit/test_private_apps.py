from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from caraer_cli.api.apps import delete_private_app, fetch_app
from caraer_cli.commands.apps import build_public_app_placeholder
from caraer_cli.errors import NotFoundError
from caraer_cli.project.scaffold import scaffold_app_project
from caraer_cli.project.schema import load_workspace


def test_delete_private_app_calls_delete() -> None:
    client = MagicMock()
    client.request.return_value = {"data": {"uuid": "priv-1", "privateApp": True}}
    assert delete_private_app(client, "priv-1")["data"]["uuid"] == "priv-1"
    client.request.assert_called_once_with("DELETE", "/api/v2/apps/private/priv-1")


def test_fetch_app_falls_back_to_company_app_for_private() -> None:
    client = MagicMock()
    private = {"data": {"uuid": "app-1", "privateApp": True, "label": "Internal"}}
    with (
        patch(
            "caraer_cli.api.apps.get_public_app",
            side_effect=NotFoundError("App is not a public app", status=404),
        ),
        patch("caraer_cli.api.apps.get_app", return_value=private) as get_app,
    ):
        assert fetch_app(client, "app-1") == private
        get_app.assert_called_once_with(client, "app-1")


def test_scaffold_persists_private_app_flag(tmp_path: Path) -> None:
    root = tmp_path / "internal"
    scaffold_app_project(
        root,
        app_payload=build_public_app_placeholder(label="Internal", private=True),
        sample_function=None,
        private_app=True,
        force=True,
    )
    config = load_workspace(root)
    assert config.privateApp is True
    raw = (root / "caraer.json").read_text(encoding="utf-8")
    assert '"privateApp": true' in raw


def test_create_private_app_uses_private_endpoints(tmp_path: Path) -> None:
    root = tmp_path / "internal"
    scaffold_app_project(
        root,
        app_payload=build_public_app_placeholder(label="Internal", private=True),
        sample_function=None,
        private_app=True,
        force=True,
    )
    config = load_workspace(root)
    created = {
        "data": {
            "uuid": "priv-1",
            "label": "Internal",
            "name": "internal",
            "privateApp": True,
        }
    }
    updated = {
        "data": {
            "uuid": "priv-1",
            "label": "Internal",
            "name": "internal",
            "privateApp": True,
            "authMethod": "OAUTH2",
        }
    }
    client = MagicMock()
    with (
        patch(
            "caraer_cli.app_sync.apps_api.create_private_app",
            return_value=created,
        ) as create_private,
        patch(
            "caraer_cli.app_sync.apps_api.update_private_app",
            return_value=updated,
        ) as update_private,
        patch("caraer_cli.app_sync.apps_api.create_public_app") as create_public,
    ):
        from caraer_cli.app_sync import create_app_from_manifest

        data = create_app_from_manifest(client, root, config)

    create_private.assert_called_once()
    update_private.assert_called_once()
    create_public.assert_not_called()
    assert data["uuid"] == "priv-1"
    assert load_workspace(root).appUuid == "priv-1"
    assert load_workspace(root).privateApp is True
