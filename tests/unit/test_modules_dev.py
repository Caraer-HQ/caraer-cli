"""The local CMS module preview harness."""

from __future__ import annotations

import json
from pathlib import Path

from caraer_cli.project.modules_dev import (
    _harness_install_command,
    _harness_ready,
    write_harness,
)
from caraer_cli.project.schema import load_workspace


def _workspace(tmp_path: Path) -> Path:
    (tmp_path / "caraer.json").write_text(
        json.dumps(
            {
                "platformVersion": "2026.2",
                "name": "demo_app",
                "srcDir": "src",
                "runtime": "nodejs22",
                "privateApp": True,
            }
        ),
        encoding="utf-8",
    )
    app_dir = tmp_path / "src" / "app"
    app_dir.mkdir(parents=True)
    (app_dir / "app.caraer.yaml").write_text(
        "name: demo_app\nlabel: Demo App\nruntime: nodejs22\nauthMethod: API_KEY\n",
        encoding="utf-8",
    )
    return tmp_path


def _write_module(root: Path, name: str) -> None:
    directory = root / "src" / "app" / "modules" / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "index.astro").write_text(
        "---\n"
        f'export const manifest = {{ "name": "{name}", "label": "{name}", '
        '"kind": "section", "category": "content", "fields": [] } '
        "satisfies ModuleManifest;\n"
        "---\n<div />\n",
        encoding="utf-8",
    )


def test_harness_does_not_statically_import_modules(tmp_path: Path) -> None:
    """A syntax error in one module must not fail the preview chrome."""
    root = _workspace(tmp_path)
    _write_module(root, "hero")
    _write_module(root, "rich_text")

    harness, modules = write_harness(
        root,
        load_workspace(root),
        app_name="demo_app",
        runtime_spec="latest",
        tokens_spec="latest",
    )

    page = (harness / "src" / "pages" / "index.astro").read_text(encoding="utf-8")
    config = (harness / "astro.config.mjs").read_text(encoding="utf-8")

    assert [m.name for m in modules] == ["hero", "rich_text"]
    assert "withModuleBoundary" in page
    assert "CaraerModuleBoundary" not in page
    assert "import Module0" not in page
    assert "() => import(\"@modules/hero/index.astro\")" in page
    assert "() => import(\"@modules/rich_text/index.astro\")" in page
    assert "overlay: false" in config


def test_harness_preview_uses_block_flow_like_live_pages(tmp_path: Path) -> None:
    """Modules must fill the frame the way they fill `#main` in production."""
    root = _workspace(tmp_path)
    _write_module(root, "hero")

    harness, _ = write_harness(
        root,
        load_workspace(root),
        app_name="demo_app",
        runtime_spec="latest",
        tokens_spec="latest",
    )
    page = (harness / "src" / "pages" / "index.astro").read_text(encoding="utf-8")
    preview = page.split(".harness__preview {", 1)[1].split("}", 1)[0]
    assert "display: block;" in preview
    assert "width: 100%;" in preview
    assert "display: flex;" not in preview
    assert "justify-content: center;" not in preview


def test_harness_preview_uses_an_iframe_so_media_queries_see_the_frame_width(
    tmp_path: Path,
) -> None:
    """Mobile/Tablet only change a parent max-width; @media needs a viewport."""
    root = _workspace(tmp_path)
    _write_module(root, "hero")

    harness, _ = write_harness(
        root,
        load_workspace(root),
        app_name="demo_app",
        runtime_spec="latest",
        tokens_spec="latest",
    )
    page = (harness / "src" / "pages" / "index.astro").read_text(encoding="utf-8")
    assert "searchParams.get('embed') === '1'" in page
    assert 'params.set(\'embed\', \'1\')' in page
    assert '<iframe' in page
    assert 'class="hx-frame__doc"' in page
    assert "HTMLIFrameElement" in page
    assert "querySelectorAll('.hx-bar .hx-seg button')" in page


def test_harness_hides_fields_that_are_not_visible(tmp_path: Path) -> None:
    """visibleWhen must hide unused slots, the same as the builder sidebar."""
    root = _workspace(tmp_path)
    _write_module(root, "hero")

    harness, _ = write_harness(
        root,
        load_workspace(root),
        app_name="demo_app",
        runtime_spec="latest",
        tokens_spec="latest",
    )
    page = (harness / "src" / "pages" / "index.astro").read_text(encoding="utf-8")
    assert "isFieldVisible" in page
    assert "data-visible-when" in page
    assert "applyFieldVisibility" in page
    assert ".hx-field[hidden] { display: none; }" in page
    assert "Advanced settings" in page
    assert 'class="hx-advanced"' in page
    assert "field.advanced !== true" in page
    assert "field.type === 'FILE' || field.type === 'MULTI_FILE' || field.type === 'IMAGE'" in page
    assert 'class="hx-file"' in page
    assert "/api/upload" in page
    assert "One image URL per line" not in page
    assert (harness / "src" / "pages" / "api" / "upload.ts").is_file()


def test_harness_installs_app_module_libraries(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    _write_module(root, "aurora")
    (root / "package.json").write_text(
        json.dumps({"name": "demo_app", "dependencies": {"three": "^0.185.1"}}),
        encoding="utf-8",
    )

    harness, _ = write_harness(
        root,
        load_workspace(root),
        app_name="demo_app",
        runtime_spec="latest",
        tokens_spec="latest",
    )
    payload = json.loads((harness / "package.json").read_text(encoding="utf-8"))
    assert payload["dependencies"]["three"] == "^0.185.1"
    assert "ignore-workspace=true" in (harness / ".npmrc").read_text(encoding="utf-8")
    assert not _harness_ready(harness)
    command = _harness_install_command()
    assert command[0] in {"pnpm", "npm"}
    if command[0] == "pnpm":
        assert "--ignore-workspace" in command
