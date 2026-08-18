---
name: caraer-apps
description: >-
  Scaffolds, edits, validates, and deploys Caraer Apps V2 projects with the
  caraer CLI (app.caraer.yaml, serverless functions, inbound routes, schedules,
  lifecycle hooks, settings). Use when creating or changing a Caraer
  public app, marketplace app, serverless function, webhook, inbound route, or
  when the user mentions caraer apps, app.caraer.yaml, or caraer-cli.
---

# Caraer Apps (CLI)

Build Caraer apps with the **caraer** CLI and the V2 layout (`platformVersion:
2026.2`). Prefer CLI scaffolds over inventing folders by hand.

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

## Golden path

```bash
caraer apps init --name my_app --label "My App"
cd my_app
# edit src/app/app.caraer.yaml + functions
caraer apps validate
caraer apps push --dry-run
caraer apps push --deploy
caraer apps install
caraer apps status
caraer apps local logs --follow
```

Local loop without deploy:

```bash
caraer apps local dev
caraer apps local test --function <name> --sample-only
```

## Project layout (V2)

```text
caraer.json
package.json                # npm-style scripts (dev/validate/push/deploy); Node adds @caraer/client
src/app/
  app.caraer.yaml           # identity, auth, settings, pricing, OAuth
  functions/<name>/         # index.js|main.py (function.caraer.json optional)
  shared/                   # code shared by all functions (require "../../shared/...")
  settings/*.json           # modular settingsSchema fields
  settings-sections/*.json  # optional installer cards (title, subtitle, field names)
  lifecycle/*.json          # install|uninstall|rotate|update → function
  inbound/*.json            # public HTTP → function
  schedules/*.json          # cron → function
  webhooks/*.json           # platform events → function
```

Payload types: import from `@caraer/client` (Node) or `caraer-client` (Python),
e.g. `LifecyclePayload`, `WebhookPayload`, `SchedulePayload`. Do **not** run
`caraer apps typegen` (deprecated no-op).

`function.caraer.json` is only needed to override conventions (custom entry,
description); a folder with `index.js` / `main.py` is a function named after
the folder.

Do **not** add a `# yaml-language-server: $schema=…` line pointing at
`raw.githubusercontent.com`: caraer-cli is private, so an editor can only report
that the schema failed to load. `caraer apps validate` checks the manifest
against the schemas bundled with the CLI (`schemas/*.caraer.schema.json`).

Reference example: `examples/webhook-inbox` in the caraer-cli repo.

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
- [ ] `caraer apps push --dry-run` then `--deploy` when user asks
```

### Clarify before coding

Ask only what blocks design:

- Trigger: inbound HTTP, schedule, record event, or install lifecycle?
- Runtime: `nodejs22` (default) or `python312`?
- Need installation state/secrets? → `authMethod: API_KEY` (gets `installationToken`).
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
- Group related fields into installer cards with `settingsSections` (or
  `src/app/settings-sections/*.json`). Do not invent a grid; Caraer lays
  cards out left-to-right, top-to-bottom, max 3 across.
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
  action dialog needs an upload.

### Functions

- Node: `exports.handler = async (req, res) => { ... }`.
- Python: `def handler(request): ...` returning `{statusCode, body}`.
- Shared helpers live in `src/app/shared/` and are imported with the same
  relative path locally and deployed:
  `require("../../shared")` / `require("../../shared/<file>")` from
  `functions/<name>/index.js` (platform 2026.2 build pushes only).
- Read settings via flattened `body.settingsSchema` (`name` → `value`).
- Use `body.installationToken` + `body.appUuid` for
  `/v2/apps/{appUuid}/installation/state|secrets|jobs`.
- Prefer `body.caraerApiBase` when calling Caraer APIs.
- The pushed build archive is the source of truth for V2 runtimes: the
  platform keeps function metadata only, not code. Editing function code in
  the Caraer UI is rejected for build-deployed apps — always change code
  locally and `caraer apps push --deploy`.

### Scaffolding commands

| Need | Command |
|------|---------|
| New function | `caraer apps add function` |
| Options loader | `caraer apps add options-function` (or `function --template options`) |
| Inbound route | `caraer apps add inbound` |
| Schedule | `caraer apps add schedule` (wizard prompts for cron presets / custom) |
| Webhook | `caraer apps add webhook` |
| Setting | `caraer apps add setting` (YAML by default; `--modular` → `settings/`) |
| Lifecycle | `caraer apps add lifecycle-hook` |
| Pricing | `caraer apps add pricing-plan` |

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
