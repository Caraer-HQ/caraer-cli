from __future__ import annotations

from pathlib import Path

import pytest

from caraer_cli.project.schema import ProjectConfig
from caraer_cli.project.typegen import generate_types, typegen_output_path


def test_typegen_python(tmp_path: Path) -> None:
    config = ProjectConfig(name="demo", runtime="python312")
    result = generate_types(tmp_path, config)
    assert result["runtime"] == "python"
    path = typegen_output_path(tmp_path, config)
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "class LifecyclePayload" in text
    assert "InstallationState" in text
    with pytest.raises(FileExistsError):
        generate_types(tmp_path, config)


def test_typegen_nodejs_force(tmp_path: Path) -> None:
    config = ProjectConfig(name="demo", runtime="nodejs22")
    generate_types(tmp_path, config)
    result = generate_types(tmp_path, config, force=True)
    assert result["runtime"] == "nodejs"
    text = Path(result["path"]).read_text(encoding="utf-8")
    assert "export interface LifecyclePayload" in text
    assert "EnqueueJobRequest" in text
