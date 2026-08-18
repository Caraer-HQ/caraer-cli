from __future__ import annotations

from pathlib import Path

import pytest

from caraer_cli.project.scaffold import scaffold_app_project
from caraer_cli.project.schema import load_workspace
from caraer_cli.project.sync import scaffold_options_function
from caraer_cli.wizard.catalog import SETTING_FIELD_TYPES
from caraer_cli.wizard.marketplace import (
    _parse_static_options,
    normalize_setting_field_name,
    prompt_setting_field,
)


def test_setting_field_types_include_object_and_property_selects() -> None:
    keys = {key for key, _ in SETTING_FIELD_TYPES}
    assert {
        "OBJECT_SINGLE_SELECT",
        "OBJECT_MULTI_SELECT",
        "PROPERTY_SINGLE_SELECT",
        "PROPERTY_MULTI_SELECT",
        "RECORD_SINGLE_SELECT",
        "RECORD_MULTI_SELECT",
        "MAPPING",
        "SECRET",
        "SINGLE_SELECT",
        "MULTI_SELECT",
    } <= keys


def test_parse_static_options_uses_name_label() -> None:
    assert _parse_static_options("Alpha=a, Beta") == [
        {"name": "a", "label": "Alpha"},
        {"name": "Beta", "label": "Beta"},
    ]


def test_normalize_setting_field_name() -> None:
    assert normalize_setting_field_name("My Field!") == "my_field"
    assert normalize_setting_field_name("API Key 2") == "api_key"


def test_prompt_setting_field_derives_name_from_label_noninteractive() -> None:
    field = prompt_setting_field(
        label="API Key",
        field_type="SECRET",
        required=True,
        help_text="",
        default_value="",
    )
    assert field["name"] == "api_key"
    assert field["label"] == "API Key"


def test_prompt_object_select_noninteractive() -> None:
    field = prompt_setting_field(
        name="attendee_object",
        label="Attendee object",
        field_type="OBJECT_SINGLE_SELECT",
        required=True,
        help_text="Pick contacts",
        default_value="",
    )
    assert field["type"] == "OBJECT_SINGLE_SELECT"
    assert "options" not in field
    assert "optionsSource" not in field


def test_prompt_property_select_noninteractive() -> None:
    field = prompt_setting_field(
        name="email_property",
        label="Email property",
        field_type="PROPERTY_SINGLE_SELECT",
        required=False,
        help_text="",
        default_value="",
    )
    assert field["type"] == "PROPERTY_SINGLE_SELECT"


def test_prompt_dynamic_select_with_depends_on() -> None:
    field = prompt_setting_field(
        name="calendars",
        label="Calendars",
        field_type="MULTI_SELECT",
        required=True,
        help_text="",
        default_value="",
        options_mode="dynamic",
        options_function="list-calendars",
        depends_on=["attendee_object"],
    )
    assert field["optionsSource"]["serverlessFunctionName"] == "list-calendars"
    assert field["optionsSource"]["dependsOn"] == ["attendee_object"]
    assert field["optionsSource"]["type"] == "SERVERLESS"


def test_prompt_static_select_noninteractive() -> None:
    field = prompt_setting_field(
        name="mode",
        label="Mode",
        field_type="SINGLE_SELECT",
        required=False,
        help_text="",
        default_value="",
        options_mode="static",
        static_options="Fast=fast,Safe=safe",
    )
    assert field["options"] == [
        {"name": "fast", "label": "Fast"},
        {"name": "safe", "label": "Safe"},
    ]


def test_prompt_static_select_requires_options_noninteractive() -> None:
    with pytest.raises(ValueError, match="--options"):
        prompt_setting_field(
            name="mode",
            field_type="SINGLE_SELECT",
            options_mode="static",
            required=False,
            help_text="",
            default_value="",
        )


def test_scaffold_options_function_nodejs(tmp_path: Path) -> None:
    result = scaffold_app_project(
        tmp_path / "demo",
        app_payload={"name": "demo", "label": "Demo", "description": "Demo"},
        sample_function=None,
    )
    root = result["root"]
    config = load_workspace(root)
    folder = scaffold_options_function(root, config, "list-items", "nodejs22")
    source = (folder / "index.js").read_text(encoding="utf-8")
    assert "LOAD_SETTING_OPTIONS" in source
    assert "options" in source
    assert "flattenSettings" in source
    assert "dependsOn" in source
    manifest = folder / "function.caraer.json"
    assert manifest.is_file()
