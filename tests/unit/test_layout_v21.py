from __future__ import annotations

from pathlib import Path

import yaml

from caraer_cli.commands.apps import build_public_app_placeholder
from caraer_cli.project.code_manifest import parse_code_manifest, upsert_code_manifest
from caraer_cli.project.function_files import discover_layout_v21_functions, webhook_items_from_files
from caraer_cli.project.layout_upgrade import upgrade_layout_to_v21
from caraer_cli.project.marketplace_assemble import assemble_local_manifest
from caraer_cli.project.scaffold import scaffold_app_project
from caraer_cli.project.schema import PLATFORM_VERSION, PLATFORM_VERSION_V2, load_workspace
from caraer_cli.project.validate_app import validate_local_app
from caraer_cli.project.settings_sections_sync import discover_local_settings_sections
from caraer_cli.project.settings_sync import (
    append_settings_yaml_field,
    parse_settings_yaml,
    write_settings_yaml,
)


def test_parse_js_and_python_manifests() -> None:
    js = """
exports.handler = async () => ({});
exports.manifest = { webhooks: [{ topic: "record.created" }] };
"""
    assert parse_code_manifest(js)["webhooks"][0]["topic"] == "record.created"
    py = 'manifest = {"schedule": "0 * * * * *", "enabled": True}\n\ndef handler(request):\n    return {}\n'
    assert parse_code_manifest(py, path=Path("x.py"))["schedule"] == "0 * * * * *"


def test_upsert_code_manifest_replaces_literal() -> None:
    source = "exports.handler = async () => ({});\nexports.manifest = { enabled: true };\n"
    next_source = upsert_code_manifest(source, {"enabled": False, "lifecycle": "install"})
    parsed = parse_code_manifest(next_source)
    assert parsed["lifecycle"] == "install"
    assert parsed["enabled"] is False


def test_scaffold_v21_layout(tmp_path: Path) -> None:
    root = tmp_path / "app"
    scaffold_app_project(
        root,
        app_payload=build_public_app_placeholder(label="Demo", name="demo"),
        sample_function="hello-world",
        runtime="nodejs22",
    )
    config = load_workspace(root)
    assert config.platformVersion == PLATFORM_VERSION
    files = discover_layout_v21_functions(root, config)
    names = {item.name: item for item in files}
    assert "hello-world" in names
    assert names["hello-world"].path.name == "hello-world.js"
    assert names["install"].path.parent.name == "lifecycle"
    hooks = webhook_items_from_files(files)
    assert any(item[1]["topic"] == "record.candidate.created" for item in hooks)
    settings_yaml = (root / "src" / "app" / "settings.yaml").read_text(encoding="utf-8")
    assert yaml.safe_load(settings_yaml) == []
    assert "settingsSchema" not in settings_yaml
    assert "settingsSections" not in settings_yaml
    assert not (root / "src" / "app" / "app-bars.yaml").exists()
    assert (root / "src" / "app" / "inbound").is_dir()
    assert (root / "src" / "app" / "schedules").is_dir()
    assert (root / "src" / "app" / "inbound" / ".gitkeep").is_file()
    assert (root / "src" / "app" / "schedules" / ".gitkeep").is_file()
    assert not (root / "src" / "app" / "webhooks").exists()


def test_function_manifest_app_bar_attaches_that_function(tmp_path: Path) -> None:
    root = tmp_path / "app"
    scaffold_app_project(
        root,
        app_payload=build_public_app_placeholder(label="Demo", name="demo"),
        sample_function="hello-world",
        runtime="nodejs22",
    )
    path = root / "src" / "app" / "functions" / "hello-world.js"
    source = path.read_text(encoding="utf-8")
    manifest = parse_code_manifest(source)
    manifest["appBars"] = [
        {
            "name": "ping_overview",
            "location": "RECORD_OVERVIEW",
            "label": "Layout v21 ping",
            "actionLabel": "Ping",
        }
    ]
    path.write_text(upsert_code_manifest(source, manifest), encoding="utf-8")
    config = load_workspace(root)
    assembled = assemble_local_manifest(
        root, config, {"name": "demo"}, resolve_functions=False
    )
    bar = assembled["appBars"][0]
    assert bar["name"] == "ping_overview"
    assert bar["location"] == "RECORD_OVERVIEW"
    assert bar["webhook"]["topic"] == "app.bar.triggered"
    assert bar["webhook"]["serverlessFunction"] == {"name": "hello-world"}
    assert "serverlessFunction" not in path.read_text(encoding="utf-8")


def test_upgrade_moves_app_bar_onto_the_function(tmp_path: Path) -> None:
    root = tmp_path / "legacy"
    scaffold_app_project(
        root,
        app_payload=build_public_app_placeholder(label="Legacy", name="legacy"),
        sample_function="hello-world",
        runtime="nodejs22",
        platform_version=PLATFORM_VERSION_V2,
    )
    bar_dir = root / "src" / "app" / "app-bars"
    bar_dir.mkdir()
    (bar_dir / "ping.json").write_text(
        """{
  "name": "ping_overview",
  "location": "RECORD_OVERVIEW",
  "label": "Layout v21 ping",
  "webhook": {
    "topic": "app.bar.triggered",
    "deliveryMode": "SERVERLESS",
    "serverlessFunction": { "name": "hello-world" }
  }
}
""",
        encoding="utf-8",
    )
    upgrade_layout_to_v21(root)
    hello = (root / "src" / "app" / "functions" / "hello-world.js").read_text(encoding="utf-8")
    assert "ping_overview" in hello
    assert "serverlessFunction" not in hello
    assert not (root / "src" / "app" / "app-bars.yaml").exists()
    assert not bar_dir.exists()
    config = load_workspace(root)
    assembled = assemble_local_manifest(
        root, config, {"name": "legacy"}, resolve_functions=False
    )
    bar = assembled["appBars"][0]
    assert bar["webhook"]["serverlessFunction"]["name"] == "hello-world"
    assert bar["webhook"]["topic"] == "app.bar.triggered"


def test_upgrade_rewrites_2026_2_tree(tmp_path: Path) -> None:
    root = tmp_path / "legacy"
    scaffold_app_project(
        root,
        app_payload=build_public_app_placeholder(label="Legacy", name="legacy"),
        sample_function="hello-world",
        runtime="nodejs22",
        platform_version=PLATFORM_VERSION_V2,
    )
    assert (root / "src" / "app" / "functions" / "hello-world" / "index.js").is_file()
    assert (root / "src" / "app" / "inbound").is_dir()
    assert (root / "src" / "app" / "schedules").is_dir()
    result = upgrade_layout_to_v21(root)
    assert result["skipped"] is False
    config = load_workspace(root)
    assert config.platformVersion == PLATFORM_VERSION
    assert (root / "src" / "app" / "functions" / "hello-world.js").is_file()
    assert (root / "src" / "app" / "lifecycle" / "install.js").is_file()
    assert (root / "src" / "app" / "inbound").is_dir()
    assert (root / "src" / "app" / "schedules").is_dir()
    settings_yaml = (root / "src" / "app" / "settings.yaml").read_text(encoding="utf-8")
    assert yaml.safe_load(settings_yaml) == []
    assert "settingsSchema" not in settings_yaml
    assert not (root / "src" / "app" / "webhooks").exists()
    hello = (root / "src" / "app" / "functions" / "hello-world.js").read_text(encoding="utf-8")
    assert "record.candidate.created" in hello


def test_write_settings_yaml_empty_list(tmp_path: Path) -> None:
    root = tmp_path / "app"
    scaffold_app_project(
        root,
        app_payload=build_public_app_placeholder(label="Demo", name="demo"),
        sample_function=None,
    )
    config = load_workspace(root)
    path = write_settings_yaml(root, config, [], [])
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data == []


def test_write_settings_yaml_fields_with_section(tmp_path: Path) -> None:
    root = tmp_path / "app"
    scaffold_app_project(
        root,
        app_payload=build_public_app_placeholder(label="Demo", name="demo"),
        sample_function=None,
    )
    config = load_workspace(root)
    path = write_settings_yaml(
        root,
        config,
        [
            {
                "name": "candidate_mapping",
                "type": "MAPPING",
                "label": "Candidate mapping",
                "section": "Candidate",
                "sectionSubtitle": "Map CV fields and parsing behavior",
            },
            {
                "name": "parse_on_cv_change",
                "type": "SWITCH",
                "label": "Parse when a CV changes",
                "section": "Candidate",
            },
            {"name": "orphan", "type": "SWITCH", "label": "Standalone"},
        ],
    )
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    assert isinstance(data, list)
    assert "settingsSchema" not in text
    assert data[0]["section"] == "Candidate"
    assert data[0]["sectionSubtitle"] == "Map CV fields and parsing behavior"
    assert data[2].get("section") is None

    assembled = assemble_local_manifest(
        root, config, {"name": "demo"}, resolve_functions=False
    )
    assert [item["name"] for item in assembled["settingsSchema"]] == [
        "candidate_mapping",
        "parse_on_cv_change",
        "orphan",
    ]
    assert "section" not in assembled["settingsSchema"][0]
    assert assembled["settingsSections"] == [
        {
            "title": "Candidate",
            "subtitle": "Map CV fields and parsing behavior",
            "settings": ["candidate_mapping", "parse_on_cv_change"],
        }
    ]


def test_read_legacy_two_key_settings_yaml(tmp_path: Path) -> None:
    root = tmp_path / "app"
    scaffold_app_project(
        root,
        app_payload=build_public_app_placeholder(label="Demo", name="demo"),
        sample_function=None,
    )
    config = load_workspace(root)
    path = root / "src" / "app" / "settings.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "settingsSchema": [
                    {"name": "candidate_mapping", "type": "MAPPING", "label": "Candidate"},
                    {"name": "orphan", "type": "SWITCH"},
                ],
                "settingsSections": [
                    {
                        "title": "Candidate",
                        "subtitle": "From old file",
                        "settings": ["candidate_mapping"],
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    parsed = parse_settings_yaml(yaml.safe_load(path.read_text(encoding="utf-8")))
    assert parsed[0]["section"] == "Candidate"
    assert parsed[0]["sectionSubtitle"] == "From old file"
    assert "section" not in parsed[1]

    sections = [item for _p, item in discover_local_settings_sections(root, config)]
    assert sections == [
        {
            "title": "Candidate",
            "subtitle": "From old file",
            "settings": ["candidate_mapping"],
        }
    ]

    rewritten = write_settings_yaml(root, config, parsed)
    text = rewritten.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    assert isinstance(data, list)
    assert "settingsSchema:" not in text
    assert data[0]["section"] == "Candidate"


def test_parse_section_object_list() -> None:
    fields = parse_settings_yaml(
        [
            {
                "title": "Candidate",
                "subtitle": "From section objects",
                "fields": [
                    {"name": "candidate_mapping", "type": "MAPPING"},
                    {"name": "parse_on_cv_change", "type": "SWITCH"},
                ],
            }
        ]
    )
    assert [item["name"] for item in fields] == [
        "candidate_mapping",
        "parse_on_cv_change",
    ]
    assert fields[0]["section"] == "Candidate"
    assert fields[0]["sectionSubtitle"] == "From section objects"


def test_add_setting_appends_to_settings_yaml(tmp_path: Path) -> None:
    root = tmp_path / "app"
    scaffold_app_project(
        root,
        app_payload=build_public_app_placeholder(label="Demo", name="demo"),
        sample_function=None,
    )
    config = load_workspace(root)
    path = append_settings_yaml_field(
        root,
        config,
        {"name": "api_base", "type": "SINGLE_LINE", "label": "API base"},
    )
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data == [
        {"name": "api_base", "type": "SINGLE_LINE", "label": "API base"}
    ]
    manifest = (root / "src" / "app" / "app.caraer.yaml").read_text(encoding="utf-8")
    assert "api_base" not in manifest


def test_upgrade_copies_yaml_settings_into_flat_list(tmp_path: Path) -> None:
    root = tmp_path / "legacy"
    scaffold_app_project(
        root,
        app_payload=build_public_app_placeholder(label="Legacy", name="legacy"),
        sample_function=None,
        platform_version=PLATFORM_VERSION_V2,
    )
    manifest = root / "src" / "app" / "app.caraer.yaml"
    payload = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    payload["settingsSchema"] = [
        {"name": "candidate_mapping", "type": "MAPPING", "label": "Candidate mapping"}
    ]
    payload["settingsSections"] = [
        {
            "title": "Candidate",
            "subtitle": "From 2026.2 yaml",
            "settings": ["candidate_mapping"],
        }
    ]
    manifest.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    upgrade_layout_to_v21(root)
    data = yaml.safe_load((root / "src" / "app" / "settings.yaml").read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert data[0]["name"] == "candidate_mapping"
    assert data[0]["section"] == "Candidate"
    assert data[0]["sectionSubtitle"] == "From 2026.2 yaml"
    upgraded = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    assert "settingsSchema" not in upgraded
    assert "settingsSections" not in upgraded


def test_app_bar_dialog_rejects_unknown_field_type(tmp_path: Path) -> None:
    root = tmp_path / "app"
    scaffold_app_project(
        root,
        app_payload=build_public_app_placeholder(label="Demo", name="demo"),
        sample_function="hello-world",
        runtime="nodejs22",
    )
    path = root / "src" / "app" / "functions" / "hello-world.js"
    source = path.read_text(encoding="utf-8")
    manifest = parse_code_manifest(source)
    manifest["appBars"] = [
        {
            "name": "ping_overview",
            "location": "RECORD_OVERVIEW",
            "label": "Ping",
            "settingsSchema": [{"name": "note", "type": "NOT_A_TYPE"}],
        }
    ]
    path.write_text(upsert_code_manifest(source, manifest), encoding="utf-8")
    report = validate_local_app(root)
    assert any("NOT_A_TYPE" in issue.message for issue in report.issues)


EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "layout-v21"
DUE_TOPIC = "record.<setting:due_date.objectName>.date_due.<setting:due_date.propertyName>"


def _webhook_topics(root: Path) -> list[dict]:
    config = load_workspace(root)
    files = discover_layout_v21_functions(root, config)
    return [item for _, item in webhook_items_from_files(files)]


def test_example_webhook_cases_are_separate_functions() -> None:
    items = _webhook_topics(EXAMPLE)
    by_topic = {item["topic"]: item for item in items}
    assert "record.<setting:target_object>.created" in by_topic
    assert by_topic[DUE_TOPIC]["triggerOffsetSeconds"] == 0
    stems = {item["serverlessFunction"]["name"] for item in items}
    assert {"hello-world", "due-date"} <= stems
    assert "field-map" not in stems
    config = load_workspace(EXAMPLE)
    files = discover_layout_v21_functions(EXAMPLE, config)
    by_name = {item.name: item for item in files}
    assert by_name["ping"].role == "appbars"
    assert by_name["list-dialog-options"].path.parent.name == "appbars"
    assert "appBars" not in (EXAMPLE / "src" / "app" / "functions" / "hello-world.js").read_text(
        encoding="utf-8"
    )
    assert not (EXAMPLE / "src" / "app" / "app-bars.yaml").exists()
    report = validate_local_app(EXAMPLE)
    assert report.ok, [issue.message for issue in report.issues]


def test_example_documents_function_body_shapes() -> None:
    shared = (EXAMPLE / "src" / "app" / "shared" / "index.js").read_text(encoding="utf-8")
    assert "eventType:" in shared
    assert "dialog: body.appBarSettingsValues" in shared
    assert "body.record && body.record.record" in shared or "record.record" in shared
    docs = (Path(__file__).resolve().parents[2] / "docs")
    functions = (docs / "functions.md").read_text(encoding="utf-8")
    webhooks = (docs / "webhooks.md").read_text(encoding="utf-8")
    assert "scheduleName" in functions
    assert "app.inbound" in functions
    assert "Installed" in functions
    assert "body.record.record" in webhooks or "record.record" in webhooks
    assert "appBarSettingsValues" in webhooks
    install = (EXAMPLE / "src" / "app" / "lifecycle" / "install.js").read_text(encoding="utf-8")
    heartbeat = (EXAMPLE / "src" / "app" / "schedules" / "heartbeat.js").read_text(encoding="utf-8")
    echo = (EXAMPLE / "src" / "app" / "inbound" / "echo.js").read_text(encoding="utf-8")
    assert "Installed" in install
    assert "scheduleName" in heartbeat or "body.payload" in heartbeat
    assert "body.payload" in echo or "ctx.body" in echo
