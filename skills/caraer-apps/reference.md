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

Lifecycle, schedule, and inbound calls use this envelope. A record webhook
does not: `req.body` is the event itself (`event.type`, `record.record`).
An app bar is flat, with `event: "app.bar.triggered"` and
`appBarSettingsValues`. Full examples are in the CLI
`docs/webhooks.md`.

Approximate lifecycle JSON body (also wrapped as `req.body` for Node):

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
`SWITCH`, `MAPPING`, `FILE`, `MULTI_FILE`, `IMAGE`, `COLOR`, `SECRET`.

CMS modules also allow `FORM_SINGLE_SELECT` and `REPEATABLE`. They reject
`SECRET` and `ACTION`. See the `caraer-cms` skill.

Use `caraer apps add setting` for the interactive picker (includes object /
property selects). For `SINGLE_SELECT` / `MULTI_SELECT` choose static
`options[]` or dynamic `optionsSource`.

`FILE` lets the installer upload one file; the stored value is the file key.
`MULTI_FILE` lets them upload several; the stored value is a list of keys.
Resolve a key to a download URL from a function with
`GET {caraerApiBase}/v2/files/?key=<value>` (already-absolute URLs pass through).

### Settings sections (UI layout)

`settings.yaml` is a single-level list of fields (values, `visibleWhen`,
`optionsSource.dependsOn`, webhook payloads). Optional `section` /
`sectionSubtitle` on a field groups it into an installer card. Assemble/push
still emit backend `settingsSchema` (section keys stripped) and
`settingsSections`.

```yaml
- name: candidate_mapping
  type: MAPPING
  section: Candidate
  sectionSubtitle: Map CV fields and parsing behavior
- name: parse_on_cv_change
  type: SWITCH
  section: Candidate
- name: work_experience_mapping
  type: MAPPING
  section: Work experience
  sectionSubtitle: Map Affinda work history to your objects
```

On 2026.2, modular files under `src/app/settings-sections/` (sorted, files win
on title slug) still group JSON settings:

```json
{
  "title": "Candidate",
  "subtitle": "Map CV fields and control automatic reparsing",
  "settings": ["candidate_mapping", "parse_on_cv_change"]
}
```

Rules:

- Omit `section` to keep a field schema-only (no section card).
- Card order is first-seen `section` order. Caraer wraps them automatically
  (1–3 columns). Do not define rows, columns, or spans.
- Unassigned fields appear in a final **Other settings** card.
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
`{ "options": [{ "name", "label", "helpText?", "preview?" }, ...] }`.

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

On `2026.2.1` declare a static topic on `exports.manifest.webhooks`. On
`2026.2` use one JSON file under `src/app/webhooks/`.

The object (and property) may be a literal name or a setting/trait
placeholder, the same tokens as `requiredScopes`:

```js
exports.manifest = {
  webhooks: [{ topic: "record.<setting:target_object>.created" }],
};
```

Caraer writes the concrete topic on that company's webhook when the app is
installed or settings are saved. Pair it with `records.<setting:target_object>.all`.
An empty setting means no company copy. A path reads one key:
`record.<setting:due_date.objectName>.date_due.<setting:due_date.propertyName>`
becomes `record.candidate.date_due.interview_date`. A mapping object is
`<setting:field_map.objectName>`. A row is `<setting:field_map.email>`, the
`fieldName` key. Caraer stores the
concrete topic on that company's webhook when settings are saved, and
schedules that copy. The template still needs `triggerOffsetSeconds`.

| Topic | Fires on |
|-------|----------|
| `record.<object>.created` / `.updated` / `.deleted` | any change to a record |
| `record.<object>.property_changed.<property>` | one property's value changing |
| `record.<object>.date_due.<property>` | a date property coming due |
| `record.<object>.formsubmission[.<form>]` | a form submission |
| `record.<object>.relation_created` / `_updated` / `_deleted`[`.<relation>`] | relation changes |

`<object>` is lower case. Object and property scoping lives entirely in the topic
string — there is no separate filter block.

Prefer a static placeholder topic on the function. Lifecycle POST is only
needed when the topic cannot be expressed as a setting or trait reference.

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

On `2026.2.1` declare `appBars` on the function that should run (no
`add app-bar` scaffold and no `app-bars.yaml`). Caraer sends
`app.bar.triggered` to that function.

- `RECORD_PREVIEW`, `RECORD_OVERVIEW`, `RECORD_TRAIT`, `RECORD_DETAIL`, `TOOL_BAR`, `TRAIT_BAR`

`2026.2` still uses one JSON file under `src/app/app-bars/` with
`webhook.serverlessFunction.name`.

### Action dialogs

`RECORD_PREVIEW`, `RECORD_OVERVIEW`, and `RECORD_TRAIT` are actions. Give the bar its own
`settingsSchema` and Caraer shows it as a dialog before triggering the function —
that is how an action collects input (including a `FILE` upload):

```js
exports.manifest = {
  appBars: [
    {
      location: "RECORD_OVERVIEW",
      label: "Upload CV",
      actionLabel: "Parse CV",
      settingsSchema: [
        { name: "cv_file", label: "CV", type: "FILE", required: true },
      ],
    },
  ],
};
```

Field types match installation settings: `SINGLE_LINE`, `MULTI_LINE`,
`SWITCH`, `SINGLE_SELECT`, `MULTI_SELECT`, `RECORD_SINGLE_SELECT`,
`RECORD_MULTI_SELECT`, `OBJECT_SINGLE_SELECT`, `OBJECT_MULTI_SELECT`,
`PROPERTY_SINGLE_SELECT`, `PROPERTY_MULTI_SELECT`, `MAPPING`, `FILE`,
`MULTI_FILE`, `IMAGE`, `COLOR`, `SECRET`, `REPEATABLE`, and `ACTION`.
Use `options` or `optionsSource`, plus `visibleWhen`, `advanced`, `hidden`,
`required`, `helpText`, `defaultValue`, and `filterTraits`. `icon` is a
Font Awesome name (`bolt`). Iframe locations take `iframeUrl` and no dialog.

`examples/layout-v21` `hello-world.js` declares every location and every
dialog field on `ping_overview`.

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
`tools.forms.all`), and **typed placeholders**:

```yaml
requiredScopes:
  - tools.objects_schemas.write
  - records.<setting:candidate_mapping>.all
  - records.<setting:candidate_mapping>.properties_all
  - records.<setting:candidate_mapping>.relations_all
  - records.<trait:user>.all
  - records.<trait:user>.properties_all
```

| Form | Meaning |
|---|---|
| `<fieldName>` | Setting value (still supported) |
| `<setting:fieldName>` | Same setting value, preferred for new apps |
| `<setting:field.key>` | One key on that value (`objectName`, `propertyName`, `propertyNames`, `mappingValue.objectName`) |
| `records.<setting:field.objectName>.property.<setting:field.propertyName>.all` | Read and write for the property a property single-select stored. `propertyNames` grants each selected property. |
| `<trait:traitName>` | Every object with that trait (e.g. `user` → employee) |

Object-select fields use the selected object name. Mapping fields use
`mappingValue.objectName`. Empty settings or unmatched traits grant no extra
record scopes. Setting and trait scopes update when the installer saves.

The same tokens work in webhook `topic` strings
(`record.<setting:field>.created`). See
[Record webhook topics](#record-webhook-topics).

## Useful CLI

```bash
caraer apps current
caraer apps validate
caraer apps push --dry-run
caraer apps push
caraer apps status
caraer apps local logs --follow
caraer apps state get
caraer apps jobs list
caraer apps connections list
caraer apps local test --function <name> --record <uuid>
caraer apps local dev --invoke-schedule <schedule-name>
caraer skill install --project
```
