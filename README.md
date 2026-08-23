# Caraer CLI

Standalone developer CLI for Caraer app lifecycle management.

Install and use this package independently of the Caraer backend. It talks to
the Caraer API as a thin client — no GCP credentials are required on your machine.

## Requirements

- **Python 3.10+**
- A Caraer account with access to a company that can create public apps

## Install

### From PyPI

```bash
pipx install caraer-cli
# or: uv tool install caraer-cli
# or: pip install caraer-cli
```

Publishing (maintainers): tag `v*` runs [`.github/workflows/publish.yml`](.github/workflows/publish.yml).
Add a PyPI API token as the `API_TOKEN` secret on the GitHub `pypi` environment
(or as a repository secret with the same name).

### From source (development)

```bash
git clone <this-repo> caraer-cli
cd caraer-cli
python3 -m venv .venv
source .venv/bin/activate
./scripts/install.sh                 # pip install + shell tab completion
# or: ./scripts/install.sh --shell zsh
caraer --help
```

If install fails with `requires a different Python`, create the venv with
`python3.10` / `python3.11` / `python3.12` explicitly.

Tab completion is installed by `scripts/install.sh`. Restart the terminal afterward.

## AI IDEs (Cursor skill)

Ship an Agent Skill so Cursor (and similar IDEs) can scaffold and validate Caraer
apps correctly:

```bash
caraer skill install              # ~/.cursor/skills/caraer-apps
caraer skill install --project    # ./.cursor/skills/caraer-apps
caraer skill list
```

Source of truth: [`skills/caraer-apps`](skills/caraer-apps). After install, start a
new agent chat and ask it to create or edit a Caraer app.

## Quick start

```bash
caraer auth login
# or password/CI: caraer auth login --email you@example.com
caraer company list
caraer company select <company-uuid>
caraer apps list
caraer apps select <app-uuid>   # pulls the full app folder locally
```

Create a new local app and push everything in one step:

```bash
caraer apps init --label "My App"
cd my_app
# edit src/app/app.caraer.yaml, src/app/functions/, src/app/webhooks/
caraer apps push --deploy       # prompts for version (> previous) + release notes
caraer apps release version     # live semver + recent builds
caraer apps status
caraer apps local logs          # uses the only local function (or prompts)
caraer apps local logs --all    # V2 app container logs
caraer apps local dev           # local server: POST /functions/<name>
caraer apps local test --record <uuid>
caraer apps state get
caraer apps secrets list
caraer apps release rollback    # redeploy prior READY build
```

New apps default to workspace `platformVersion: 2026.2` (App platform V2: one async
container runtime per app). Use `caraer apps init --platform 2026.1` only for the
legacy per-function Cloud Functions model. See [docs/platform_versioning.md](docs/platform_versioning.md).

`apps push` syncs the full app: marketplace manifest (including settings),
functions, webhooks, schedules, inbound routes, and external OAuth providers.
There is no separate upload command.

Add local scaffolds inside an app folder:

```bash
caraer apps add function my-action
caraer apps add options-function list-items   # LOAD_SETTING_OPTIONS loader
caraer apps add webhook --topic record.created --function my-action
caraer apps add schedule renew-watch --function my-action --cron "0 0 */6 * * *"
caraer apps add schedule         # wizard → cron presets / custom + function picker
caraer apps add inbound gmail-push --function my-action --auth SHARED_SECRET
caraer apps add setting          # wizard → appends to app.caraer.yaml
caraer apps add lifecycle-hook   # wizard → lifecycle/*.json + function
caraer apps add webhook --topic app.bar.triggered --mode HTTP --url https://example.com/hook
```

`add schedule` prompts for cron (presets or custom Spring 5–6 field expression),
function, description, and enabled when run interactively without those flags.
`add setting` writes into `app.caraer.yaml` by default
(use `--modular` for a separate JSON file under `settings/`).
`add options-function` (or `add function --template options`) scaffolds a
dynamic select options loader; wire via `optionsSource.serverlessFunctionName`
and optional `optionsSource.dependsOn`.
`add setting` also asks for conditional visibility, or takes
`--visible-when 'other_field:EQUALS:true'`; see
[Conditional settings](#conditional-settings).
`apps init` does not create empty `settings/` folders.
Lifecycle hooks stay under `src/app/lifecycle/` because they pair with function folders.

Lifecycle hooks (`install` / `uninstall` / `rotate` / `update`) and matching
`functions/on-*` folders are created automatically by `caraer apps init`.

### Settings sections

Optional `settingsSections` groups the flat `settingsSchema` into multiple
installer cards (title, subtitle, field names). Caraer lays the cards out
left-to-right, top-to-bottom, max 3 across — do not define a grid yourself.

```yaml
settingsSections:
  - title: Candidate
    subtitle: Map CV fields and parsing behavior
    settings:
      - candidate_mapping
      - parse_on_cv_change
```

Modular files also work: `src/app/settings-sections/01-candidate.json`.
Apps without `settingsSections` keep a single Settings card.

### Conditional settings

A settings field can declare `visibleWhen`; it is shown, required and submitted
only while **all** of its conditions hold:

```yaml
settingsSchema:
  - name: custom_mapping
    label: Custom mapping for work experience
    type: SWITCH
    defaultValue: false
  - name: work_experience_mapping
    type: MAPPING
    visibleWhen:
      - field: custom_mapping
        operator: EQUALS      # default when omitted
        value: true
```

Operators: `EQUALS`, `NOT_EQUALS`, `IN`, `NOT_IN` (list value), `IS_SET`,
`IS_NOT_SET` (no value).

`visibleWhen` controls presentation and validation; `optionsSource.dependsOn`
controls when option lists reload. Hidden fields are not required, their values
are dropped, and their options loader is not called.

### Payload types (Node / Python)

Do **not** run `caraer apps typegen` (deprecated no-op). Import serverless
payload helpers from the published clients:

```ts
import type { LifecyclePayload, WebhookPayload } from "@caraer/client";
```

```python
from caraer_client import LifecyclePayload, WebhookPayload
```

Node scaffolds add `@caraer/client` as a `devDependency`.

Only the **app creator company** (or super-admin) can push builds for an app.

## Platform versions

| CLI `platformVersion` | App platform | Notes |
|-----------------------|--------------|-------|
| `2026.2` (default) | V2 | One container per app; async deploy; poll `runtimeStatus` |
| `2026.1` | V1 | One Cloud Function per serverless function (legacy) |

Existing V1 apps are migrated to V2 via the backend Neo4j migration
`apps-platform-v2` (`run-migration apps-platform-v2 up`). New private apps and
CLI scaffolds (`2026.2`) already use the V2 runtime. After a backend migration,
set local `caraer.json` to `platformVersion: 2026.2` (and matching `runtime`)
before the next `caraer apps push`.

## Command groups

- `auth` / `company` / `profile` — session and profiles
- `apps` — local folder lifecycle + full sync (`pull` / `push`), builds, logs, local dev
- `webhooks` — formats, events, and test helpers
- `publish` — submit / status for marketplace review
- `sandbox` — clone the company Neo4j DB (same company; `X-Caraer-Sandbox-Uuid` overrides `databaseid`)

## Local app layout

```text
my_app/
  caraer.json                 # workspace metadata (platformVersion, appUuid, …)
  src/app/
    app.caraer.yaml           # identity, auth, OAuth, settings, app bars
    lifecycle/*.json          # install|uninstall|rotate|update hooks
    functions/<name>/         # function.caraer.json + entry source
    webhooks/*.json           # one webhook definition per file
    schedules/*.json          # cron → function (integration runtime)
    inbound/*.json            # public inbound routes → function
```

`add setting` appends to `app.caraer.yaml` by default.
Optional modular JSON files (`settings/`) still merge on push when
present (`--modular`). `apps init` always creates all four lifecycle hooks +
`on-*` functions. See [docs/app_lifecycle.md](docs/app_lifecycle.md).

See [`examples/webhook-inbox`](examples/webhook-inbox) for a minimal sample
(inbound route, settings, lifecycle, app bar).

## Profiles

Config lives in the user config dir (`config.toml`). Defaults include `dev`,
`staging`, and `prod`.

```bash
caraer profile list
caraer profile use staging
caraer profile set --base-url https://api.caraer.com --output json
```

Override the active profile for a single command with `--profile <name>`.

For local API development against a running backend:

```bash
caraer profile set --base-url http://localhost:8080
```

## Developer sandboxes

Create a Neo4j DB clone of the selected company, then activate it per request.
Company identity stays the same; only the Neo4j `databaseid` is overridden:

```bash
caraer company select <owner-company-uuid>
caraer sandbox create --name my-test
caraer sandbox list
caraer sandbox use <sandbox-uuid>   # same company; sends X-Caraer-Sandbox-Uuid
# … test against the clone DB …
caraer sandbox clear                # back to the company production database
```

Each company may have at most **3** active sandboxes. After a backend deploy that
changed the sandbox model, recreate sandboxes (old clone-company sandboxes are invalid).

Sandboxes isolate **Neo4j data only** — function runtime code is still shared with
production. Prefer `caraer apps push --dry-run` to preview changes, and treat
`--target sandbox` as a data sandbox, not a separate code environment.

## Documentation

- [Platform versioning](docs/platform_versioning.md) — V1 vs V2 runtime model
- [Backend contract](docs/backend_contract.md) — REST endpoints used by the CLI
- [Changelog](CHANGELOG.md)
- [Security](SECURITY.md)
- Cursor skill: [`skills/caraer-apps`](skills/caraer-apps) (`caraer skill install`)

## Related

- API / platform: Caraer backend
- Docs site: https://developer.caraer.com
- Example app: [`examples/webhook-inbox`](examples/webhook-inbox)

## Development / CI

```bash
./scripts/ci.sh
```

GitHub Actions workflow: `.github/workflows/ci.yml`

## License

Proprietary — see [LICENSE](LICENSE).
