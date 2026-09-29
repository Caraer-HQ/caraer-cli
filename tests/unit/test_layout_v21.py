from __future__ import annotations

import json
from pathlib import Path

from caraer_cli.commands.apps import build_public_app_placeholder
from caraer_cli.project.code_manifest import parse_code_manifest, upsert_code_manifest
from caraer_cli.project.function_files import discover_layout_v21_functions, webhook_items_from_files
from caraer_cli.project.layout_upgrade import upgrade_layout_to_v21
from caraer_cli.project.scaffold import scaffold_app_project
from caraer_cli.project.schema import PLATFORM_VERSION, PLATFORM_VERSION_V2, load_workspace


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
    assert (root / "src" / "app" / "settings.yaml").is_file()
    assert (root / "src" / "app" / "app-bars.yaml").is_file()
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
    result = upgrade_layout_to_v21(root)
    assert result["skipped"] is False
    config = load_workspace(root)
    assert config.platformVersion == PLATFORM_VERSION
    assert (root / "src" / "app" / "functions" / "hello-world.js").is_file()
    assert (root / "src" / "app" / "lifecycle" / "install.js").is_file()
    assert (root / "src" / "app" / "settings.yaml").is_file()
    assert not (root / "src" / "app" / "webhooks").exists()
    hello = (root / "src" / "app" / "functions" / "hello-world.js").read_text(encoding="utf-8")
    assert "record.candidate.created" in hello
