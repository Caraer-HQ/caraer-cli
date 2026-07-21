from __future__ import annotations

from pathlib import Path

import pytest

from caraer_cli.commands.apps import build_public_app_placeholder
from caraer_cli.project.scaffold import scaffold_app_project
from caraer_cli.project.schema import load_workspace
from caraer_cli.project.sync import resolve_local_function_name


def test_resolve_single_local_function(tmp_path: Path) -> None:
    root = tmp_path / "demo"
    scaffold_app_project(
        root,
        app_payload=build_public_app_placeholder(label="Demo", name="demo"),
        sample_function="hello-world",
        force=True,
    )
    config = load_workspace(root)
    assert resolve_local_function_name(root, config, None, interactive=False) == "hello-world"
    assert resolve_local_function_name(root, config, "hello-world") == "hello-world"


def test_resolve_requires_flag_when_multiple(tmp_path: Path) -> None:
    root = tmp_path / "demo"
    scaffold_app_project(
        root,
        app_payload=build_public_app_placeholder(label="Demo", name="demo"),
        sample_function="hello-world",
        force=True,
    )
    second = root / "src" / "app" / "functions" / "other"
    second.mkdir(parents=True)
    (second / "function.caraer.json").write_text(
        '{"name":"other","runtime":"nodejs22"}\n',
        encoding="utf-8",
    )
    (second / "index.js").write_text("exports.handler = async () => {};\n", encoding="utf-8")
    config = load_workspace(root)
    with pytest.raises(ValueError, match="Multiple functions"):
        resolve_local_function_name(root, config, None, interactive=False)
    assert resolve_local_function_name(root, config, "other") == "other"
