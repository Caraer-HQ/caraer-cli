from caraer_cli.formatters.output import _print_rows, project_rows


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
