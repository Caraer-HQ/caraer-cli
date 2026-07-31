from __future__ import annotations

from typer.testing import CliRunner

from caraer_cli.main import app as typer_app
from caraer_cli.project.typegen import generate_types
from caraer_cli.project.schema import ProjectConfig

runner = CliRunner()


def test_typegen_command_is_deprecated_noop() -> None:
    result = runner.invoke(typer_app, ["apps", "typegen"])
    assert result.exit_code == 0
    assert "deprecated" in result.output.lower()
    assert "@caraer/client" in result.output
    assert "caraer_client" in result.output
    assert "LifecyclePayload" in result.output


def test_generate_types_module_still_writes_for_compat(tmp_path) -> None:
    """Internal helper kept for one release; command no longer calls it."""
    config = ProjectConfig(name="demo", runtime="nodejs22")
    result = generate_types(tmp_path, config)
    assert result["runtime"] == "nodejs"
    text = result["path"].read_text(encoding="utf-8")
    assert "export interface LifecyclePayload" in text
