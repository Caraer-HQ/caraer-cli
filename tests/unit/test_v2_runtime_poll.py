from __future__ import annotations

from unittest.mock import MagicMock, patch

from caraer_cli.app_sync import _poll_v2_runtime
from caraer_cli.project.schema import ProjectConfig


def test_poll_v2_runtime_returns_when_ready() -> None:
    client = MagicMock()
    config = ProjectConfig(
        name="demo",
        appUuid="app-1",
        platformVersion="2026.2",
        runtime="nodejs22",
    )
    with patch("caraer_cli.app_sync.apps_api.get_app") as get_app:
        get_app.return_value = {
            "data": {
                "platformVersion": 2,
                "runtime": "nodejs22",
                "runtimeStatus": "READY",
                "runtimeBaseUrl": "https://example.run.app",
                "runtimeRevision": "rev-1",
            }
        }
        result = _poll_v2_runtime(client, config, timeout_s=5, interval_s=0.01)
    assert result["runtimeStatus"] == "READY"
    assert result["runtimeBaseUrl"] == "https://example.run.app"


def test_poll_v2_skipped_for_v1() -> None:
    client = MagicMock()
    config = ProjectConfig(name="demo", appUuid="app-1", platformVersion="2026.1")
    assert _poll_v2_runtime(client, config) == {}
