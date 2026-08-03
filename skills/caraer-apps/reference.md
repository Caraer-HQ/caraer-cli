# Caraer Apps — reference

Companion to [SKILL.md](SKILL.md). Read when implementing handlers or wiring
marketplace modules.

## Auth methods

| `authMethod` | Use when | Notes |
|--------------|----------|-------|
| `API_KEY` | App needs `installationToken` for state/secrets/jobs | Typical for integrations |
| `OAUTH2` | Install uses Caraer OAuth app flow | Set `oauthRedirectUris` |

Set `hideApiKeyField: true` (CLI scaffold default) to hide the installation API
key from the Caraer UI. Use `false` only when installers must copy the key.

External providers (`externalOAuthProviders`) are separate from `authMethod`.

- `connectionOwner: COMPANY` (default) — one shared connection per install;
  tokens also mirrored as `{provider}_access_token`.
- `connectionOwner: USER` — one connection per Caraer user under the company
  install; tokens arrive on `body.connections[]` (and connection-scoped secret
  keys). Prefer `POST .../installation/oauth/{provider}/start` to begin OAuth.

Settings may set `valueScope: USER` so values are saved per user
(`PUT .../installation/settings/user`) and delivered via `userSettings` /
overlay on `settingsSchema` when that user acts.

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
  "connections": [],
  "userSettings": {},
  "payload": {}
}
```

Typed helpers ship in the Caraer clients (do **not** use `caraer apps typegen`):

```ts
import type { LifecyclePayload, WebhookPayload } from "@caraer/client";
```

```python
from caraer_client import LifecyclePayload, WebhookPayload
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

Use `caraer apps add setting` for the interactive picker (includes object /
property selects). For `SINGLE_SELECT` / `MULTI_SELECT` choose static
`options[]` or dynamic `optionsSource`.

### Dynamic options (`optionsSource`)

```yaml
- name: google_calendars
  type: MULTI_SELECT
  optionsSource:
    type: SERVERLESS
    serverlessFunctionName: list-calendars
    dependsOn: []          # sibling field names; UI refetches when they change
    searchable: true
```

Scaffold the loader:

```bash
caraer apps add options-function list-calendars
# or: caraer apps add function list-calendars --template options
```

Request action is `loadSettingOptions`. Response must be
`{ "options": [{ "name", "label", "helpText?" }, ...] }`.

Sibling values are available as:
- `settingsValues` — flat `{ [fieldName]: value }` (preferred)
- `settingsSchema` — full draft fields with `value` / `defaultValue`
- `dependsOn` — echo of `optionsSource.dependsOn` when set

```js
const settings = body.settingsValues
  || Object.fromEntries(
      (body.settingsSchema || []).map((f) => [
        f.name,
        f.value ?? f.defaultValue ?? null,
      ])
    );
// const parent = settings.attendee_object; // listed in optionsSource.dependsOn
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

Spring-style 5–6 field cron (`sec min hour dom mon dow`, seconds optional).
Scaffold interactively or with flags:

```bash
caraer apps add schedule                         # wizard: presets + custom cron
caraer apps add schedule heartbeat \
  --function heartbeat \
  --cron "0 0 */12 * * *" \
  --description "12h ping"
```

Example every 12 hours:

```json
{
  "name": "heartbeat",
  "schedule": "0 0 */12 * * *",
  "enabled": true,
  "serverlessFunction": { "name": "heartbeat" }
}
```

## App bars

Define `appBars` in `app.caraer.yaml` when needed (no `add app-bar` scaffold).
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
caraer apps local logs --follow
caraer apps state get
caraer apps jobs list
caraer apps connections list
caraer apps local test --function <name> --record <uuid>
caraer apps local dev --invoke-schedule <schedule-name>
caraer skill install --project
```
