---
name: caraer-apps
description: >-
  Scaffolds, edits, validates, and deploys Caraer Apps V2 projects with the
  caraer CLI (app.caraer.yaml, serverless functions, inbound routes, schedules,
  lifecycle hooks, settings). Use when creating or changing a Caraer
  public app, private app, marketplace app, serverless function, webhook,
  inbound route, or when the user mentions caraer apps, app.caraer.yaml, or
  caraer-cli.
---

# Caraer Apps (CLI)

Build Caraer apps with the **caraer** CLI and the V2 layout (`platformVersion:
2026.2.1` by default; `2026.2` is the older folder layout). Prefer CLI
scaffolds over inventing folders by hand.

## Install this skill

From a machine with `caraer-cli` installed:

```bash
caraer skill install              # ~/.cursor/skills/caraer-apps
caraer skill install --project    # ./.cursor/skills/caraer-apps (this repo)
```

Or copy `skills/caraer-apps/` from the [caraer-cli](https://github.com/Caraer-HQ/caraer-cli)
repo into `~/.cursor/skills/caraer-apps/`.

## Preconditions

1. CLI available: `caraer --version` (Python 3.10+).
2. Auth + company: `caraer auth login` then `caraer company select <uuid>`.
3. Work inside an app folder (has `caraer.json`) or pass `--file`.
4. Company-private apps: `caraer apps init --private` writes `privateApp: true`
   to `caraer.json`. Push/pull then use `/api/v2/apps/private*`. Skip
   marketplace listing fields (`brandmark`, `details`). Do not run
   `caraer publish` for private apps.

## Golden path

```bash
caraer apps init --name my_app --label "My App"
caraer apps init --private --name internal_tool --label "Internal Tool"
cd my_app
# edit src/app/app.caraer.yaml + functions
caraer apps validate
caraer apps push --dry-run
caraer apps push
caraer apps status
caraer apps local logs --follow
```

Local loop without deploy:

```bash
caraer apps local dev
caraer apps local test --function <name> --sample-only
```

## Project layout (2026.2.1)

```text
caraer.json
package.json                # npm/pnpm `dev` = caraer apps local dev (functions + CMS)
tsconfig.json               # resolves module npm imports from package.json
src/app/
  app.caraer.yaml           # identity, scopes, auth, details
  settings.yaml             # installer setting fields (optional section grouping)
  functions/<name>.js       # name is the filename; webhooks and app bars in exports.manifest
  lifecycle/<hook>.js       # install|uninstall|rotate|update
  schedules/<name>.js
  inbound/<name>.js
  shared/                   # require("../shared")
  modules/<name>/<name>.astro
```

`2026.2` apps keep folders and JSON. Rewrite them with `caraer apps upgrade`.

Payload types: import from `@caraer/client` (Node) or `caraer-client` (Python),
e.g. `LifecyclePayload`, `WebhookPayload`, `SchedulePayload`.

On `2026.2.1` the filename is the function name. Webhooks, app bars, schedules,
inbound, and lifecycle are `exports.manifest` / `manifest = {...}` literals.
The function that declares an app bar is the handler. `2026.2` still uses
folders and JSON.

Add this line at the top of `app.caraer.yaml` so the editor loads the public
schema (also emitted by `caraer apps init`):

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/Caraer-HQ/caraer-app-schemas/main/schemas/app.caraer.schema.json
```

Browse the schemas at [Caraer-HQ/caraer-app-schemas](https://github.com/Caraer-HQ/caraer-app-schemas).
`caraer apps validate` still uses the copies bundled with the CLI.

Reference example: `examples/layout-v21` in the caraer-cli repo
(`2026.2.1`). `examples/webhook-inbox` is the older `2026.2` folder layout.

## Agent workflow

Copy and track:

```text
App progress:
- [ ] Clarify job (inbound / schedule / record bar / OAuth / records)
- [ ] `caraer apps init` or open existing app
- [ ] Edit manifest settings (user-facing only)
- [ ] Add/edit functions (shared helpers in `src/app/shared/`)
- [ ] Wire inbound / schedule / webhook / lifecycle
- [ ] `caraer apps validate` → fix until 0 errors
- [ ] `caraer apps push --dry-run` then `caraer apps push` when user asks
```

### Clarify before coding

Ask only what blocks design:

- Trigger: inbound HTTP, schedule, record event, or install lifecycle?
- Runtime: `nodejs22` (default) or `python312`?
- Need installation state/secrets/jobs? Either `API_KEY` or `OAUTH2`. Webhooks
  inject a short-lived `inst_…` `installationToken` (about 1h), not the API key.
  Prefer `hideApiKeyField: true` so installers do not see the API key in the UI.
- Need Caraer user OAuth app install? → `OAUTH2` + redirect URIs.
- External provider (Google, etc.)? → `externalOAuthProviders` + `${ENV}` secrets.

### Settings UX rules

Installation settings are for **admins installing the app**, not developers.

- Use clear labels + `helpText`. Prefer `SWITCH`, `OBJECT_SINGLE_SELECT`,
  `SINGLE_SELECT` over free-text when possible.
- Do **not** add `caraer_api_base` or other platform URLs — runtime injects
  `body.caraerApiBase`.
- Do **not** ask for object/property names as raw strings when a select type exists.
- Keep required settings to the minimum that makes the app work.
- When the app writes mapped records, declare
  `records.<setting:mapping_field>.all` (and `.properties_all` /
  `.relations_all`) instead of hard-coding object names. A property
  single-select targets that property with
  `records.<setting:due_date.objectName>.property.<setting:due_date.propertyName>.all`.
  `propertyNames` grants each selected property. Bare `<field>`
  still works. Empty mappings grant no extra scopes. Use
  `records.<trait:user>.all` when every object with that trait must be
  reachable. The same placeholders work on webhook topics
  (`record.<setting:target_object>.created`). `date_due` uses the same
  placeholder; the company copy is what gets scheduled. Read a key with a
  path: `record.<setting:due_date.objectName>.date_due.<setting:due_date.propertyName>`.
  Mapping fields use `<setting:field_map.objectName>` for the object and
  `<setting:field_map.email>` for the row whose `fieldName` is `email`.
  Scopes stay `records.<setting:field_map.objectName>.all`. The template still needs
  `triggerOffsetSeconds`.
- Group related fields into installer cards with `section` / `sectionSubtitle`
  on each field in `settings.yaml`. On 2026.2 use `settings-sections/*.json`.
  Do not invent a grid; Caraer lays cards out left-to-right, top-to-bottom,
  max 3 across.
- Hide advanced settings behind a `SWITCH` + `visibleWhen` instead of showing
  everything at once:

```yaml
- name: custom_mapping
  type: SWITCH
  defaultValue: false
- name: field_mapping
  type: MAPPING
  visibleWhen:
    - field: custom_mapping
      value: true
```

  Hidden fields are not required and their values are dropped. Use `FILE` when an
  action dialog needs one upload, or `MULTI_FILE` for several.

### Functions

- Node: `exports.handler = async (req, res) => { ... }`.
- Python: `def handler(request): ...` returning `{statusCode, body}`.
- Shared helpers live in `src/app/shared/` and are imported with the same
  relative path locally and deployed:
  `require("../../shared")` / `require("../../shared/<file>")` from
  `functions/<name>/index.js` (platform 2026.2 build pushes only).
- Read settings via flattened `body.settingsSchema` (`name` → `value`).
- Use `body.installationToken` (short-lived `inst_…` Bearer) + `body.appUuid`
  for `/v2/apps/{appUuid}/installation/state|secrets|jobs`.
- Prefer `body.caraerApiBase` when calling Caraer APIs.
- The pushed build archive is the source of truth for V2 runtimes: the
  platform keeps function metadata only, not code. Editing function code in
  the Caraer UI is rejected for build-deployed apps — always change code
  locally and `caraer apps push`.

### Scaffolding commands

| Need | Command |
|------|---------|
| New function | `caraer apps add function` |
| Options loader | `caraer apps add options-function` (or `function --template options`) |
| Inbound route | `caraer apps add inbound` |
| Schedule | `caraer apps add schedule` (wizard prompts for cron presets / custom) |
| Webhook | `caraer apps add webhook` |
| Setting | `caraer apps add setting` (`settings.yaml` on 2026.2.1; `--modular` → `settings/` on 2026.2) |
| CMS module | `caraer apps add module` (Astro + `module.caraer.json` fields) |
| Lifecycle | `caraer apps add lifecycle-hook` |

### Validate loop

After every structural edit:

```bash
caraer apps validate --file .
```

Fix errors before push. Warnings (e.g. missing inbound `sharedSecret`) are OK
to leave for the installer when documented in README.

### Deploy safety

- Never push/deploy/install unless the user asks.
- Use `caraer apps push --dry-run` first for non-trivial changes.
- Do not commit secrets (`.env`, OAuth client secrets, inbound shared secrets).
- Expand `${ENV_VAR}` OAuth client fields from the **process environment** on push.
- Root `.env` is packed on push and applied to the Cloud Run runtime as
  environment variables (`AFFINDA_API_KEY`, …). It is not stored on the
  persisted build manifest.

## Anti-patterns

- Inventing V1 per-function GCP layouts when V2 is default.
- Hand-writing remote UUIDs into YAML (let push fill them).
- Copying helper files into every function folder (use `src/app/shared/`).
- Putting developer-only knobs in `settingsSchema`.
- Skipping `validate` before `push`.

## Dig deeper

- Payload shapes, lifecycle events, settings flattening: [reference.md](reference.md)
- CLI docs in the caraer-cli repo: `docs/app_lifecycle.md`, `docs/platform_versioning.md`
- Schemas: `schemas/*.caraer.schema.json`
