from __future__ import annotations

import pytest

from caraer_cli.commands.apps_add import parse_visible_when


def test_parses_boolean_equals() -> None:
    assert parse_visible_when("custom_mapping:EQUALS:true") == [
        {"field": "custom_mapping", "operator": "EQUALS", "value": True}
    ]


def test_defaults_to_equals() -> None:
    assert parse_visible_when("toggle::on")[0]["operator"] == "EQUALS"


def test_parses_list_operators() -> None:
    parsed = parse_visible_when("region:IN:eu1|us1")

    assert parsed == [{"field": "region", "operator": "IN", "value": ["eu1", "us1"]}]


def test_parses_multiple_conditions() -> None:
    parsed = parse_visible_when(
        "import_work_experience:EQUALS:true,custom_mapping:EQUALS:true"
    )

    assert [condition["field"] for condition in parsed] == [
        "import_work_experience",
        "custom_mapping",
    ]


def test_valueless_operator_needs_no_value() -> None:
    assert parse_visible_when("candidate_object:IS_SET") == [
        {"field": "candidate_object", "operator": "IS_SET"}
    ]


def test_missing_value_is_rejected() -> None:
    with pytest.raises(ValueError):
        parse_visible_when("toggle:EQUALS")


def test_missing_field_is_rejected() -> None:
    with pytest.raises(ValueError):
        parse_visible_when(":EQUALS:true")
