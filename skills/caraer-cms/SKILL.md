---
name: caraer-cms
description: >-
  Builds and edits Caraer CMS v2 modules and page field values. Use when the
  company is on cmsVersion 2, or when creating Astro modules, module.caraer.json
  fields, local CMS preview, or caraer-core page modules. Do not use for CMS v1
  PageContent trees.
---

# Caraer CMS v2

Install like `caraer-apps`:

```bash
caraer skill install              # ~/.cursor/skills/caraer-apps and caraer-cms
caraer skill install --project    # ./.cursor/skills/...
```

Source of truth: [`skills/caraer-cms`](https://github.com/Caraer-HQ/caraer-cli)
in the caraer-cli repo. The module contract lives in the **vendored**
`@caraer/cms-runtime` package (`caraer-web/packages/cms-runtime`), not the
standalone `caraer-cms-runtime` repo until that repo catches up.

## Guard: v1 vs v2

1. Read the company's `cmsVersion` (company record / MCP / staff tools).
2. **`cmsVersion` is 1 or missing** → stop. Use the `caraer-webpages` skill and
   `webpage_*` MCP tools. Do **not** invent `cms_v2_*` / `cms.v2_*` MCP tools;
   they do not exist.
3. **`cmsVersion` is 2** → this skill. Edit **page field values**, never the
   shared module source of an installed marketplace app unless the user asked
   to change that app.

v1 companies stay on WerkenBij. Never point a v2 preview at a live
`{subdomain}.caraer.com` host while `cmsVersion` is 1.

## Module path (new or existing app)

```bash
caraer apps add module hero
# edit src/app/modules/<name>/index.astro — literal `export const manifest`
caraer apps validate
caraer apps local          # sidebar + iframe preview
caraer apps push --deploy  # only when the user asks
```

The manifest must be a **literal**. The CLI reads it without running the file.
Use `satisfies ModuleManifest` from `@caraer/cms-runtime`.

```astro
---
import type { ModuleManifest, ModuleProps } from '@caraer/cms-runtime';
import type { HeroFields } from './fields.d.ts';

export const manifest = {
  name: 'hero',
  label: 'Hero',
  kind: 'section',
  category: 'hero',
  fields: [
    { name: 'heading', label: 'Heading', type: 'SINGLE_LINE', required: true },
    { name: 'image', label: 'Image', type: 'IMAGE' },
    { name: 'tint', label: 'Tint', type: 'COLOR', advanced: true },
  ],
} satisfies ModuleManifest;

const { fields } = Astro.props as ModuleProps<HeroFields>;
---

<section>
  <h1 data-caraer-field="heading">{fields.heading}</h1>
</section>
```

`fields.d.ts` is generated. Do not edit it by hand.

## Field rules

Allowed: `SINGLE_LINE`, `MULTI_LINE`, `SINGLE_SELECT`, `MULTI_SELECT`,
`RECORD_*`, `FORM_SINGLE_SELECT`, `OBJECT_*`, `PROPERTY_*`, `SWITCH`,
`MAPPING`, `FILE`, `MULTI_FILE`, `IMAGE`, `COLOR`, `REPEATABLE`.

Rejected: `SECRET`, `ACTION`, serverless `optionsSource`, nested `REPEATABLE`.

| Flag / type | Meaning |
| --- | --- |
| `advanced: true` | Collapsed under **Advanced settings** |
| `FORM_SINGLE_SELECT` | Picks one Form record |
| `REPEATABLE` | List of objects. Set `itemFields`, optional `min` / `max` / `itemLabel` |
| `IMAGE` | Image-only upload + thumbnail. Keep `FILE` for generic files |
| `COLOR` | Hex, `rgba(...)`, or `var(--caraer-color-*)` |
| `data-caraer-field` | Click-in-preview opens this sidebar field |
| `data-caraer-item` | REPEATABLE row index for that click |

AI edits **page instance field values**. Do not rewrite shared `caraer-core`
module source unless the user is changing the marketplace app itself.

## Tokens and preview

Use `--caraer-*` tokens, not hard-coded brand colours. Local preview:
`caraer apps local`. Validate before push.

See [reference.md](reference.md) for kinds, categories, and isolation.
