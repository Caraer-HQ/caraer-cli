from caraer_cli.project.app_bars_sync import (
    resolve_app_bar_functions,
    stamp_app_bar_identities,
)


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
