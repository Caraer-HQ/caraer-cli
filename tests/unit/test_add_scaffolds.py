from __future__ import annotations

import json
from pathlib import Path

import pytest

from caraer_cli.project.scaffold import scaffold_app_project, scaffold_webhook
from caraer_cli.project.schema import ProjectConfig, load_workspace
from caraer_cli.project.sync import scaffold_function


def test_scaffold_function_creates_nodejs_folder(tmp_path: Path) -> None:
    result = scaffold_app_project(
        tmp_path / "demo",
        app_payload={"name": "demo", "label": "Demo", "description": "Demo"},
        sample_function=None,
    )
    root = result["root"]
    config = load_workspace(root)
    folder = scaffold_function(root, config, "my-action", "nodejs22")
    # Conventional functions need no function.caraer.json; discovery uses the
    # folder name and entry file.
    assert not (folder / "function.caraer.json").exists()
    assert (folder / "index.js").is_file()
    from caraer_cli.project.sync import discover_local_functions

    discovered = {m.name: m for m, _, _, _ in discover_local_functions(root, config)}
    assert "my-action" in discovered
    assert discovered["my-action"].runtime == "nodejs22"


def test_scaffold_function_refuses_overwrite(tmp_path: Path) -> None:
    result = scaffold_app_project(
        tmp_path / "demo",
        app_payload={"name": "demo", "label": "Demo", "description": "Demo"},
        sample_function="hello-world",
    )
    root = result["root"]
    config = load_workspace(root)
    with pytest.raises(FileExistsError):
        scaffold_function(root, config, "hello-world", "nodejs22")


def test_scaffold_webhook_http_and_serverless(tmp_path: Path) -> None:
    result = scaffold_app_project(
        tmp_path / "demo",
        app_payload={"name": "demo", "label": "Demo", "description": "Demo"},
        sample_function=None,
    )
    root = result["root"]
    config = ProjectConfig(name="demo", srcDir="src")
    serverless = scaffold_webhook(
        root, config, topic="record.updated", function_name="my-action"
    )
    assert serverless.name == "record-updated-serverless.json"
    payload = json.loads(serverless.read_text(encoding="utf-8"))
    assert payload["deliveryMode"] == "SERVERLESS"
    assert payload["serverlessFunction"]["name"] == "my-action"

    http = scaffold_webhook(
        root,
        config,
        topic="record.deleted",
        delivery_mode="HTTP",
        url="https://example.com/hook",
    )
    assert http.name == "record-deleted-http.json"
    http_payload = json.loads(http.read_text(encoding="utf-8"))
    assert http_payload["url"] == "https://example.com/hook"
