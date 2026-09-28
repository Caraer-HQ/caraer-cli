# Caraer CMS v2 — reference

Companion to [SKILL.md](SKILL.md).

## Company isolation

| `cmsVersion` | Site | Editor |
| --- | --- | --- |
| `1` (default) | WerkenBij / `{subdomain}.caraer.com` | v1 PageContent (`webpage_*`) |
| `2` | caraer-web Astro | CMS v2 builder + this skill |

`CARAER_DEFAULT_CMS_VERSION` must stay `1`. Attach a sidecar host before
cutover. Transfer APIs: attach → QA on sidecar → rollback drill → cutover.

Standalone `/forms/{name}` URLs are still v1-only. Remap if a v2 company used
those paths.

## Manifest kinds and categories

Kinds: `section`, `page`, `header`, `footer` (and `cookie_banner` for consent).

Categories: `hero`, `content`, `listing`, `layout`, `media`, `form`, `cta`,
`social_proof`.

## Contract package

Import types and platform components from `@caraer/cms-runtime`:

`CaraerRichText`, `CaraerImage`, `CaraerLink`, `CaraerMenu`, `CaraerForm`,
`CaraerRecordList`.

`PROPERTY_*` fields resolve to the **record value**. Listing modules that need
the property **name** read `rawFields`.

## Click-to-setting

In the builder iframe only (`editor-bridge`):

```html
<h1 data-caraer-field="heading">...</h1>
<li data-caraer-item="0">
  <p data-caraer-field="quote">...</p>
</li>
```

Live site ignores these attributes when the bridge is off.

## What not to do

- Do not call non-existent `cms_v2_*` / `cms.v2_*` MCP tools.
- Do not edit `caraer-cms-runtime` on `main` as the source of truth.
- Do not add `SECRET` or `ACTION` to a module.
- Do not invent a second `GROUP` type; use `REPEATABLE`.
- Do not push or deploy unless the user asks.
