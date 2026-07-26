from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from caraer_cli.project.schema import PLATFORM_VERSION, ProjectConfig, save_project_config


def test_migrate_v2_updates_local_workspace(tmp_path: Path) -> None:
    """Simulate the local side of migrate-v2 (config rewrite after READY)."""
    save_project_config(
        tmp_path / "caraer.json",
        ProjectConfig(platformVersion="2026.1", name="legacy", appUuid="app-1"),
    )
    config = ProjectConfig(
        platformVersion=PLATFORM_VERSION,
        name="legacy",
        appUuid="app-1",
        runtime="nodejs22",
    )
    save_project_config(tmp_path / "caraer.json", config)
    loaded = ProjectConfig.model_validate(
        json.loads((tmp_path / "caraer.json").read_text(encoding="utf-8"))
    )
    assert loaded.platformVersion == "2026.2"
    assert loaded.runtime == "nodejs22"


def test_migrate_v2_api_client_called() -> None:
    from caraer_cli.api import apps as apps_api

    client = MagicMock()
    client.context.timeout_seconds = 30.0
    client.request.return_value = {
        "data": {
            "app": {"uuid": "app-1", "platformVersion": 2, "runtimeStatus": "PROVISIONING"},
            "migration": {"fromVersion": 1, "toVersion": 2},
        }
    }
    result = apps_api.migrate_app_to_v2(client, "app-1", runtime="nodejs22")
    client.request.assert_called_once()
    args = client.request.call_args
    assert args.args[0] == "POST"
    assert "migrate-v2" in args.args[1]
    assert result["data"]["migration"]["toVersion"] == 2
