import json
from pathlib import Path

import jsonschema
import pytest

SCHEMA = json.loads((Path(__file__).resolve().parents[2] / "schemas/app.caraer.schema.json").read_text())


def validate(definition, value):
    jsonschema.Draft202012Validator({"$defs": SCHEMA["$defs"], "$ref": f"#/$defs/{definition}"}).validate(value)


def test_action_capability_requires_its_function_scopes_and_action_location():
    bar = {"name": "check", "label": "Check", "location": "RECORD_TRAIT", "capability": "events.availability",
           "capabilityFunction": "discover", "requiredUserScopes": ["records.event.availability.read"]}
    validate("appBar", bar)
    for change in ({"requiredUserScopes": []}, {"location": "TOOL_BAR"}):
        with pytest.raises(jsonschema.ValidationError):
            validate("appBar", {**bar, **change})
    del bar["capabilityFunction"]
    with pytest.raises(jsonschema.ValidationError):
        validate("appBar", bar)


def test_existing_toolbars_keep_empty_scope_metadata_and_info_fields_validate():
    validate("appBar", {"name": "legacy", "label": "Legacy", "location": "TOOL_BAR", "requiredUserScopes": []})
    validate("settingField", {"name": "setup", "type": "INFO", "label": "Setup"})
