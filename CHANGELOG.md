# Changelog

## Unreleased

- Local app definition is now **`src/app/app.caraer.yaml`** (legacy `app.caraer.json` still loads);
  scaffolds include commented examples for scopes, settings, pricing, and app bars
- App platform **V2** (`platformVersion: 2026.2`): one async container runtime per app;
  `apps push --deploy` polls `runtimeStatus`; `apps status` shows runtime fields
- Default scaffold is `2026.2`; use `--platform 2026.1` for legacy per-function Cloud Functions
- `caraer apps migrate-v2` — opt-in in-place V1 → V2 migration with runtime polling
- Collapsed local **project** into **app**: `caraer.json` replaces `caraer.project.json`;
  opaque developer-project id lives in `.caraer/state.json`
- Single sync pair: `caraer apps pull` / `caraer apps push` syncs manifest, functions, and webhooks
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
- `caraer apps add-function` / `add-webhook` scaffold local function folders and
  webhook JSON files
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
- Example project under `examples/hello-function`
- CI workflow and `scripts/ci.sh`
