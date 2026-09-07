"""Local Astro harness for developing CMS v2 modules.

Generates a throwaway Astro workspace under ``.caraer/cms-dev`` that imports the
app's modules directly from source, then runs ``astro dev`` against it. The
harness renders each module with sample field values and a sidebar for editing
them, so a developer sees the same inputs a content editor will get without
needing a company, a backend or a deployed build.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from caraer_cli.project.modules_sync import LocalModule, discover_local_modules
from caraer_cli.project.paths import modules_dir
from caraer_cli.project.schema import ProjectConfig

HARNESS_DIR = Path(".caraer") / "cms-dev"

#: Placeholder values per field type, so a module renders something meaningful
#: before the developer touches the sidebar.
_SAMPLE_VALUES: dict[str, Any] = {
    "SINGLE_LINE": "Sample heading",
    "MULTI_LINE": "Sample body copy with **markdown** support.",
    "SINGLE_SELECT": None,
    "MULTI_SELECT": [],
    "RECORD_SINGLE_SELECT": None,
    "RECORD_MULTI_SELECT": [],
    "OBJECT_SINGLE_SELECT": "vacancy",
    "OBJECT_MULTI_SELECT": [],
    "PROPERTY_SINGLE_SELECT": "title",
    "PROPERTY_MULTI_SELECT": [],
    "SWITCH": True,
    "MAPPING": {},
    "FILE": None,
    "MULTI_FILE": [],
}


def resolve_runtime_specs(root: Path) -> tuple[str, str]:
    """Work out where to install ``@caraer/cms-runtime`` and ``-tokens`` from.

    The published packages are the normal answer, but a developer working on
    the runtime itself, or working before the first publish, needs the local
    checkout instead. Falling back to ``latest`` without looking would fail the
    install with a bare npm 404 that says nothing about what to do.

    Order: explicit spec env vars, then ``CARAER_WEB_PATH``, then a sibling
    ``caraer-web`` checkout, then the registry.
    """
    runtime = os.environ.get("CARAER_CMS_RUNTIME_SPEC")
    tokens = os.environ.get("CARAER_CMS_TOKENS_SPEC")
    if runtime and tokens:
        return runtime, tokens

    candidates: list[Path] = []
    configured = os.environ.get("CARAER_WEB_PATH")
    if configured:
        candidates.append(Path(configured).expanduser())

    # Walk up looking for a sibling checkout: app repos and caraer-web usually
    # live next to each other under one workspace directory.
    current = root.resolve()
    for parent in [current, *current.parents][:5]:
        candidates.append(parent / "caraer-web")

    for candidate in candidates:
        runtime_pkg = candidate / "packages" / "cms-runtime" / "package.json"
        tokens_pkg = candidate / "packages" / "cms-tokens" / "package.json"
        if runtime_pkg.is_file() and tokens_pkg.is_file():
            return (
                runtime or f"file:{runtime_pkg.parent.resolve()}",
                tokens or f"file:{tokens_pkg.parent.resolve()}",
            )

    return runtime or "latest", tokens or "latest"


def sample_fields(module: LocalModule) -> dict[str, Any]:
    """Build a plausible starting value for every field on a module."""
    values: dict[str, Any] = {}
    for item in module.fields:
        name = str(item.get("name") or "")
        if not name:
            continue
        if "defaultValue" in item and item["defaultValue"] is not None:
            values[name] = item["defaultValue"]
            continue

        field_type = str(item.get("type") or "").upper()
        if field_type == "SINGLE_SELECT":
            options = item.get("options") or []
            values[name] = options[0].get("name") if options else None
        elif field_type == "SINGLE_LINE":
            # The field's own label, so you can see at a glance which input
            # produced which piece of the rendered output.
            values[name] = str(item.get("label") or name)
        else:
            values[name] = _SAMPLE_VALUES.get(field_type)
    return values


def _package_json(app_name: str, runtime_spec: str, tokens_spec: str, frameworks: set[str]) -> dict:
    deps: dict[str, str] = {
        "astro": "^7.3.1",
        # The harness renders on demand so the field sidebar can read its values
        # from the query string; a static build would drop them.
        "@astrojs/node": "^11.1.5",
        "@caraer/cms-runtime": runtime_spec,
        "@caraer/cms-tokens": tokens_spec,
    }
    if "react" in frameworks:
        deps.update({"@astrojs/react": "^6.0.5", "react": "^19.2.0", "react-dom": "^19.2.0"})
    if "preact" in frameworks:
        deps.update({"@astrojs/preact": "^6.0.5", "preact": "^10.27.2"})
    if "solid" in frameworks:
        deps.update({"@astrojs/solid-js": "^7.0.2", "solid-js": "^1.9.9"})
    if "svelte" in frameworks:
        deps.update({"@astrojs/svelte": "^9.0.1", "svelte": "^5.42.2"})
    if "vue" in frameworks:
        deps.update({"@astrojs/vue": "^7.0.2", "vue": "^3.5.22"})

    return {
        "name": f"{app_name}-cms-dev",
        "private": True,
        "type": "module",
        "dependencies": deps,
    }


def _astro_config(modules_path: Path, frameworks: set[str], harness: Path) -> str:
    imports = [
        "import { defineConfig } from 'astro/config';",
        "import node from '@astrojs/node';",
    ]
    integrations = []

    if "react" in frameworks:
        imports.append("import react from '@astrojs/react';")
        integrations.append("react({ include: ['**/modules/*/react/**'] })")
    if "preact" in frameworks:
        imports.append("import preact from '@astrojs/preact';")
        integrations.append("preact({ include: ['**/modules/*/preact/**'] })")
    if "solid" in frameworks:
        imports.append("import solid from '@astrojs/solid-js';")
        integrations.append("solid({ include: ['**/modules/*/solid/**'] })")
    if "svelte" in frameworks:
        imports.append("import svelte from '@astrojs/svelte';")
        integrations.append("svelte()")
    if "vue" in frameworks:
        imports.append("import vue from '@astrojs/vue';")
        integrations.append("vue()")

    runtime = (harness / "node_modules" / "@caraer" / "cms-runtime").as_posix()
    tokens = (harness / "node_modules" / "@caraer" / "cms-tokens").as_posix()

    return f"""// GENERATED by `caraer apps local dev --cms` - do not edit.
{chr(10).join(imports)}

export default defineConfig({{
  // On demand, not static: the field sidebar passes values through the query
  // string, and a prerendered page would not see them.
  output: 'server',
  adapter: node({{ mode: 'standalone' }}),
  integrations: [{', '.join(integrations)}],
  server: {{ host: true }},
  vite: {{
    resolve: {{
      // Modules are loaded from your app directory, which has no node_modules
      // of its own, so their bare `@caraer/*` imports would not resolve. These
      // aliases point them at the copies installed here. Order matters: the
      // most specific pattern has to come first.
      alias: [
        {{ find: '@modules', replacement: '{modules_path.as_posix()}' }},
        {{
          find: /^@caraer\\/cms-runtime\\/(Caraer\\w+\\.astro)$/,
          replacement: '{runtime}/src/components/$1',
        }},
        {{ find: '@caraer/cms-runtime/components', replacement: '{runtime}/src/components/index.ts' }},
        {{ find: '@caraer/cms-runtime', replacement: '{runtime}/src/index.ts' }},
        {{ find: '@caraer/cms-tokens/tokens.css', replacement: '{tokens}/src/tokens.css' }},
        {{ find: '@caraer/cms-tokens', replacement: '{tokens}/src/index.ts' }},
      ],
    }},
    // Modules are consumed as source, so they must not be externalised.
    ssr: {{ noExternal: ['@caraer/cms-runtime', '@caraer/cms-tokens'] }},
    server: {{
      fs: {{
        // The runtime may be a file: link to a caraer-web checkout outside this
        // directory, so Vite has to be allowed to read from there.
        allow: ['{modules_path.parent.as_posix()}', '{runtime}', '{tokens}', '.'],
      }},
    }},
  }},
}});
"""


def _harness_middleware() -> str:
    """Provide the server capabilities platform components read off `Astro.locals`.

    Without this, any module using `CaraerLink`, `CaraerMenu`, `CaraerForm` or
    `CaraerRecordList` fails to render locally, which would make the harness
    useless for exactly the modules most worth previewing.

    Two modes. By default everything is sample data, so the preview works with
    no company, no backend and no network. When `CARAER_SUBDOMAIN` is set
    (`--company`), the same calls hit the real public API, so you see a module
    against a customer's actual branding, menus and records.
    """
    return """// GENERATED by `caraer apps local dev` - do not edit.
import { defineMiddleware } from 'astro:middleware';
import { DEFAULT_TOKENS, resolveTokens } from '@caraer/cms-tokens';

const SUBDOMAIN = process.env.CARAER_SUBDOMAIN;
const API_BASE = (process.env.CARAER_API_BASE_URL || '').replace(/\\/$/, '');
const RECORD_OBJECT = process.env.CARAER_RECORD_OBJECT;
const LIVE = Boolean(SUBDOMAIN && API_BASE);

const SAMPLE_RECORD = {
  uuid: 'sample-record',
  object: RECORD_OBJECT || 'vacancy',
  properties: { title: 'Senior Developer', location: 'Utrecht' },
  parsedProperties: { title: 'Senior Developer', location: 'Utrecht' },
};

const SAMPLE_MENU = {
  location: 'header',
  title: 'Sample menu',
  items: [
    { label: 'Vacatures', url: '/vacatures' },
    { label: 'Over ons', url: '/over-ons' },
  ],
};

const SAMPLE_FORM = (form) => ({
  uuid: String(form),
  name: String(form),
  label: 'Sample form',
  wizard: false,
  submitLabel: 'Verzenden',
  steps: [
    {
      title: 'Sample',
      fields: [
        { uuid: '1', name: 'name', label: 'Naam', type: 'STRING', required: true },
        { uuid: '2', name: 'email', label: 'E-mail', type: 'STRING', format: 'EMAIL', required: true },
      ],
    },
  ],
});

const sampleRecords = (object, limit) => ({
  total: limit,
  records: Array.from({ length: limit }, (_, index) => ({
    uuid: `sample-${index + 1}`,
    slug: `/sample-${index + 1}`,
    url: `/sample-${index + 1}`,
    properties: { title: `Sample ${object} ${index + 1}`, location: 'Utrecht' },
    parsedProperties: { title: `Sample ${object} ${index + 1}`, location: 'Utrecht' },
  })),
});

/**
 * Calls the public CMS API for the company named by --company.
 *
 * Returns null on any failure rather than throwing: a preview that falls back
 * to sample data is far more useful than one that shows a stack trace because
 * a VPN dropped.
 */
async function live(path, init = {}) {
  if (!LIVE) return null;
  try {
    const response = await fetch(`${API_BASE}/api/v2/webpages/v2/public${path}`, {
      ...init,
      headers: {
        Accept: 'application/json',
        'X-Caraer-Subdomain': SUBDOMAIN,
        ...(init.body ? { 'Content-Type': 'application/json' } : {}),
        ...(init.headers || {}),
      },
    });
    if (!response.ok) {
      // Must be loud. Silently serving sample data when you asked for a real
      // company would have you debugging a module against the wrong content.
      console.warn(
        `[harness] ${path} returned ${response.status} for '${SUBDOMAIN}' - using sample data.`,
      );
      return null;
    }
    const payload = await response.json();
    return payload?.data ?? payload;
  } catch (error) {
    console.warn(`[harness] ${path} failed (${error.message}) - using sample data.`);
    return null;
  }
}

// Fetched once per process rather than per request: settings change rarely and
// a preview reloads constantly while you edit.
let settingsPromise;
const loadSettings = () =>
  (settingsPromise ??= (async () => {
    const settings = await live('/settings');
    if (LIVE && !settings) {
      console.warn(
        `[harness] Could not reach company '${SUBDOMAIN}'. Everything below is ` +
          'sample data, not that company\\'s content.',
      );
    }
    return settings;
  })());

let recordPromise;
const loadRecord = () =>
  (recordPromise ??= (async () => {
    if (!LIVE || !RECORD_OBJECT) return SAMPLE_RECORD;
    const result = await live('/records', {
      method: 'POST',
      body: JSON.stringify({ object: RECORD_OBJECT, limit: 1 }),
    });
    const first = result?.records?.[0];
    if (!first) return SAMPLE_RECORD;
    return {
      uuid: first.uuid,
      object: RECORD_OBJECT,
      properties: first.properties ?? {},
      parsedProperties: first.parsedProperties ?? {},
    };
  })());

export const onRequest = defineMiddleware(async (context, next) => {
  const settings = await loadSettings();

  context.locals.company = settings?.company ?? {
    uuid: 'sample-company',
    name: 'Sample Company',
    subdomain: SUBDOMAIN || 'sample',
    logo: null,
    logoDark: null,
    favicon: null,
  };

  context.locals.page = {
    uuid: 'sample-page',
    title: 'Harness',
    slug: '/',
    locale: 'nl',
    state: 'draft',
    path: '/',
    origin: context.url.origin,
  };

  // Real branding when attached to a company, so you see the module in the
  // customer's actual colours and typography rather than platform defaults.
  context.locals.tokens = settings
    ? resolveTokens({
        digitalIdentity: settings.digitalIdentity,
        websiteSettings: settings.websiteSettings,
      })
    : DEFAULT_TOKENS;

  context.locals.editor = null;
  context.locals.record = await loadRecord();

  context.locals.assetUrl = (key) => key ?? null;
  context.locals.localePath = (path) => (path?.startsWith('/') ? path : `/${path ?? ''}`);
  context.locals.tag = () => {};

  context.locals.getMenu = async (location) => {
    const menus = await live(`/menus?locale=nl`);
    const match = Array.isArray(menus) ? menus.find((m) => m.location === location) : null;
    // Every location falls back to the same sample menu, so a footer module
    // with four columns still renders something recognisable.
    return match ?? { ...SAMPLE_MENU, location };
  };

  context.locals.getForm = async (form) =>
    (await live(`/forms/${encodeURIComponent(String(form))}`)) ?? SAMPLE_FORM(form);

  context.locals.listRecords = async ({ object, limit = 6, offset, orderBy, filter }) =>
    (await live('/records', {
      method: 'POST',
      body: JSON.stringify({ object, limit, offset, orderBy, filter }),
    })) ?? sampleRecords(object, limit);

  return next();
});
"""


def _harness_page(modules: list[LocalModule]) -> str:
    """The harness page: renders each module with an editable field sidebar."""
    imports = []
    entries = []
    for index, module in enumerate(modules):
        alias = f"Module{index}"
        imports.append(f"import {alias} from '@modules/{module.name}/index.astro';")
        imports.append(
            f"import manifest{index} from '@modules/{module.name}/module.caraer.json';"
        )
        entries.append(f"  {{ name: '{module.name}', component: {alias}, manifest: manifest{index} }},")

    return f"""---
// GENERATED by `caraer apps local dev --cms` - do not edit.
import {{ DEFAULT_TOKENS, toCustomProperties, toStyleAttribute }} from '@caraer/cms-tokens';
import {{ resolveFieldValues }} from '@caraer/cms-runtime';

{chr(10).join(imports)}
import samples from '../../samples.json';

const modules = [
{chr(10).join(entries)}
];

const active = Astro.url.searchParams.get('module') ?? modules[0]?.name;
const selected = modules.find((m) => m.name === active) ?? modules[0];
const manifestFields = selected?.manifest.fields ?? [];

/*
 * Query strings carry everything as text, but a field's declared type is what
 * the runtime works with. Without coercion a SWITCH arrives as the string
 * "true", and a `visibleWhen: EQUALS true` on a sibling field compares string
 * to boolean and silently hides it.
 */
function coerce(name: string, raw: string): unknown {{
  if (raw === '') return null;

  const type = manifestFields.find((f) => f.name === name)?.type;
  switch (type) {{
    case 'SWITCH':
      return raw === 'true';
    case 'MULTI_SELECT':
    case 'MULTI_FILE':
    case 'PROPERTY_MULTI_SELECT':
    case 'RECORD_MULTI_SELECT':
    case 'OBJECT_MULTI_SELECT':
      return raw.split(',').map((part) => part.trim()).filter(Boolean);
    default:
      return raw;
  }}
}}

// Field values come from the query string when the sidebar has been used, so
// edits survive a reload without any server state.
const overrides: Record<string, unknown> = {{}};
for (const [key, value] of Astro.url.searchParams) {{
  if (key.startsWith('f.')) overrides[key.slice(2)] = coerce(key.slice(2), value);
}}

const stored = {{ ...(samples[selected?.name] ?? {{}}), ...overrides }};

// Set by the middleware: a stand-in record by default, or a real one from the
// company when running with --company and --record.
const record = Astro.locals.record;

const props = {{
  fields: resolveFieldValues(manifestFields, stored, record),
  rawFields: stored,
  record,
  page: {{
    uuid: 'sample',
    title: 'Harness',
    slug: '/',
    locale: 'nl',
    state: 'draft',
    path: '/',
    origin: Astro.url.origin,
  }},
  company: {{
    uuid: 'sample',
    name: 'Sample Company',
    subdomain: 'sample',
    logo: null,
    logoDark: null,
    favicon: null,
  }},
  module: {{ id: 'sample', ref: `local/${{selected?.name}}`, kind: selected?.manifest.kind }},
  editor: null,
}};

const Selected = selected?.component;
const style = toStyleAttribute(toCustomProperties(DEFAULT_TOKENS));
---

<html lang="nl" style={{style}}>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Caraer module harness</title>
  </head>
  <body>
    <div class="harness">
      <aside class="harness__sidebar">
        <h1>Modules</h1>
        <ul class="harness__list">
          {{modules.map((m) => (
            <li>
              <a href={{`?module=${{m.name}}`}} aria-current={{m.name === selected?.name ? 'page' : undefined}}>
                {{m.manifest.label}} <small>{{m.manifest.kind}}</small>
              </a>
            </li>
          ))}}
        </ul>

        <h2>Fields</h2>
        <form method="get" class="harness__fields">
          <input type="hidden" name="module" value={{selected?.name}} />
          {{manifestFields.map((field) => (
            <label>
              <span>{{field.label}}<small>{{field.type}}</small></span>
              {{field.type === 'SWITCH' ? (
                <input type="checkbox" name={{`f.${{field.name}}`}} checked={{Boolean(stored[field.name])}} value="true" />
              ) : field.type === 'MULTI_LINE' ? (
                <textarea name={{`f.${{field.name}}`}} rows="3">{{String(stored[field.name] ?? '')}}</textarea>
              ) : field.options ? (
                <select name={{`f.${{field.name}}`}}>
                  {{field.options.map((o) => (
                    <option value={{o.name}} selected={{stored[field.name] === o.name}}>{{o.label}}</option>
                  ))}}
                </select>
              ) : (
                <input name={{`f.${{field.name}}`}} value={{String(stored[field.name] ?? '')}} />
              )}}
            </label>
          ))}}
          <button type="submit">Apply</button>
        </form>
      </aside>

      <main class="harness__preview" id="harness-preview">
        {{Selected && <Selected {{...props}} />}}
      </main>
    </div>

    <script>
      // Live preview: re-render as you type instead of on Apply. Only the
      // preview pane is swapped, so focus and caret position survive editing.
      // The Apply button still works with JavaScript disabled.
      const form = document.querySelector('.harness__fields');
      const preview = document.getElementById('harness-preview');

      if (form instanceof HTMLFormElement && preview) {{
        let timer;
        let inFlight;

        const render = async () => {{
          const params = new URLSearchParams(new FormData(form));

          // An unchecked checkbox submits nothing, so the value would fall back
          // to the sample and a switch could never be turned off.
          form.querySelectorAll('input[type="checkbox"]').forEach((box) => {{
            if (!box.checked) params.set(box.name, 'false');
          }});

          const query = params.toString();
          history.replaceState(null, '', '?' + query);

          inFlight?.abort();
          inFlight = new AbortController();

          try {{
            const response = await fetch('/?' + query, {{ signal: inFlight.signal }});
            if (!response.ok) return;

            // Parsed into a detached document rather than assigned as a string:
            // it never runs inline scripts, and adopting real nodes lets the
            // browser upgrade Astro's island elements so they rehydrate.
            const parsed = new DOMParser().parseFromString(await response.text(), 'text/html');
            const next = parsed.getElementById('harness-preview');
            if (!next) return;

            preview.replaceChildren(
              ...Array.from(next.childNodes).map((node) => document.adoptNode(node)),
            );
          }} catch (error) {{
            if (error.name !== 'AbortError') console.error(error);
          }}
        }};

        const schedule = () => {{
          clearTimeout(timer);
          timer = setTimeout(render, 250);
        }};

        form.addEventListener('input', schedule);
        form.addEventListener('change', schedule);
        form.addEventListener('submit', (event) => {{
          event.preventDefault();
          render();
        }});
      }}
    </script>

    <style is:global>
      @import '@caraer/cms-tokens/tokens.css';

      body {{ margin: 0; font-family: system-ui, sans-serif; }}
      .harness {{ display: grid; grid-template-columns: 20rem 1fr; min-height: 100vh; }}
      .harness__sidebar {{
        padding: 1rem; background: #f7f7f9; border-right: 1px solid #e5e6e8;
        overflow-y: auto; max-height: 100vh;
      }}
      .harness__sidebar h1, .harness__sidebar h2 {{ font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.06em; color: #737882; }}
      .harness__list {{ list-style: none; margin: 0 0 1.5rem; padding: 0; display: grid; gap: 0.25rem; }}
      .harness__list a {{ display: flex; justify-content: space-between; padding: 0.5rem; border-radius: 0.375rem; color: #17181A; text-decoration: none; }}
      .harness__list a[aria-current] {{ background: #E3ECF9; font-weight: 600; }}
      .harness__list small, .harness__fields small {{ color: #92969E; font-weight: 400; }}
      .harness__fields {{ display: grid; gap: 0.75rem; }}
      .harness__fields label {{ display: grid; gap: 0.25rem; font-size: 0.8125rem; }}
      .harness__fields span {{ display: flex; justify-content: space-between; gap: 0.5rem; font-weight: 600; }}
      .harness__fields input, .harness__fields select, .harness__fields textarea {{
        font: inherit; padding: 0.375rem 0.5rem; border: 1px solid #C6C8CC; border-radius: 0.375rem;
      }}
      .harness__fields button {{ padding: 0.5rem; border: 0; border-radius: 0.375rem; background: #0D47A1; color: #fff; font-weight: 600; cursor: pointer; }}
      .harness__preview {{ overflow-x: hidden; }}
    </style>
  </body>
</html>
"""


def write_harness(
    root: Path,
    config: ProjectConfig,
    *,
    app_name: str,
    runtime_spec: str,
    tokens_spec: str,
) -> tuple[Path, list[LocalModule]]:
    """Generate the harness workspace. Returns its directory and the modules."""
    modules = [m for m in discover_local_modules(root, config) if m.config and m.entry.is_file()]
    if not modules:
        # Name the directory searched. The app can come from the profile's
        # pinned app_file rather than the current directory, and a message that
        # only says "src/app/modules/" sends you looking in the wrong place.
        raise ValueError(
            f"No modules found under {modules_dir(root, config.srcDir)}.\n"
            f"That app is '{config.name or root.name}' at {root}.\n"
            "If you meant a different app, pass --file <path/to/app.caraer.yaml> "
            "or run 'caraer apps clear' to unpin the one in your profile.\n"
            "To add a module here, run 'caraer apps add module <name>'."
        )

    frameworks: set[str] = set()
    for module in modules:
        frameworks.update(module.frameworks)

    harness = root / HARNESS_DIR
    (harness / "src" / "pages").mkdir(parents=True, exist_ok=True)

    (harness / "package.json").write_text(
        json.dumps(_package_json(app_name, runtime_spec, tokens_spec, frameworks), indent=2) + "\n",
        encoding="utf-8",
    )
    (harness / "astro.config.mjs").write_text(
        _astro_config(modules_dir(root, config.srcDir).resolve(), frameworks, harness.resolve()),
        encoding="utf-8",
    )
    (harness / "src" / "pages" / "index.astro").write_text(_harness_page(modules), encoding="utf-8")
    (harness / "src" / "middleware.ts").write_text(_harness_middleware(), encoding="utf-8")
    (harness / "samples.json").write_text(
        json.dumps({m.name: sample_fields(m) for m in modules}, indent=2) + "\n", encoding="utf-8"
    )
    (harness / ".gitignore").write_text("*\n", encoding="utf-8")

    return harness, modules


def _package_manager() -> str:
    return "pnpm" if shutil.which("pnpm") else "npm"


def install_harness(harness: Path, *, force: bool = False) -> int:
    """Install the harness dependencies. Returns the exit code."""
    if not force and (harness / "node_modules").is_dir():
        return 0

    return subprocess.run(
        [_package_manager(), "install"], cwd=harness, env={**os.environ}, check=False
    ).returncode


def start_harness(
    harness: Path,
    *,
    port: int,
    host: str,
    env: dict[str, str] | None = None,
) -> subprocess.Popen[bytes]:
    """Start `astro dev` in the background.

    Non-blocking so the caller can run the function server in the foreground at
    the same time; the two together are what "run my app locally" means.
    """
    return subprocess.Popen(
        [
            _package_manager(),
            "exec",
            "astro",
            "dev",
            "--port",
            str(port),
            "--host",
            host,
            # A crashed previous run leaves a lock behind and Astro then refuses
            # to start, which would look like the harness is simply broken.
            "--ignore-lock",
        ],
        cwd=harness,
        env={**os.environ, **(env or {})},
    )
