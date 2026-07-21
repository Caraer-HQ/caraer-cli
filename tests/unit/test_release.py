from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from caraer_cli.project.release import (
    bump_patch,
    is_greater,
    latest_build_version,
    next_version,
    resolve_release_for_build,
)


def test_bump_and_compare() -> None:
    assert bump_patch("1.2.3") == "1.2.4"
    assert next_version(None) == "0.1.0"
    assert next_version("0.1.0") == "0.1.1"
    assert is_greater("1.0.0", "0.9.9")
    assert not is_greater("1.0.0", "1.0.0")
    assert not is_greater("1.0.0", "1.0.1")


def test_latest_build_version_picks_highest(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    monkeypatch.setattr(
        "caraer_cli.project.release.projects_api.list_builds",
        lambda _c, _p: {
            "data": [
                {"version": "0.1.0"},
                {"version": "0.2.0"},
                {"version": "0.1.9"},
                {"version": "bad"},
            ]
        },
    )
    assert latest_build_version(client, "proj") == "0.2.0"


def test_resolve_non_interactive_requires_increment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = MagicMock()
    monkeypatch.setattr(
        "caraer_cli.project.release.latest_build_version",
        lambda *_a, **_k: "1.0.0",
    )
    with pytest.raises(ValueError, match="greater than previous"):
        resolve_release_for_build(
            client,
            "proj",
            version="1.0.0",
            release_notes="notes",
            interactive=False,
        )
    version, notes = resolve_release_for_build(
        client,
        "proj",
        version="1.0.1",
        release_notes="Fixed bug",
        interactive=False,
    )
    assert version == "1.0.1"
    assert notes == "Fixed bug"
