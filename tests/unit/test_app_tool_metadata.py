from pathlib import Path

import pytest

from caraer_cli.project.app_bars_sync import (
    discover_local_app_bars,
    sanitize_app_bar,
    stamp_app_bar_identities,
    write_app_bars_files,
)
from caraer_cli.project.code_manifest import parse_code_manifest_file
from caraer_cli.project.function_files import LocalFunctionFile, app_bar_items_from_files
from caraer_cli.project.schema import ProjectConfig
from caraer_cli.project.paths import appbars_dir

METADATA = {
    "navigationPlacement": "SETTINGS",
    "requiredUserScopes": ["tools.apps.read"],
    "routeAliases": ["workflow-console"],
}


@pytest.mark.parametrize("metadata", [METADATA, {}, {
    "navigationPlacement": "SUITE", "requiredUserScopes": [], "routeAliases": [],
}])
def test_sanitize_and_function_discovery_preserve_only_deliberate_metadata(metadata: dict) -> None:
    bar = {"name": "console", "location": "TOOL_BAR", "label": "Console", **metadata}
    assert sanitize_app_bar(bar) == bar
    file = LocalFunctionFile("console", "appbars", Path("console.js"), "nodejs22", {"appBar": bar})
    assert app_bar_items_from_files([file])[0][1] == bar
    stamped = stamp_app_bar_identities([bar], [{**bar, "uuid": "bar-uuid"}])[0]
    assert stamped == {**bar, "uuid": "bar-uuid"}
    assert "uuid" not in bar


def test_null_metadata_remains_omitted_instead_of_resetting_existing_server_values() -> None:
    bar = {"location": "TOOL_BAR", "label": "Console", **dict.fromkeys(METADATA)}
    assert sanitize_app_bar(bar) == {"location": "TOOL_BAR", "label": "Console"}


@pytest.mark.parametrize("metadata", [METADATA, {}, {
    "navigationPlacement": "SUITE", "requiredUserScopes": [], "routeAliases": [],
}])
def test_pull_to_function_manifest_and_rediscover_retains_metadata(tmp_path: Path, metadata: dict) -> None:
    config = ProjectConfig(name="generic-tool")
    path = appbars_dir(tmp_path, config.srcDir) / "console.js"
    path.parent.mkdir(parents=True)
    path.write_text('exports.handler = async () => ({ keep: true });\nexports.manifest = { appBar: { name: "console", location: "TOOL_BAR", label: "Console" } };\n')
    bar = {"uuid": "bar-uuid", "name": "console", "location": "TOOL_BAR", "label": "Console", **metadata}
    assert write_app_bars_files(tmp_path, config, [bar]) == 1
    source = path.read_text()
    assert "keep: true" in source
    authored = parse_code_manifest_file(path)["appBars"][0]
    assert authored == {key: value for key, value in bar.items() if key != "uuid"}
    discovered = discover_local_app_bars(tmp_path, config)
    assert len(discovered) == 1
    assert discovered[0][1] == authored
