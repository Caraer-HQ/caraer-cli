# Caraer Apps — reference

Companion to [SKILL.md](SKILL.md). Read when implementing handlers or wiring
marketplace modules.

## Auth methods

| `authMethod` | Use when | Notes |
|--------------|----------|-------|
| `API_KEY` | Installers get a long-lived API key (optional UI field) | Typical for integrations |
| `OAUTH2` | Install uses Caraer OAuth app flow | Set `oauthRedirectUris` |

Both methods inject a short-lived `inst_…` `installationToken` into webhook,
lifecycle, and app-bar payloads (about 1 hour). That token is the runtime
Bearer. It is not the API key.

Set `hideApiKeyField: true` (CLI scaffold default) to hide the installation API
key from the Caraer UI. Use `false` only when installers must copy the key.

Public apps require both `brandmark` (square SVG URL, top-level) and
`details.image` (marketplace logo SVG URL). Private apps may omit them.

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

Set `waitUntilComplete: true` on `lifecycle/install.json` (and `update.json` if
settings save must show hook-written mappings) so the install request waits for
the function and returns filled settings. Default is fire-and-forget.

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
`SWITCH`, `MAPPING`, `FILE`, `MULTI_FILE`, `SECRET`.

Use `caraer apps add setting` for the interactive picker (includes object /
property selects). For `SINGLE_SELECT` / `MULTI_SELECT` choose static
`options[]` or dynamic `optionsSource`.

`FILE` lets the installer upload one file; the stored value is the file key.
`MULTI_FILE` lets them upload several; the stored value is a list of keys.
Resolve a key to a download URL from a function with
`GET {caraerApiBase}/v2/files/?key=<value>` (already-absolute URLs pass through).

### Settings sections (UI layout)

`settingsSchema` stays a flat list of fields (values, `visibleWhen`,
`optionsSource.dependsOn`, webhook payloads). Optional `settingsSections`
only groups those fields into installer cards.

```yaml
settingsSchema:
  - name: candidate_mapping
  - name: parse_on_cv_change
  - name: work_experience_mapping

settingsSections:
  - title: Candidate
    subtitle: Map CV fields and parsing behavior
    settings:
      - candidate_mapping
      - parse_on_cv_change
  - title: Work experience
    subtitle: Map Affinda work history to your objects
    settings:
      - work_experience_mapping
```

Modular files under `src/app/settings-sections/` (sorted, files win on title
slug):

```json
{
  "title": "Candidate",
  "subtitle": "Map CV fields and control automatic reparsing",
  "settings": ["candidate_mapping", "parse_on_cv_change"]
}
```

Rules:

- Omit `settingsSections` to keep the current single "Settings" card.
- Card order is the array / filename order. Caraer wraps them automatically
  (1–3 columns). Do not define rows, columns, or spans.
- Unassigned `settingsSchema` fields appear in a final **Other settings** card.
- `caraer apps validate` errors on unknown or duplicate field names; unassigned
  fields are a warning.
- Runtime payloads still send the flat `settingsSchema` only.

### Conditional visibility (`visibleWhen`)

A field is shown, required and submitted only while **all** of its conditions
hold. Use it for progressive settings instead of asking for everything up front.

```yaml
- name: custom_work_experience_mapping
  label: Custom mapping for work experience
  type: SWITCH
  defaultValue: false
- name: work_experience_mapping
  type: MAPPING
  visibleWhen:
    - field: custom_work_experience_mapping
      operator: EQUALS          # default when omitted
      value: true
```

Operators: `EQUALS`, `NOT_EQUALS`, `IN`, `NOT_IN` (list value), `IS_SET`,
`IS_NOT_SET` (no value). Comparison is loose, so a switch matches `true` and
`"true"`.

- `visibleWhen` controls **presentation and validation**; `optionsSource.dependsOn`
  controls **when option lists reload**. They are independent.
- A field whose controlling field is itself hidden is hidden too.
- Hidden fields are not required, their value is dropped from the saved
  configuration, and their options loader is not called.
- Conditions may reference fields declared later in the schema, but not the field
  itself.

Non-interactive scaffold:

```bash
caraer apps add setting work_experience_mapping --type MAPPING \
  --visible-when 'custom_work_experience_mapping:EQUALS:true'
```

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

## Record webhook topics

`src/app/webhooks/<name>.json` declares one topic each:

| Topic | Fires on |
|-------|----------|
| `record.<object>.created` / `.updated` / `.deleted` | any change to a record |
| `record.<object>.property_changed.<property>` | one property's value changing |
| `record.<object>.date_due.<property>` | a date property coming due |
| `record.<object>.formsubmission[.<form>]` | a form submission |
| `record.<object>.relation_created` / `_updated` / `_deleted`[`.<relation>`] | relation changes |

`<object>` is lower case. Object and property scoping lives entirely in the topic
string — there is no separate filter block.

When the object or property is chosen at **install** time, register the webhook
from a lifecycle hook instead of declaring it locally:

```js
const functionUuid = await resolveFunctionUuidByName(ctx, "cv-changed");
await caraerFetch(ctx, `/v2/apps/${ctx.appUuid}/webhooks`, {
  method: "POST",
  body: JSON.stringify({
    topic: `record.${objectName.toLowerCase()}.property_changed.${propertyName}`,
    deliveryMode: "SERVERLESS",
    webhookFormat: "USER_FRIENDLY",
    serverlessFunction: { uuid: functionUuid },
  }),
});
```

List with `POST /v2/apps/{appUuid}/webhooks/index` and remove stale topics on
`app.updated` / `app.uninstalled`.

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

- `RECORD_PREVIEW`, `RECORD_OVERVIEW`, `RECORD_TRAIT`, `RECORD_DETAIL`, `TOOL_BAR`, `TRAIT_BAR`

Wire `webhook.serverlessFunction.name` to a local function folder name.

### Action dialogs

`RECORD_PREVIEW`, `RECORD_OVERVIEW`, and `RECORD_TRAIT` are actions. Give the bar its own
`settingsSchema` and Caraer shows it as a dialog before triggering the webhook —
that is how an action collects input (including a `FILE` upload):

```yaml
appBars:
  - location: RECORD_OVERVIEW
    label: Upload CV
    actionLabel: Parse CV
    webhook:
      topic: app.bar.triggered
      deliveryMode: SERVERLESS
      serverlessFunction:
        name: upload-cv
    settingsSchema:
      - name: cv_file
        label: CV
        type: FILE
        required: true
```

In the handler the dialog values arrive as **`appBarSettingsValues`** (flat
`name → value`) and `appBarSettingsSchema`. `settingsSchema` always carries the
app's *installation* settings, for both record events and app bars:

```js
const dialog = body.appBarSettingsValues || {};
const ctx = buildCtx(body);   // ctx.settings = installation settings
```

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

## Required scopes

`requiredScopes` may mix concrete scopes, macros (`records.candidate.all`,
`tools.forms.all`), and **setting placeholders**:

```yaml
requiredScopes:
  - tools.objects_schemas.write
  - records.<candidate_mapping>.all
  - records.<candidate_mapping>.properties_all
  - records.<candidate_mapping>.relations_all
```

`<fieldName>` is replaced from the installation setting. Object-select fields
use the selected object name. Mapping fields use `mappingValue.objectName`.
Empty mappings grant no extra record scopes. Scopes update when the installer
saves settings.

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
