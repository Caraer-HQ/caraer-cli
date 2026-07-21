from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from caraer_cli.project.schema import (
    FunctionManifest,
    ProjectConfig,
    load_project_config,
    load_workspace,
    save_project_config,
)
from caraer_cli.project.state import get_project_uuid
from caraer_cli.project.webhooks_sync import (
    discover_local_webhooks,
    push_webhooks,
    webhook_filename,
)


def test_project_config_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "caraer.json"
    config = ProjectConfig(name="demo", appUuid="app-1", platformVersion="2026.2", runtime="nodejs22")
    save_project_config(path, config)
    loaded = load_project_config(path)
    assert loaded.name == "demo"
    assert loaded.appUuid == "app-1"
    assert loaded.platformVersion == "2026.2"
    assert loaded.runtime == "nodejs22"
    assert loaded.api_platform_version() == 2
    assert loaded.is_app_platform_v2()
    assert "projectUuid" not in json.loads(path.read_text(encoding="utf-8"))


def test_project_config_v1_maps_to_app_platform_1() -> None:
    config = ProjectConfig(name="demo", platformVersion="2026.1")
    assert config.api_platform_version() == 1
    assert not config.is_app_platform_v2()


def test_legacy_project_file_migrates(tmp_path: Path) -> None:
    legacy = tmp_path / "caraer.project.json"
    legacy.write_text(
        json.dumps(
            {
                "platformVersion": "2026.1",
                "name": "legacy",
                "appUuid": "app-legacy",
                "projectUuid": "proj-1",
                "srcDir": "src",
                "autoDeploy": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    config = load_workspace(tmp_path)
    assert config.name == "legacy"
    assert config.appUuid == "app-legacy"
    assert get_project_uuid(tmp_path) == "proj-1"
    assert (tmp_path / "caraer.json").is_file()
    assert not legacy.exists()
    saved = json.loads((tmp_path / "caraer.json").read_text(encoding="utf-8"))
    assert "projectUuid" not in saved


def test_function_manifest_defaults_entry() -> None:
    node = FunctionManifest(name="hello", runtime="nodejs22")
    assert node.resolved_entry() == "index.js"
    py = FunctionManifest(name="hello", runtime="python312")
    assert py.resolved_entry() == "main.py"


def test_invalid_runtime_rejected() -> None:
    try:
        FunctionManifest(name="x", runtime="ruby")
        assert False, "expected validation error"
    except Exception:
        pass


def test_scaffold_writes_files(tmp_path: Path) -> None:
    from caraer_cli.project.sync import scaffold_function

    config = ProjectConfig(name="demo")
    folder = scaffold_function(tmp_path, config, "hello-world", "python312")
    assert (folder / "function.caraer.json").is_file()
    assert (folder / "main.py").is_file()
    data = json.loads((folder / "function.caraer.json").read_text(encoding="utf-8"))
    assert data["runtime"] == "python312"


def test_webhook_filename_stable() -> None:
    name = webhook_filename(
        {"topic": "record.created", "deliveryMode": "HTTP", "uuid": "abcd1234-xxxx"}
    )
    assert name.startswith("record-created-http-abcd1234")
    assert name.endswith(".json")


def test_discover_and_push_webhooks_create(tmp_path: Path) -> None:
    config = ProjectConfig(name="demo", appUuid="app-1", srcDir="src")
    wh_dir = tmp_path / "src" / "app" / "webhooks"
    wh_dir.mkdir(parents=True)
    (wh_dir / "record-created.json").write_text(
        json.dumps(
            {
                "topic": "record.created",
                "deliveryMode": "HTTP",
                "url": "https://example.com/hook",
                "webhookFormat": "USER_FRIENDLY",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    found = discover_local_webhooks(tmp_path, config)
    assert len(found) == 1

    client = MagicMock()
    client.request = MagicMock(
        side_effect=[
            {"data": []},  # list
            {"data": {"uuid": "wh-1", "topic": "record.created"}},  # create
        ]
    )
    # push_webhooks uses webhook_api which calls client.request via module helpers —
    # patch at API layer instead.
    from caraer_cli.api import webhooks as webhook_api

    original_list = webhook_api.list_webhooks
    original_create = webhook_api.create_webhook
    original_update = webhook_api.update_webhook
    original_delete = webhook_api.delete_webhook

    webhook_api.list_webhooks = MagicMock(return_value={"data": []})  # type: ignore[assignment]
    webhook_api.create_webhook = MagicMock(  # type: ignore[assignment]
        return_value={"data": {"uuid": "wh-1", "topic": "record.created"}}
    )
    webhook_api.update_webhook = MagicMock()  # type: ignore[assignment]
    webhook_api.delete_webhook = MagicMock()  # type: ignore[assignment]
    try:
        result = push_webhooks(client, tmp_path, config, delete_missing=False)
    finally:
        webhook_api.list_webhooks = original_list  # type: ignore[assignment]
        webhook_api.create_webhook = original_create  # type: ignore[assignment]
        webhook_api.update_webhook = original_update  # type: ignore[assignment]
        webhook_api.delete_webhook = original_delete  # type: ignore[assignment]

    assert result["webhooks"][0]["action"] == "created"
    assert result["webhooks"][0]["uuid"] == "wh-1"
    written = json.loads((wh_dir / "record-created.json").read_text(encoding="utf-8"))
    assert written["uuid"] == "wh-1"
