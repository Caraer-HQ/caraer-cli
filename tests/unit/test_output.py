from caraer_cli.formatters.output import (
    _format_log_timestamp,
    _log_message,
    _print_rows,
    print_logs,
    project_rows,
)


def test_project_rows_keeps_requested_columns() -> None:
    rows = project_rows(
        [{"uuid": "1", "name": "a", "details": {"x": 1}, "extra": "z"}],
        ["uuid", "name", "privateApp"],
    )
    assert rows == [{"uuid": "1", "name": "a", "privateApp": None}]


def test_print_rows_skips_nested_columns(capsys) -> None:
    _print_rows(
        [
            {
                "uuid": "abc",
                "name": "demo",
                "details": {"title": "Demo"},
                "appBars": [{"name": "bar"}],
            }
        ]
    )
    out = capsys.readouterr().out
    assert "abc" in out
    assert "demo" in out
    assert "title" not in out or "Demo" not in out


def test_print_logs_renders_entries_below_summary(capsys) -> None:
    print_logs(
        {
            "resourceId": "app-abc",
            "functionName": "hello-world",
            "message": "fallback",
            "entries": [
                {
                    "timestamp": "2026-07-21T21:00:02Z",
                    "severity": "INFO",
                    "message": "second",
                },
                {
                    "timestamp": "2026-07-21T21:00:01Z",
                    "severity": "ERROR",
                    "message": "first",
                },
            ],
        }
    )
    out = capsys.readouterr().out
    assert "resourceId" in out
    assert "app-abc" in out
    assert "2" in out
    # Oldest first
    assert out.index("first") < out.index("second")
    assert "ERROR" in out
    assert "INFO" in out
    assert "21:00:01" in out


def test_print_logs_follow_skips_seen(capsys) -> None:
    seen: set[str] = set()
    payload = {
        "resourceId": "app-abc",
        "entries": [
            {"timestamp": "t1", "severity": "INFO", "message": "one"},
        ],
    }
    print_logs(payload, seen=seen, show_header=True)
    first = capsys.readouterr().out
    assert "one" in first

    print_logs(payload, seen=seen, show_header=False)
    second = capsys.readouterr().out
    assert second == ""

    payload["entries"].append({"timestamp": "t2", "severity": "INFO", "message": "two"})
    print_logs(payload, seen=seen, show_header=False)
    third = capsys.readouterr().out
    assert "two" in third
    assert "one" not in third


def test_log_message_skips_protobuf_dumps() -> None:
    assert _log_message({"message": "hello"}) == "hello"
    assert (
        _log_message(
            {
                "message": 'type_url: "type.googleapis.com/google.cloud.audit.AuditLog"\nvalue: "\\022\\000"'
            }
        )
        is None
    )
    assert _format_log_timestamp("2026-07-21T21:16:34.931628Z") == "21:16:34"
