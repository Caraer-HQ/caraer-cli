# Platform versioning

Current app workspace schema version: **`2026.2.1`**

Set in `caraer.json` as `platformVersion`. `2026.2` and `2026.2.1` both deploy
as `App.platformVersion` 2. Only `2026.2.1` uses the flat source layout.

| CLI `platformVersion` | `App.platformVersion` | Runtime model |
|-----------------------|----------------------|---------------|
| `2026.1` | `1` | Legacy: one sync Cloud Function per serverless function |
| `2026.2` | `2` | One async container runtime per app (folder functions) |
| `2026.2.1` (default) | `2` | Same container runtime; flat files + YAML settings |

Existing V1 apps are batch-migrated on the backend with the Neo4j CLI migration
`apps-platform-v2` (`run-migration apps-platform-v2 up`). That flips
`platformVersion` to `2`, schedules the shared container rebuild, keeps invoking
via legacy `gcpReference` until `runtimeStatus=READY`, then GCs old Cloud
Functions. Apps with mixed function runtimes fail the migration until aligned.
After migration, update local `caraer.json` to `platformVersion: 2026.2`.

New private apps are always created as V2 (`runtime` defaults to `nodejs22`).

## 2026.2.1

- Default for `caraer apps init`
- Flat functions: `src/app/functions/<name>.js` (or `.py`)
- Lifecycle, schedules, and inbound are code files with `exports.manifest`
- Webhooks live on the function manifest; there is no `webhooks/` folder
- Settings are a single-level field list in `settings.yaml`
- App bars are `appBars` on a function in `src/app/appbars/`; the file is the handler
- Modules are `modules/<name>/<name>.astro`
- Upgrade an existing 2026.2 tree with `caraer apps upgrade`

## 2026.2

- Same local layout as 2026.1: `caraer.json` + `src/app/{app.caraer.yaml,functions/,webhooks/}`
  (legacy `app.caraer.json` is still loaded if present)
- Optional `runtime` on `caraer.json` (`nodejs22` | `python312`) — required for App V2 create
- `caraer apps push --deploy` builds, deploys with `ProjectDeploy.status=PENDING`, then
  polls `App.runtimeStatus` until `READY` / `FAILED`
- `caraer apps status` shows `runtime`, `runtimeStatus`, `runtimeBaseUrl`
- Functions under V2 are code modules; invoke URL is
  `{runtimeBaseUrl}/functions/{name}`
- Local `caraer apps local dev` mirrors that contract (`/functions/{name}`, header, body)
  and emulates installation state/secrets/jobs for local integration testing

## 2026.1

- Local layout: `caraer.json` + `src/app/{app.caraer.json|yaml,functions/,webhooks/}`
- Function manifest: `function.caraer.json` with `name`, `runtime` (`nodejs22`|`python312`), optional `entry`, `description`
- Webhooks: one JSON file per subscription under `src/app/webhooks/`
- Developer project APIs under `/api/v2/developer-projects` (opaque to CLI users)
- Sandboxes under `/api/v2/developer-sandboxes`
- Sync function create/update still provisions one Cloud Function per function (slow)

Legacy `caraer.project.json` is still discovered and migrated to `caraer.json` on load
(`projectUuid` moves into `.caraer/state.json`).
