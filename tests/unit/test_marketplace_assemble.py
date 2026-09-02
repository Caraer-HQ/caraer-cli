from __future__ import annotations

import json
from pathlib import Path

from caraer_cli.commands.apps import build_public_app_placeholder
from caraer_cli.project.marketplace_assemble import (
    assemble_local_manifest,
    split_marketplace_to_disk,
)
from caraer_cli.project.scaffold import scaffold_app_project, scaffold_lifecycle_hook
from caraer_cli.project.schema import load_workspace
from caraer_cli.project.settings_sections_sync import discover_local_settings_sections
from caraer_cli.project.settings_sync import discover_local_settings
from caraer_cli.project.state import load_state, save_state


def test_assemble_merges_settings_files_over_yaml(tmp_path: Path) -> None:
    root = tmp_path / "demo"
    scaffold_app_project(
        root,
        app_payload=build_public_app_placeholder(label="Demo", name="demo"),
        sample_function=None,
        force=True,
    )
    config = load_workspace(root)
    settings = root / "src" / "app" / "settings"
    settings.mkdir(parents=True, exist_ok=True)
    (settings / "api-base.json").write_text(
        json.dumps(
            {
                "name": "api_base",
                "label": "API base",
                "type": "SINGLE_LINE",
                "required": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    local = {
        "name": "demo",
        "settingsSchema": [
            {
                "name": "api_base",
                "label": "From YAML",
                "type": "SINGLE_LINE",
            }
        ],
        "appBars": [],
    }
    assembled = assemble_local_manifest(
        root, config, local, resolve_functions=False
    )
    assert len(assembled["settingsSchema"]) == 1
    assert assembled["settingsSchema"][0]["label"] == "API base"


def test_resolve_setting_options_source_by_name(tmp_path: Path) -> None:
    root = tmp_path / "demo"
    scaffold_app_project(
        root,
        app_payload=build_public_app_placeholder(label="Demo", name="demo"),
        sample_function=None,
        force=True,
    )
    config = load_workspace(root)
    save_state(
        root,
        {
            "functions": {
                "list-calendars": {"uuid": "fn-list-uuid"},
                "on-install": {"uuid": "fn-install-uuid"},
                "on-uninstall": {"uuid": "fn-uninstall-uuid"},
                "on-rotate": {"uuid": "fn-rotate-uuid"},
                "on-update": {"uuid": "fn-update-uuid"},
            }
        },
    )
    local = {
        "name": "demo",
        "settingsSchema": [
            {
                "name": "google_calendars",
                "label": "Calendars",
                "type": "MULTI_SELECT",
                "optionsSource": {
                    "type": "SERVERLESS",
                    "serverlessFunctionName": "list-calendars",
                },
            }
        ],
        "appBars": [],
    }
    assembled = assemble_local_manifest(root, config, local, resolve_functions=True)
    source = assembled["settingsSchema"][0]["optionsSource"]
    assert source["serverlessFunctionUuid"] == "fn-list-uuid"
    assert source["serverlessFunctionName"] == "list-calendars"


def test_resolve_setting_action_source_by_name(tmp_path: Path) -> None:
    root = tmp_path / "demo"
    scaffold_app_project(
        root,
        app_payload=build_public_app_placeholder(label="Demo", name="demo"),
        sample_function=None,
        force=True,
    )
    config = load_workspace(root)
    save_state(
        root,
        {
            "functions": {
                "google-sync": {"uuid": "fn-sync-uuid"},
                "on-install": {"uuid": "fn-install-uuid"},
                "on-uninstall": {"uuid": "fn-uninstall-uuid"},
                "on-rotate": {"uuid": "fn-rotate-uuid"},
                "on-update": {"uuid": "fn-update-uuid"},
            }
        },
    )
    local = {
        "name": "demo",
        "settingsSchema": [
            {
                "name": "resync",
                "label": "Resync",
                "type": "ACTION",
                "actionSource": {
                    "type": "SERVERLESS",
                    "serverlessFunctionName": "google-sync",
                    "enqueue": True,
                },
            }
        ],
        "appBars": [],
    }
    assembled = assemble_local_manifest(root, config, local, resolve_functions=True)
    source = assembled["settingsSchema"][0]["actionSource"]
    assert source["serverlessFunctionUuid"] == "fn-sync-uuid"
    assert source["serverlessFunctionName"] == "google-sync"


def test_split_and_lifecycle_resolve(tmp_path: Path) -> None:
    root = tmp_path / "demo"
    result = scaffold_app_project(
        root,
        app_payload=build_public_app_placeholder(label="Demo", name="demo"),
        sample_function=None,
        force=True,
    )
    config = load_workspace(root)
    # Force-refresh one hook after init already created them.
    scaffold_lifecycle_hook(
        root, config, event="install", force=True, create_function=True
    )

    state = load_state(root)
    state["functions"] = {
        "on-install": {"uuid": "fn-install-uuid"},
        "on-uninstall": {"uuid": "fn-uninstall-uuid"},
        "on-rotate": {"uuid": "fn-rotate-uuid"},
        "on-update": {"uuid": "fn-update-uuid"},
    }
    save_state(root, state)

    local = {"name": "demo", "settingsSchema": [], "appBars": []}
    assembled = assemble_local_manifest(root, config, local, resolve_functions=True)
    assert assembled["installWebhook"]["serverlessFunction"]["uuid"] == "fn-install-uuid"
    assert assembled["installWebhook"]["topic"] == "app.installed"

    split = split_marketplace_to_disk(
        root,
        config,
        {
            "settingsSchema": [
                {"name": "topic", "label": "Topic", "type": "SINGLE_LINE"}
            ],
            "appBars": [],
            "installWebhook": assembled["installWebhook"],
        },
    )
    assert split["settingsSchema"] == []
    assert "installWebhook" not in split
    names = [item["name"] for _p, item in discover_local_settings(root, config)]
    assert "topic" in names
    assert result["lifecycle_dir"].is_dir()


def test_assemble_merges_settings_sections(tmp_path: Path) -> None:
    root = tmp_path / "demo"
    scaffold_app_project(
        root,
        app_payload=build_public_app_placeholder(label="Demo", name="demo"),
        sample_function=None,
        force=True,
    )
    config = load_workspace(root)
    sections = root / "src" / "app" / "settings-sections"
    sections.mkdir(parents=True, exist_ok=True)
    (sections / "01-candidate.json").write_text(
        json.dumps(
            {
                "title": "Candidate",
                "subtitle": "From disk",
                "settings": ["candidate_mapping"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    local = {
        "name": "demo",
        "settingsSchema": [{"name": "candidate_mapping", "type": "MAPPING"}],
        "settingsSections": [
            {
                "title": "Candidate",
                "subtitle": "From YAML",
                "settings": ["candidate_mapping"],
            }
        ],
        "appBars": [],
    }
    assembled = assemble_local_manifest(
        root, config, local, resolve_functions=False
    )
    assert len(assembled["settingsSections"]) == 1
    assert assembled["settingsSections"][0]["subtitle"] == "From disk"

    split = split_marketplace_to_disk(
        root,
        config,
        {
            "settingsSchema": [{"name": "candidate_mapping", "type": "MAPPING"}],
            "settingsSections": assembled["settingsSections"],
            "appBars": [],
        },
    )
    assert split["settingsSections"] == []
    titles = [item["title"] for _p, item in discover_local_settings_sections(root, config)]
    assert "Candidate" in titles


def test_sanitize_lifecycle_keeps_wait_until_complete() -> None:
    from caraer_cli.project.lifecycle_sync import sanitize_lifecycle

    sanitized = sanitize_lifecycle(
        {
            "topic": "app.installed",
            "deliveryMode": "SERVERLESS",
            "waitUntilComplete": True,
            "serverlessFunction": {"name": "on-install"},
            "uuid": "should-drop",
        }
    )
    assert sanitized["waitUntilComplete"] is True
    assert "uuid" not in sanitized
