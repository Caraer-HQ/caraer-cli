"""Scaffold a CMS v2 module under ``src/app/modules/``."""

from __future__ import annotations

from pathlib import Path

from caraer_cli.project.modules_sync import (
    MODULE_ENTRY_FILE,
    PINNED_FRAMEWORK_MAJORS,
)
from caraer_cli.project.paths import modules_dir
from caraer_cli.project.schema import ProjectConfig


def _pascal_case(value: str) -> str:
    return "".join(part.capitalize() for part in value.replace("-", "_").split("_") if part)


def _manifest_source(name: str, label: str, kind: str, framework: str | None) -> str:
    """Render the `export const manifest` block for a new module."""
    frameworks = ""
    if framework:
        major = PINNED_FRAMEWORK_MAJORS[framework]
        frameworks = f"\n  frameworks: {{ {framework}: '^{major}.0.0' }},"

    return f"""export const manifest = {{
  name: '{name}',
  label: '{label}',
  kind: '{kind}',
  category: 'content',
  description: '{label} module.',{frameworks}
  fields: [
    {{
      name: 'heading',
      label: 'Heading',
      type: 'SINGLE_LINE',
      required: true,
      defaultValue: '{label}',
    }},
    {{
      group: 'Content',
      fields: [
        {{
          name: 'body',
          label: 'Text',
          type: 'MULTI_LINE',
          helpText: 'Markdown is supported.',
        }},
      ],
    }},
  ],
}} satisfies ModuleManifest;"""


def _entry_source(name: str, label: str, kind: str, framework: str | None) -> str:
    interface = f"{_pascal_case(name)}Fields"
    island = f"{_pascal_case(name)}Island"

    imports = [
        "import CaraerRichText from '@caraer/cms-runtime/CaraerRichText.astro';",
        "import type { ModuleManifest, ModuleProps } from '@caraer/cms-runtime';",
        "",
        f"import type {{ {interface} }} from './types.d.ts';",
    ]
    if framework:
        imports.insert(0, f"import {island} from './{framework}/{island}.tsx';")

    island_markup = (
        f"\n    <{island} client:visible heading={{fields.heading}} />"
        if framework
        else ""
    )

    return f"""---
{chr(10).join(imports)}

{_manifest_source(name, label, kind, framework)}

type Props = ModuleProps<{interface}>;
const {{ fields }} = Astro.props;
---

<section class="{name}">
  <div class="caraer-container">
    <h2 data-caraer-field="heading">{{fields.heading}}</h2>
    <div data-caraer-field="body">
      {{fields.body && <CaraerRichText value={{fields.body}} />}}
    </div>{island_markup}
  </div>
</section>

<style>
  .{name} {{
    padding-block: var(--caraer-space-2xl);
  }}

  .{name} h2 {{
    margin-block: 0 var(--caraer-space-md);
    font-family: var(--caraer-font-h2);
    font-size: var(--caraer-size-h2);
    font-weight: var(--caraer-weight-h2);
    line-height: var(--caraer-leading-h2);
    color: var(--caraer-color-font);
  }}
</style>
"""


def _island_source(name: str, framework: str) -> str:
    island = f"{_pascal_case(name)}Island"

    if framework in {"react", "preact"}:
        hook_import = "react" if framework == "react" else "preact/hooks"
        return f"""import {{ useState }} from '{hook_import}';

interface Props {{
  heading: string;
}}

/**
 * Interactive island for the {name} module.
 *
 * The `client:visible` directive is written statically in index.astro. Astro
 * must see it at build time to bundle this component, which is why a module's
 * entry point is always .astro.
 */
export default function {island}({{ heading }}: Props) {{
  const [count, setCount] = useState(0);

  return (
    <button type="button" onClick={{() => setCount(count + 1)}}>
      {{heading}}: {{count}}
    </button>
  );
}}
"""

    if framework == "solid":
        return f"""import {{ createSignal }} from 'solid-js';

interface Props {{
  heading: string;
}}

export default function {island}(props: Props) {{
  const [count, setCount] = createSignal(0);

  return (
    <button type="button" onClick={{() => setCount(count() + 1)}}>
      {{props.heading}}: {{count()}}
    </button>
  );
}}
"""

    return ""


def scaffold_module(
    root: Path,
    config: ProjectConfig,
    *,
    name: str,
    label: str | None = None,
    kind: str = "section",
    framework: str | None = None,
    force: bool = False,
) -> Path:
    """Create ``src/app/modules/<name>/`` with an entry and optional island."""
    directory = modules_dir(root, config.srcDir) / name
    entry_name = f"{name}.astro" if config.is_layout_v21() else MODULE_ENTRY_FILE
    entry = directory / entry_name

    if entry.exists() and not force:
        raise FileExistsError(f"Module already exists: {directory}. Use --force to overwrite.")

    directory.mkdir(parents=True, exist_ok=True)

    entry.write_text(
        _entry_source(name, label or _pascal_case(name), kind, framework),
        encoding="utf-8",
    )

    if framework:
        island_dir = directory / framework
        island_dir.mkdir(parents=True, exist_ok=True)
        suffix = "tsx" if framework in {"react", "preact", "solid"} else framework
        island_path = island_dir / f"{_pascal_case(name)}Island.{suffix}"
        source = _island_source(name, framework)
        if source:
            island_path.write_text(source, encoding="utf-8")

    return directory
