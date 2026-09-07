from __future__ import annotations

import json
from pathlib import Path

from caraer_cli.app_sync import resolve_app_root, resolve_local_app_root
from caraer_cli.project.paths import app_file_unless_in_workspace


def _make_app(root: Path, name: str) -> Path:
    """A minimal app workspace: caraer.json plus its manifest."""
    app = root / name
    (app / "src" / "app").mkdir(parents=True)
    (app / "caraer.json").write_text(json.dumps({"name": name}), encoding="utf-8")
    (app / "src" / "app" / "app.caraer.yaml").write_text(f"name: {name}\n", encoding="utf-8")
    return app


def test_the_directory_you_are_in_beats_the_pin(tmp_path, monkeypatch) -> None:
    here = _make_app(tmp_path, "here")
    pinned = _make_app(tmp_path, "pinned")
    pin = str(pinned / "src" / "app" / "app.caraer.yaml")

    monkeypatch.chdir(here)
    assert app_file_unless_in_workspace(pin) is None
    assert resolve_app_root(app_file=app_file_unless_in_workspace(pin)) == here
    assert resolve_local_app_root(profile_app_file=pin) == here


def test_a_nested_directory_still_finds_its_own_app(tmp_path, monkeypatch) -> None:
    here = _make_app(tmp_path, "here")
    pin = str(_make_app(tmp_path, "pinned") / "src" / "app" / "app.caraer.yaml")

    monkeypatch.chdir(here / "src" / "app")
    assert resolve_local_app_root(profile_app_file=pin) == here


def test_the_pin_is_used_when_you_are_not_in_an_app(tmp_path, monkeypatch) -> None:
    pinned = _make_app(tmp_path, "pinned")
    pin = str(pinned / "src" / "app" / "app.caraer.yaml")

    outside = tmp_path / "elsewhere"
    outside.mkdir()
    monkeypatch.chdir(outside)

    assert app_file_unless_in_workspace(pin) == pin
    assert resolve_local_app_root(profile_app_file=pin) == pinned


def test_an_explicit_file_beats_the_directory(tmp_path, monkeypatch) -> None:
    here = _make_app(tmp_path, "here")
    other = _make_app(tmp_path, "other")

    monkeypatch.chdir(here)
    chosen = str(other / "src" / "app" / "app.caraer.yaml")
    assert resolve_local_app_root(app_file=chosen) == other


def test_no_app_anywhere_reports_the_missing_workspace(tmp_path, monkeypatch) -> None:
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    monkeypatch.chdir(outside)

    try:
        resolve_local_app_root(profile_app_file=None)
    except FileNotFoundError as exc:
        assert "caraer.json" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected a FileNotFoundError")
