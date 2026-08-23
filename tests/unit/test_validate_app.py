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
        "brandmark": "https://example.com/brandmark.svg",
        "details": {
            "title": "Demo App",
            "description": "A real marketplace description",
            "category": "developer_tools",
            "subcategories": ["apis"],
            "url": "https://example.com",
            "image": "https://example.com/logo.svg",
            "brandColor": "#E74363",
            "textColor": "#FFFFFF",
        },
        "requiredScopes": [],
        "settingsSchema": [],
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


def test_validate_missing_brandmark(tmp_path: Path) -> None:
    _write_workspace(tmp_path)
    _write_manifest(tmp_path)
    path = tmp_path / "src" / "app" / "app.caraer.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data.pop("brandmark", None)
    path.write_text(json.dumps(data), encoding="utf-8")
    report = validate_local_app(tmp_path)
    assert not report.ok
    assert any(i.path.endswith(":brandmark") for i in report.issues)


def test_validate_missing_logo(tmp_path: Path) -> None:
    _write_workspace(tmp_path)
    _write_manifest(tmp_path)
    path = tmp_path / "src" / "app" / "app.caraer.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["details"].pop("image", None)
    path.write_text(json.dumps(data), encoding="utf-8")
    report = validate_local_app(tmp_path)
    assert not report.ok
    assert any(i.path.endswith(":details.image") for i in report.issues)


def test_validate_brandmark_must_be_svg(tmp_path: Path) -> None:
    _write_workspace(tmp_path)
    _write_manifest(tmp_path, brandmark="https://example.com/brandmark.png")
    report = validate_local_app(tmp_path)
    assert not report.ok
    assert any(
        i.path.endswith(":brandmark") and "SVG" in i.message for i in report.issues
    )


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
            "image": "https://example.com/logo.svg",
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


def _settings_report(tmp_path: Path, settings: list[dict[str, object]]):
    _write_workspace(tmp_path)
    _write_manifest(tmp_path, settingsSchema=settings)
    _write_function(tmp_path)
    return validate_local_app(tmp_path)


def test_validate_visible_when_ok(tmp_path: Path) -> None:
    report = _settings_report(
        tmp_path,
        [
            {"name": "custom_mapping", "type": "SWITCH", "defaultValue": False},
            {
                "name": "work_experience_mapping",
                "type": "MAPPING",
                "visibleWhen": [
                    {"field": "custom_mapping", "operator": "EQUALS", "value": True}
                ],
            },
        ],
    )
    assert report.ok
    assert report.settings == 2


def test_validate_visible_when_unknown_field(tmp_path: Path) -> None:
    report = _settings_report(
        tmp_path,
        [
            {
                "name": "mapping",
                "type": "MAPPING",
                "visibleWhen": [{"field": "missing", "operator": "EQUALS", "value": True}],
            }
        ],
    )
    assert not report.ok
    assert any("visibleWhen[0].field" in i.path for i in report.issues)


def test_validate_visible_when_self_reference(tmp_path: Path) -> None:
    report = _settings_report(
        tmp_path,
        [
            {
                "name": "mapping",
                "type": "MAPPING",
                "visibleWhen": [{"field": "mapping", "operator": "EQUALS", "value": True}],
            }
        ],
    )
    assert not report.ok
    assert any("cannot reference the field itself" in i.message for i in report.issues)


def test_validate_visible_when_unknown_operator(tmp_path: Path) -> None:
    report = _settings_report(
        tmp_path,
        [
            {"name": "toggle", "type": "SWITCH"},
            {
                "name": "mapping",
                "type": "MAPPING",
                "visibleWhen": [{"field": "toggle", "operator": "STARTS_WITH", "value": "x"}],
            },
        ],
    )
    assert not report.ok
    assert any("visibleWhen[0].operator" in i.path for i in report.issues)


def test_validate_visible_when_missing_value(tmp_path: Path) -> None:
    report = _settings_report(
        tmp_path,
        [
            {"name": "toggle", "type": "SWITCH"},
            {
                "name": "mapping",
                "type": "MAPPING",
                "visibleWhen": [{"field": "toggle", "operator": "EQUALS"}],
            },
        ],
    )
    assert not report.ok
    assert any("visibleWhen[0].value" in i.path for i in report.issues)


def test_validate_visible_when_in_requires_list(tmp_path: Path) -> None:
    report = _settings_report(
        tmp_path,
        [
            {"name": "region", "type": "SINGLE_LINE"},
            {
                "name": "workspace",
                "type": "SINGLE_LINE",
                "visibleWhen": [{"field": "region", "operator": "IN", "value": "eu1"}],
            },
        ],
    )
    assert not report.ok
    assert any("requires a list" in i.message for i in report.issues)


def test_validate_visible_when_is_set_needs_no_value(tmp_path: Path) -> None:
    report = _settings_report(
        tmp_path,
        [
            {"name": "candidate_object", "type": "OBJECT_SINGLE_SELECT"},
            {
                "name": "cv_property",
                "type": "PROPERTY_SINGLE_SELECT",
                "visibleWhen": [{"field": "candidate_object", "operator": "IS_SET"}],
            },
        ],
    )
    assert report.ok


def test_validate_file_setting_type(tmp_path: Path) -> None:
    report = _settings_report(tmp_path, [{"name": "cv_file", "type": "FILE", "required": True}])
    assert report.ok


def test_validate_settings_sections_ok(tmp_path: Path) -> None:
    _write_workspace(tmp_path)
    _write_manifest(
        tmp_path,
        settingsSchema=[
            {"name": "candidate_mapping", "type": "MAPPING"},
            {"name": "parse_on_cv_change", "type": "SWITCH"},
        ],
        settingsSections=[
            {
                "title": "Candidate",
                "subtitle": "Map CV fields",
                "settings": ["candidate_mapping", "parse_on_cv_change"],
            }
        ],
    )
    _write_function(tmp_path)
    report = validate_local_app(tmp_path)
    assert report.ok
    assert not any("settings section" in i.message for i in report.issues)


def test_validate_settings_sections_unknown_field(tmp_path: Path) -> None:
    _write_workspace(tmp_path)
    _write_manifest(
        tmp_path,
        settingsSchema=[{"name": "candidate_mapping", "type": "MAPPING"}],
        settingsSections=[
            {"title": "Candidate", "settings": ["missing_field"]},
        ],
    )
    _write_function(tmp_path)
    report = validate_local_app(tmp_path)
    assert not report.ok
    assert any("not defined in settingsSchema" in i.message for i in report.issues)


def test_validate_settings_sections_duplicate_assignment(tmp_path: Path) -> None:
    _write_workspace(tmp_path)
    _write_manifest(
        tmp_path,
        settingsSchema=[{"name": "candidate_mapping", "type": "MAPPING"}],
        settingsSections=[
            {"title": "Candidate", "settings": ["candidate_mapping"]},
            {"title": "Other", "settings": ["candidate_mapping"]},
        ],
    )
    _write_function(tmp_path)
    report = validate_local_app(tmp_path)
    assert not report.ok
    assert any("more than one settings section" in i.message for i in report.issues)


def test_validate_settings_sections_unassigned_warning(tmp_path: Path) -> None:
    _write_workspace(tmp_path)
    _write_manifest(
        tmp_path,
        settingsSchema=[
            {"name": "candidate_mapping", "type": "MAPPING"},
            {"name": "parse_on_cv_change", "type": "SWITCH"},
        ],
        settingsSections=[
            {"title": "Candidate", "settings": ["candidate_mapping"]},
        ],
    )
    _write_function(tmp_path)
    report = validate_local_app(tmp_path)
    assert report.ok
    assert any(
        i.severity == "warning" and "Other settings" in i.message
        for i in report.issues
    )
