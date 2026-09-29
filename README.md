# Caraer CLI

Developer CLI for building Caraer apps: serverless functions, webhooks, schedules,
inbound routes, lifecycle hooks, and CMS modules.

The CLI is a thin client of the Caraer API. You do not need GCP credentials on
your machine.

Docs: [developer.caraer.com](https://developer.caraer.com)

## Requirements

- **Python 3.10+** (the CLI itself)
- **Node.js 22** and npm (default `nodejs22` runtime and the starter CMS module)
- A Caraer account that can create apps in a company

## Install

```bash
pipx install caraer-cli
# or: uv tool install caraer-cli
# or: pip install caraer-cli
```

Confirm:

```bash
caraer --version
caraer profile current    # prod, https://api.caraer.com
```

A new install uses the `prod` profile. `caraer profile use local`, `dev`, or
`staging` switches API host.

### Install from source

```bash
git clone https://github.com/Caraer-HQ/caraer-cli.git
cd caraer-cli
python3 -m venv .venv
source .venv/bin/activate
./scripts/install.sh
caraer --version
```

If install fails with `requires a different Python`, create the venv with
`python3.10`, `python3.11`, or `python3.12`. Restart the terminal so tab
completion loads.

## Prompt for an AI coding agent

Paste this into Cursor, Claude Code, or a similar agent. It installs the CLI,
logs you into production, and scaffolds an app. It does not deploy.

```text
Set up the Caraer CLI on this machine and scaffold a Caraer app. Do not push,
deploy, install, or publish the app unless I explicitly ask.

1. Check Python is 3.10 or newer (`python3 --version`). If it is older, stop
   and tell me how to install it.
2. Check Node.js 22 is available (`node --version`). The default `nodejs22`
   runtime and starter CMS module need it. If it is missing, stop and tell me.
3. If `caraer --version` fails, install the CLI:
   prefer `pipx install caraer-cli`, else `uv tool install caraer-cli`,
   else `pip install caraer-cli`. Confirm with `caraer --version`.
4. Confirm the active profile is production before login:
   `caraer profile current`
   base_url must be https://api.caraer.com. If it is not, run `caraer profile use prod`.
5. Install the agent skills so later edits follow Caraer app conventions:
   `caraer skill install`
   Tell me to start a new chat before relying on those skills.
6. Log in with `caraer auth login` and stop so I can approve the device code
   in the browser. Do not ask for or type my password. If device login is
   unavailable, ask me to run `caraer auth login --email <my-email>` myself.
7. Run `caraer company list` and ask which company to use, then
   `caraer company select <uuid>`.
8. Ask whether the app is private to that company or a public marketplace app,
   and what label to use. Then scaffold with platform 2026.2.1 (the default):
   - Private: `caraer apps init --private --label "<Label>" --auth-method API_KEY`
   - Public: `caraer apps init --label "<Label>"`
   Do not pass `--platform 2026.1`.
9. Change into the new folder and run `caraer apps validate`. Fix only errors
   the scaffold itself reported.
10. Summarize the folder, how to run it locally (`caraer apps local dev`), and
    that `caraer apps push` deploys and installs on the selected company.
    Wait for me before pushing.
```

After that chat, open a **new** agent chat in the app folder. The installed
skills (`caraer-apps`, `caraer-cms`) are what teach the agent the app layout.

```bash
caraer skill install              # ~/.cursor/skills/caraer-apps and caraer-cms
caraer skill install --project    # ./.cursor/skills in the current directory
caraer skill list
```

## Quick start

```bash
caraer auth login
# CI or password login: caraer auth login --email you@example.com
caraer company list
caraer company select <company-uuid>
```

Create a local app:

```bash
caraer apps init --label "My App"
# company-only app:
caraer apps init --private --label "Internal Tool" --auth-method API_KEY
cd my_app
caraer apps validate
caraer apps local dev           # local server: POST /functions/<name>
```

Deploy only when you mean to. `caraer apps push` syncs the manifest, functions,
webhooks, schedules, inbound routes, and OAuth providers, deploys the function
build, publishes CMS modules, and installs the app on the selected company.

```bash
caraer apps push --dry-run
caraer apps push                # add --wait to block until the runtime is READY
caraer apps status
caraer apps local logs          # the only local function, or a prompt
caraer apps local logs --all
```

Only the company that created the app (or a super-admin) can push builds.

`--no-deploy` syncs without a build. Private apps (`caraer apps init --private`,
or `privateApp: true` in `caraer.json`) use the private app API and cannot be
submitted with `caraer publish`.

New apps use workspace `platformVersion: 2026.2.1` (one container per app). Use
`--platform 2026.1` only for the legacy per-function model. See
[docs/platform_versioning.md](docs/platform_versioning.md).

### Add pieces

Run these inside the app folder:

```bash
caraer apps add function my-action
caraer apps add options-function list-items   # dynamic select options
caraer apps add webhook --topic record.candidate.created --function my-action
caraer apps add schedule renew-watch --function my-action --cron "0 0 */6 * * *"
caraer apps add inbound gmail-push --function my-action --auth SHARED_SECRET
caraer apps add setting
caraer apps add lifecycle-hook
caraer apps add module hello --kind section
```

`caraer apps init` already creates lifecycle files (`install`, `uninstall`,
`rotate`, `update`) and a starter `modules/hello_world`. Existing `2026.2`
apps stay as they are until you run `caraer apps upgrade`.

`add schedule` and `add setting` open a wizard when you omit flags.
`add setting` writes into `src/app/settings.yaml`.

## Project layout

```text
my_app/
  caraer.json                 # platformVersion 2026.2.1, appUuid, privateApp
  package.json
  src/app/
    app.caraer.yaml           # identity, scopes, auth, details
    settings.yaml             # installer setting fields (optional section grouping)
    functions/<name>.js       # name is the filename; webhooks and app bars live in its manifest
    lifecycle/<hook>.js       # install | uninstall | rotate | update
    schedules/<name>.js
    inbound/<name>.js
    shared/                   # require("../shared") from each of the above
    modules/<name>/<name>.astro
```

A function is a file named after the function, with `exports.handler` (Node) or
`def handler` (Python). Helpers live in `shared/`.

Node handlers export `handler`. Payload types come from `@caraer/client`
(`LifecyclePayload`, `WebhookPayload`, `SchedulePayload`):

```js
exports.handler = async (req, res) => {
  const body = req.body || {};
  res.status(200).json({ ok: true, event: body.event || null });
};
```

Python handlers use `caraer-client` for the same payload types:

```python
def handler(request):
    return {"statusCode": 200, "body": {"ok": True}}
```

Shared helpers live in `src/app/shared/` and are imported with the same relative
path locally and when deployed, for example `require("../shared")` from
`functions/<name>.js`.

See [`examples/layout-v21`](examples/layout-v21) for a full `2026.2.1` app
(named files, settings list, inbound, schedule, app bar, CMS module, and a
setting-targeted record webhook). [`examples/webhook-inbox`](examples/webhook-inbox)
is the older `2026.2` folder layout.

## App pieces

Each piece is a file under `src/app/` that points at a function, except CMS
modules, which are Astro components published with the app.

| Piece | What it does | Guide |
|-------|----------------|-------|
| Serverless functions | The code that runs | [docs/functions.md](docs/functions.md) |
| CMS modules | Blocks for the website builder | [docs/modules.md](docs/modules.md) |
| Webhooks | Run a function when a record or relation changes | [docs/webhooks.md](docs/webhooks.md) |
| Lifecycle | Run a function on install, update, uninstall, or credential rotate | [docs/app_lifecycle.md](docs/app_lifecycle.md) |
| Schedules | Run a function on a cron | [docs/schedules.md](docs/schedules.md) |
| Inbound routes | Public HTTP from an outside system into a function | [docs/inbound.md](docs/inbound.md) |

## Settings

Installation settings are filled in by the admin who installs the app.

`src/app/settings.yaml` is a single-level list of fields. Group related
fields into installer cards with `section` / `sectionSubtitle` on the field.
Caraer lays cards out left to right, top to bottom, at most 3 across.
Fields without `section` stay schema-only (no section card).

```yaml
- name: candidate_mapping
  type: MAPPING
  label: Candidate mapping
  section: Candidate
  sectionSubtitle: Map CV fields and parsing behavior
- name: parse_on_cv_change
  type: SWITCH
  label: Parse when a CV changes
  section: Candidate
- name: custom_mapping
  label: Custom mapping for work experience
  type: SWITCH
  defaultValue: false
- name: work_experience_mapping
  type: MAPPING
  visibleWhen:
    - field: custom_mapping
      operator: EQUALS
      value: true
```

A field with `visibleWhen` is shown, required, and submitted only while every
condition holds. Hidden fields are dropped.

Operators: `EQUALS` (default), `NOT_EQUALS`, `IN`, `NOT_IN`, `IS_SET`,
`IS_NOT_SET`.

Do not ask the installer for the Caraer API base URL. The runtime injects
`body.caraerApiBase`.

`records.<setting:field>.all` on `requiredScopes` follows the installer's
object pick. The same placeholder works on webhook topics
(`record.<setting:field>.created`). See [docs/webhooks.md](docs/webhooks.md).

## Profiles

Config is stored in the user config directory (`config.toml`). Built-in
profiles:

| Profile | API |
|---------|-----|
| `prod` (default) | `https://api.caraer.com` |
| `staging` | `https://v2.staging.api.caraer.com` |
| `dev` | `https://v2.dev.api.caraer.com` |
| `local` | `http://localhost:8080` |

`prod` is the Cloudflare edge. `staging` and `dev` are DNS aliases on Vercel
(`v2.staging.api` → `staging.api.caraer.com`, `v2.dev.api` → `dev.api.caraer.com`)
and are not proxied through Cloudflare.

```bash
caraer profile list
caraer profile use staging
caraer profile set --base-url https://api.caraer.com --output json
```

`--profile <name>` overrides the active profile for a single command.

## Sandboxes

A sandbox clones the selected company's Neo4j database. The company stays the
same. Each company can have at most 3 active sandboxes.

```bash
caraer company select <company-uuid>
caraer sandbox create --name my-test
caraer sandbox use <sandbox-uuid>
caraer sandbox clear
```

Sandboxes isolate Neo4j data. Function runtime code is still the deployed
build. Preview a push with `caraer apps push --dry-run` before you deploy.

## Command groups

- `auth`, `company`, `profile` — session and which API you talk to
- `apps` — scaffold, validate, push, logs, local dev
- `webhooks` — formats, events, and test helpers
- `publish` — marketplace review for public apps
- `sandbox` — Neo4j clone of the selected company
- `skill` — install the Cursor agent skills shipped with the CLI

## Further reading

- [Serverless functions](docs/functions.md)
- [CMS modules](docs/modules.md)
- [Webhooks](docs/webhooks.md)
- [App lifecycle hooks](docs/app_lifecycle.md)
- [Scheduled functions](docs/schedules.md)
- [Inbound routes](docs/inbound.md)
- [Platform versioning](docs/platform_versioning.md)
- [Backend contract](docs/backend_contract.md)
- [Changelog](CHANGELOG.md)
- [Security](SECURITY.md)
- Agent skills: [`skills/caraer-apps`](skills/caraer-apps), [`skills/caraer-cms`](skills/caraer-cms)

## License

Proprietary — see [LICENSE](LICENSE).
