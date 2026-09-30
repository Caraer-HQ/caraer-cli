# CMS modules

A module is an Astro component the website builder can place on a page. It
does not run in the app container. `caraer apps push` publishes it to the
Caraer npm registry, and each installing company's site build compiles it in.

Modules are for companies on CMS v2. A company still on CMS v1 keeps the older
page editor. On a CMS v2 company the app page in Caraer also has a **Modules**
tab (private and public apps). It lists every module the app publishes,
including retired ones: label, kind, category, and `ref · version`. The
company library picker still hides retired modules.

## Add one

```bash
caraer apps add module hero --kind section
caraer apps add module site-header --kind header
```

Kinds: `section`, `page`, `header`, `footer`, and `cookie_banner` for the
consent bar.

## One file

On `2026.2.1` the entry is `src/app/modules/<name>/<name>.astro`. Published
packages also export `index.astro` as an alias. `2026.2` apps still use
`index.astro`. The field list is a
literal `export const manifest` in that file. The CLI reads the object without
running your code, so it cannot be built by a function.

```astro
---
import type { ModuleManifest, ModuleProps } from "@caraer/cms-runtime";
import type { HeroFields } from "./types.d.ts";

export const manifest = {
  name: "hero",
  label: "Hero",
  kind: "section",
  category: "hero",
  fields: [
    { name: "heading", label: "Heading", type: "SINGLE_LINE", required: true },
    { name: "image", label: "Image", type: "IMAGE" },
    { group: "Style", fields: [
      { name: "tint", label: "Tint", type: "COLOR" },
    ]},
  ],
} satisfies ModuleManifest;

const { fields } = Astro.props as ModuleProps<HeroFields>;
---

<section>
  <h1 data-caraer-field="heading">{fields.heading}</h1>
</section>
```

`caraer apps validate` writes `types.d.ts`. Do not edit that file.

`label`, `helpText`, and `description` are what the AI rewrite feature reads,
so write them for a person.

## Fields

Modules reuse app setting field types, except `SECRET` and `ACTION`. A
serverless `optionsSource` is not available either: the builder renders inputs
without calling your app. Use static `options`.

`PROPERTY_SINGLE_SELECT` gives the module the **value** of the chosen property
on the page's record. Use `rawFields` when a listing needs the property
**name**. Limit the picker with `filterPropertyTypes` / `filterPropertyFormats`
(or the CMS aliases `allowedPropertyTypes` / `allowedPropertyFormats`).
`OBJECT_*` fields may set `filterTraits` so only objects with those traits
appear.

Style with `--caraer-*` design tokens. Hard-coded colours and spacing stay
wrong on every site except the one you wrote against.

A `{ group: "Style", fields: [...] }` object in `fields` is a sidebar
expandable in `caraer apps local` and the CMS builder. Do not set `group`
on a field, and do not use a top-level `components` list. Ungrouped fields
stay at the top. `advanced: true` (outside a group) still collapses under
**Advanced settings**.

For anything that needs the platform (rich text, images, links, menus, forms,
record lists), import the component from `@caraer/cms-runtime`. A module does
not build its own API client.

## Preview

```bash
caraer apps local dev
```

The preview top bar switches between sample data and any company you can
reach, so you can check the module against real branding before you push.

Mark rendered nodes with `data-caraer-field="<name>"` (and
`data-caraer-item="<index>"` on a REPEATABLE row). In `caraer apps local`
and the CMS builder, clicking that node focuses the matching sidebar
field. The live site ignores the attributes.
