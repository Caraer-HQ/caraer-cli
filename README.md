# Caraer CLI

Standalone developer CLI for Caraer app lifecycle management.

Install and use this package independently of the Caraer backend. It talks to
the Caraer API as a thin client — no GCP credentials are required on your machine.

## Requirements

- **Python 3.10+**
- A Caraer account with access to a company that can create public apps

## Install

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

### From PyPI (when published)

```bash
pipx install caraer-cli
# or: pip install caraer-cli
```

## Quick start

```bash
caraer auth login --email you@example.com
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
caraer apps version             # live semver + recent builds
caraer apps status
caraer apps logs                # uses the only local function (or prompts)
caraer apps logs --all          # V2 app container logs
caraer apps dev                 # local server: POST /functions/<name>
caraer apps test --record <uuid>
caraer apps state get
caraer apps secrets list
caraer apps rollback            # redeploy prior READY build
```

New apps default to workspace `platformVersion: 2026.2` (App platform V2: one async
container runtime per app). Use `caraer apps init --platform 2026.1` only for the
legacy per-function Cloud Functions model. See [docs/platform_versioning.md](docs/platform_versioning.md).

`apps push` syncs the full app: marketplace manifest (including pricing + app bars),
functions, webhooks, schedules, inbound routes, and external OAuth providers.
There is no separate upload command.

Add local scaffolds inside an app folder:

```bash
caraer apps add-function my-action
caraer apps add-webhook --topic record.created --function my-action
caraer apps add-schedule renew-watch --function my-action --cron "0 0 */6 * * *"
caraer apps add-inbound gmail-push --function my-action --auth SHARED_SECRET
caraer apps add-setting api_base_url --label "API base URL" --type SINGLE_LINE
caraer apps add-pricing-plan Free --type FLAT --price 0 --unit installations
caraer apps add-app-bar "Sync now" --location RECORD_PREVIEW --function my-action
caraer apps add-lifecycle-hook uninstall   # recreate one hook if deleted
caraer apps add-webhook --topic app.bar.triggered --mode HTTP --url https://example.com/hook
```

Lifecycle hooks (`install` / `uninstall` / `rotate` / `update`) and matching
`functions/on-*` folders are created automatically by `caraer apps init`.


Only the **app creator company** (or super-admin) can push builds for an app.

## Platform versions

| CLI `platformVersion` | App platform | Notes |
|-----------------------|--------------|-------|
| `2026.2` (default) | V2 | One container per app; async deploy; poll `runtimeStatus` |
| `2026.1` | V1 | One Cloud Function per serverless function (legacy) |

Migrate an existing V1 app in place with:

```bash
caraer apps migrate-v2 [--runtime nodejs22|python312]
```

This provisions the shared container, keeps webhook delivery on legacy function URLs
until `runtimeStatus=READY`, then updates local `caraer.json` to `2026.2`.

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
    app.caraer.yaml           # identity, auth, OAuth, rate limits
    settings/*.json           # installation settingsSchema fields
    pricing/*.json            # marketplace pricing plans
    app-bars/*.json           # app bars (actions / iframes)
    lifecycle/*.json          # install|uninstall|rotate|update hooks
    functions/<name>/         # function.caraer.json + entry source
    webhooks/*.json           # one webhook definition per file
    schedules/*.json          # cron → function (integration runtime)
    inbound/*.json            # public inbound routes → function
```

Marketplace arrays may still be inlined in `app.caraer.yaml`; modular files win on
name conflict. `apps init` always creates all four lifecycle hooks + `on-*`
functions. See [docs/app_lifecycle.md](docs/app_lifecycle.md) for payloads.

See [`examples/hello-function`](examples/hello-function) for a minimal sample and
[`examples/gmail-sync`](examples/gmail-sync) for settings + lifecycle hooks.

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

## Documentation

- [Platform versioning](docs/platform_versioning.md) — V1 vs V2 runtime model
- [Backend contract](docs/backend_contract.md) — REST endpoints used by the CLI
- [Changelog](CHANGELOG.md)
- [Security](SECURITY.md)

## Related

- API / platform: Caraer backend
- Docs site: https://developer.caraer.com
- Example app: [`examples/hello-function`](examples/hello-function)

## Development / CI

```bash
./scripts/ci.sh
```

GitHub Actions workflow: `.github/workflows/ci.yml`

## License

Proprietary — see [LICENSE](LICENSE).
