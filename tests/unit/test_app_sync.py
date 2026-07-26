from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from caraer_cli.commands.apps import build_public_app_placeholder
from caraer_cli.project.scaffold import scaffold_app_project


def test_canonicalize_app_uuid_resolves_name() -> None:
    client = MagicMock()
    client_response = {"data": {"uuid": "f66e0650-26ab-4bd0-942f-10e0c52a6ff8", "name": "demo"}}
    with patch("caraer_cli.app_sync.apps_api.get_app", return_value=client_response):
        from caraer_cli.app_sync import _canonicalize_app_uuid

        assert _canonicalize_app_uuid(client, "demo") == "f66e0650-26ab-4bd0-942f-10e0c52a6ff8"


def test_push_app_pipeline_order(tmp_path: Path) -> None:
    root = tmp_path / "demo"
    scaffold_app_project(
        root,
        app_payload=build_public_app_placeholder(label="Demo", name="demo"),
        app_uuid="app-1",
        sample_function=None,
        force=True,
    )
    wh = root / "src" / "app" / "webhooks" / "hook.json"
    wh.write_text(
        json.dumps(
            {
                "topic": "record.created",
                "deliveryMode": "HTTP",
                "url": "https://example.com",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    calls: list[str] = []

    def track_manifest(*_a, **_k):
        calls.append("manifest")
        return {"uuid": "app-1", "name": "demo", "label": "Demo"}

    def track_functions(*_a, **_k):
        calls.append("functions")
        return {"mode": "legacy", "functions": []}

    def track_webhooks(*_a, **_k):
        calls.append("webhooks")
        return {"webhooks": [{"action": "created"}], "deleted": []}

    def track_schedules(*_a, **_k):
        calls.append("schedules")
        return {"pushed": 0}

    def track_inbound(*_a, **_k):
        calls.append("inbound")
        return {"pushed": 0}

    def track_oauth(*_a, **_k):
        calls.append("oauth")
        return {"pushed": 0, "skipped": True}

    client = MagicMock()
    with (
        patch("caraer_cli.app_sync.ensure_linked", side_effect=lambda c, r, cfg, **k: cfg),
        patch("caraer_cli.app_sync.push_manifest", side_effect=track_manifest),
        patch("caraer_cli.app_sync.push_functions", side_effect=track_functions),
        patch("caraer_cli.app_sync.push_webhooks", side_effect=track_webhooks),
        patch("caraer_cli.app_sync.push_schedules", side_effect=track_schedules),
        patch("caraer_cli.app_sync.push_inbound", side_effect=track_inbound),
        patch("caraer_cli.app_sync.push_external_oauth_providers", side_effect=track_oauth),
    ):
        from caraer_cli.app_sync import push_app

        result = push_app(client, root, app_uuid="app-1", legacy_functions=True)

    assert calls == ["manifest", "functions", "webhooks", "schedules", "inbound", "oauth"]
    assert result["appUuid"] == "app-1"
    assert "schedules" in result
    assert "inbound" in result
    assert "externalOAuthProviders" in result
