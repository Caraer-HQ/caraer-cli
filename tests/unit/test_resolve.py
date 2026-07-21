from __future__ import annotations

from caraer_cli.context import AppContext
from caraer_cli.resolve import resolve_app_file, resolve_app_uuid
from caraer_cli.state.config import CliConfig, ProfileConfig


def test_resolve_app_uuid_from_profile() -> None:
    ctx = AppContext(
        config=CliConfig.default(),
        profile_name="dev",
        profile=ProfileConfig(base_url="http://localhost:8080", app_uuid="app-1"),
        token="t",
        output="table",
        debug=False,
    )
    assert resolve_app_uuid(ctx, None) == "app-1"
    assert resolve_app_uuid(ctx, "app-2") == "app-2"


def test_resolve_app_uuid_requires_selection() -> None:
    ctx = AppContext(
        config=CliConfig.default(),
        profile_name="dev",
        profile=ProfileConfig(base_url="http://localhost:8080", app_file="/tmp/app.caraer.yaml"),
        token="t",
        output="table",
        debug=False,
    )
    try:
        resolve_app_uuid(ctx, None)
    except ValueError as exc:
        assert "apps select" in str(exc)
        assert "local app file" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_resolve_app_file_from_profile(tmp_path) -> None:
    app_path = tmp_path / "app.caraer.yaml"
    app_path.write_text("name: demo\n", encoding="utf-8")
    ctx = AppContext(
        config=CliConfig.default(),
        profile_name="dev",
        profile=ProfileConfig(base_url="http://localhost:8080", app_file=str(app_path)),
        token="t",
        output="table",
        debug=False,
    )
    assert resolve_app_file(ctx, None) == app_path.resolve()
