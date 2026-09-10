"""Local Astro harness for developing CMS v2 modules.

Generates a throwaway Astro workspace under ``.caraer/cms-dev`` that imports the
app's modules directly from source, then runs ``astro dev`` against it. The
harness renders each module with sample field values and a sidebar for editing
them, so a developer sees the same inputs a content editor will get without
needing a company, a backend or a deployed build.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from caraer_cli.project.modules_publish import read_app_dependencies
from caraer_cli.project.modules_sync import LocalModule, discover_local_modules
from caraer_cli.project.paths import modules_dir
from caraer_cli.project.schema import ProjectConfig

log = logging.getLogger(__name__)

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


def fetch_companies(client: Any) -> list[dict[str, Any]]:
    """Companies the signed-in user can preview against.

    Read once here with the CLI's credentials and written to the harness as
    plain data, so the preview never holds a token. The payload already carries
    each company's branding, which means the dropdown can restyle the preview
    instantly and without a network call.
    """
    from caraer_cli.api import auth as auth_api

    try:
        payload = auth_api.companies(client).get("data") or []
    except Exception as e:  # noqa: BLE001
        log.debug("Could not list companies for the module preview: %s", e)
        return []

    companies: list[dict[str, Any]] = []
    for company in payload:
        if not isinstance(company, dict):
            continue
        settings = company.get("websiteSettings") or {}
        subdomain = settings.get("subdomain")
        # A company with no subdomain has no site to preview against.
        if not subdomain:
            continue
        companies.append(
            {
                "uuid": company.get("uuid"),
                "name": company.get("name") or subdomain,
                "subdomain": subdomain,
                "digitalIdentity": company.get("digitalIdentity") or {},
                "websiteSettings": settings,
            }
        )

    companies.sort(key=lambda c: (c["name"] or "").lower())
    return companies


PUBLISHED_RUNTIME_SPEC = "github:Caraer-HQ/caraer-cms-runtime#v0.1.1"
PUBLISHED_TOKENS_SPEC = "github:Caraer-HQ/caraer-cms-tokens#v0.1.1"


def resolve_runtime_specs(root: Path) -> tuple[str, str]:
    """Work out where to install ``@caraer/cms-runtime`` and ``-tokens`` from.

    Order: explicit spec env vars, then ``CARAER_WEB_PATH`` / a sibling
    ``caraer-web`` workspace copy, then sibling ``caraer-cms-runtime`` and
    ``caraer-cms-tokens`` checkouts, then the published GitHub packages.
    """
    runtime = os.environ.get("CARAER_CMS_RUNTIME_SPEC")
    tokens = os.environ.get("CARAER_CMS_TOKENS_SPEC")
    if runtime and tokens:
        return runtime, tokens

    candidates: list[Path] = []
    configured = os.environ.get("CARAER_WEB_PATH")
    if configured:
        candidates.append(Path(configured).expanduser())

    # Walk up looking for sibling checkouts: app repos and the CMS packages
    # usually live next to each other under one workspace directory.
    current = root.resolve()
    parents = [current, *current.parents][:5]
    for parent in parents:
        candidates.append(parent / "caraer-web")

    for candidate in candidates:
        runtime_pkg = candidate / "packages" / "cms-runtime" / "package.json"
        tokens_pkg = candidate / "packages" / "cms-tokens" / "package.json"
        if runtime_pkg.is_file() and tokens_pkg.is_file():
            return (
                runtime or f"file:{runtime_pkg.parent.resolve()}",
                tokens or f"file:{tokens_pkg.parent.resolve()}",
            )

    for parent in parents:
        runtime_pkg = parent / "caraer-cms-runtime" / "package.json"
        tokens_pkg = parent / "caraer-cms-tokens" / "package.json"
        if runtime_pkg.is_file() and tokens_pkg.is_file():
            return (
                runtime or f"file:{runtime_pkg.parent.resolve()}",
                tokens or f"file:{tokens_pkg.parent.resolve()}",
            )

    return runtime or PUBLISHED_RUNTIME_SPEC, tokens or PUBLISHED_TOKENS_SPEC


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


def _package_json(
    app_name: str,
    runtime_spec: str,
    tokens_spec: str,
    frameworks: set[str],
    extra_deps: dict[str, str] | None = None,
) -> dict:
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
    if extra_deps:
        deps.update(extra_deps)

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
  // The toolbar floats over the bottom of the preview, which is exactly where
  // a footer module renders.
  devToolbar: {{ enabled: false }},
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
      // Our module error UI replaces this. A Vite overlay would cover the
      // whole preview, which is the failure this harness exists to contain.
      hmr: {{ overlay: false }},
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
const HARNESS_API = process.env.CARAER_HARNESS_API;
const HARNESS_TOKEN = process.env.CARAER_HARNESS_TOKEN;
const API_BASE = (process.env.CARAER_API_BASE_URL || '').replace(/\\/$/, '');
const RECORD_OBJECT = process.env.CARAER_RECORD_OBJECT;

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
 * Calls the public CMS API for the currently selected company.
 *
 * Returns null on any failure rather than throwing: a preview that falls back
 * to sample data is far more useful than one that shows a stack trace because
 * a VPN dropped.
 */
async function live(path, init = {}, subdomain = SUBDOMAIN) {
  if (!subdomain || !API_BASE) return null;
  try {
    const response = await fetch(`${API_BASE}/api/v2/webpages/v2/public${path}`, {
      ...init,
      headers: {
        Accept: 'application/json',
        'X-Caraer-Subdomain': subdomain,
        ...(init.body ? { 'Content-Type': 'application/json' } : {}),
        ...(init.headers || {}),
      },
    });
    if (!response.ok) {
      // Must be loud. Silently serving sample data when you asked for a real
      // company would have you debugging a module against the wrong content.
      console.warn(
        `[harness] ${path} returned ${response.status} for '${subdomain}' - using sample data.`,
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

/*
 * The company list and its branding are real customer data, so the CLI holds
 * them in memory and serves them over loopback for as long as the preview
 * runs, rather than writing them into your checkout. Cached per process, so
 * changing module or field does not refetch.
 */
async function harnessApi(path) {
  if (!HARNESS_API) return null;
  try {
    const response = await fetch(`${HARNESS_API}${path}`, {
      headers: { Authorization: `Bearer ${HARNESS_TOKEN}` },
    });
    return response.ok ? await response.json() : null;
  } catch (error) {
    console.warn(`[harness] Could not reach the CLI (${error.message}).`);
    return null;
  }
}

let companiesPromise;
const loadCompanies = () =>
  (companiesPromise ??= harnessApi('/companies').then((list) => list ?? []));

// Branding is per company, so a preview you never point at one never asks.
const companyCache = new Map();
const loadCompany = (subdomain) => {
  if (!companyCache.has(subdomain)) {
    companyCache.set(subdomain, harnessApi(`/companies/${encodeURIComponent(subdomain)}`));
  }
  return companyCache.get(subdomain);
};

// Cached per company rather than per request: this data changes rarely while a
// preview reloads on every keystroke, but switching companies must refetch.
const settingsCache = new Map();
const loadSettings = (subdomain) => {
  if (!subdomain) return Promise.resolve(null);
  if (!settingsCache.has(subdomain)) {
    settingsCache.set(
      subdomain,
      (async () => {
        const settings = await live('/settings', {}, subdomain);
        if (!settings) {
          console.warn(
            `[harness] Could not reach company '${subdomain}'. Everything below is ` +
              'sample data, not that company\\'s content.',
          );
        }
        return settings;
      })(),
    );
  }
  return settingsCache.get(subdomain);
};

const recordCache = new Map();
const loadRecord = (subdomain) => {
  if (!subdomain || !RECORD_OBJECT) return Promise.resolve(SAMPLE_RECORD);
  const key = `${subdomain}:${RECORD_OBJECT}`;
  if (!recordCache.has(key)) {
    recordCache.set(
      key,
      (async () => {
        const result = await live(
          '/records',
          { method: 'POST', body: JSON.stringify({ object: RECORD_OBJECT, limit: 1 }) },
          subdomain,
        );
        const first = result?.records?.[0];
        if (!first) return SAMPLE_RECORD;
        return {
          uuid: first.uuid,
          object: RECORD_OBJECT,
          properties: first.properties ?? {},
          parsedProperties: first.parsedProperties ?? {},
        };
      })(),
    );
  }
  return recordCache.get(key);
};

export const onRequest = defineMiddleware(async (context, next) => {
  /*
   * The dropdown picks a company per request. Its branding already arrived with
   * the company list, so switching restyles the preview with no network call
   * and keeps working where the public API is unreachable.
   */
  // Absent means "not chosen yet", so --company decides. Empty means the
  // picker chose sample data, which must survive --company.
  const requested = context.url.searchParams.has('company')
    ? context.url.searchParams.get('company')
    : SUBDOMAIN;
  const selectedCompany = requested ? await loadCompany(requested) : null;
  const activeSubdomain = selectedCompany?.subdomain ?? requested ?? null;

  // Only companies missing from the list need fetching; the rest came baked.
  const settings = selectedCompany ? null : await loadSettings(activeSubdomain);

  context.locals.company = selectedCompany
    ? {
        uuid: selectedCompany.uuid,
        name: selectedCompany.name,
        subdomain: selectedCompany.subdomain,
        logo: selectedCompany.websiteSettings?.logo ?? null,
        logoDark: selectedCompany.websiteSettings?.logoDark ?? null,
        favicon: selectedCompany.websiteSettings?.favicon ?? null,
      }
    : settings?.company ?? {
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
  const branding = selectedCompany ?? settings;
  context.locals.tokens = branding
    ? resolveTokens({
        digitalIdentity: branding.digitalIdentity,
        websiteSettings: branding.websiteSettings,
      })
    : DEFAULT_TOKENS;

  context.locals.editor = null;
  context.locals.record = await loadRecord(activeSubdomain);

  // Lets the chrome say whether you are looking at real content or samples.
  context.locals.harness = {
    live: Boolean(selectedCompany || settings),
    subdomain: activeSubdomain,
    companyName: selectedCompany?.name ?? settings?.company?.name ?? null,
    companies: await loadCompanies(),
  };

  context.locals.assetUrl = (key) => key ?? null;
  context.locals.localePath = (path) => (path?.startsWith('/') ? path : `/${path ?? ''}`);
  context.locals.tag = () => {};

  context.locals.getMenu = async (location) => {
    const menus = await live(`/menus?locale=nl`, {}, activeSubdomain);
    const match = Array.isArray(menus) ? menus.find((m) => m.location === location) : null;
    // Every location falls back to the same sample menu, so a footer module
    // with four columns still renders something recognisable.
    return match ?? { ...SAMPLE_MENU, location };
  };

  context.locals.getForm = async (form) =>
    (await live(`/forms/${encodeURIComponent(String(form))}`, {}, activeSubdomain)) ??
    SAMPLE_FORM(form);

  context.locals.listRecords = async ({ object, limit = 6, offset, orderBy, filter }) =>
    (await live(
      '/records',
      { method: 'POST', body: JSON.stringify({ object, limit, offset, orderBy, filter }) },
      activeSubdomain,
    )) ?? sampleRecords(object, limit);

  return next();
});
"""


def _harness_page(modules: list[LocalModule], app_label: str) -> str:
    """The harness page: renders each module with an editable field sidebar."""
    # Metadata is baked in so a syntax error in one module cannot fail the
    # page module graph. The selected component is loaded on demand.
    catalog = [
        {
            "name": m.name,
            "label": m.label,
            "kind": m.kind,
            "description": m.config.get("description") or "",
            "fields": m.fields,
            "frameworks": m.frameworks,
        }
        for m in modules
    ]
    loaders = ",\n".join(
        f"  {json.dumps(m.name)}: () => import({json.dumps(f'@modules/{m.name}/index.astro')})"
        for m in modules
    )

    return f"""---
// GENERATED by `caraer apps local dev --cms` - do not edit.
import {{ DEFAULT_TOKENS, toCustomProperties, toStyleAttribute }} from '@caraer/cms-tokens';
import {{ resolveFieldValues, renderModuleErrorHtml, withModuleBoundary }} from '@caraer/cms-runtime';

import samples from '../../samples.json';

const modules = {json.dumps(catalog, ensure_ascii=False, indent=2)};

const loaders = {{
{loaders}
}};

const active = Astro.url.searchParams.get('module') ?? modules[0]?.name;
const selected = modules.find((m) => m.name === active) ?? modules[0];
const manifestFields = selected?.fields ?? [];

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

let Selected = null;
let loadError = null;
if (selected?.name && loaders[selected.name]) {{
  try {{
    const loaded = await loaders[selected.name]();
    Selected = withModuleBoundary(loaded.default, {{
      moduleRef: `local/${{selected.name}}`,
      detail: true,
    }}, selected);
  }} catch (error) {{
    loadError = error;
  }}
}}

let props = null;
try {{
  props = {{
    fields: resolveFieldValues(manifestFields, stored, record),
    rawFields: stored,
    record,
    page: Astro.locals.page,
    company: Astro.locals.company,
    module: {{ id: 'sample', ref: `local/${{selected?.name}}`, kind: selected?.kind }},
    editor: null,
  }};
}} catch (error) {{
  loadError ??= error;
}}

// The middleware resolves these from the attached company when --company is
// set, so the preview shows real branding rather than platform defaults.
const style = toStyleAttribute(toCustomProperties(Astro.locals.tokens ?? DEFAULT_TOKENS));
const live = Astro.locals.harness?.live ?? false;
const subdomain = Astro.locals.harness?.subdomain ?? '';
const companies = Astro.locals.harness?.companies ?? [];

// Carry the exact choice across module links, including the empty value that
// means "sample data even though --company is set". Dropping the parameter
// would hand the decision back to the flag every time you changed module.
const companyChoice = Astro.url.searchParams.get('company');
const moduleHref = (name) => {{
  const params = new URLSearchParams({{ module: name }});
  if (companyChoice !== null) params.set('company', companyChoice);
  return `?${{params}}`;
}};

// Resolved values, not the defaults: these are what the selected company
// actually renders with, which is the whole point of showing them here.
const tokenValues = toCustomProperties(Astro.locals.tokens ?? DEFAULT_TOKENS);
const TYPE_TOKEN = /^--caraer-(font|size|weight|leading)-/;
const tokenGroups = [
  {{ label: 'Colour', kind: 'color', match: (n) => n.startsWith('--caraer-color-') }},
  {{ label: 'Spacing', kind: 'space', match: (n) => n.startsWith('--caraer-space-') }},
  {{ label: 'Radius', kind: 'radius', match: (n) => n.startsWith('--caraer-radius-') }},
  {{ label: 'Typography', kind: 'type', match: (n) => TYPE_TOKEN.test(n) }},
  {{ label: 'Shadow', kind: 'shadow', match: (n) => n.startsWith('--caraer-shadow-') }},
  {{ label: 'Breakpoint', kind: 'plain', match: (n) => n.startsWith('--caraer-breakpoint-') }},
  {{ label: 'Layout', kind: 'plain', match: (n) => n.startsWith('--caraer-container') || n.startsWith('--caraer-header') }},
]
  .map((group) => ({{
    ...group,
    tokens: Object.entries(tokenValues).filter(([name]) => group.match(name)),
  }}))
  .filter((group) => group.tokens.length > 0);

/*
 * Media queries evaluate against the viewport, not a parent max-width. The
 * production builder already renders the page in an iframe for that reason.
 * This embed document is the same idea: Mobile/Tablet resize the iframe, so
 * `@media (max-width: 640px)` in a module actually fires.
 */
const embed = Astro.url.searchParams.get('embed') === '1';
const embedSrc = (() => {{
  const params = new URLSearchParams(Astro.url.search);
  params.set('embed', '1');
  return `?${{params}}`;
}})();
---

<html lang="nl" style={{style}}>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{{selected?.label ?? 'Modules'}} - Caraer module preview</title>
  </head>
  <body class={{embed ? 'is-embed' : undefined}}>
    {{embed ? (
      <div class="harness__preview" id="harness-preview">
        {{loadError ? (
          <Fragment set:html={{renderModuleErrorHtml({{ moduleRef: `local/${{selected?.name}}`, detail: true }}, loadError)}} />
        ) : (
          Selected && props && <Selected {{...props}} />
        )}}
      </div>
    ) : (
    <div class="hx">
      <header class="hx-bar">
        <div class="hx-brand">
          <span class="hx-mark">C</span>
          <div class="hx-brand__text">
            <strong>{app_label}</strong>
            <span>{{modules.length}} module{{modules.length === 1 ? '' : 's'}}</span>
          </div>
        </div>

        <label class="hx-source" data-live={{live ? '' : undefined}}>
          <span class="hx-dot"></span>
          <span class="hx-sr">Preview data</span>
          <select id="hx-company" name="company">
            <option value="">Sample data</option>
            {{companies.map((c) => (
              <option value={{c.subdomain}} selected={{c.subdomain === subdomain}}>{{c.name}}</option>
            ))}}
          </select>
        </label>

        <div class="hx-seg" role="group" aria-label="Viewport width">
          <button type="button" data-width="390">Mobile</button>
          <button type="button" data-width="820">Tablet</button>
          <button type="button" data-width="0" class="is-on">Full</button>
        </div>
      </header>

      <aside class="hx-modules">
        <h2>Modules</h2>
        <ul>
          {{modules.map((m) => (
            <li>
              <a href={{moduleHref(m.name)}} aria-current={{m.name === selected?.name ? 'page' : undefined}}>
                <span class="hx-modules__name">{{m.label}}</span>
                <span class="hx-kind" data-kind={{m.kind}}>{{m.kind}}</span>
              </a>
            </li>
          ))}}
        </ul>
      </aside>

      <main class="hx-canvas">
        <div class="hx-frame" id="harness-frame">
          <iframe
            id="harness-preview"
            class="hx-frame__doc"
            title="Module preview"
            src={{embedSrc}}
          ></iframe>
        </div>
      </main>

      <aside class="hx-fields">
        <header class="hx-fields__head">
          <h2>{{selected?.label}}</h2>
          {{selected?.description && <p>{{selected.description}}</p>}}
          <code>{{selected?.name}}</code>

          <div class="hx-seg hx-seg--panel" role="group" aria-label="Sidebar panel">
            <button type="button" data-panel="fields" class="is-on">Fields</button>
            <button type="button" data-panel="tokens">Tokens</button>
          </div>
        </header>

        <div class="hx-panel" data-panel="fields">
        <form method="get" class="harness__fields">
          <input type="hidden" name="module" value={{selected?.name}} />
          <input type="hidden" name="company" value={{subdomain}} />

          {{manifestFields.length === 0 && (
            <p class="hx-empty">This module has no editable fields.</p>
          )}}

          {{/* Note: a textarea's tag content is its value, so it stays on one line. */}}
          {{manifestFields.map((field) => (
            <div class="hx-field" data-type={{field.type}}>
              <label class="hx-field__label" for={{`f-${{field.name}}`}}>
                <span>
                  {{field.label}}
                  {{field.required && <em class="hx-req" title="Required">*</em>}}
                </span>
                <code>{{field.type.toLowerCase().replace(/_/g, ' ')}}</code>
              </label>

              {{field.type === 'SWITCH' ? (
                <label class="hx-switch">
                  <input
                    id={{`f-${{field.name}}`}}
                    type="checkbox"
                    name={{`f.${{field.name}}`}}
                    checked={{Boolean(stored[field.name])}}
                    value="true"
                  />
                  <span class="hx-switch__track"><span class="hx-switch__thumb"></span></span>
                  <span class="hx-switch__state">{{stored[field.name] ? 'On' : 'Off'}}</span>
                </label>
              ) : field.type === 'MULTI_LINE' ? (
                <textarea id={{`f-${{field.name}}`}} name={{`f.${{field.name}}`}} rows="4">{{String(stored[field.name] ?? '')}}</textarea>
              ) : field.options ? (
                <select id={{`f-${{field.name}}`}} name={{`f.${{field.name}}`}}>
                  {{field.options.map((o) => (
                    <option value={{o.name}} selected={{stored[field.name] === o.name}}>{{o.label}}</option>
                  ))}}
                </select>
              ) : (
                <input
                  id={{`f-${{field.name}}`}}
                  name={{`f.${{field.name}}`}}
                  value={{String(stored[field.name] ?? '')}}
                  placeholder={{field.helpText ?? ''}}
                />
              )}}

              {{field.helpText && <small class="hx-help">{{field.helpText}}</small>}}
            </div>
          ))}}

          <button type="submit" class="hx-apply">Apply</button>
        </form>
        </div>

        <div class="hx-panel" data-panel="tokens" hidden>
          <p class="hx-panel__note">
            Every value below is what{{' '}}
            {{Astro.locals.harness?.companyName ?? 'sample data'}} renders with.
            Click a token to copy its <code>var()</code>.
          </p>

          <input
            type="search"
            class="hx-token-filter"
            placeholder="Filter tokens"
            aria-label="Filter tokens"
          />

          {{tokenGroups.map((group) => (
            <section class="hx-token-group">
              <h3>{{group.label}}</h3>
              {{group.tokens.map(([name, value]) => (
                <button type="button" class="hx-token" data-name={{name}} data-kind={{group.kind}}>
                  {{group.kind !== 'plain' && group.kind !== 'type' && (
                    <span class="hx-token__chip" style={{`--chip: var(${{name}})`}}></span>
                  )}}
                  <code class="hx-token__name">{{name.replace('--caraer-', '')}}</code>
                  <span class="hx-token__value">{{value}}</span>
                </button>
              ))}}
            </section>
          ))}}

          <p class="hx-empty" hidden>No token matches that filter.</p>
        </div>
      </aside>
    </div>
    )}}

    <script>
      // Live preview: re-render as you type instead of on Apply. Only the
      // preview pane is swapped, so focus and caret position survive editing.
      // The Apply button still works with JavaScript disabled.
      const form = document.querySelector('.harness__fields');
      const preview = document.getElementById('harness-preview');

      if (form instanceof HTMLFormElement && preview instanceof HTMLIFrameElement) {{
        let timer;
        let inFlight;

        const render = async () => {{
          const params = new URLSearchParams(new FormData(form));

          // An unchecked checkbox submits nothing, so the value would fall back
          // to the sample and a switch could never be turned off.
          form.querySelectorAll('input[type="checkbox"]').forEach((box) => {{
            if (!box.checked) params.set(box.name, 'false');
          }});

          const chrome = params.toString();
          history.replaceState(null, '', '?' + chrome);

          params.set('embed', '1');
          const query = params.toString();

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
            const doc = preview.contentDocument;
            const current = doc?.getElementById('harness-preview');
            if (!next) return;
            if (!current) {{
              preview.src = '/?' + query;
              return;
            }}

            current.replaceChildren(
              ...Array.from(next.childNodes).map((node) => doc.adoptNode(node)),
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

    <script is:inline>
      // Company switch. A reload rather than a partial swap: the whole document
      // restyles, since design tokens live on <html>.
      document.getElementById('hx-company')?.addEventListener('change', (event) => {{
        const url = new URL(window.location.href);
        // Always set, never delete: an absent value would hand the choice back
        // to --company and you could not return to sample data.
        url.searchParams.set('company', event.target.value);
        window.location.href = url.toString();
      }});
    </script>

    <script is:inline>
      // Tokens panel: switch, filter and copy. Inert chrome, so it stays out of
      // the script that talks to the server.
      const panels = document.querySelectorAll('.hx-panel');
      document.querySelectorAll('.hx-seg--panel button').forEach((tab) => {{
        tab.addEventListener('click', () => {{
          document
            .querySelectorAll('.hx-seg--panel button')
            .forEach((b) => b.classList.toggle('is-on', b === tab));
          panels.forEach((panel) => {{
            panel.hidden = panel.dataset.panel !== tab.dataset.panel;
          }});
        }});
      }});

      const filter = document.querySelector('.hx-token-filter');
      const noMatch = document.querySelector('.hx-panel[data-panel="tokens"] .hx-empty');
      filter?.addEventListener('input', () => {{
        const term = filter.value.trim().toLowerCase();
        let shown = 0;
        document.querySelectorAll('.hx-token').forEach((token) => {{
          const hit = token.dataset.name.includes(term);
          token.hidden = !hit;
          if (hit) shown += 1;
        }});
        // Hide a group whose every token was filtered out, so the headings
        // left on screen still describe something.
        document.querySelectorAll('.hx-token-group').forEach((group) => {{
          group.hidden = !group.querySelector('.hx-token:not([hidden])');
        }});
        if (noMatch) noMatch.hidden = shown > 0;
      }});

      document.querySelectorAll('.hx-token').forEach((token) => {{
        token.addEventListener('click', async () => {{
          const snippet = `var(${{token.dataset.name}})`;
          try {{
            await navigator.clipboard.writeText(snippet);
            token.dataset.copied = '';
            setTimeout(() => delete token.dataset.copied, 900);
          }} catch {{
            // Clipboard needs a secure context, which plain http on a LAN
            // address is not. Select the text so it can still be copied.
            const range = document.createRange();
            range.selectNodeContents(token.querySelector('.hx-token__name'));
            getSelection()?.removeAllRanges();
            getSelection()?.addRange(range);
          }}
        }});
      }});
    </script>

    <script is:inline>
      // Viewport width toggle. Chrome-only, so it lives here rather than in the
      // live-update script that talks to the server.
      const frame = document.getElementById('harness-frame');
      document.querySelectorAll('.hx-bar .hx-seg button').forEach((button) => {{
        button.addEventListener('click', () => {{
          document.querySelectorAll('.hx-bar .hx-seg button').forEach((b) => {{
            b.classList.remove('is-on');
          }});
          button.classList.add('is-on');
          const width = Number(button.dataset.width);
          frame.style.maxWidth = width ? width + 'px' : '';
          frame.toggleAttribute('data-constrained', Boolean(width));
        }});
      }});
    </script>

    <style is:global>
      /*
       * Chrome styles only. Namespaced under .hx- and scoped selectors so they
       * never reach the previewed module, which brings its own CSS and the
       * company's design tokens.
       */
      :root {{
        --hx-bg: #0f1115;
        --hx-panel: #161920;
        --hx-panel-2: #1c2029;
        --hx-line: #272c37;
        --hx-text: #e7e9ee;
        --hx-muted: #98a0ae;
        --hx-accent: #5b8cff;
      }}

      html, body {{ height: 100%; }}
      body {{
        margin: 0;
        background: var(--hx-bg);
        font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
        color: var(--hx-text);
      }}
      /*
       * Embed document: chrome styles stay namespaced under .hx, so they do
       * not leak in. These reset the iframe document to a live page shell.
       */
      body.is-embed {{
        height: auto;
        min-height: 100%;
        background: var(--caraer-color-background);
        color: var(--caraer-color-font);
        font-family: var(--caraer-font-body);
        font-size: var(--caraer-size-body);
        line-height: var(--caraer-leading-body);
      }}
      body.is-embed .harness__preview {{
        display: block;
        width: 100%;
        background: var(--caraer-color-background);
        color: var(--caraer-color-font);
        font-family: var(--caraer-font-body);
        font-size: var(--caraer-size-body);
        line-height: var(--caraer-leading-body);
      }}

      .hx {{
        display: grid;
        grid-template-columns: 200px minmax(0, 1fr) 300px;
        grid-template-rows: 52px minmax(0, 1fr);
        height: 100vh;
      }}

      /* Top bar */
      .hx-bar {{
        grid-column: 1 / -1;
        display: flex;
        align-items: center;
        gap: 1rem;
        padding: 0 0.875rem;
        background: var(--hx-panel);
        border-bottom: 1px solid var(--hx-line);
      }}
      .hx-brand {{ display: flex; align-items: center; gap: 0.625rem; min-width: 0; }}
      .hx-mark {{
        display: grid; place-items: center;
        width: 26px; height: 26px; border-radius: 7px;
        background: var(--hx-accent); color: #fff;
        font-weight: 700; font-size: 0.8125rem;
      }}
      .hx-brand__text {{ display: grid; line-height: 1.2; min-width: 0; }}
      .hx-brand__text strong {{ font-size: 0.8125rem; }}
      .hx-brand__text span {{ font-size: 0.6875rem; color: var(--hx-muted); }}

      .hx-source {{
        display: flex; align-items: center; gap: 0.4rem;
        margin-left: auto;
        padding: 0.25rem 0.6rem;
        border: 1px solid var(--hx-line); border-radius: 999px;
        font-size: 0.6875rem; color: var(--hx-muted);
      }}
      .hx-source:hover {{ border-color: #2c3240; }}
      .hx-source select {{
        appearance: none;
        border: 0; background: transparent; color: inherit;
        font: inherit; font-size: 0.6875rem;
        padding-right: 0.75rem; cursor: pointer; outline: none;
        background-image: linear-gradient(45deg, transparent 50%, currentColor 50%),
          linear-gradient(135deg, currentColor 50%, transparent 50%);
        background-position: right 3px center, right 0 center;
        background-size: 4px 4px, 4px 4px;
        background-repeat: no-repeat;
      }}
      .hx-source select option {{ background: var(--hx-panel); color: var(--hx-text); }}
      .hx-dot {{ width: 6px; height: 6px; border-radius: 50%; background: #6b7280; flex: none; }}
      .hx-source[data-live] {{ color: #86efac; border-color: #14532d; }}
      .hx-source[data-live] .hx-dot {{ background: #22c55e; }}
      .hx-sr {{
        position: absolute; width: 1px; height: 1px;
        padding: 0; margin: -1px; overflow: hidden;
        clip: rect(0 0 0 0); white-space: nowrap; border: 0;
      }}

      .hx-seg {{
        display: flex; gap: 2px; padding: 2px;
        background: var(--hx-panel-2); border-radius: 8px;
      }}
      .hx-seg button {{
        border: 0; background: transparent; color: var(--hx-muted);
        font: inherit; font-size: 0.6875rem;
        padding: 0.3rem 0.6rem; border-radius: 6px; cursor: pointer;
      }}
      .hx-seg button:hover {{ color: var(--hx-text); }}
      .hx-seg button.is-on {{ background: var(--hx-bg); color: var(--hx-text); }}

      /* Tokens panel */
      .hx-seg--panel {{ margin-top: 0.625rem; width: fit-content; }}
      .hx-panel[hidden] {{ display: none; }}
      .hx-panel__note {{
        margin: 0 0 0.75rem; font-size: 0.6875rem; line-height: 1.5;
        color: var(--hx-muted);
      }}
      .hx-panel__note code {{ font-size: 0.625rem; }}

      .hx-token-filter {{
        width: 100%; margin-bottom: 0.75rem;
        padding: 0.4rem 0.6rem;
        background: var(--hx-panel-2); color: var(--hx-text);
        border: 1px solid var(--hx-line); border-radius: 7px;
        font: inherit; font-size: 0.75rem;
      }}
      .hx-token-filter:focus {{ outline: none; border-color: var(--hx-accent); }}

      .hx-token-group {{ margin-bottom: 1rem; }}
      .hx-token-group[hidden] {{ display: none; }}
      .hx-token-group h3 {{
        margin: 0 0 0.375rem;
        font-size: 0.625rem; font-weight: 600;
        text-transform: uppercase; letter-spacing: 0.08em;
        color: var(--hx-muted);
      }}

      .hx-token {{
        display: flex; align-items: center; gap: 0.5rem;
        width: 100%; padding: 0.3rem 0.4rem;
        border: 0; border-radius: 6px;
        background: transparent; color: var(--hx-text);
        font: inherit; text-align: left; cursor: pointer;
      }}
      .hx-token[hidden] {{ display: none; }}
      .hx-token:hover {{ background: var(--hx-panel-2); }}
      .hx-token__name {{
        flex: 1; min-width: 0;
        font-size: 0.6875rem;
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
      }}
      .hx-token__value {{
        flex: none; max-width: 45%;
        font-size: 0.625rem; color: var(--hx-muted);
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
      }}
      .hx-token[data-copied] .hx-token__value {{ color: #86efac; }}
      .hx-token[data-copied] .hx-token__value::after {{ content: ' copied'; }}

      /* One chip per kind, so a value is legible at a glance rather than read. */
      .hx-token__chip {{
        flex: none; width: 16px; height: 16px; border-radius: 4px;
        background: var(--hx-panel-2);
      }}
      .hx-token[data-kind='color'] .hx-token__chip {{
        background: var(--chip);
        box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.14);
      }}
      .hx-token[data-kind='radius'] .hx-token__chip {{
        border-radius: var(--chip);
        background: #3b4252;
      }}
      .hx-token[data-kind='shadow'] .hx-token__chip {{
        background: #fff; box-shadow: var(--chip);
      }}
      /* Width tracks the real value, capped so --caraer-space-section still fits. */
      .hx-token[data-kind='space'] .hx-token__chip {{
        width: min(var(--chip), 16px); min-width: 2px;
        height: 8px; border-radius: 2px; background: var(--hx-accent);
      }}

      /* Module list */
      .hx-modules {{
        background: var(--hx-panel);
        border-right: 1px solid var(--hx-line);
        padding: 0.875rem 0.625rem;
        overflow-y: auto;
      }}
      .hx-modules h2, .hx-fields h2 {{
        margin: 0 0 0.5rem;
        font-size: 0.625rem; font-weight: 600;
        text-transform: uppercase; letter-spacing: 0.08em;
        color: var(--hx-muted);
      }}
      .hx-modules ul {{ list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; }}
      .hx-modules a {{
        display: flex; align-items: center; justify-content: space-between; gap: 0.5rem;
        padding: 0.5rem 0.6rem; border-radius: 7px;
        color: var(--hx-muted); text-decoration: none; font-size: 0.8125rem;
      }}
      .hx-modules a:hover {{ background: var(--hx-panel-2); color: var(--hx-text); }}
      .hx-modules a[aria-current] {{ background: var(--hx-panel-2); color: var(--hx-text); font-weight: 600; }}
      .hx-modules a[aria-current] .hx-modules__name {{ box-shadow: inset 2px 0 0 var(--hx-accent); padding-left: 0.5rem; margin-left: -0.5rem; }}
      .hx-modules__name {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}

      .hx-kind {{
        flex: none;
        font-size: 0.5625rem; text-transform: uppercase; letter-spacing: 0.05em;
        padding: 0.1rem 0.35rem; border-radius: 4px;
        background: #23304a; color: #9cc0ff;
      }}
      .hx-kind[data-kind="page"] {{ background: #3a2a4d; color: #d3b0ff; }}
      .hx-kind[data-kind="header"], .hx-kind[data-kind="footer"] {{ background: #2c3340; color: #b6c0d0; }}

      /* Preview canvas */
      .hx-canvas {{
        padding: 1.25rem;
        overflow: hidden;
        min-height: 0;
        display: flex;
        flex-direction: column;
        background:
          linear-gradient(45deg, #14171d 25%, transparent 25%) -8px 0/16px 16px,
          linear-gradient(-45deg, #14171d 25%, transparent 25%) -8px 0/16px 16px,
          var(--hx-bg);
      }}
      /*
       * Full width is deliberately unstyled: no radius and no clipping, because
       * both are chrome a real page does not have. Sticky positioning lives
       * inside the iframe document, so it sticks to that viewport the way it
       * does on a live page.
       *
       * A constrained width is different - there the rounding reads as a device
       * frame, which is the whole point of the mobile and tablet views.
       */
      .hx-frame {{
        position: relative;
        margin: 0 auto;
        width: 100%;
        flex: 1 1 auto;
        min-height: 0;
        background: var(--caraer-color-background, #fff);
        box-shadow: 0 12px 40px rgba(0, 0, 0, 0.45);
        transition: max-width 180ms ease;
      }}
      .hx-frame[data-constrained] {{
        border-radius: 14px;
        overflow: hidden;
      }}
      .hx-frame__doc {{
        position: absolute;
        inset: 0;
        width: 100%;
        height: 100%;
        border: 0;
        background: var(--caraer-color-background, #fff);
      }}

      /* Field panel */
      .hx-fields {{
        background: var(--hx-panel);
        border-left: 1px solid var(--hx-line);
        padding: 0.875rem;
        overflow-y: auto;
      }}
      .hx-fields__head {{ margin-bottom: 1rem; }}
      .hx-fields__head h2 {{
        font-size: 0.9375rem; font-weight: 600; text-transform: none;
        letter-spacing: 0; color: var(--hx-text); margin-bottom: 0.25rem;
      }}
      .hx-fields__head p {{ margin: 0 0 0.4rem; font-size: 0.75rem; color: var(--hx-muted); line-height: 1.45; }}
      .hx-fields__head code, .hx-field__label code {{
        font-size: 0.625rem; color: var(--hx-muted);
        background: var(--hx-panel-2); padding: 0.1rem 0.35rem; border-radius: 4px;
      }}

      .harness__fields {{ display: grid; gap: 0.875rem; }}
      .hx-field {{ display: grid; gap: 0.3rem; }}
      .hx-field__label {{
        display: flex; align-items: center; justify-content: space-between; gap: 0.5rem;
        font-size: 0.75rem; font-weight: 600;
      }}
      .hx-req {{ color: #f87171; font-style: normal; }}
      .hx-help {{ font-size: 0.6875rem; color: var(--hx-muted); line-height: 1.4; }}
      .hx-empty {{ font-size: 0.75rem; color: var(--hx-muted); }}

      .harness__fields input[type="text"],
      .harness__fields input:not([type]),
      .harness__fields select,
      .harness__fields textarea {{
        width: 100%; box-sizing: border-box;
        font: inherit; font-size: 0.8125rem;
        padding: 0.45rem 0.55rem;
        background: var(--hx-bg);
        border: 1px solid var(--hx-line); border-radius: 7px;
        color: var(--hx-text);
      }}
      .harness__fields textarea {{ resize: vertical; line-height: 1.5; }}
      .harness__fields input:focus-visible,
      .harness__fields select:focus-visible,
      .harness__fields textarea:focus-visible {{
        outline: none; border-color: var(--hx-accent);
        box-shadow: 0 0 0 3px rgba(91, 140, 255, 0.18);
      }}

      /* Switch */
      .hx-switch {{ display: flex; align-items: center; gap: 0.5rem; cursor: pointer; }}
      .hx-switch input {{ position: absolute; opacity: 0; width: 0; height: 0; }}
      .hx-switch__track {{
        width: 34px; height: 20px; border-radius: 999px;
        background: var(--hx-line); position: relative; transition: background 140ms ease;
      }}
      .hx-switch__thumb {{
        position: absolute; top: 2px; left: 2px;
        width: 16px; height: 16px; border-radius: 50%;
        background: #fff; transition: transform 140ms ease;
      }}
      .hx-switch input:checked + .hx-switch__track {{ background: var(--hx-accent); }}
      .hx-switch input:checked + .hx-switch__track .hx-switch__thumb {{ transform: translateX(14px); }}
      .hx-switch input:focus-visible + .hx-switch__track {{ box-shadow: 0 0 0 3px rgba(91, 140, 255, 0.18); }}
      .hx-switch__state {{ font-size: 0.75rem; color: var(--hx-muted); }}

      .hx-apply {{
        margin-top: 0.25rem; padding: 0.5rem;
        border: 1px solid var(--hx-line); border-radius: 7px;
        background: var(--hx-panel-2); color: var(--hx-muted);
        font: inherit; font-size: 0.75rem; cursor: pointer;
      }}
      .hx-apply:hover {{ color: var(--hx-text); border-color: var(--hx-accent); }}

      /* The preview is the point, so the panels give up width first. */
      @media (max-width: 1200px) {{
        .hx {{ grid-template-columns: 170px minmax(0, 1fr) 260px; }}
        .hx-canvas {{ padding: 0.75rem; }}
      }}

      /*
       * Below this, three columns leave the preview too narrow to judge
       * anything, so the fields move underneath and the preview takes the width.
       */
      @media (max-width: 960px) {{
        .hx {{
          grid-template-columns: 150px minmax(0, 1fr);
          grid-template-rows: 52px minmax(0, 1fr) minmax(160px, 34vh);
        }}
        .hx-fields {{
          grid-column: 1 / -1;
          border-left: 0;
          border-top: 1px solid var(--hx-line);
        }}
      }}
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
        json.dumps(
            _package_json(
                app_name,
                runtime_spec,
                tokens_spec,
                frameworks,
                extra_deps=read_app_dependencies(root),
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (harness / "astro.config.mjs").write_text(
        _astro_config(modules_dir(root, config.srcDir).resolve(), frameworks, harness.resolve()),
        encoding="utf-8",
    )
    (harness / "src" / "pages" / "index.astro").write_text(_harness_page(modules, app_name), encoding="utf-8")
    (harness / "src" / "middleware.ts").write_text(_harness_middleware(), encoding="utf-8")
    (harness / "samples.json").write_text(
        json.dumps({m.name: sample_fields(m) for m in modules}, indent=2) + "\n", encoding="utf-8"
    )
    (harness / ".gitignore").write_text("*\n", encoding="utf-8")
    # The app root now has its own package.json. Without this, `pnpm install`
    # in the harness walks up, treats the app as the project, and skips
    # @astrojs/node. Vite then loads from the app and the preview dies.
    (harness / ".npmrc").write_text("ignore-workspace=true\n", encoding="utf-8")

    return harness, modules


def _package_manager() -> str:
    return "pnpm" if shutil.which("pnpm") else "npm"


def _harness_install_command() -> list[str]:
    manager = _package_manager()
    if manager == "pnpm":
        return ["pnpm", "install", "--ignore-workspace"]
    return ["npm", "install"]


def _harness_ready(harness: Path) -> bool:
    return (harness / "node_modules" / "@astrojs" / "node").is_dir()


def install_harness(harness: Path, *, force: bool = False) -> int:
    """Install the harness dependencies. Returns the exit code."""
    if not force and _harness_ready(harness):
        return 0

    return subprocess.run(
        _harness_install_command(), cwd=harness, env={**os.environ}, check=False
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
    astro = harness / "node_modules" / ".bin" / "astro"
    command = (
        [
            str(astro),
            "dev",
            "--port",
            str(port),
            "--host",
            host,
            "--ignore-lock",
        ]
        if astro.is_file()
        else [
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
        ]
    )
    return subprocess.Popen(
        command,
        cwd=harness,
        env={**os.environ, **(env or {})},
    )
