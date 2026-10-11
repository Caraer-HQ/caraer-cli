from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from caraer_cli.api.apps import delete_private_app, fetch_app
from caraer_cli.commands.apps import build_public_app_placeholder
from caraer_cli.errors import NotFoundError, ValidationError
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
    client = MagicMock()
    with (
        patch(
            "caraer_cli.app_sync.apps_api.create_private_app",
            return_value=created,
        ) as create_private,
        patch(
            "caraer_cli.app_sync.apps_api.update_private_app",
        ) as update_private,
        patch("caraer_cli.app_sync.apps_api.create_public_app") as create_public,
    ):
        from caraer_cli.app_sync import create_app_from_manifest

        data = create_app_from_manifest(client, root, config)

    create_private.assert_called_once()
    update_private.assert_not_called()
    create_public.assert_not_called()
    create_body = create_private.call_args.args[1]
    assert create_body["name"] == "internal"
    assert create_body["authMethod"] == "OAUTH2"
    assert "installWebhook" not in create_body
    assert create_body.get("appBars") in (None, [])
    assert data["uuid"] == "priv-1"
    assert load_workspace(root).appUuid == "priv-1"
    assert load_workspace(root).privateApp is True


def test_duplicate_private_name_does_not_leave_empty_remote_app(tmp_path: Path) -> None:
    from caraer_cli.app_sync import create_app_from_manifest

    root = tmp_path / "internal"
    payload = build_public_app_placeholder(label="Internal", private=True)
    payload["name"] = "internal"
    scaffold_app_project(
        root, app_payload=payload, private_app=True, sample_function=None, force=True
    )
    remote_apps = {"existing": {"uuid": "existing", "name": "internal"}}

    def request(method: str, path: str, *, json_body: dict) -> dict:
        name = json_body.get("name", "generated_private_name")
        uuid = "created" if method == "POST" else path.rsplit("/", 1)[-1]
        if any(app["name"] == name and app["uuid"] != uuid for app in remote_apps.values()):
            raise ValidationError("Validation failed Duplicate value for name", status=400)
        remote_apps[uuid] = {**json_body, "uuid": uuid, "name": name, "privateApp": True}
        return {"data": remote_apps[uuid]}

    client = MagicMock()
    client.request.side_effect = request
    with pytest.raises(ValidationError, match="Duplicate value for name"):
        create_app_from_manifest(client, root, load_workspace(root))

    assert set(remote_apps) == {"existing"}, "A rejected name must not leave an empty remote app"
    assert load_workspace(root).appUuid is None
