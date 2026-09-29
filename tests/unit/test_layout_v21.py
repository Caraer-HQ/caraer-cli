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
    assert (root / "src" / "app" / "app-bars.yaml").is_file()
    assert (root / "src" / "app" / "inbound").is_dir()
    assert (root / "src" / "app" / "schedules").is_dir()
    assert (root / "src" / "app" / "inbound" / ".gitkeep").is_file()
    assert (root / "src" / "app" / "schedules" / ".gitkeep").is_file()
    assert not (root / "src" / "app" / "webhooks").exists()


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
