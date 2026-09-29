from __future__ import annotations

import json
from pathlib import Path

from caraer_cli.project.schema import ProjectConfig
from caraer_cli.project.settings_sync import (
    discover_local_settings,
    join_settings_payload,
    parse_settings_yaml,
    sanitize_setting,
    split_settings_payload,
    write_settings_files,
)

CONFIG = ProjectConfig(platformVersion="2026.2", name="demo_app", runtime="nodejs22")

CONDITIONAL_FIELD = {
    "name": "work_experience_mapping",
    "label": "Work experience mapping",
    "type": "MAPPING",
    "required": False,
    "valueScope": "COMPANY",
    "visibleWhen": [
        {"field": "custom_work_experience_mapping", "operator": "EQUALS", "value": True}
    ],
    "mappingValue": {"items": [{"fieldName": "jobTitle", "fieldLabel": "Job title"}]},
}


def test_sanitize_setting_keeps_visible_when_and_value_scope() -> None:
    sanitized = sanitize_setting(CONDITIONAL_FIELD)

    assert sanitized["visibleWhen"] == CONDITIONAL_FIELD["visibleWhen"]
    assert sanitized["valueScope"] == "COMPANY"
    assert sanitized["mappingValue"] == CONDITIONAL_FIELD["mappingValue"]


def test_sanitize_setting_drops_unknown_keys() -> None:
    sanitized = sanitize_setting({**CONDITIONAL_FIELD, "_internal": "drop me"})

    assert "_internal" not in sanitized


def test_modular_settings_round_trip_preserves_conditions(tmp_path: Path) -> None:
    write_settings_files(tmp_path, CONFIG, [CONDITIONAL_FIELD])

    written = tmp_path / "src" / "app" / "settings" / "01-work-experience-mapping.json"
    assert json.loads(written.read_text(encoding="utf-8"))["visibleWhen"] == (
        CONDITIONAL_FIELD["visibleWhen"]
    )

    discovered = discover_local_settings(tmp_path, CONFIG)
    assert len(discovered) == 1
    assert discovered[0][1]["visibleWhen"] == CONDITIONAL_FIELD["visibleWhen"]


def test_file_setting_round_trips(tmp_path: Path) -> None:
    field = {"name": "cv_file", "label": "CV", "type": "FILE", "required": True}

    write_settings_files(tmp_path, CONFIG, [field])
    discovered = discover_local_settings(tmp_path, CONFIG)

    assert discovered[0][1]["type"] == "FILE"
    assert discovered[0][0].name == "01-cv-file.json"


def test_write_settings_files_keeps_list_order(tmp_path: Path) -> None:
    write_settings_files(
        tmp_path,
        CONFIG,
        [
            {"name": "candidate_mapping", "type": "MAPPING"},
            {"name": "parse_on_cv_change", "type": "SWITCH"},
            {"name": "enable_matching", "type": "SWITCH"},
        ],
    )

    discovered = discover_local_settings(tmp_path, CONFIG)
    assert [path.name for path, _item in discovered] == [
        "01-candidate-mapping.json",
        "02-parse-on-cv-change.json",
        "03-enable-matching.json",
    ]
    assert [item["name"] for _path, item in discovered] == [
        "candidate_mapping",
        "parse_on_cv_change",
        "enable_matching",
    ]


def test_parse_split_join_settings_yaml_helpers() -> None:
    fields = parse_settings_yaml(
        {
            "settingsSchema": [
                {"name": "candidate_mapping", "type": "MAPPING", "label": "Candidate"},
                {"name": "orphan", "type": "SWITCH"},
            ],
            "settingsSections": [
                {
                    "title": "Candidate",
                    "subtitle": "Map CV fields",
                    "settings": ["candidate_mapping"],
                }
            ],
        }
    )
    assert fields[0]["section"] == "Candidate"
    assert fields[0]["sectionSubtitle"] == "Map CV fields"
    assert "section" not in fields[1]

    schema, sections = split_settings_payload(fields)
    assert [item["name"] for item in schema] == ["candidate_mapping", "orphan"]
    assert "section" not in schema[0]
    assert sections == [
        {
            "title": "Candidate",
            "subtitle": "Map CV fields",
            "settings": ["candidate_mapping"],
        }
    ]

    rejoined = join_settings_payload(schema, sections)
    assert rejoined[0]["section"] == "Candidate"
    assert rejoined[0]["sectionSubtitle"] == "Map CV fields"
    assert "section" not in rejoined[1]
