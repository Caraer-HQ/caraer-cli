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
src/app/shared/                  # require("../shared")
```

The filename is the function name. Put webhooks on `exports.manifest` (or
Python `manifest = {...}`). Helpers used by more than one function live in
`src/app/shared/`.

`2026.2` still uses a folder with `index.js` / `main.py` and
`require("../../shared")`.

## Handlers

Node:

```js
exports.handler = async (req, res) => {
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

Payload types come from `@caraer/client` (Node) or `caraer-client` (Python):
`LifecyclePayload`, `WebhookPayload`, `SchedulePayload`.

The body always includes:

| Field | Use |
|-------|-----|
| `installationToken` | Short-lived `inst_…` Bearer (about 1 hour). This is the token you call Caraer with. |
| `caraerApiBase` | API origin. Do not ask the installer for this. |
| `appUuid` | This app. |
| `companyUuid` | The company that installed it. |
| `settingsSchema` | Installation settings, each field with `name` and `value`. |
| `functionName` | Which function was invoked. |

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
