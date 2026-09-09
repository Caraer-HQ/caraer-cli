# Changelog

## Unreleased

- `apps init` writes a root `tsconfig.json` (same options as `caraer-core`) so
  module scripts can resolve npm libraries such as `three`. Node `package.json`
  scaffolds set `"type": "module"` and include `three` + `@types/three` (r185
  has no bundled types). `apps add module` and `apps validate` write the
  tsconfig and backfill those packages when they are missing.

## 0.1.3

- Settings schema `filterTraits` on `OBJECT_SINGLE_SELECT` / `OBJECT_MULTI_SELECT`
  so installers can be limited to objects that have specific traits
- Parse CMS module `manifest` object literals without `json5`, so existing
  `caraer` installs keep working after this release

- Settings schema `ACTION` fields with `actionSource` trigger a serverless
  function without saving settings (cannot be `required` or a `visibleWhen` target)
- App scaffolds write a public `# yaml-language-server: $schema=…` line that
  loads [Caraer-HQ/caraer-app-schemas](https://github.com/Caraer-HQ/caraer-app-schemas)
- Removed `caraer apps migrate-v2`. Existing V1 apps are migrated via the backend
  Neo4j migration `apps-platform-v2` (`run-migration apps-platform-v2 up`).
- Removed `caraer apps typegen`. Import serverless payload helpers from the
  Caraer clients instead: `@caraer/client` (Node) / `caraer-client` (Python).
  Node scaffolds add `@caraer/client` as a `devDependency`.
- App scaffolds (`apps init` / wizard) default `hideApiKeyField: true` so the
  installation API key is hidden in the Caraer UI unless explicitly shown
- `caraer apps add schedule` interactive wizard: cron presets (hourly,
  daily, weekdays, …) or custom Spring 5–6 field expression, plus
  function picker, description, and enabled. `--cron` / `--description` /
  `--enabled|--disabled` still work non-interactively.
- **Breaking (with aliases):** regrouped `caraer apps` into nested
  `add/`, `local/`, and `release/` groups. Golden-path leaves stay flat
  (`list`, `select`, `init`, `push`, `validate`, …). Old flat paths
  (`add-function`, `dev`, `deploy`, `builds`, …) remain as **hidden**
  aliases that print a one-line deprecation warning. Aliases will be
  removed after one release — migrate to the new paths now.
- V2 runtimes now deploy straight from the pushed build archive (Cloud Run
  style): the platform stores function metadata only, not source code. After a
  build push, the CLI refreshes function UUID tracking read-only instead of
  re-uploading code through the legacy API, and `apps pull` never overwrites
  local sources when the platform has no stored code
- Shared code: `src/app/shared/` is deployed at the runtime archive root, so
  functions import helpers with the same relative path locally and deployed
  (`require("../../shared")` from `functions/<name>/index.js`). No more
  copying `shared.js` into every function folder (requires backend support;
  platform 2026.2 build pushes only — legacy sync warns and skips it)
- `function.caraer.json` is now optional: a folder under `src/app/functions/`
  with `index.js` / `main.py` is a function named after the folder, using the
  app-level runtime. Keep the manifest only for a custom `entry` or
  `description`. Scaffolds and `apps pull` no longer write redundant manifests
- `apps init` scaffolds a root `package.json` with npm scripts
  (`dev`, `validate`, `push`, `deploy`, `logs`) for Node projects
- `apps init` no longer creates empty `settings/`, `pricing/`, and `app-bars/`
  directories; their writers create them on demand

## 0.1.2

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
