import copy
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator


class AppToolSchemaTest(unittest.TestCase):
    def test_bundled_schema_validates_optional_metadata_without_inserting_defaults(self):
        schema = json.loads((Path(__file__).parents[2] / "schemas/app.caraer.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator({"$ref": "#/$defs/appBar", "$defs": schema["$defs"]})
        bar = {"location": "TOOL_BAR", "label": "Console"}
        original = copy.deepcopy(bar)
        validator.validate(bar)
        self.assertEqual(original, bar)
        fields = schema["$defs"]["appBar"]["properties"]
        for name in ("navigationPlacement", "requiredUserScopes", "routeAliases"):
            self.assertNotIn("default", fields[name])
        validator.validate({**bar, "navigationPlacement": "SETTINGS", "requiredUserScopes": ["tools.apps.read"],
                            "routeAliases": ["workflow-console"]})
        validator.validate({**bar, "navigationPlacement": "SUITE", "requiredUserScopes": [], "routeAliases": []})
        self.assertTrue(list(validator.iter_errors({**bar, "navigationPlacement": "UNKNOWN"})))
        self.assertTrue(list(validator.iter_errors({**bar, "routeAliases": ["../settings"]})))
