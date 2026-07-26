# Changelog

## Unreleased

- Cursor Agent Skill `caraer-apps` under `skills/caraer-apps`, installable via
  `caraer skill install` / `caraer skill install --project`
- JSON Schemas under `schemas/` for app / function / webhook / schedule /
  inbound / lifecycle configs (IDE `$schema` + optional `caraer-cli[schemas]`)
- `caraer apps typegen` writes `src/types/caraer.d.ts` (Node) or
  `caraer_types.py` (Python) payload helpers
- Example app `examples/webhook-inbox` (inbound catch → installation state)
- Modular marketplace files: `src/app/settings/`, `pricing/`, `app-bars/`, `lifecycle/`
  (merged into the manifest on push; split on pull). Scaffolds:
  `apps add-setting|add-pricing-plan|add-app-bar|add-lifecycle-hook`
- `apps validate` covers settings, pricing, app bars, and lifecycle hooks
- `apps add-setting|pricing-plan|app-bar` use wizard prompts and append to
  `app.caraer.yaml` by default (`--modular` for separate JSON files)
- `apps init` always scaffolds all four lifecycle hooks + `on-*` functions
- Function sync includes sidecar `sourceFiles` so multi-file handlers deploy correctly
- Docs: [docs/app_lifecycle.md](docs/app_lifecycle.md); webhook-inbox includes all
  lifecycle hooks (install/uninstall/rotate/update)
- V2 local `apps dev` matches container contract: `POST /functions/{name}`,
  `X-Caraer-Function` header, and `body.functionName` (legacy `POST /{name}` kept)
- `apps dev` emulates installation state/secrets/jobs/connections + inbound routes;
  `--invoke-schedule` fires a local schedule once
- `apps deploy --wait/--no-wait` polls `runtimeStatus` (same as `push --deploy`)
- `apps pull` aligns local `platformVersion`/`runtime` with remote and pulls
  external OAuth providers
- Installation commands: `apps state|secrets|jobs|connections`
- `apps test` remote-invokes a function (or `--sample-only`); `apps rollback`
  redeploys a prior READY build; `apps builds list|get`
- `apps logs --all` fetches app-level V2 container logs
- `apps validate` covers schedules, inbound routes, and OAuth providers
- `apps push` / `pull` sync schedules, inbound routes, and OAuth providers
  (in addition to manifest, functions, webhooks)
- Local app definition is now **`src/app/app.caraer.yaml`** (legacy `app.caraer.json` still loads);
  scaffolds include commented examples for scopes, settings, pricing, and app bars
- App platform **V2** (`platformVersion: 2026.2`): one async container runtime per app;
  `apps push --deploy` polls `runtimeStatus`; `apps status` shows runtime fields
- Default scaffold is `2026.2`; use `--platform 2026.1` for legacy per-function Cloud Functions
- `caraer apps migrate-v2` — opt-in in-place V1 → V2 migration with runtime polling
- Collapsed local **project** into **app**: `caraer.json` replaces `caraer.project.json`;
  opaque developer-project id lives in `.caraer/state.json`
- Single sync pair: `caraer apps pull` / `caraer apps push` syncs manifest, functions,
  webhooks, schedules, inbound, and OAuth providers
- Removed top-level `webhooks`, `pricing`, `appbars`, and `functions` command groups
  (edit files under `src/app/` instead)
- Removed `caraer apps link` and `caraer apps watch` (use `select` / `push` instead)
- Removed deprecated `caraer project` command group (use `caraer apps` instead)
- Removed `caraer config` command group (use `caraer profile` instead)
- Removed `caraer completion` command group; shell completion is installed by `scripts/install.sh`
- Public packaging polish: LICENSE, SECURITY, CONTRIBUTING; example defaults to `2026.2`
- Developer sandboxes clone the selected company Neo4j DB only (same company
  identity; `X-Caraer-Sandbox-Uuid` overrides `databaseid`). Recreate sandboxes
  after upgrading past the old clone-company model
  (`caraer sandbox use` / `clear`)
- `caraer apps add-function` / `add-webhook` / `add-schedule` / `add-inbound`
  scaffold local function folders and integration-runtime JSON files
- Missing required args/options prompt interactively (questionary) instead of
  failing with Typer usage errors; non-TTY still fails clearly
- `caraer apps logs` prints log lines below the summary table; `--follow`
  streams only new entries; skips unreadable Cloud Audit protobuf dumps

## 0.1.0

- Standalone `caraer-cli` package extracted from backend `clients/python`
- Existing app / webhook / function commands
- `caraer project` local project workflow (`init`, `link`, `upload`, `pull`, `watch`, `status`)
- Build/deploy/logs/dev commands wired to developer-project APIs
- `caraer functions delete`
- `caraer sandbox` commands
- Example project under `examples/webhook-inbox`
- CI workflow and `scripts/ci.sh`
