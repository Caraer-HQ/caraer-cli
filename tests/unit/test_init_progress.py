from threading import Event, Thread
from unittest.mock import MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

from caraer_cli.commands import apps as apps_commands
from caraer_cli.context import AppContext
from caraer_cli.formatters import progress
from caraer_cli.state.config import CliConfig, ProfileConfig


def test_progress_reports_start_and_completion_on_stderr(capsys):
    with progress.progress_step("Creating files"):
        during = capsys.readouterr()
        assert "… Creating files" in during.err
        assert "✓" not in during.err
        assert during.out == ""
    assert "✓ Creating files" in capsys.readouterr().err


def test_progress_reports_long_wait_and_stops_reporter(monkeypatch, capsys):
    reported = Event()
    reporters = []
    original_print = progress.console.print

    def record_print(message):
        original_print(message)
        if "still working" in str(message):
            reported.set()

    def create_thread(**kwargs):
        thread = Thread(**kwargs)
        reporters.append(thread)
        return thread

    monkeypatch.setattr(progress.console, "print", record_print)
    monkeypatch.setattr(progress, "Thread", create_thread)
    with progress.progress_step("Installing dependencies", interval=0.01):
        assert reported.wait(2), "No progress update during a quiet operation"
    output = capsys.readouterr().err
    assert "still working" in output
    assert "elapsed)" in output
    assert "✓ Installing dependencies" in output
    assert not reporters[0].is_alive()


def test_progress_does_not_report_success_after_failure(monkeypatch, capsys):
    reporters = []

    def create_thread(**kwargs):
        thread = Thread(**kwargs)
        reporters.append(thread)
        return thread

    monkeypatch.setattr(progress, "Thread", create_thread)
    with pytest.raises(RuntimeError, match="failed"):
        with progress.progress_step("Installing dependencies"):
            raise RuntimeError("failed")
    assert "✓" not in capsys.readouterr().err
    assert not reporters[0].is_alive()


@pytest.mark.parametrize("linked", [False, True])
def test_init_shows_progress_before_installing_dependencies(tmp_path, linked):
    profile = ProfileConfig(base_url="http://localhost:8080", app_uuid="app-1" if linked else None)
    ctx = AppContext(
        config=CliConfig(active_profile="dev", profiles={"dev": profile}),
        profile_name="dev", profile=profile, token="token", output="json", debug=False,
    )
    app = typer.Typer()
    app.add_typer(apps_commands.app, name="apps")

    @app.callback()
    def root(context: typer.Context):
        context.obj = ctx

    def install(_root):
        # Installation starts only after scaffolding has completed.
        assert (_root / "caraer.json").is_file()
        assert (_root / "src/app/modules/home/home.astro").is_file()
        assert (_root / "src/app/modules/_components/FeatureCard.astro").is_file()
        return True

    with (
        patch("caraer_cli.project.scaffold.install_npm_dependencies", side_effect=install),
        patch("caraer_cli.api.apps.get_app", return_value={"data": {}}),
        patch("caraer_cli.api.projects.create_or_get_project", return_value={"data": {"uuid": "project-1"}}),
        patch("caraer_cli.app_sync.ensure_linked", return_value=MagicMock()),
    ):
        result = CliRunner().invoke(app, ["apps", "init", "--dir", str(tmp_path / "demo"), "--no-select"])
    assert result.exit_code == 0, result.output
    assert "… Creating app files" in result.stderr
    assert "✓ Creating app files" in result.stderr
    assert "Created app at" in result.stdout
    if linked:
        assert "… Fetching linked app" in result.stderr
        assert "… Preparing remote project" in result.stderr
        assert "… Linking app to remote project" in result.stderr
