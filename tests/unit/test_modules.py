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
    """A module on disk: one .astro carrying both manifest and markup.

    JSON is a subset of the object literal syntax the manifest uses, so the
    config can be dumped straight into the export.
    """
    directory = root / "src" / "app" / "modules" / name
    directory.mkdir(parents=True, exist_ok=True)
    if entry:
        payload = {"category": "content", **config}
        (directory / "index.astro").write_text(
            f"---\nexport const manifest = {json.dumps(payload, indent=2)} "
            "satisfies ModuleManifest;\n---\n<div />\n",
            encoding="utf-8",
        )
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


def test_codegen_maps_form_single_select_to_string(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    _write_module(
        root,
        "cta",
        {
            "name": "cta",
            "label": "CTA",
            "kind": "section",
            "fields": [
                {"name": "form", "label": "Form", "type": "FORM_SINGLE_SELECT", "required": True},
            ],
        },
    )
    module = discover_local_modules(root, load_workspace(root))[0]
    types = render_module_types(module)

    assert "form: string;" in types


def test_codegen_maps_repeatable_to_array_of_items(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    _write_module(
        root,
        "steps",
        {
            "name": "steps",
            "label": "Steps",
            "kind": "section",
            "fields": [
                {
                    "name": "steps",
                    "label": "Steps",
                    "type": "REPEATABLE",
                    "min": 1,
                    "max": 6,
                    "itemLabel": "Step",
                    "itemFields": [
                        {"name": "title", "label": "Title", "type": "SINGLE_LINE", "required": True},
                        {"name": "text", "label": "Text", "type": "MULTI_LINE"},
                    ],
                },
            ],
        },
    )
    module = discover_local_modules(root, load_workspace(root))[0]
    types = render_module_types(module)

    assert "steps: Array<{ title: string; text: string | null }>;" in types


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
    tsconfig = json.loads((root / "tsconfig.json").read_text(encoding="utf-8"))
    assert tsconfig["compilerOptions"]["moduleResolution"] == "bundler"


def test_scaffold_creates_a_valid_module(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    config = load_workspace(root)
    scaffold_module(root, config, name="feature_grid", kind="section")

    directory = root / "src/app/modules/feature_grid"
    assert [p.name for p in directory.iterdir()] == ["index.astro"]
    assert _errors(root) == []


def test_scaffold_with_a_framework_places_the_island_correctly(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    config = load_workspace(root)
    scaffold_module(root, config, name="counter", kind="section", framework="react")

    island = root / "src/app/modules/counter/react/CounterIsland.tsx"
    assert island.is_file()
    assert _errors(root) == []


def test_manifest_survives_prettier_formatting(tmp_path: Path) -> None:
    """Single quotes, trailing commas and a satisfies suffix are all normal TS."""
    root = _workspace(tmp_path)
    directory = root / "src" / "app" / "modules" / "hero"
    directory.mkdir(parents=True)
    (directory / "index.astro").write_text(
        """---
import type { ModuleManifest } from '@caraer/cms-runtime';

export const manifest = {
  name: 'hero',
  label: 'Hero',
  kind: 'section',
  category: 'hero',
  fields: [{ name: 'heading', label: 'Heading', type: 'SINGLE_LINE' }],
} satisfies ModuleManifest;

const { fields } = Astro.props;
---
<div>{fields.heading}</div>
""",
        encoding="utf-8",
    )

    module = discover_local_modules(root, load_workspace(root))[0]
    assert module.kind == "section"
    assert module.config["category"] == "hero"
    assert [f["name"] for f in module.fields] == ["heading"]
    assert _errors(root) == []


def test_a_manifest_that_is_not_a_literal_is_rejected(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    directory = root / "src" / "app" / "modules" / "hero"
    directory.mkdir(parents=True)
    (directory / "index.astro").write_text(
        "---\nexport const manifest = buildManifest();\n---\n<div />\n",
        encoding="utf-8",
    )

    assert any("plain literal" in error for error in _errors(root))


def test_manifest_can_import_a_shared_field(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    modules = root / "src" / "app" / "modules"
    modules.mkdir(parents=True, exist_ok=True)
    (modules / "settings.ts").write_text(
        """
import type { ModuleField } from '@caraer/cms-runtime';

export const widthField = {
  name: 'width',
  label: 'Width',
  type: 'SINGLE_SELECT',
  required: true,
  defaultValue: 'max',
  options: [
    { name: 'max', label: 'Max width' },
    { name: '1100px', label: '1100px' },
  ],
} satisfies ModuleField;

export function containerMaxWidth(width: string | null | undefined): string {
  return width === '1100px' ? '1100px' : 'var(--caraer-container-max-width)';
}
""",
        encoding="utf-8",
    )
    (modules / "hero").mkdir()
    (modules / "hero" / "index.astro").write_text(
        """---
import type { ModuleManifest } from '@caraer/cms-runtime';
import { widthField, containerMaxWidth } from '../settings';

export const manifest = {
  name: 'hero',
  label: 'Hero',
  kind: 'section',
  category: 'hero',
  fields: [widthField],
} satisfies ModuleManifest;
---
<div style={`max-width: ${containerMaxWidth('max')}`} />
""",
        encoding="utf-8",
    )

    module = discover_local_modules(root, load_workspace(root))[0]
    assert module.fields == [
        {
            "name": "width",
            "label": "Width",
            "type": "SINGLE_SELECT",
            "required": True,
            "defaultValue": "max",
            "options": [
                {"name": "max", "label": "Max width"},
                {"name": "1100px", "label": "1100px"},
            ],
        }
    ]
    assert _errors(root) == []


def test_manifest_can_reuse_string_consts_from_a_fields_file(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    modules = root / "src" / "app" / "modules"
    directory = modules / "steps"
    directory.mkdir(parents=True)
    (directory / "fields.ts").write_text(
        """
import type { ModuleField } from '@caraer/cms-runtime';

export const CARD_STYLE_PROCESS = "process";
export const CARD_STYLE_STATUS = "status";

export const cardStyleField = {
  name: "card_style",
  label: "Card style",
  type: "SINGLE_SELECT",
  required: true,
  defaultValue: CARD_STYLE_PROCESS,
  options: [
    { name: CARD_STYLE_PROCESS, label: "Process", helpText: "Plain cards." },
    { name: CARD_STYLE_STATUS, label: "Status", helpText: "Badges." },
  ],
} satisfies ModuleField;
""",
        encoding="utf-8",
    )
    (directory / "index.astro").write_text(
        """---
import type { ModuleManifest } from '@caraer/cms-runtime';
import { CARD_STYLE_PROCESS, cardStyleField } from './fields';

export const manifest = {
  name: 'steps',
  label: 'Steps',
  kind: 'section',
  category: 'content',
  fields: [
    cardStyleField,
    {
      name: 'body',
      label: 'Text',
      type: 'MULTI_LINE',
      visibleWhen: [
        { field: 'card_style', operator: 'EQUALS', value: CARD_STYLE_PROCESS },
      ],
    },
  ],
} satisfies ModuleManifest;
---
<div />
""",
        encoding="utf-8",
    )

    module = discover_local_modules(root, load_workspace(root))[0]
    assert module.fields[0]["defaultValue"] == "process"
    assert module.fields[0]["options"][0]["name"] == "process"
    assert module.fields[1]["visibleWhen"][0]["value"] == "process"
    assert _errors(root) == []


def test_manifest_can_spread_imported_field_groups(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    modules = root / "src" / "app" / "modules"
    modules.mkdir(parents=True, exist_ok=True)
    (modules / "settings.ts").write_text(
        """
export const backgroundTypeField = {
  name: 'background_type',
  label: 'Background',
  type: 'SINGLE_SELECT',
  required: true,
  defaultValue: 'color',
  options: [
    { name: 'color', label: 'Color' },
    { name: 'image', label: 'Image' },
  ],
};

export const backgroundColorField = {
  name: 'background_color',
  label: 'Background color',
  type: 'SINGLE_SELECT',
  options: [{ name: 'primary', label: 'Primary' }],
  visibleWhen: [{ field: 'background_type', operator: 'EQUALS', value: 'color' }],
};

export const backgroundFields = [backgroundTypeField, backgroundColorField];
""",
        encoding="utf-8",
    )
    (modules / "hero").mkdir()
    (modules / "hero" / "index.astro").write_text(
        """---
import type { ModuleManifest } from '@caraer/cms-runtime';
import { backgroundFields } from '../settings';

export const manifest = {
  name: 'hero',
  label: 'Hero',
  kind: 'section',
  category: 'hero',
  fields: [...backgroundFields],
} satisfies ModuleManifest;
---
<div />
""",
        encoding="utf-8",
    )

    module = discover_local_modules(root, load_workspace(root))[0]
    assert [field["name"] for field in module.fields] == [
        "background_type",
        "background_color",
    ]
    assert _errors(root) == []


def test_manifest_can_import_fields_that_reuse_colors_from_settings(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    modules = root / "src" / "app" / "modules"
    modules.mkdir(parents=True, exist_ok=True)
    (modules / "settings.ts").write_text(
        """
export const COLORS = [
  { name: 'primary', label: 'Primary' },
  { name: 'font', label: 'Font' },
];
""",
        encoding="utf-8",
    )
    text = modules / "_text"
    text.mkdir()
    (text / "fields.ts").write_text(
        """
import { COLORS } from '../settings';

export const headingColorField = {
  name: 'heading_color',
  label: 'Heading color',
  type: 'SINGLE_SELECT',
  defaultValue: 'font',
  options: COLORS,
};

export const headingTextFields = [headingColorField];
""",
        encoding="utf-8",
    )
    (modules / "hero").mkdir()
    (modules / "hero" / "index.astro").write_text(
        """---
import type { ModuleManifest } from '@caraer/cms-runtime';
import { headingTextFields } from '../_text/fields';

export const manifest = {
  name: 'hero',
  label: 'Hero',
  kind: 'section',
  category: 'hero',
  fields: [...headingTextFields],
} satisfies ModuleManifest;
---
<div />
""",
        encoding="utf-8",
    )

    module = discover_local_modules(root, load_workspace(root))[0]
    assert module.fields == [
        {
            "name": "heading_color",
            "label": "Heading color",
            "type": "SINGLE_SELECT",
            "defaultValue": "font",
            "options": [
                {"name": "primary", "label": "Primary"},
                {"name": "font", "label": "Font"},
            ],
        }
    ]
    assert _errors(root) == []


def test_a_module_without_a_manifest_says_what_is_missing(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    directory = root / "src" / "app" / "modules" / "hero"
    directory.mkdir(parents=True)
    (directory / "index.astro").write_text("---\n---\n<div />\n", encoding="utf-8")

    assert any("export const manifest" in error for error in _errors(root))


def test_category_must_be_one_of_the_standard_set(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    _write_module(
        root,
        "hero",
        {"name": "hero", "label": "Hero", "kind": "section", "category": "splash"},
    )

    assert any("category 'splash' is not one of" in error for error in _errors(root))


def test_category_is_required(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    directory = root / "src" / "app" / "modules" / "hero"
    directory.mkdir(parents=True)
    (directory / "index.astro").write_text(
        "---\nexport const manifest = "
        '{ "name": "hero", "label": "Hero", "kind": "section", "fields": [] };\n'
        "---\n<div />\n",
        encoding="utf-8",
    )

    assert any("missing 'category'" in error for error in _errors(root))


def test_a_leftover_json_config_is_flagged(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    directory = _write_module(
        root, "hero", {"name": "hero", "label": "Hero", "kind": "section", "category": "hero"}
    )
    (directory / "module.caraer.json").write_text("{}", encoding="utf-8")

    assert any("A module is one file now" in error for error in _errors(root))


def test_cookie_banner_is_a_valid_distinct_module_kind(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    _write_module(root, "consent", {"name": "consent", "label": "Consent", "kind": "cookie_banner"})
    assert _errors(root) == []
    assert discover_local_modules(root, load_workspace(root))[0].kind == "cookie_banner"
