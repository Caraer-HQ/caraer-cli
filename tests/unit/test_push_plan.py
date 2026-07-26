from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from caraer_cli.commands.apps import build_public_app_placeholder
from caraer_cli.project.scaffold import scaffold_app_project
from caraer_cli.project.schema import load_workspace


def test_build_push_plan_unlinked_creates(tmp_path: Path) -> None:
    root = tmp_path / "demo"
    scaffold_app_project(
        root,
        app_payload=build_public_app_placeholder(label="Demo", name="demo"),
        sample_function="hello-world",
        force=True,
    )
    # Unlinked scaffold may still write appUuid when passed; clear it.
    config = load_workspace(root)
    config.appUuid = None
    from caraer_cli.project.paths import workspace_file
    from caraer_cli.project.schema import save_project_config

    save_project_config(workspace_file(root), config)
    config = load_workspace(root)

    wh = root / "src" / "app" / "webhooks" / "hook.json"
    wh.parent.mkdir(parents=True, exist_ok=True)
    wh.write_text(
        json.dumps(
            {
                "topic": "record.created",
                "deliveryMode": "HTTP",
                "url": "https://example.com",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    schedules = root / "src" / "app" / "schedules"
    schedules.mkdir(parents=True, exist_ok=True)
    (schedules / "nightly.json").write_text(
        json.dumps(
            {
                "name": "nightly",
                "schedule": "0 0 * * * *",
                "enabled": True,
                "serverlessFunction": {"name": "hello-world"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    inbound = root / "src" / "app" / "inbound"
    inbound.mkdir(parents=True, exist_ok=True)
    (inbound / "push.json").write_text(
        json.dumps(
            {
                "name": "push",
                "authMode": "SHARED_SECRET",
                "enqueue": True,
                "serverlessFunction": {"name": "hello-world"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    client = MagicMock()
    from caraer_cli.project.push_plan import build_push_plan

    plan = build_push_plan(client, root, config, delete_missing=False)

    assert plan["linked"] is False
    assert plan["manifest"]["action"] == "create"
    assert any(r["action"] == "create" for r in plan["functions"])
    assert any(r["action"] == "create" for r in plan["webhooks"])
    assert any(r["action"] == "create" for r in plan["schedules"])
    assert any(r["action"] == "create" for r in plan["inbound"])
    assert plan["counts"]["create"] >= 4


def test_build_push_plan_detects_update_and_remote_only(tmp_path: Path) -> None:
    root = tmp_path / "demo"
    scaffold_app_project(
        root,
        app_payload=build_public_app_placeholder(label="Demo", name="demo"),
        app_uuid="app-1",
        sample_function="hello-world",
        force=True,
    )
    config = load_workspace(root)

    client = MagicMock()
    with (
        patch(
            "caraer_cli.project.push_plan.apps_api.get_public_app",
            return_value={
                "data": {
                    "uuid": "app-1",
                    "label": "Old Label",
                    "details": {"description": "old"},
                }
            },
        ),
        patch(
            "caraer_cli.project.push_plan.functions_api.list_functions",
            return_value={
                "data": [
                    {
                        "uuid": "fn-1",
                        "name": "hello-world",
                        "runtime": "nodejs22",
                        "description": "hello-world",
                        "code": "// different",
                        "sourceFiles": {},
                    },
                    {
                        "uuid": "fn-2",
                        "name": "orphan",
                        "runtime": "nodejs22",
                        "code": "x",
                    },
                ]
            },
        ),
        patch(
            "caraer_cli.project.push_plan.webhook_api.list_webhooks",
            return_value={"data": []},
        ),
        patch(
            "caraer_cli.project.push_plan.runtime_api.list_schedules",
            return_value={"data": []},
        ),
        patch(
            "caraer_cli.project.push_plan.runtime_api.list_inbound_routes",
            return_value={"data": []},
        ),
        patch(
            "caraer_cli.project.push_plan.runtime_api.list_external_oauth_providers",
            return_value={"data": []},
        ),
    ):
        from caraer_cli.project.push_plan import build_push_plan

        plan = build_push_plan(client, root, config, delete_missing=False)

    assert plan["manifest"]["action"] == "update"
    assert "label" in plan["manifest"]["changes"]
    fn_by_name = {r["name"]: r["action"] for r in plan["functions"]}
    assert fn_by_name["hello-world"] == "update"
    assert fn_by_name["orphan"] == "remote-only"

    plan_delete = None
    with (
        patch(
            "caraer_cli.project.push_plan.apps_api.get_public_app",
            return_value={
                "data": {
                    "uuid": "app-1",
                    "label": "Demo",
                    "details": {"description": "TODO: short marketplace description"},
                }
            },
        ),
        patch(
            "caraer_cli.project.push_plan.functions_api.list_functions",
            return_value={
                "data": [
                    {"uuid": "fn-2", "name": "orphan", "runtime": "nodejs22", "code": "x"},
                ]
            },
        ),
        patch(
            "caraer_cli.project.push_plan.webhook_api.list_webhooks",
            return_value={"data": []},
        ),
        patch(
            "caraer_cli.project.push_plan.runtime_api.list_schedules",
            return_value={"data": []},
        ),
        patch(
            "caraer_cli.project.push_plan.runtime_api.list_inbound_routes",
            return_value={"data": []},
        ),
        patch(
            "caraer_cli.project.push_plan.runtime_api.list_external_oauth_providers",
            return_value={"data": []},
        ),
    ):
        from caraer_cli.project.push_plan import build_push_plan

        plan_delete = build_push_plan(client, root, config, delete_missing=True)

    fn_by_name = {r["name"]: r["action"] for r in plan_delete["functions"]}
    assert fn_by_name["hello-world"] == "create"
    assert fn_by_name["orphan"] == "delete"
