# Changelog

## Unreleased

- CMS preview installs `@caraer/cms-runtime` v0.1.4, which adds
  `cookie_banner` to `ModuleKind` and exports site-chrome helpers. A preview
  that already has the packages reinstalls when that pin changes.

## 0.1.8

- Support `authMethod: NONE` for Caraer-hosted apps using platform-managed
  installation tokens. Validation, scaffolds, the app wizard, and the bundled
  app schema accept an empty `oauthRedirectUris` list without adding a callback.

- Keep new workspaces unlinked until their first push creates the app, so they
  do not inherit an app selected in another folder.

## 0.1.5

- The first `caraer apps push` of a new app no longer sends lifecycle and
  app-bar functions before they exist. Those hooks are attached after the
  build, so create does not fail with an empty runtime.

- The only example app is `examples/example` (name `example`, label Example).
  `examples/webhook-inbox` is removed.

- HTTP webhook files are deployed as HTTP webhooks. A file without `name`
  uses its filename.

- Module sidebar groups stay `{ group: "Style", fields: [...] }` in `fields`.
  A top-level `components` list is rejected.

## 0.1.4

- HTTP webhooks are first-class on 2026.2.1: one YAML file each under
  `src/app/webhooks/`. `caraer apps add webhook --mode HTTP --url …` writes
  that file. Serverless webhooks stay on the function manifest.

- Module `fields` is a list of field objects or `{ group: "Style", fields:
  [...] }` expandables. Do not set `group` on a field. `advanced: true`
  stays the unnamed Advanced settings group.

- Clicking a `data-caraer-field` node in the CMS preview focuses that
  sidebar field (local `caraer apps local` harness and the Flutter builder).
  `examples/layout-v21` and new `caraer apps add module` scaffolds mark heading
  and body.

- `caraer apps push` warns when the workspace is still 2026.2 and offers to
  rewrite it to 2026.2.1 (default yes). `--upgrade` / `--no-upgrade` skip the
  prompt. `caraer apps upgrade` still rewrites without deploying.

- Docs and `examples/layout-v21` match the 2026.2.1 layout: flat functions,
  `src/app/appbars/`, JS lifecycle / inbound / schedules, webhook `label` and
  `webhookFormat`, company-copy topics on the Webhooks tab, CMS Modules tab,
  and `caraer apps delete` versus uninstall. `caraer apps add webhook`,
  `add schedule`, and `add inbound` write 2026.2.1 code files (function
  manifest / JS). JSON remains only on a 2026.2 workspace.

- Webhook topics and required scopes read a key on a setting. A property
  single-select uses `objectName` and `propertyName`
  (`record.<setting:due_date.objectName>.date_due.<setting:due_date.propertyName>`,
  and `records.<setting:due_date.objectName>.property.<setting:due_date.propertyName>.all`).
  A mapping row is addressed by `fieldName` (`<setting:field_map.email>`).
  Mapping scopes stay on the object. Caraer stores the concrete topic on the
  company webhook when the app is installed or settings are saved.

- Example app `examples/layout-v21`: full 2026.2.1 layout with settings,
  inbound, schedule, app bar, CMS module, and a setting-targeted record webhook.

- Guides for serverless functions, CMS modules, webhooks, lifecycle hooks,
  schedules, and inbound routes: `docs/functions.md`, `docs/modules.md`,
  `docs/webhooks.md`, `docs/app_lifecycle.md`, `docs/schedules.md`,
  `docs/inbound.md`.

- The default profile is `prod` (`https://api.caraer.com`). Built-in profiles
  are `local` (`http://localhost:8080`), `dev` (`https://v2.dev.api.caraer.com`),
  `staging` (`https://v2.staging.api.caraer.com`), and `prod`. Existing configs
  that still use the old hosts are updated on the next command. Staging and
  dev are not proxied through Cloudflare.

- CMS preview reinstalls when `@caraer/cms-runtime` or `@caraer/cms-tokens`
  are missing or are broken `caraer-web/packages` links, instead of treating
  an existing `@astrojs/node` as enough.

- CMS module preview (`.harness__preview`) uses block flow like live
  `#main`, so section modules fill the frame instead of shrink-wrapping
  in a centered flex row.

- CMS module manifests can import shared field objects (for example
  `widthField` from `src/app/modules/settings.ts`) instead of repeating
  options in every module. Field groups can be spread (`...backgroundFields`).
  Shared files at the modules root, and `_`-prefixed folders, are included
  in the published package. Nested settings files may reuse exported arrays
  such as `COLORS`.

- `caraer apps push` is the one command for private and public apps: it
  deploys by default, publishes CMS modules, and installs on the selected
  company. `--no-deploy` syncs without a build. `--wait` blocks on function
  runtime provisioning; the default skips that wait.

- App `package.json` `dev` is `caraer apps local dev`, so `npm run dev` /
  `pnpm dev` starts functions and the CMS preview. A missing `dev` script
  is filled in; an existing one is left alone.

- `apps local dev --cms` isolates the preview harness from the app
  `package.json`, so pnpm does not skip `@astrojs/node`.

- `apps init` scaffolds `src/app/modules/hello_world` (entry + `fields.d.ts`),
  the same starter CMS module `apps add module` would create.

- `apps init` writes a root `tsconfig.json` (same options as `caraer-core`) so
  module scripts can resolve npm libraries from `package.json`. Node
  `package.json` scaffolds set `"type": "module"`, `@caraer/client`, and the
  published CMS contract packages (`@caraer/cms-runtime`, `@caraer/cms-tokens`)
  and runs `npm install` so the default `hello_world` module resolves. They no
  longer add `three` / `@types/three`. Add those only when a module imports
  them.

- Settings schema `filterPropertyTypes` / `filterPropertyFormats` on
  `PROPERTY_SINGLE_SELECT` / `PROPERTY_MULTI_SELECT` (CMS alias
  `allowedPropertyTypes` / `allowedPropertyFormats`)

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
