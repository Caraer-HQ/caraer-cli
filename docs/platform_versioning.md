# Platform versioning

Current app workspace schema version: **`2026.2`**

Set in `caraer.json` as `platformVersion`.

| CLI `platformVersion` | `App.platformVersion` | Runtime model |
|-----------------------|----------------------|---------------|
| `2026.1` | `1` | Legacy: one sync Cloud Function per serverless function |
| `2026.2` (default) | `2` | One async container runtime per app |

Migrate an existing V1 app in place with:

```bash
caraer apps migrate-v2 [--runtime nodejs22|python312]
```

The API flips `platformVersion` to `2`, schedules the shared container rebuild, keeps
invoking via legacy `gcpReference` until `runtimeStatus=READY`, then GCs old Cloud
Functions. The CLI polls until READY and sets local `caraer.json` to `2026.2`.
Use `--runtime` when functions disagree or have no runtime set.

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
