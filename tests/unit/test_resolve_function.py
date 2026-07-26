from __future__ import annotations

from pathlib import Path
import shutil

import pytest

from caraer_cli.commands.apps import build_public_app_placeholder
from caraer_cli.project.scaffold import scaffold_app_project
from caraer_cli.project.schema import load_workspace
from caraer_cli.project.sync import resolve_local_function_name, scaffold_function


def test_resolve_single_local_function(tmp_path: Path) -> None:
    root = tmp_path / "demo"
    result = scaffold_app_project(
        root,
        app_payload=build_public_app_placeholder(label="Demo", name="demo"),
        sample_function=None,
        force=True,
    )
    # Strip default lifecycle functions so only one function remains.
    for stem in ("install", "uninstall", "rotate", "update"):
        shutil.rmtree(root / "src" / "app" / "functions" / f"on-{stem}", ignore_errors=True)
        (root / "src" / "app" / "lifecycle" / f"{stem}.json").unlink(missing_ok=True)
    config = load_workspace(root)
    scaffold_function(root, config, "hello-world", "nodejs22")
    assert resolve_local_function_name(root, config, None, interactive=False) == "hello-world"
    assert resolve_local_function_name(root, config, "hello-world") == "hello-world"
    assert result["lifecycle_hooks"]  # still recorded at scaffold time


def test_resolve_requires_flag_when_multiple(tmp_path: Path) -> None:
    root = tmp_path / "demo"
    scaffold_app_project(
        root,
        app_payload=build_public_app_placeholder(label="Demo", name="demo"),
        sample_function="hello-world",
        force=True,
    )
    config = load_workspace(root)
    with pytest.raises(ValueError, match="Multiple functions"):
        resolve_local_function_name(root, config, None, interactive=False)
    assert resolve_local_function_name(root, config, "hello-world") == "hello-world"
    assert resolve_local_function_name(root, config, "on-install") == "on-install"
