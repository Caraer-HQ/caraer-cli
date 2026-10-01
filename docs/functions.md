# Serverless functions

A function is code Caraer runs when something happens: an install, a webhook,
a schedule, an inbound HTTP call, or an app-bar action. On platform `2026.2`
and `2026.2.1` every function in the app shares one container. You change code
locally and `caraer apps push`. The Caraer UI does not edit function source for
a build-deployed app.

## Add one

```bash
caraer apps add function my-action
caraer apps add function my-action --runtime python312
caraer apps add options-function list-items
```

`add options-function` (or `add function --template options`) is a loader for
a settings field whose options come from your code. See
[Settings](../README.md#settings).

## Layout

`2026.2.1` (default):

```text
src/app/functions/my-action.js   # Node
src/app/functions/my-action.py   # Python
src/app/shared/                  # import { helper } from "../shared/index.js"
```

The filename is the function name. Put record webhooks on
`manifest.webhooks` on the exported `manifest` object (or Python `manifest = {...}`). App bars live in
`src/app/appbars/<name>.js` with `manifest.appBars` on the exported `manifest` object; that file is the
one Caraer runs for `app.bar.triggered`. Helpers used by more than one
function live in `src/app/shared/` and import as `import { helper } from "../shared/index.js"`.

`2026.2` still uses a folder with `index.js` / `main.py` and
`import { helper } from "../../shared/index.js"`.

Node functions use ES modules. The project’s `package.json` declares
`"type": "module"`; relative imports include the filename and `.js` extension.

## Handlers

Node:

```js
export const handler = async (req, res) => {
  const body = typeof req.body === "string" ? JSON.parse(req.body || "{}") : req.body || {};
  res.status(200).json({ ok: true });
};
```

Python:

```python
def handler(request):
    body = request.get("body") if isinstance(request, dict) else {}
    return {"statusCode": 200, "body": {"ok": True}}
```

An installation can also keep rows in its own Postgres schema via
`POST /api/v2/apps/{appUuid}/installation/db` with the installation token.
See the backend `docs/installation-db-cloud-sql.md`.

A record webhook and an app-bar click do not share one envelope. The record
event is the body (`body.event.type`, `body.record.record`). An app bar is a
flat body with `event: "app.bar.triggered"`. Both shapes are in
[webhooks](webhooks.md#what-the-function-receives). Lifecycle, schedule, and
inbound calls use the envelope below.

The body always includes:

| Field | Use |
|-------|-----|
| `installationToken` | Short-lived `inst_…` Bearer (about 1 hour). This is the token you call Caraer with. |
| `caraerApiBase` | API origin. Do not ask the installer for this. |
| `appUuid` | This app. |
| `companyUuid` | The company that installed it. |
| `settingsSchema` | Installation settings, each field with `name` and `value`. |
| `functionName` | Set when the caller includes it. The runtime also routes on `/functions/<name>` and `X-Caraer-Function`. |

## Lifecycle

`event` is the class name: `Installed`, `Updated`, `Uninstalled`, or `Rotated`.
The fields sit on `req.body`. There is no nested `payload`.

```json
{
  "event": "Installed",
  "timestamp": 1710000000000,
  "appUuid": "…",
  "appName": "example",
  "appLabel": "Example",
  "privateApp": true,
  "authMethod": "API_KEY",
  "companyUuid": "…",
  "companyName": "Acme",
  "userUuid": "…",
  "actingUserUuid": "…",
  "installationToken": "inst_…",
  "caraerApiBase": "https://api.caraer.com/api",
  "settingsSchema": [
    { "name": "display_name", "type": "SINGLE_LINE", "value": "Hello" }
  ],
  "scopes": []
}
```

`Updated` also sets `settingsChanged`, `scopesChanged`, `filtersChanged`, and
`userSettingsChanged`. `caraerApiBase`, `secrets`, and `connections` are added
on the way to the function, the same as a webhook.

## Schedule

A schedule is queued, then invoked. `req.body.payload` is the schedule.
Installation fields are on the root, next to `action` and `jobId`.

```json
{
  "action": "app.schedule",
  "jobId": "…",
  "payload": { "scheduleName": "heartbeat" },
  "appUuid": "…",
  "companyUuid": "…",
  "installationToken": "inst_…",
  "caraerApiBase": "https://api.caraer.com/api",
  "settingsSchema": [
    { "name": "display_name", "type": "SINGLE_LINE", "value": "Hello" }
  ],
  "scopes": []
}
```

Anything in the schedule's payload template is copied onto `payload` next to
`scheduleName`.

## Inbound

A direct inbound call puts the HTTP body on `body`. A queued inbound call
wraps that object under `payload`, the same way a schedule does.

```json
{
  "action": "app.inbound",
  "inboundRoute": "echo",
  "headers": { "content-type": "application/json" },
  "body": { "hello": "caraer" },
  "appUuid": "…",
  "companyUuid": "…",
  "installationToken": "inst_…",
  "caraerApiBase": "https://api.caraer.com/api",
  "settingsSchema": [
    { "name": "display_name", "type": "SINGLE_LINE", "value": "Hello" }
  ],
  "scopes": []
}
```

Queued (`enqueue: true`) the same object is `req.body.payload`, and the root
`action` is still `app.inbound` with a `jobId`.

Installation state, secrets, and background jobs:

| Method | Path |
|--------|------|
| GET / PUT | `{caraerApiBase}/v2/apps/{appUuid}/installation/state` |
| GET / PUT | `{caraerApiBase}/v2/apps/{appUuid}/installation/secrets` |
| POST | `{caraerApiBase}/v2/apps/{appUuid}/installation/jobs` |

Send `Authorization: Bearer <installationToken>`.

## Run locally

```bash
caraer apps local dev
caraer apps local test --function my-action --sample-only
caraer apps local logs --follow
```

`local dev` serves `POST /functions/<name>`.
