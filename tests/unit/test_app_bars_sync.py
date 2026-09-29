from pathlib import Path

from caraer_cli.project.app_bars_sync import (
    resolve_app_bar_functions,
    sanitize_app_bar,
    stamp_app_bar_identities,
    write_app_bars_files,
)
from caraer_cli.project.schema import ProjectConfig


def test_stamp_app_bar_identities_copies_bar_and_webhook_uuids() -> None:
    local = [
        {
            "name": "parse-cvs",
            "location": "RECORD_OVERVIEW",
            "label": "Parse CVs",
            "webhook": {"topic": "app.bar.triggered", "deliveryMode": "SERVERLESS"},
        }
    ]
    remote = [
        {
            "uuid": "bar-1",
            "name": "parse-cvs",
            "location": "RECORD_OVERVIEW",
            "label": "Parse CVs",
            "webhook": {"uuid": "hook-1", "topic": "app.bar.triggered"},
        }
    ]

    stamped = stamp_app_bar_identities(local, remote)

    assert stamped[0]["uuid"] == "bar-1"
    assert stamped[0]["webhook"]["uuid"] == "hook-1"
    assert "uuid" not in local[0]


def test_stamp_app_bar_identities_matches_by_name() -> None:
    local = [
        {
            "name": "parse-cvs",
            "location": "RECORD_OVERVIEW",
            "label": "Parse CVs now",
            "webhook": {"topic": "app.bar.triggered"},
        }
    ]
    remote = [
        {
            "uuid": "bar-1",
            "name": "parse-cvs",
            "location": "RECORD_OVERVIEW",
            "label": "Parse CVs",
            "webhook": {"uuid": "hook-1"},
        }
    ]

    stamped = stamp_app_bar_identities(local, remote)

    assert stamped[0]["uuid"] == "bar-1"
    assert stamped[0]["webhook"]["uuid"] == "hook-1"


def test_sanitize_app_bar_keeps_function_name_and_uuid() -> None:
    sanitized = sanitize_app_bar(
        {
            "name": "ping_overview",
            "location": "RECORD_OVERVIEW",
            "label": "Layout v21 ping",
            "webhook": {
                "topic": "app.bar.triggered",
                "deliveryMode": "SERVERLESS",
                "serverlessFunction": {"name": "hello-world", "uuid": "fn-1"},
            },
        }
    )

    assert sanitized["webhook"]["topic"] == "app.bar.triggered"
    assert sanitized["webhook"]["serverlessFunction"] == {
        "uuid": "fn-1",
        "name": "hello-world",
    }


def test_resolve_app_bar_functions_keeps_existing_uuids() -> None:
    resolved = resolve_app_bar_functions(
        {
            "uuid": "bar-1",
            "location": "RECORD_PREVIEW",
            "label": "Find matches",
            "webhook": {
                "uuid": "hook-1",
                "topic": "app.bar.triggered",
                "serverlessFunction": {"name": "match-records"},
            },
        },
        fn_by_name={"match-records": "fn-1"},
    )

    assert resolved is not None
    assert resolved["uuid"] == "bar-1"
    assert resolved["webhook"]["uuid"] == "hook-1"
    assert resolved["webhook"]["serverlessFunction"]["uuid"] == "fn-1"


def test_write_app_bars_keeps_function_when_remote_omits_webhook(tmp_path: Path) -> None:
    config = ProjectConfig(name="layout_v21_test", platformVersion="2026.2.1", srcDir="src")
    path = tmp_path / "src" / "app" / "functions" / "hello-world.js"
    path.parent.mkdir(parents=True)
    path.write_text(
        "exports.handler = async () => ({});\n"
        "exports.manifest = {\n"
        '  "webhooks": [{ "topic": "record.candidate.created" }],\n'
        '  "appBars": [{\n'
        '    "name": "ping_overview",\n'
        '    "location": "RECORD_OVERVIEW",\n'
        '    "label": "Layout v21 ping"\n'
        "  }]\n"
        "};\n",
        encoding="utf-8",
    )

    write_app_bars_files(
        tmp_path,
        config,
        [
            {
                "uuid": "bar-1",
                "name": "ping_overview",
                "location": "RECORD_OVERVIEW",
                "label": "Layout v21 ping",
            }
        ],
    )

    written = path.read_text(encoding="utf-8")
    assert "serverlessFunction" not in written
    assert "bar-1" not in written
    assert "record.candidate.created" in written
    from caraer_cli.project.app_bars_sync import discover_local_app_bars

    _path, bar = discover_local_app_bars(tmp_path, config)[0]
    assert bar["webhook"]["topic"] == "app.bar.triggered"
    assert bar["webhook"]["serverlessFunction"]["name"] == "hello-world"
