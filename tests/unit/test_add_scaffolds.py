from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from caraer_cli.project.code_manifest import parse_code_manifest_file
from caraer_cli.project.scaffold import (
    scaffold_app_project,
    scaffold_inbound,
    scaffold_schedule,
    scaffold_webhook,
)
from caraer_cli.project.schema import PLATFORM_VERSION_V2, ProjectConfig, load_workspace
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
    assert folder.name == "my-action.js"
    assert folder.is_file()
    assert "exports.handler" in folder.read_text(encoding="utf-8")
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
    config = ProjectConfig(
        name="demo", srcDir="src", platformVersion=PLATFORM_VERSION_V2
    )
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


def test_scaffold_webhook_writes_function_manifest_on_v21(tmp_path: Path) -> None:
    result = scaffold_app_project(
        tmp_path / "demo",
        app_payload={"name": "demo", "label": "Demo", "description": "Demo"},
        sample_function=None,
    )
    root = result["root"]
    config = load_workspace(root)
    path = scaffold_webhook(
        root, config, topic="record.candidate.created", function_name="hello"
    )
    assert path.name == "hello.js"
    manifest = parse_code_manifest_file(path)
    assert manifest["webhooks"][0]["topic"] == "record.candidate.created"
    assert manifest["webhooks"][0]["label"] == "Candidate created"
    assert manifest["webhooks"][0]["webhookFormat"] == "USER_FRIENDLY"

    again = scaffold_webhook(
        root,
        config,
        topic="record.candidate.updated",
        function_name="hello",
    )
    assert again == path
    hooks = parse_code_manifest_file(path)["webhooks"]
    assert [item["topic"] for item in hooks] == [
        "record.candidate.created",
        "record.candidate.updated",
    ]


def test_scaffold_webhook_writes_yaml_for_http_on_v21(tmp_path: Path) -> None:
    result = scaffold_app_project(
        tmp_path / "demo",
        app_payload={"name": "demo", "label": "Demo", "description": "Demo"},
        sample_function=None,
    )
    root = result["root"]
    path = scaffold_webhook(
        root,
        load_workspace(root),
        topic="record.candidate.updated",
        delivery_mode="HTTP",
        url="https://example.com/hook",
    )
    assert path.name == "record-candidate-updated.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert payload["deliveryMode"] == "HTTP"
    assert payload["url"] == "https://example.com/hook"
    assert payload["label"] == "Candidate updated"

    from caraer_cli.project.webhooks_sync import discover_local_webhooks

    found = discover_local_webhooks(root, load_workspace(root))
    http = [item for _path, item in found if item.get("deliveryMode") == "HTTP"]
    assert len(http) == 1
    assert http[0]["url"] == "https://example.com/hook"


def test_scaffold_schedule_and_inbound_write_js_on_v21(tmp_path: Path) -> None:
    result = scaffold_app_project(
        tmp_path / "demo",
        app_payload={"name": "demo", "label": "Demo", "description": "Demo"},
        sample_function=None,
    )
    root = result["root"]
    config = load_workspace(root)
    schedule = scaffold_schedule(
        root,
        config,
        name="heartbeat",
        cron="0 0 */12 * * *",
        description="12h ping",
    )
    assert schedule.name == "heartbeat.js"
    assert parse_code_manifest_file(schedule)["schedule"] == "0 0 */12 * * *"
    inbound = scaffold_inbound(root, config, name="echo", auth_mode="NONE", enqueue=False)
    assert inbound.name == "echo.js"
    assert parse_code_manifest_file(inbound)["authMode"] == "NONE"


def test_scaffold_schedule_writes_json_on_2026_2(tmp_path: Path) -> None:
    result = scaffold_app_project(
        tmp_path / "demo",
        app_payload={"name": "demo", "label": "Demo", "description": "Demo"},
        sample_function=None,
    )
    root = result["root"]
    config = ProjectConfig(
        name="demo", srcDir="src", platformVersion=PLATFORM_VERSION_V2
    )
    path = scaffold_schedule(
        root,
        config,
        name="heartbeat",
        cron="0 0 * * * *",
        function_name="my-action",
    )
    assert path.name == "heartbeat.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["serverlessFunction"]["name"] == "my-action"
