# Caraer Apps — reference

Companion to [SKILL.md](SKILL.md). Read when implementing handlers or wiring
marketplace modules.

## Auth methods

| `authMethod` | Use when | Notes |
|--------------|----------|-------|
| `API_KEY` | App needs `installationToken` for state/secrets/jobs | Typical for integrations |
| `OAUTH2` | Install uses Caraer OAuth app flow | Set `oauthRedirectUris` |

External providers (`externalOAuthProviders`) are separate from `authMethod`.
Connected tokens arrive as installation secrets (e.g. `gmail_access_token`).

## Handler envelope (SERVERLESS)

Approximate JSON body (also wrapped as `req.body` for Node):

```json
{
  "event": "Installed",
  "appUuid": "...",
  "companyUuid": "...",
  "installationToken": "...",
  "caraerApiBase": "https://api.caraer.com/api",
  "functionName": "catch",
  "settingsSchema": [
    { "name": "inbox_label", "type": "SINGLE_LINE", "value": "Main" }
  ],
  "secrets": {},
  "payload": {}
}
```

Lifecycle `event` values: `Installed`, `Updated`, `Uninstalled`, `Rotated`.

Connect / Disconnect for external OAuth are **not** lifecycle webhooks — read
secrets from the payload / secrets API after the user connects.

## Installation APIs (Bearer installationToken)

Base: `{caraerApiBase}` (no trailing slash).

| Method | Path | Purpose |
|--------|------|---------|
| GET/PUT | `/v2/apps/{appUuid}/installation/state` | JSON blob state |
| GET/PUT | `/v2/apps/{appUuid}/installation/secrets` | Secret map |
| POST | `/v2/apps/{appUuid}/installation/jobs` | `{ "functionName", "payload" }` |

## Setting field types

`SINGLE_LINE`, `MULTI_LINE`, `SINGLE_SELECT`, `MULTI_SELECT`,
`RECORD_SINGLE_SELECT`, `RECORD_MULTI_SELECT`, `OBJECT_SINGLE_SELECT`,
`OBJECT_MULTI_SELECT`, `PROPERTY_SINGLE_SELECT`, `PROPERTY_MULTI_SELECT`,
`SWITCH`, `MAPPING`, `SECRET`.

Flatten helper:

```js
function flattenSettings(schema) {
  const out = {};
  for (const field of schema || []) {
    if (field && field.name) {
      out[field.name] = field.value ?? field.defaultValue ?? null;
    }
  }
  return out;
}
```

`OBJECT_*_SELECT` values may be a string name or an object with `name` /
`internalName` — normalize before API calls.

## Inbound routes

`src/app/inbound/<name>.json`:

```json
{
  "name": "catch",
  "authMode": "SHARED_SECRET",
  "enqueue": true,
  "serverlessFunction": { "name": "catch" }
}
```

Public URL shape (after deploy):

`POST /api/v2/public/apps/{appUuid}/inbound/{name}?companyUuid={companyUuid}`

Header: `X-Caraer-Inbound-Secret: <sharedSecret>`.

Set `sharedSecret` before production traffic; `validate` warns if missing.

## Schedules

Six-field cron (sec min hour dom mon dow), example every 12 hours:

```json
{
  "name": "heartbeat",
  "schedule": "0 0 */12 * * *",
  "enabled": true,
  "serverlessFunction": { "name": "heartbeat" }
}
```

## App bars

Action locations can use SERVERLESS without `iframeUrl`:

- `RECORD_PREVIEW`, `RECORD_OVERVIEW`, `RECORD_DETAIL`, `TOOL_BAR`, `TRAIT_BAR`

Wire `webhook.serverlessFunction.name` to a local function folder name.

## Node handler skeleton

```js
exports.handler = async (req, res) => {
  try {
    const body =
      typeof req.body === "string"
        ? JSON.parse(req.body || "{}")
        : req.body || {};
    // ...
    return res.status(200).json({ ok: true });
  } catch (err) {
    return res.status(500).json({
      ok: false,
      error: String(err && err.message ? err.message : err),
    });
  }
};
```

## Python handler skeleton

```python
def handler(request):
    body = request.get("body") if isinstance(request, dict) else {}
    if isinstance(body, str):
        import json
        body = json.loads(body or "{}")
    return {"statusCode": 200, "body": {"ok": True}}
```

## Useful CLI

```bash
caraer apps current
caraer apps validate
caraer apps push --dry-run
caraer apps push --deploy
caraer apps status
caraer apps logs --follow
caraer apps state get
caraer apps jobs list
caraer apps connections list
caraer apps test --function <name> --record <uuid>
caraer apps dev --invoke-schedule <schedule-name>
caraer skill install --project
```
