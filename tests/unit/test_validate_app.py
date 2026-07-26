from __future__ import annotations

import json
from pathlib import Path

from caraer_cli.project.schema import ProjectConfig, save_project_config
from caraer_cli.project.validate_app import validate_local_app


def _write_workspace(root: Path) -> None:
    save_project_config(
        root / "caraer.json",
        ProjectConfig(
            platformVersion="2026.2",
            name="demo_app",
            runtime="nodejs22",
        ),
    )


def _write_manifest(root: Path, **overrides: object) -> None:
    payload = {
        "label": "Demo App",
        "name": "demo_app",
        "runtime": "nodejs22",
        "authMethod": "OAUTH2",
        "oauthRedirectUris": ["http://localhost:3000/oauth/callback"],
        "details": {
            "title": "Demo App",
            "description": "A real marketplace description",
            "category": "developer_tools",
            "subcategories": ["apis"],
            "url": "https://example.com",
            "brandColor": "#E74363",
            "textColor": "#FFFFFF",
        },
        "requiredScopes": [],
        "settingsSchema": [],
        "pricingPlans": [],
        "appBars": [],
    }
    payload.update(overrides)
    path = root / "src" / "app" / "app.caraer.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    # Minimal YAML via json is fine for load_local_app if yaml/json both work —
    # write JSON content with .yaml only if yaml loader accepts JSON; prefer json file.
    json_path = root / "src" / "app" / "app.caraer.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")


def _write_function(root: Path, name: str = "hello-world") -> None:
    folder = root / "src" / "app" / "functions" / name
    folder.mkdir(parents=True)
    (folder / "function.caraer.json").write_text(
        json.dumps({"name": name, "runtime": "nodejs22", "entry": "index.js"}),
        encoding="utf-8",
    )
    (folder / "index.js").write_text("exports.handler = async () => ({});\n", encoding="utf-8")


def test_validate_local_app_ok(tmp_path: Path) -> None:
    _write_workspace(tmp_path)
    _write_manifest(tmp_path)
    _write_function(tmp_path)
    report = validate_local_app(tmp_path)
    assert report.ok
    assert report.functions == 1
    assert not any(i.severity == "error" for i in report.issues)


def test_validate_missing_details(tmp_path: Path) -> None:
    _write_workspace(tmp_path)
    _write_manifest(tmp_path, details=None)
    # json.dumps drops None values if we use update with None — force write without details.
    path = tmp_path / "src" / "app" / "app.caraer.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data.pop("details", None)
    path.write_text(json.dumps(data), encoding="utf-8")
    report = validate_local_app(tmp_path)
    assert not report.ok
    assert any(i.path.endswith(":details") for i in report.issues)


def test_validate_webhook_unknown_function(tmp_path: Path) -> None:
    _write_workspace(tmp_path)
    _write_manifest(tmp_path)
    _write_function(tmp_path, "hello-world")
    webhooks = tmp_path / "src" / "app" / "webhooks"
    webhooks.mkdir(parents=True)
    (webhooks / "hook.json").write_text(
        json.dumps(
            {
                "topic": "record.contact.created",
                "deliveryMode": "SERVERLESS",
                "serverlessFunction": {"name": "missing-fn"},
            }
        ),
        encoding="utf-8",
    )
    report = validate_local_app(tmp_path)
    assert not report.ok
    assert any("Unknown local function" in i.message for i in report.issues)


def test_validate_strict_treats_warnings_as_failure(tmp_path: Path) -> None:
    _write_workspace(tmp_path)
    _write_manifest(
        tmp_path,
        details={
            "title": "Demo App",
            "description": "TODO: replace me",
            "category": "developer_tools",
            "subcategories": ["apis"],
            "url": "https://example.com",
            "brandColor": "#E74363",
            "textColor": "#FFFFFF",
        },
    )
    _write_function(tmp_path)
    soft = validate_local_app(tmp_path, strict=False)
    assert soft.ok
    assert any(i.severity == "warning" for i in soft.issues)
    hard = validate_local_app(tmp_path, strict=True)
    assert not hard.ok


def test_validate_schedule_and_inbound(tmp_path: Path) -> None:
    _write_workspace(tmp_path)
    _write_manifest(tmp_path)
    _write_function(tmp_path, "hello-world")
    schedules = tmp_path / "src" / "app" / "schedules"
    schedules.mkdir(parents=True)
    (schedules / "renew.json").write_text(
        json.dumps(
            {
                "name": "renew",
                "schedule": "0 0 * * *",
                "serverlessFunction": {"name": "hello-world"},
            }
        ),
        encoding="utf-8",
    )
    inbound = tmp_path / "src" / "app" / "inbound"
    inbound.mkdir(parents=True)
    (inbound / "push.json").write_text(
        json.dumps(
            {
                "name": "push",
                "authMode": "SHARED_SECRET",
                "sharedSecret": "s3cret",
                "serverlessFunction": {"name": "hello-world"},
            }
        ),
        encoding="utf-8",
    )
    report = validate_local_app(tmp_path)
    assert report.ok
    assert report.schedules == 1
    assert report.inbound == 1


def test_validate_inbound_bad_auth_mode(tmp_path: Path) -> None:
    _write_workspace(tmp_path)
    _write_manifest(tmp_path)
    _write_function(tmp_path)
    inbound = tmp_path / "src" / "app" / "inbound"
    inbound.mkdir(parents=True)
    (inbound / "bad.json").write_text(
        json.dumps(
            {
                "name": "bad",
                "authMode": "NOPE",
                "serverlessFunction": {"name": "hello-world"},
            }
        ),
        encoding="utf-8",
    )
    report = validate_local_app(tmp_path)
    assert not report.ok
    assert any("authMode" in i.path for i in report.issues)
