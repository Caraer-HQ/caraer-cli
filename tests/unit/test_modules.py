"""CMS v2 module discovery, validation and TypeScript codegen."""

from __future__ import annotations

import json
from pathlib import Path

from caraer_cli.project.modules_codegen import render_module_types
from caraer_cli.project.modules_scaffold import scaffold_module
from caraer_cli.project.modules_sync import discover_local_modules, parse_major
from caraer_cli.project.schema import load_workspace
from caraer_cli.project.validate_app import validate_local_app


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


def _write_module(root: Path, name: str, config: dict, *, entry: bool = True) -> Path:
    directory = root / "src" / "app" / "modules" / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "module.caraer.json").write_text(json.dumps(config), encoding="utf-8")
    if entry:
        (directory / "index.astro").write_text("---\n---\n<div />\n", encoding="utf-8")
    return directory


def _errors(root: Path) -> list[str]:
    report = validate_local_app(root)
    return [f"{i.path}: {i.message}" for i in report.issues if i.severity == "error"]


def test_discovers_modules_and_reads_kind(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    _write_module(root, "hero", {"name": "hero", "label": "Hero", "kind": "section"})
    _write_module(root, "site_footer", {"name": "site_footer", "label": "F", "kind": "footer"})

    modules = discover_local_modules(root, load_workspace(root))
    assert [m.name for m in modules] == ["hero", "site_footer"]
    assert modules[1].kind == "footer"


def test_valid_module_passes(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    _write_module(
        root,
        "hero",
        {
            "name": "hero",
            "label": "Hero",
            "kind": "section",
            "fields": [{"name": "heading", "label": "Heading", "type": "SINGLE_LINE"}],
        },
    )
    assert _errors(root) == []


def test_entry_must_be_astro(tmp_path: Path) -> None:
    # Astro can only apply client:* to statically resolved components, so the
    # entry point cannot be a framework file.
    root = _workspace(tmp_path)
    _write_module(root, "hero", {"name": "hero", "label": "Hero", "kind": "section"}, entry=False)
    assert any("Missing index.astro" in e for e in _errors(root))


def test_directory_name_must_match_config_name(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    _write_module(root, "hero", {"name": "banner", "label": "Hero", "kind": "section"})
    assert any("must match the directory name" in e for e in _errors(root))


def test_secret_and_action_field_types_are_rejected(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    _write_module(
        root,
        "hero",
        {
            "name": "hero",
            "label": "Hero",
            "kind": "section",
            "fields": [{"name": "token", "label": "Token", "type": "SECRET"}],
        },
    )
    assert any("not available on modules" in e for e in _errors(root))


def test_select_field_requires_static_options(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    _write_module(
        root,
        "hero",
        {
            "name": "hero",
            "label": "Hero",
            "kind": "section",
            "fields": [{"name": "align", "label": "Align", "type": "SINGLE_SELECT"}],
        },
    )
    assert any("needs 'options'" in e for e in _errors(root))


def test_visible_when_must_target_a_known_field(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    _write_module(
        root,
        "hero",
        {
            "name": "hero",
            "label": "Hero",
            "kind": "section",
            "fields": [
                {
                    "name": "cta",
                    "label": "CTA",
                    "type": "SINGLE_LINE",
                    "visibleWhen": [{"field": "nope", "operator": "IS_SET"}],
                }
            ],
        },
    )
    assert any("unknown field 'nope'" in e for e in _errors(root))


def test_jsx_island_outside_a_framework_folder_is_rejected(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    directory = _write_module(
        root,
        "hero",
        {"name": "hero", "label": "Hero", "kind": "section", "frameworks": {"react": "^19.0.0"}},
    )
    (directory / "Widget.tsx").write_text("export default () => null;\n", encoding="utf-8")

    assert any("must live in a framework folder" in e for e in _errors(root))


def test_island_folder_must_be_declared(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    directory = _write_module(root, "hero", {"name": "hero", "label": "Hero", "kind": "section"})
    react = directory / "react"
    react.mkdir()
    (react / "Widget.tsx").write_text("export default () => null;\n", encoding="utf-8")

    assert any("does not declare 'react'" in e for e in _errors(root))


def test_framework_major_must_match_the_platform_pin(tmp_path: Path) -> None:
    # A build hoists one copy of each framework, so a mismatch must fail for
    # this developer rather than break every site that installs the app.
    root = _workspace(tmp_path)
    _write_module(
        root,
        "hero",
        {"name": "hero", "label": "Hero", "kind": "section", "frameworks": {"react": "^18.2.0"}},
    )
    assert any("platform pins 19" in e for e in _errors(root))


def test_parse_major_handles_common_ranges() -> None:
    assert parse_major("^19.2.0") == 19
    assert parse_major("~10.1") == 10
    assert parse_major(">=3.5.0") == 3
    assert parse_major("latest") is None


def test_codegen_narrows_selects_and_nulls_optional_fields(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    _write_module(
        root,
        "hero",
        {
            "name": "hero",
            "label": "Hero",
            "kind": "section",
            "fields": [
                {"name": "heading", "label": "Heading", "type": "SINGLE_LINE", "required": True},
                {"name": "body", "label": "Body", "type": "MULTI_LINE"},
                {
                    "name": "align",
                    "label": "Align",
                    "type": "SINGLE_SELECT",
                    "required": True,
                    "options": [{"name": "left", "label": "L"}, {"name": "center", "label": "C"}],
                },
                {"name": "job_title", "label": "Job title", "type": "PROPERTY_SINGLE_SELECT"},
                {"name": "enabled", "label": "Enabled", "type": "SWITCH"},
            ],
        },
    )
    module = discover_local_modules(root, load_workspace(root))[0]
    types = render_module_types(module)

    assert "heading: string;" in types
    assert "body: string | null;" in types
    assert "align: 'left' | 'center';" in types
    assert "job_title: string | number | boolean | null;" in types
    # A switch always has a value, so it must not be nullable.
    assert "enabled: boolean;" in types


def test_codegen_runs_during_validation(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    _write_module(
        root,
        "hero",
        {
            "name": "hero",
            "label": "Hero",
            "kind": "section",
            "fields": [{"name": "heading", "label": "Heading", "type": "SINGLE_LINE"}],
        },
    )
    validate_local_app(root)

    generated = root / "src" / "app" / "modules" / "hero" / "fields.d.ts"
    assert generated.is_file()
    assert "HeroFields" in generated.read_text(encoding="utf-8")


def test_scaffold_creates_a_valid_module(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    config = load_workspace(root)
    scaffold_module(root, config, name="feature_grid", kind="section")

    assert (root / "src/app/modules/feature_grid/index.astro").is_file()
    assert (root / "src/app/modules/feature_grid/module.caraer.json").is_file()
    assert _errors(root) == []


def test_scaffold_with_a_framework_places_the_island_correctly(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    config = load_workspace(root)
    scaffold_module(root, config, name="counter", kind="section", framework="react")

    island = root / "src/app/modules/counter/react/CounterIsland.tsx"
    assert island.is_file()
    assert _errors(root) == []
