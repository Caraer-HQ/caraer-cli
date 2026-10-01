"""The local CMS module preview harness."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

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
    assert "closest('[data-caraer-field]')" in page
    assert "focusSidebarField" in page


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
    assert "item.advanced === true" in page
    assert "isModuleFieldGroup" in page
    assert "flattenModuleFields" in page
    assert 'class="hx-advanced hx-group"' in page
    assert "field.type === 'FILE' || field.type === 'MULTI_FILE' || field.type === 'IMAGE'" in page
    assert 'class="hx-file"' in page
    assert "/api/upload" in page
    assert "One image URL per line" not in page
    assert (harness / "src" / "pages" / "api" / "upload.ts").is_file()


def test_harness_ready_rejects_broken_cms_package_links(tmp_path: Path) -> None:
    """A leftover caraer-web symlink must not count as an installed preview."""
    harness = tmp_path / "cms-dev"
    (harness / "node_modules" / "@astrojs" / "node").mkdir(parents=True)
    caraer = harness / "node_modules" / "@caraer"
    caraer.mkdir(parents=True)
    (caraer / "cms-runtime").symlink_to(tmp_path / "missing-runtime")
    (caraer / "cms-tokens").symlink_to(tmp_path / "missing-tokens")
    assert not _harness_ready(harness)

    (tmp_path / "runtime").mkdir()
    (tmp_path / "tokens").mkdir()
    (caraer / "cms-runtime").unlink()
    (caraer / "cms-tokens").unlink()
    (caraer / "cms-runtime").symlink_to(tmp_path / "runtime")
    (caraer / "cms-tokens").symlink_to(tmp_path / "tokens")
    assert _harness_ready(harness)

    (harness / "package.json").write_text(
        json.dumps(
            {
                "dependencies": {
                    "@caraer/cms-runtime": "github:Caraer-HQ/caraer-cms-runtime#v0.1.4",
                    "@caraer/cms-tokens": "github:Caraer-HQ/caraer-cms-tokens#v0.1.1",
                }
            }
        ),
        encoding="utf-8",
    )
    assert not _harness_ready(harness)
    (harness / "node_modules" / ".caraer-cms-specs.json").write_text(
        json.dumps(
            {
                "@caraer/cms-runtime": "github:Caraer-HQ/caraer-cms-runtime#v0.1.2",
                "@caraer/cms-tokens": "github:Caraer-HQ/caraer-cms-tokens#v0.1.1",
            }
        ),
        encoding="utf-8",
    )
    assert not _harness_ready(harness)
    (harness / "node_modules" / ".caraer-cms-specs.json").write_text(
        json.dumps(
            {
                "@caraer/cms-runtime": "github:Caraer-HQ/caraer-cms-runtime#v0.1.4",
                "@caraer/cms-tokens": "github:Caraer-HQ/caraer-cms-tokens#v0.1.1",
            }
        ),
        encoding="utf-8",
    )
    assert _harness_ready(harness)


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
    assert "ignore-workspace=false" in (harness / ".npmrc").read_text(encoding="utf-8")
    assert not _harness_ready(harness)


@pytest.mark.parametrize("existing_preview", [False, True])
def test_harness_has_its_own_build_approval_workspace(
    tmp_path: Path, existing_preview: bool
) -> None:
    root = _workspace(tmp_path)
    _write_module(root, "hero")
    parent_workspace = root / "pnpm-workspace.yaml"
    parent_config = "packages:\n  - packages/*\nallowBuilds:\n  esbuild: false\n"
    parent_workspace.write_text(parent_config, encoding="utf-8")
    harness = root / ".caraer" / "cms-dev"
    if existing_preview:
        harness.mkdir(parents=True)
        (harness / ".npmrc").write_text("ignore-workspace=true\n", encoding="utf-8")

    write_harness(
        root,
        load_workspace(root),
        app_name="demo_app",
        runtime_spec="latest",
        tokens_spec="latest",
    )

    assert (harness / "pnpm-workspace.yaml").read_text(encoding="utf-8") == (
        "allowBuilds:\n  esbuild: true\n"
    )
    assert (harness / ".npmrc").read_text(encoding="utf-8") == "ignore-workspace=false\n"
    assert parent_workspace.read_text(encoding="utf-8") == parent_config


@pytest.mark.parametrize("manager", ["pnpm", "npm"])
def test_harness_install_loads_workspace_build_approvals(
    monkeypatch: pytest.MonkeyPatch, manager: str
) -> None:
    monkeypatch.setattr(
        "caraer_cli.project.modules_dev._package_manager", lambda: manager
    )
    assert _harness_install_command() == [manager, "install"]
