"""Extracting a deployed build archive over a pull scaffold."""

import io
import zipfile
from pathlib import Path

from caraer_cli.project.source_archive import extract_deployed_archive


def _zip(entries: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in entries.items():
            archive.writestr(name, text)
    return buffer.getvalue()


def test_extract_replaces_scaffold_module(tmp_path: Path) -> None:
    modules = tmp_path / "src" / "app" / "modules"
    (modules / "hello_world").mkdir(parents=True)
    (modules / "hello_world" / "index.astro").write_text("scaffold", encoding="utf-8")
    (tmp_path / "src" / "app" / "functions" / "on-install").mkdir(parents=True)
    (tmp_path / "src" / "app" / "functions" / "on-install" / "index.js").write_text(
        "stub", encoding="utf-8"
    )

    count = extract_deployed_archive(
        tmp_path,
        _zip(
            {
                "src/app/modules/button/index.astro": "button",
                "src/app/functions/install/index.js": "install",
                "../secret.txt": "nope",
            }
        ),
    )

    assert count == 2
    assert (modules / "button" / "index.astro").read_text(encoding="utf-8") == "button"
    assert not (modules / "hello_world").exists()
    assert not (tmp_path / "src" / "app" / "functions" / "on-install").exists()
    assert (tmp_path / "src" / "app" / "functions" / "install" / "index.js").read_text(
        encoding="utf-8"
    ) == "install"
    assert not (tmp_path / "secret.txt").exists()
