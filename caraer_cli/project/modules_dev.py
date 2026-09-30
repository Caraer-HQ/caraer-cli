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
    "FORM_SINGLE_SELECT": "job-alert",
    "OBJECT_SINGLE_SELECT": "vacancy",
    "OBJECT_MULTI_SELECT": [],
    "PROPERTY_SINGLE_SELECT": "title",
    "PROPERTY_MULTI_SELECT": [],
    "SWITCH": True,
    "MAPPING": {},
    "FILE": None,
    "MULTI_FILE": [],
    "IMAGE": None,
    "COLOR": "#1a73e8",
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
        details = company.get("details") or {}
        companies.append(
            {
                "uuid": company.get("uuid"),
                "name": company.get("name") or subdomain,
                "subdomain": subdomain,
                "digitalIdentity": company.get("digitalIdentity") or {},
                "websiteSettings": settings,
                "socials": {
                    "facebook": details.get("facebook") or None,
                    "instagram": details.get("instagram") or None,
                    "linkedIn": details.get("linkedIn") or None,
                    "twitter": details.get("twitter") or None,
                    "youtube": details.get("youtube") or None,
                },
            }
        )

    companies.sort(key=lambda c: (c["name"] or "").lower())
    return companies


def fetch_forms(client: Any, company_uuid: str) -> list[dict[str, Any]]:
    """Forms the signed-in user can pick for the given company.

    Loaded through the CLI so the preview never holds a token. The sidebar
    FORM_SINGLE_SELECT picker shows these instead of asking for a uuid.
    """
    if not company_uuid:
        return []

    try:
        payload = client.request(
            "POST",
            "/api/v2/forms/index",
            json_body={
                "page": 1,
                "limit": 200,
                "query": "",
                "filters": [{"key": "deletedAt", "operator": "isnull"}],
            },
            company_uuid=company_uuid,
        )
    except Exception as e:  # noqa: BLE001
        log.debug("Could not list forms for the module preview: %s", e)
        return []

    raw = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(raw, list):
        return []

    forms: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        uuid = item.get("uuid")
        if not uuid:
            continue
        name = item.get("name") or ""
        forms.append(
            {
                "uuid": uuid,
                "name": name,
                "label": item.get("label") or name or uuid,
            }
        )
    return forms


def fetch_form(client: Any, company_uuid: str, form_ref: str) -> dict[str, Any] | None:
    """Full form definition for the preview, uuid or machine name.

    Uses the authenticated forms API the CLI already has, not the CMS public
    website routes. The preview maps grids onto CaraerForm itself.
    """
    if not company_uuid or not form_ref:
        return None

    try:
        payload = client.request(
            "GET",
            f"/api/v2/forms/{form_ref}",
            company_uuid=company_uuid,
        )
    except Exception as e:  # noqa: BLE001
        log.debug("Could not load form '%s' for the module preview: %s", form_ref, e)
        return None

    raw = payload.get("data") if isinstance(payload, dict) else payload
    return raw if isinstance(raw, dict) and raw.get("uuid") else None


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
    for item in module.field_entries:
        name = str(item.get("name") or "")
        if not name:
            continue
        if "defaultValue" in item and item["defaultValue"] is not None:
            values[name] = item["defaultValue"]
            continue

        field_type = str(item.get("type") or "").upper()
        if field_type == "REPEATABLE":
            values[name] = _sample_repeatable(item)
        elif field_type == "SINGLE_SELECT":
            options = item.get("options") or []
            values[name] = options[0].get("name") if options else None
        elif field_type == "SINGLE_LINE":
            # The field's own label, so you can see at a glance which input
            # produced which piece of the rendered output.
            values[name] = str(item.get("label") or name)
        else:
            values[name] = _SAMPLE_VALUES.get(field_type)
    return values


def _sample_repeatable_item(item: dict[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {}
    nested = item.get("itemFields")
    if not isinstance(nested, list):
        return row
    for child in nested:
        if not isinstance(child, dict):
            continue
        child_name = str(child.get("name") or "")
        if not child_name:
            continue
        if "defaultValue" in child and child["defaultValue"] is not None:
            row[child_name] = child["defaultValue"]
            continue
        child_type = str(child.get("type") or "").upper()
        if child_type == "SINGLE_SELECT":
            options = child.get("options") or []
            row[child_name] = options[0].get("name") if options else None
        elif child_type == "SINGLE_LINE":
            row[child_name] = str(child.get("label") or child_name)
        else:
            row[child_name] = _SAMPLE_VALUES.get(child_type)
    return row


def _sample_repeatable(item: dict[str, Any]) -> list[dict[str, Any]]:
    minimum = item.get("min", 0)
    count = minimum if isinstance(minimum, int) and minimum > 0 else 1
    template = _sample_repeatable_item(item)
    return [dict(template) for _ in range(count)]


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
      rows: [[
        { uuid: '1', name: 'name', label: 'Naam', type: 'STRING', required: true },
        { uuid: '2', name: 'email', label: 'E-mail', type: 'STRING', format: 'EMAIL', required: true },
      ]],
    },
  ],
});

const SAMPLE_FORMS = [
  { uuid: 'job-alert', name: 'job-alert', label: 'Sample form' },
];

const text = (value) => (typeof value === 'string' && value.trim() ? value : null);

const toCaraerForm = (form) => {
  const fieldOf = (cell) => {
    const property = cell.property;
    if (!property?.name || cell.settings?.hidden) return null;
    const format = property.format;
    const formatName = typeof format === 'string' ? format : text(format?.name);
    const normalizedFormat = (formatName ?? '').toLowerCase().replace(/_/g, '-');
    const options = (property.options ?? [])
      .map((option) => {
        const name = text(option.name);
        return name ? { name, label: text(option.label) ?? name } : null;
      })
      .filter(Boolean);
    return {
      uuid: text(property.uuid) ?? property.name,
      name: property.name,
      label: text(cell.settings?.label) ?? text(property.label) ?? property.name,
      type: normalizedFormat === 'multi-line' ? 'TEXT_AREA' : (text(property.type) ?? 'string'),
      format: formatName,
      required: Boolean(cell.settings?.isRequired),
      placeholder: text(cell.settings?.placeholder),
      helpText: text(cell.settings?.helpText),
      options: options.length > 0 ? options : undefined,
    };
  };
  const rowsOf = (step) => {
    const rows = [];
    for (const row of step.grid ?? []) {
      const fields = [];
      for (const cell of row ?? []) {
        const field = fieldOf(cell);
        if (field) fields.push(field);
      }
      if (fields.length > 0) rows.push(fields);
    }
    return rows;
  };
  let submitLabel = null;
  for (const step of form.grids ?? []) {
    for (const row of step.grid ?? []) {
      for (const cell of row ?? []) {
        const label = text(cell.submitButton);
        if (label) submitLabel = label;
      }
    }
  }
  return {
    uuid: form.uuid,
    name: form.name,
    label: text(form.label) ?? form.name,
    wizard: Boolean(form.wizard),
    steps: (form.grids ?? []).map((step) => ({
      title: text(step.title),
      description: text(step.description),
      fields: rowsOf(step).flat(),
      rows: rowsOf(step),
    })),
    submitLabel,
    thankYouMessage: text(form.thankYouMessage),
    redirectUrl: text(form.redirectUrl),
  };
};

const sampleRecords = (object, limit) => ({
  total: limit,
  records: Array.from({ length: limit }, (_, index) => {
    const title = `Sample ${object} ${index + 1}`;
    const description = `Short description for sample ${object} ${index + 1}.`;
    return {
      uuid: `sample-${index + 1}`,
      slug: `/sample-${index + 1}`,
      url: `/sample-${index + 1}`,
      properties: { title, description, location: 'Utrecht' },
      parsedProperties: { title, description, location: 'Utrecht' },
    };
  }),
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

const formsCache = new Map();
const loadForms = (subdomain) => {
  if (!subdomain) return Promise.resolve(SAMPLE_FORMS);
  if (!formsCache.has(subdomain)) {
    formsCache.set(
      subdomain,
      (async () => {
        const listed = await harnessApi(`/forms/${encodeURIComponent(subdomain)}`);
        return Array.isArray(listed) && listed.length > 0 ? listed : SAMPLE_FORMS;
      })(),
    );
  }
  return formsCache.get(subdomain);
};

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

function socialAccounts(source) {
  const bags = [];
  if (source && typeof source === 'object') bags.push(source);
  if (source?.socials && typeof source.socials === 'object') bags.push(source.socials);
  if (source?.details && typeof source.details === 'object') bags.push(source.details);
  const pick = (...keys) => {
    for (const bag of bags) {
      for (const key of keys) {
        const value = bag[key];
        if (typeof value === 'string' && value.trim()) return value.trim();
      }
    }
    return null;
  };
  return {
    facebook: pick('facebook'),
    instagram: pick('instagram'),
    linkedIn: pick('linkedIn', 'linkedin'),
    twitter: pick('twitter'),
    youtube: pick('youtube'),
  };
}

export const onRequest = defineMiddleware(async (context, next) => {
  if (context.url.pathname.startsWith('/api/')) {
    return next();
  }

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

  const companyIdentity = selectedCompany
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
  context.locals.company = {
    ...companyIdentity,
    ...socialAccounts(selectedCompany ?? settings?.company),
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
    forms: await loadForms(activeSubdomain),
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

  context.locals.getForm = async (form) => {
    const raw = activeSubdomain
      ? await harnessApi(
          `/forms/${encodeURIComponent(activeSubdomain)}/${encodeURIComponent(String(form))}`,
        )
      : null;
    if (raw?.uuid && Array.isArray(raw.grids)) return toCaraerForm(raw);
    if (raw?.uuid && Array.isArray(raw.steps)) return raw;
    return SAMPLE_FORM(form);
  };

  context.locals.listRecords = async (query) =>
    (await live(
      '/records',
      { method: 'POST', body: JSON.stringify({ limit: 6, ...query }) },
      activeSubdomain,
    )) ?? sampleRecords(query.object, query.limit ?? 6);

  if (context.url.pathname === '/caraer/records' && context.request.method === 'POST') {
    let body = {};
    try {
      body = await context.request.json();
    } catch {
      return Response.json({ total: 0, records: [] }, { status: 400 });
    }
    const result =
      (await live(
        '/records',
        { method: 'POST', body: JSON.stringify(body) },
        activeSubdomain,
      )) ?? sampleRecords(body.object, Number(body.limit) || 6);
    return Response.json(result ?? { total: 0, records: [] }, {
      headers: { 'Cache-Control': 'no-store' },
    });
  }

  return next();
});
"""


def _harness_upload_api() -> str:
    """Accepts local FILE / MULTI_FILE uploads and stores them under public/."""
    return """// GENERATED by `caraer apps local dev --cms` - do not edit.
import type { APIRoute } from 'astro';
import { randomBytes } from 'node:crypto';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

const MAX_BYTES = 20 * 1024 * 1024;
const UPLOAD_DIR = path.join(process.cwd(), 'public', 'uploads');

function safeName(name: string): string {
  const base = path
    .basename(name)
    .replace(/[^a-zA-Z0-9._-]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return base.slice(0, 80) || 'file';
}

function allowed(file: File): boolean {
  if (!file.type) {
    return /\\.(avif|gif|jpe?g|png|svg|webp|mp4|webm|ogg|mov)$/i.test(file.name);
  }
  return /^(image|video)\\//.test(file.type);
}

export const POST: APIRoute = async ({ request }) => {
  const form = await request.formData();
  const incoming = form.getAll('file').filter((item): item is File => item instanceof File);
  if (incoming.length === 0) {
    return Response.json({ error: 'No file' }, { status: 400 });
  }

  await mkdir(UPLOAD_DIR, { recursive: true });
  const urls: string[] = [];

  for (const file of incoming) {
    if (file.size > MAX_BYTES) {
      return Response.json({ error: 'File is too large' }, { status: 413 });
    }
    if (!allowed(file)) {
      return Response.json({ error: 'Only images and videos can be uploaded' }, { status: 415 });
    }
    const name = `${randomBytes(6).toString('hex')}-${safeName(file.name)}`;
    await writeFile(path.join(UPLOAD_DIR, name), Buffer.from(await file.arrayBuffer()));
    urls.push(`/uploads/${name}`);
  }

  return Response.json({ urls });
};
"""


def _harness_records_api() -> str:
    """Proxies preview search to the public records API for the local harness."""
    return r"""// GENERATED by `caraer apps local dev` - do not edit.
import type { APIRoute } from 'astro';

export const prerender = false;

const SUBDOMAIN = process.env.CARAER_SUBDOMAIN;
const API_BASE = (process.env.CARAER_API_BASE_URL || '').replace(/\/$/, '');

export const POST: APIRoute = async ({ request }) => {
  if (!SUBDOMAIN || !API_BASE) {
    return Response.json({ total: 0, records: [] });
  }

  let payload: Record<string, unknown> = {};
  try {
    const parsed = await request.json();
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      payload = parsed as Record<string, unknown>;
    }
  } catch {
    return Response.json({ total: 0, records: [] }, { status: 400 });
  }

  const environment = typeof payload.environment === 'string' ? payload.environment.trim() : '';
  try {
    const response = await fetch(`${API_BASE}/api/v2/webpages/v2/public/records`, {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'X-Caraer-Subdomain': SUBDOMAIN,
        ...(environment ? { 'X-Caraer-Environment': environment } : {}),
      },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      return Response.json({ total: 0, records: [] }, { status: 502 });
    }
    const data = await response.json();
    return Response.json(data?.data ?? data, {
      headers: { 'Cache-Control': 'no-store' },
    });
  } catch {
    return Response.json({ total: 0, records: [] }, { status: 502 });
  }
};
"""


def _harness_file_field_markup() -> str:
    """Sidebar control for FILE / MULTI_FILE: upload instead of pasting a URL."""
    return """              ) : field.type === 'FILE' || field.type === 'MULTI_FILE' || field.type === 'IMAGE' ? (
                <div
                  class="hx-file"
                  data-multiple={field.type === 'MULTI_FILE' ? '' : undefined}
                >
                  <input
                    type="hidden"
                    id={`f-${field.name}`}
                    name={`f.${field.name}`}
                    value={field.type === 'MULTI_FILE'
                      ? (Array.isArray(stored[field.name]) ? (stored[field.name] as string[]).join('\\n') : String(stored[field.name] ?? ''))
                      : String(stored[field.name] ?? '')}
                  />
                  <div class="hx-file__list"></div>
                  <button type="button" class="hx-file__pick">
                    {field.type === 'MULTI_FILE' ? 'Add files' : field.type === 'IMAGE' ? 'Upload image' : 'Upload file'}
                  </button>
                  <input
                    type="file"
                    accept={field.type === 'IMAGE' ? 'image/*' : 'image/*,video/*'}
                    multiple={field.type === 'MULTI_FILE'}
                    hidden
                  />
                </div>
              ) : field.type === 'COLOR' ? (
                <div class="hx-color">
                  <input
                    type="color"
                    value={String(stored[field.name] || '#1a73e8').startsWith('#') ? String(stored[field.name] || '#1a73e8') : '#1a73e8'}
                    onInput={(event) => {
                      const text = event.currentTarget.parentElement?.querySelector('input[type="text"]');
                      if (text) text.value = event.currentTarget.value;
                    }}
                  />
                  <input
                    id={`f-${field.name}`}
                    type="text"
                    name={`f.${field.name}`}
                    value={String(stored[field.name] ?? '')}
                    placeholder="#RRGGBB or var(--caraer-color-primary)"
                  />
                </div>
              ) : field.type === 'REPEATABLE' ? (
                <div
                  class="hx-repeat"
                  data-min={String(field.min ?? 0)}
                  data-max={String(field.max ?? 20)}
                  data-item-label={field.itemLabel || 'Item'}
                  data-item-fields={JSON.stringify(field.itemFields ?? [])}
                >
                  <input
                    type="hidden"
                    id={`f-${field.name}`}
                    name={`f.${field.name}`}
                    value={JSON.stringify(Array.isArray(stored[field.name]) ? stored[field.name] : [])}
                  />
                  <div class="hx-repeat__bar">
                    <button type="button" class="hx-repeat__prev" aria-label="Previous item">‹</button>
                    <span class="hx-repeat__status"></span>
                    <button type="button" class="hx-repeat__next" aria-label="Next item">›</button>
                  </div>
                  <div class="hx-repeat__body"></div>
                  <div class="hx-repeat__actions">
                    <button type="button" class="hx-repeat__add">Add</button>
                    <button type="button" class="hx-repeat__remove">Remove</button>
                  </div>
                </div>
"""


def _harness_field_rows(fields_expr: str) -> str:
    """One sidebar field list. Used for both normal and advanced fields."""
    return f"""          {{{fields_expr}.map((field) => (
            <div
              class="hx-field"
              data-type={{field.type}}
              data-visible-when={{JSON.stringify(field.visibleWhen ?? [])}}
              hidden={{!isFieldVisible(field, stored)}}
            >
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
{_harness_file_field_markup()}              ) : field.type === 'FORM_SINGLE_SELECT' ? (
                <select id={{`f-${{field.name}}`}} name={{`f.${{field.name}}`}}>
                  <option value="">Select a form</option>
                  {{forms.map((form) => (
                    <option
                      value={{form.uuid}}
                      selected={{stored[field.name] === form.uuid || stored[field.name] === form.name}}
                    >{{form.label || form.name || form.uuid}}</option>
                  ))}}
                  {{stored[field.name] && !forms.some((form) => form.uuid === stored[field.name] || form.name === stored[field.name]) && (
                    <option value={{stored[field.name]}} selected>{{String(stored[field.name])}}</option>
                  )}}
                </select>
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
"""


def _harness_file_field_script() -> str:
    """Uploads picked files to /api/upload and writes the returned URLs."""
    return """
    <script is:inline>
      // FILE / MULTI_FILE: pick from disk, store a local URL. Query strings
      // cannot carry the bytes, so the file is posted first and the returned
      // /uploads/... path is what the module receives.
      const fileUrls = (value) =>
        String(value || '')
          .split(/[\\n,]+/)
          .map((part) => part.trim())
          .filter(Boolean);

      const fileKind = (url) => {
        if (/\\.(avif|gif|jpe?g|png|svg|webp)(\\?|#|$)/i.test(url) || url.startsWith('data:image/')) {
          return 'image';
        }
        if (/\\.(mp4|webm|ogg|mov)(\\?|#|$)/i.test(url) || url.startsWith('data:video/')) {
          return 'video';
        }
        return 'file';
      };

      const fileLabel = (url) => {
        try {
          return decodeURIComponent((url.split('/').pop() || url).replace(/^[a-f0-9]{12}-/, ''));
        } catch {
          return url;
        }
      };

      const uploadFiles = async (files) => {
        const urls = [];
        for (const file of files) {
          const body = new FormData();
          body.append('file', file);
          const response = await fetch('/api/upload', { method: 'POST', body });
          if (!response.ok) {
            throw new Error(await response.text());
          }
          const payload = await response.json();
          urls.push(...(payload.urls || []));
        }
        return urls;
      };

      const renderFileField = (root) => {
        const hidden = root.querySelector('input[type="hidden"]');
        const list = root.querySelector('.hx-file__list');
        const pick = root.querySelector('.hx-file__pick');
        const multiple = root.hasAttribute('data-multiple');
        const urls = fileUrls(hidden?.value);
        list.replaceChildren(
          ...urls.map((url, index) => {
            const item = document.createElement('div');
            item.className = 'hx-file__item';
            if (fileKind(url) === 'image') {
              const img = document.createElement('img');
              img.src = url;
              img.alt = '';
              item.append(img);
            } else {
              const mark = document.createElement('span');
              mark.className = 'hx-file__name';
              mark.textContent = fileLabel(url);
              item.append(mark);
            }
            const remove = document.createElement('button');
            remove.type = 'button';
            remove.className = 'hx-file__remove';
            remove.setAttribute('aria-label', 'Remove file');
            remove.textContent = '×';
            remove.addEventListener('click', () => {
              hidden.value = urls.filter((_, i) => i !== index).join('\\n');
              hidden.dispatchEvent(new Event('input', { bubbles: true }));
              renderFileField(root);
            });
            item.append(remove);
            return item;
          }),
        );
        if (pick) {
          pick.textContent = multiple
            ? 'Add files'
            : urls.length
              ? 'Replace file'
              : 'Upload file';
        }
      };

      const addFilesToField = async (root, files) => {
        const hidden = root.querySelector('input[type="hidden"]');
        if (!hidden || files.length === 0) return;
        root.dataset.busy = '';
        try {
          const uploaded = await uploadFiles(files);
          hidden.value = root.hasAttribute('data-multiple')
            ? [...fileUrls(hidden.value), ...uploaded].join('\\n')
            : uploaded[0] ?? '';
          hidden.dispatchEvent(new Event('input', { bubbles: true }));
          renderFileField(root);
        } catch (error) {
          console.error(error);
        } finally {
          delete root.dataset.busy;
        }
      };

      document.querySelectorAll('.hx-file').forEach((root) => {
        const picker = root.querySelector('input[type="file"]');
        const pick = root.querySelector('.hx-file__pick');
        renderFileField(root);
        pick?.addEventListener('click', () => picker?.click());
        picker?.addEventListener('change', () => {
          const files = Array.from(picker.files || []);
          picker.value = '';
          addFilesToField(root, files);
        });
        root.addEventListener('dragover', (event) => {
          event.preventDefault();
          root.dataset.drop = '';
        });
        root.addEventListener('dragleave', () => delete root.dataset.drop);
        root.addEventListener('drop', (event) => {
          event.preventDefault();
          delete root.dataset.drop;
          addFilesToField(root, Array.from(event.dataTransfer?.files || []));
        });
      });
    </script>
"""


def _harness_repeatable_script() -> str:
    """Pages through REPEATABLE items so the sidebar does not grow a long list."""
    return r"""
    <script is:inline>
      const emptyRepeatItem = (fields) => {
        const row = {};
        for (const field of fields) {
          if (field.defaultValue !== undefined && field.defaultValue !== null) {
            row[field.name] = field.defaultValue;
            continue;
          }
          if (field.type === 'SWITCH') row[field.name] = false;
          else if (field.type === 'MULTI_FILE' || field.type === 'MULTI_SELECT') row[field.name] = [];
          else row[field.name] = '';
        }
        return row;
      };

      const readRepeatItems = (input) => {
        try {
          const parsed = JSON.parse(input.value || '[]');
          return Array.isArray(parsed) ? parsed : [];
        } catch {
          return [];
        }
      };

      const bindRepeatable = (root) => {
        const input = root.querySelector('input[type="hidden"]');
        const body = root.querySelector('.hx-repeat__body');
        const status = root.querySelector('.hx-repeat__status');
        const prev = root.querySelector('.hx-repeat__prev');
        const next = root.querySelector('.hx-repeat__next');
        const add = root.querySelector('.hx-repeat__add');
        const remove = root.querySelector('.hx-repeat__remove');
        if (!(input instanceof HTMLInputElement) || !body || !status) return;

        const min = Math.max(0, Number(root.dataset.min || '0') || 0);
        const max = Math.max(min || 1, Number(root.dataset.max || '20') || 20);
        const itemLabel = root.dataset.itemLabel || 'Item';
        let fields = [];
        try {
          fields = JSON.parse(root.dataset.itemFields || '[]');
        } catch {
          fields = [];
        }
        if (!Array.isArray(fields)) fields = [];

        let items = readRepeatItems(input);
        if (items.length < min) {
          while (items.length < min) items.push(emptyRepeatItem(fields));
        }
        let index = 0;
        const visibilityKeys = [...new Set(
          fields.flatMap((field) => (Array.isArray(field.visibleWhen) ? field.visibleWhen : [])
            .map((rule) => rule && rule.field)
            .filter(Boolean)),
        )];

        const readParentValues = () => {
          const values = {};
          const form = root.closest('form');
          if (!(form instanceof HTMLFormElement)) return values;
          new FormData(form).forEach((value, key) => {
            if (key.startsWith('f.')) values[key.slice(2)] = String(value);
          });
          return values;
        };

        const itemConditionHolds = (condition, values) => {
          const actual = values[condition.field];
          const set = actual !== undefined && actual !== null && actual !== '';
          switch (condition.operator) {
            case 'IS_SET':
              return set;
            case 'IS_NOT_SET':
              return !set;
            case 'EQUALS':
              return actual === condition.value;
            case 'NOT_EQUALS':
              return actual !== condition.value;
            case 'IN':
              return Array.isArray(condition.value) && condition.value.includes(actual);
            case 'NOT_IN':
              return !(Array.isArray(condition.value) && condition.value.includes(actual));
            default:
              return true;
          }
        };

        const visibilitySnapshot = () => {
          const values = readParentValues();
          return JSON.stringify(Object.fromEntries(visibilityKeys.map((key) => [key, values[key]])));
        };

        const commit = () => {
          input.value = JSON.stringify(items);
          input.dispatchEvent(new Event('input', { bubbles: true }));
        };

        const fieldControl = (field, value, onValue) => {
          const wrap = document.createElement('label');
          wrap.className = 'hx-repeat__field';
          const caption = document.createElement('span');
          caption.textContent = field.label || field.name;
          wrap.append(caption);

          if (field.type === 'MULTI_LINE') {
            const box = document.createElement('textarea');
            box.rows = 4;
            box.value = String(value ?? '');
            box.addEventListener('input', () => onValue(box.value));
            wrap.append(box);
            return wrap;
          }
          if (field.type === 'SWITCH') {
            const box = document.createElement('input');
            box.type = 'checkbox';
            box.checked = value === true || value === 'true';
            box.addEventListener('change', () => onValue(box.checked));
            wrap.append(box);
            return wrap;
          }
          if (field.type === 'SINGLE_SELECT' && Array.isArray(field.options)) {
            const select = document.createElement('select');
            for (const option of field.options) {
              const node = document.createElement('option');
              node.value = option.name;
              node.textContent = option.label || option.name;
              if (String(value ?? '') === String(option.name)) node.selected = true;
              select.append(node);
            }
            select.addEventListener('change', () => onValue(select.value));
            wrap.append(select);
            return wrap;
          }
          if (field.type === 'COLOR') {
            const swatch = document.createElement('input');
            swatch.type = 'color';
            swatch.value = String(value || '#1a73e8').startsWith('#') ? String(value || '#1a73e8') : '#1a73e8';
            const text = document.createElement('input');
            text.type = 'text';
            text.value = String(value ?? '');
            text.placeholder = '#RRGGBB or var(--caraer-color-primary)';
            swatch.addEventListener('input', () => {
              text.value = swatch.value;
              onValue(swatch.value);
            });
            text.addEventListener('input', () => onValue(text.value));
            wrap.append(swatch, text);
            return wrap;
          }
          if (field.type === 'FILE' || field.type === 'MULTI_FILE' || field.type === 'IMAGE') {
            const pick = document.createElement('button');
            pick.type = 'button';
            pick.className = 'hx-file__pick';
            pick.textContent = field.type === 'MULTI_FILE' ? 'Add files' : (value ? 'Replace' : field.type === 'IMAGE' ? 'Upload image' : 'Upload file');
            const hint = document.createElement('small');
            hint.className = 'hx-help';
            hint.textContent = typeof value === 'string' && value ? value : (Array.isArray(value) ? value.join(', ') : '');
            pick.addEventListener('click', async () => {
              const picker = document.createElement('input');
              picker.type = 'file';
              picker.accept = field.type === 'IMAGE' ? 'image/*' : 'image/*,video/*';
              picker.multiple = field.type === 'MULTI_FILE';
              picker.addEventListener('change', async () => {
                const files = Array.from(picker.files || []);
                if (!files.length || typeof uploadFiles !== 'function') return;
                const urls = await uploadFiles(files);
                if (field.type === 'MULTI_FILE') {
                  const next = Array.isArray(value) ? [...value, ...urls] : urls;
                  onValue(next);
                } else {
                  onValue(urls[0] || '');
                }
              });
              picker.click();
            });
            wrap.append(pick, hint);
            return wrap;
          }

          const box = document.createElement('input');
          box.type = 'text';
          box.value = String(value ?? '');
          box.addEventListener('input', () => onValue(box.value));
          wrap.append(box);
          return wrap;
        };

        const paint = () => {
          if (items.length === 0) {
            status.textContent = `No ${itemLabel.toLowerCase()}s`;
            body.replaceChildren();
            prev.disabled = true;
            next.disabled = true;
            add.disabled = items.length >= max;
            remove.disabled = true;
            const empty = document.createElement('p');
            empty.className = 'hx-empty';
            empty.textContent = `Add a ${itemLabel.toLowerCase()} to start.`;
            body.append(empty);
            return;
          }
          index = Math.min(Math.max(0, index), items.length - 1);
          status.textContent = `${itemLabel} ${index + 1} of ${items.length}`;
          prev.disabled = index <= 0;
          next.disabled = index >= items.length - 1;
          add.disabled = items.length >= max;
          add.textContent = `Add ${itemLabel.toLowerCase()}`;
          remove.disabled = items.length <= min;
          const current = items[index] && typeof items[index] === 'object' ? items[index] : {};
          const context = { ...readParentValues(), ...current };
          body.replaceChildren();
          for (const field of fields) {
            const rules = Array.isArray(field.visibleWhen) ? field.visibleWhen : [];
            if (rules.length && !rules.every((rule) => itemConditionHolds(rule, context))) {
              continue;
            }
            body.append(
              fieldControl(field, current[field.name], (nextValue) => {
                items[index] = { ...items[index], [field.name]: nextValue };
                commit();
              }),
            );
          }
        };

        prev.addEventListener('click', () => {
          index -= 1;
          paint();
        });
        next.addEventListener('click', () => {
          index += 1;
          paint();
        });
        add.addEventListener('click', () => {
          if (items.length >= max) return;
          items.push(emptyRepeatItem(fields));
          index = items.length - 1;
          commit();
          paint();
        });
        remove.addEventListener('click', () => {
          if (items.length <= min) return;
          items.splice(index, 1);
          index = Math.max(0, index - 1);
          commit();
          paint();
        });

        commit();
        paint();

        const form = root.closest('form');
        if (form instanceof HTMLFormElement && visibilityKeys.length) {
          let lastVisibility = visibilitySnapshot();
          const refreshIfParentChanged = () => {
            const next = visibilitySnapshot();
            if (next === lastVisibility) return;
            lastVisibility = next;
            paint();
          };
          form.addEventListener('change', refreshIfParentChanged);
          form.addEventListener('input', refreshIfParentChanged);
        }
      };

      document.querySelectorAll('.hx-repeat').forEach(bindRepeatable);
    </script>
"""


def _harness_file_field_styles() -> str:
    return """
      .hx-file { display: grid; gap: 0.4rem; }
      .hx-color { display: flex; align-items: center; gap: 0.5rem; }
      .hx-color input[type="color"] { width: 2.5rem; height: 2rem; padding: 0; border: 1px solid var(--border); background: transparent; }
      .hx-file[data-drop] { outline: 1px dashed var(--hx-accent); outline-offset: 2px; }
      .hx-file[data-busy] .hx-file__pick { opacity: 0.6; pointer-events: none; }
      .hx-file__list { display: flex; flex-wrap: wrap; gap: 0.4rem; }
      .hx-file__list:empty { display: none; }
      .hx-file__item {
        position: relative;
        width: 72px; height: 72px;
        border-radius: 8px; overflow: hidden;
        background: var(--hx-panel-2);
        border: 1px solid var(--hx-line);
      }
      .hx-file__item img {
        display: block; width: 100%; height: 100%; object-fit: cover;
      }
      .hx-file__name {
        display: grid; place-items: center;
        width: 100%; height: 100%;
        padding: 0.35rem;
        font-size: 0.5625rem; color: var(--hx-muted);
        text-align: center; overflow: hidden; word-break: break-all;
      }
      .hx-file__remove {
        position: absolute; top: 2px; right: 2px;
        width: 18px; height: 18px;
        border: 0; border-radius: 50%;
        background: rgba(15, 17, 21, 0.75); color: #fff;
        font: inherit; font-size: 0.75rem; line-height: 1;
        cursor: pointer;
      }
      .hx-file__pick {
        width: 100%;
        padding: 0.45rem 0.55rem;
        border: 1px dashed var(--hx-line); border-radius: 7px;
        background: var(--hx-panel-2); color: var(--hx-muted);
        font: inherit; font-size: 0.75rem;
        cursor: pointer;
      }
      .hx-file__pick:hover { color: var(--hx-text); border-color: var(--hx-accent); }

      .hx-repeat { display: grid; gap: 0.65rem; }
      .hx-repeat__bar {
        display: flex; align-items: center; gap: 0.4rem;
      }
      .hx-repeat__status {
        flex: 1; text-align: center;
        font-size: 0.75rem; color: var(--hx-muted);
      }
      .hx-repeat__prev, .hx-repeat__next, .hx-repeat__add, .hx-repeat__remove {
        border: 1px solid var(--hx-line); border-radius: 7px;
        background: var(--hx-panel-2); color: var(--hx-text);
        font: inherit; font-size: 0.75rem;
        padding: 0.3rem 0.55rem; cursor: pointer;
      }
      .hx-repeat__prev:disabled, .hx-repeat__next:disabled,
      .hx-repeat__add:disabled, .hx-repeat__remove:disabled {
        opacity: 0.4; cursor: default;
      }
      .hx-repeat__body { display: grid; gap: 0.65rem; }
      .hx-repeat__field { display: grid; gap: 0.3rem; font-size: 0.75rem; }
      .hx-repeat__field span { color: var(--hx-muted); }
      .hx-repeat__actions { display: flex; gap: 0.4rem; }
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
        f"  {json.dumps(m.name)}: () => import({json.dumps(f'@modules/{m.name}/{m.entry.name}')})"
        for m in modules
    )

    return f"""---
// GENERATED by `caraer apps local dev --cms` - do not edit.
import {{ DEFAULT_TOKENS, toCustomProperties, toStyleAttribute }} from '@caraer/cms-tokens';
import {{ toResponsiveTypeCss }} from '../responsive-type.ts';
import {{ isFieldVisible, resolveFieldValues, flattenModuleFields, isModuleFieldGroup, renderModuleErrorHtml, withModuleBoundary }} from '@caraer/cms-runtime';

import samples from '../../samples.json';

const modules = {json.dumps(catalog, ensure_ascii=False, indent=2)};

const loaders = {{
{loaders}
}};

const active = Astro.url.searchParams.get('module') ?? modules[0]?.name;
const selected = modules.find((m) => m.name === active) ?? modules[0];
const manifestFields = selected?.fields ?? [];
const declaredFields = flattenModuleFields(manifestFields);
const ungroupedFields = [];
const fieldGroups = [];
const advancedFields = [];
for (const item of manifestFields) {{
  if (isModuleFieldGroup(item)) {{
    fieldGroups.push({{ name: item.group, fields: item.fields }});
    continue;
  }}
  if (item.advanced === true) advancedFields.push(item);
  else ungroupedFields.push(item);
}}

/*
 * Query strings carry everything as text, but a field's declared type is what
 * the runtime works with. Without coercion a SWITCH arrives as the string
 * "true", and a `visibleWhen: EQUALS true` on a sibling field compares string
 * to boolean and silently hides it.
 */
function coerce(name: string, raw: string): unknown {{
  if (raw === '') return null;

  const type = declaredFields.find((f) => f.name === name)?.type;
  switch (type) {{
    case 'SWITCH':
      return raw === 'true';
    case 'MULTI_SELECT':
    case 'MULTI_FILE':
    case 'PROPERTY_MULTI_SELECT':
    case 'RECORD_MULTI_SELECT':
    case 'OBJECT_MULTI_SELECT':
      return raw.split(/[\\n,]+/).map((part) => part.trim()).filter(Boolean);
    case 'REPEATABLE':
      try {{
        const parsed = JSON.parse(raw);
        return Array.isArray(parsed) ? parsed : [];
      }} catch {{
        return [];
      }}
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
const responsiveTypeCss = toResponsiveTypeCss(Astro.locals.tokens ?? DEFAULT_TOKENS);
const responsiveTypeStyle = responsiveTypeCss ? `<style>${{responsiveTypeCss}}</style>` : "";
const live = Astro.locals.harness?.live ?? false;
const subdomain = Astro.locals.harness?.subdomain ?? '';
const companies = Astro.locals.harness?.companies ?? [];
const forms = Astro.locals.harness?.forms ?? [];

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
    <Fragment set:html={{responsiveTypeStyle}} />
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
{_harness_field_rows("ungroupedFields")}
          {{fieldGroups.map((group) => (
            <details class="hx-advanced hx-group">
              <summary>{{group.name}}</summary>
{_harness_field_rows("group.fields")}
            </details>
          ))}}
          {{advancedFields.length > 0 && (
            <details class="hx-advanced">
              <summary>Advanced settings</summary>
{_harness_field_rows("advancedFields")}
            </details>
          )}}

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

        const focusSidebarField = (name, item) => {{
          if (!name) return;
          const id = item == null || item === '' ? `f-${{name}}` : `f-${{name}}-${{item}}`;
          const input = form.querySelector(`#${{CSS.escape(id)}}`)
            || form.querySelector(`[name="f.${{name}}"]`);
          if (!(input instanceof HTMLElement)) return;
          const details = input.closest('details');
          if (details) details.open = true;
          form.querySelectorAll('.hx-field.is-focused').forEach((el) => {{
            el.classList.remove('is-focused');
          }});
          input.closest('.hx-field')?.classList.add('is-focused');
          input.focus({{ preventScroll: true }});
          input.closest('.hx-field')?.scrollIntoView({{ block: 'nearest', behavior: 'smooth' }});
        }};

        const bindPreviewClicks = () => {{
          const doc = preview.contentDocument;
          if (!doc || doc.documentElement.dataset.caraerFieldClicks === '1') return;
          doc.documentElement.dataset.caraerFieldClicks = '1';
          doc.addEventListener('click', (event) => {{
            const node = event.target instanceof Element ? event.target : null;
            const field = node?.closest('[data-caraer-field]');
            if (!field) return;
            event.preventDefault();
            focusSidebarField(
              field.getAttribute('data-caraer-field'),
              field.closest('[data-caraer-item]')?.getAttribute('data-caraer-item'),
            );
          }});
        }};
        preview.addEventListener('load', bindPreviewClicks);
        if (preview.contentDocument?.readyState === 'complete') bindPreviewClicks();
      }}
    </script>

    <script is:inline>
      // Honour visibleWhen the same way the builder does, so a count of 5
      // only offers five item slots and a colour field hides when unused.
      const fieldsForm = document.querySelector('.harness__fields');

      const fieldValues = (form) => {{
        const values = {{}};
        new FormData(form).forEach((value, key) => {{
          if (key.startsWith('f.')) values[key.slice(2)] = String(value);
        }});
        form.querySelectorAll('input[type="checkbox"]').forEach((box) => {{
          if (box.name.startsWith('f.')) {{
            values[box.name.slice(2)] = box.checked ? 'true' : 'false';
          }}
        }});
        return values;
      }};

      const conditionHolds = (condition, values) => {{
        const actual = values[condition.field];
        const set = actual !== undefined && actual !== null && actual !== '';
        switch (condition.operator) {{
          case 'IS_SET':
            return set;
          case 'IS_NOT_SET':
            return !set;
          case 'EQUALS':
            return actual === condition.value;
          case 'NOT_EQUALS':
            return actual !== condition.value;
          case 'IN':
            return Array.isArray(condition.value) && condition.value.includes(actual);
          case 'NOT_IN':
            return !(Array.isArray(condition.value) && condition.value.includes(actual));
          default:
            return true;
        }}
      }};

      const applyFieldVisibility = (form) => {{
        const values = fieldValues(form);
        form.querySelectorAll('.hx-field').forEach((row) => {{
          let rules = [];
          try {{
            rules = JSON.parse(row.dataset.visibleWhen || '[]');
          }} catch {{
            rules = [];
          }}
          row.hidden = !(Array.isArray(rules) && rules.every((rule) => conditionHolds(rule, values)));
        }});
        form.querySelectorAll('.hx-advanced, .hx-group').forEach((section) => {{
          section.hidden = ![...section.querySelectorAll('.hx-field')].some((row) => !row.hidden);
        }});
      }};

      if (fieldsForm instanceof HTMLFormElement) {{
        applyFieldVisibility(fieldsForm);
        fieldsForm.addEventListener('input', () => applyFieldVisibility(fieldsForm));
        fieldsForm.addEventListener('change', () => applyFieldVisibility(fieldsForm));
      }}
    </script>
{_harness_file_field_script()}
{_harness_repeatable_script()}

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
      body.is-embed [data-caraer-field] {{
        cursor: pointer;
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
      .hx-field.is-focused {{
        outline: 2px solid var(--hx-accent);
        outline-offset: 4px;
        border-radius: 4px;
      }}
      .hx-field[hidden] {{ display: none; }}
      .hx-advanced {{
        display: grid; gap: 0.875rem;
        border-top: 1px solid var(--hx-line);
        padding-top: 0.25rem;
      }}
      .hx-advanced[hidden] {{ display: none; }}
      .hx-advanced summary {{
        cursor: pointer;
        font-size: 0.75rem; font-weight: 600;
        color: var(--hx-text);
        list-style: none;
        display: flex; align-items: center; justify-content: space-between;
      }}
      .hx-advanced summary::-webkit-details-marker {{ display: none; }}
      .hx-advanced summary::after {{
        content: '▸';
        font-size: 0.7rem; color: var(--hx-muted);
      }}
      .hx-advanced[open] summary::after {{ content: '▾'; }}
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

{_harness_file_field_styles()}
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
    (harness / "src" / "pages" / "api").mkdir(parents=True, exist_ok=True)
    (harness / "public" / "uploads").mkdir(parents=True, exist_ok=True)
    (harness / "src" / "pages" / "api" / "upload.ts").write_text(_harness_upload_api(), encoding="utf-8")
    (harness / "src" / "pages" / "caraer").mkdir(parents=True, exist_ok=True)
    (harness / "src" / "pages" / "caraer" / "records.ts").write_text(_harness_records_api(), encoding="utf-8")
    (harness / "src" / "middleware.ts").write_text(_harness_middleware(), encoding="utf-8")
    samples_path = harness / "samples.json"
    existing_samples: dict[str, Any] = {}
    if samples_path.is_file():
        try:
            loaded = json.loads(samples_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing_samples = loaded
        except json.JSONDecodeError:
            existing_samples = {}
    samples = {}
    for module in modules:
        generated = sample_fields(module)
        stored = existing_samples.get(module.name)
        samples[module.name] = (
            {**generated, **stored} if isinstance(stored, dict) else generated
        )
    samples_path.write_text(json.dumps(samples, indent=2) + "\n", encoding="utf-8")
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


def _harness_package_resolves(harness: Path, *parts: str) -> bool:
    """True when the installed package is a real directory, not a broken link."""
    dest = harness / "node_modules"
    for part in parts:
        dest = dest / part
    return dest.is_dir()


def _harness_ready(harness: Path) -> bool:
    # ``@astrojs/node`` is the previous gate. After cms-runtime / cms-tokens
    # moved out of caraer-web, that left a working Astro install pointing at
    # broken ``@caraer/*`` links and Vite then cannot resolve the tokens.
    return (
        _harness_package_resolves(harness, "@astrojs", "node")
        and _harness_package_resolves(harness, "@caraer", "cms-runtime")
        and _harness_package_resolves(harness, "@caraer", "cms-tokens")
    )


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
