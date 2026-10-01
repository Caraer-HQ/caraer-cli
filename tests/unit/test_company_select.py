from __future__ import annotations

from caraer_cli.commands.company import _company_rows


def test_company_rows_keep_name_and_uuid() -> None:
    rows = _company_rows(
        [
            {"name": "Acme", "uuid": "aaa"},
            {"name": "", "uuid": "bbb"},
            {"uuid": ""},
            "skip",
        ]
    )
    assert rows == [
        {"name": "Acme", "uuid": "aaa"},
        {"name": "bbb", "uuid": "bbb"},
    ]
