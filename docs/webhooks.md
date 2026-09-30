# Webhooks

A webhook fires when something happens in Caraer: a record is created, a
property changes, a form is submitted, or a relation is added. Delivery is
either a function in this app or an HTTP POST to a URL you own.

On `2026.2.1` a **serverless** webhook lives on the function that should run:

```js
exports.manifest = {
  webhooks: [{
    topic: "record.<setting:target_object>.created",
    label: "Record created",
    webhookFormat: "USER_FRIENDLY",
  }],
};
```

`label` is the title on the app's Webhooks tab. The CLI fills it from the
topic when you omit it (`record.candidate.created` → **Candidate created**).
`webhookFormat: USER_FRIENDLY` is the normal payload. The CLI also defaults
it on push. A webhook created without a format shows a **LEGACY** chip in
the UI. `RAW` is the platform event as stored.

An **HTTP** webhook is one YAML file under `src/app/webhooks/`:

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/Caraer-HQ/caraer-app-schemas/main/schemas/webhook.caraer.schema.json
topic: record.candidate.updated
deliveryMode: HTTP
url: https://example.com/hooks/caraer
webhookFormat: USER_FRIENDLY
enabled: true
label: Candidate updated
```

`2026.2` still uses one JSON file under `src/app/webhooks/` for both modes.

## What the company list shows

A topic may contain a setting or trait placeholder
(`record.<setting:target_object>.created`). Caraer keeps that template on the
app and writes a **company copy** with the concrete topic when the app is
installed or settings are saved.

On the app's Webhooks tab you see the company copy:

- Title: the resolved label (**Candidate created**, **Availability date due**)
- Metadata: the concrete topic (`record.candidate.created`)
- Chips: delivery mode and format (`USER_FRIENDLY`)

The token template stays in your source. It is not listed once a copy exists.
An empty setting means no copy, so nothing is listed and nothing is
scheduled.

## Add one

```bash
caraer apps add webhook --topic record.<setting:target_object>.created --function hello-world
```

On `2026.2.1` that writes (or updates) `src/app/functions/hello-world.js`
and puts the topic on `exports.manifest.webhooks`. HTTP delivery writes
`src/app/webhooks/<topic>.yaml` instead:

```bash
caraer apps add webhook --mode HTTP --topic record.candidate.updated --url https://example.com/hooks/caraer
```

On `2026.2` both modes write `src/app/webhooks/*.json`.

`deliveryMode` is `SERVERLESS` (call a function in this app) or `HTTP` (POST
to a URL you own). The function receives the event as `req.body`. It is not
nested under `payload`. Lifecycle hooks use a different envelope; see
[functions](functions.md).

## What the function receives

A record webhook (`webhookFormat: USER_FRIENDLY`) looks like this. The
record is `body.record.record`. `body.record.relations` is present only when
the webhook lists `includeRelations`.

```json
{
  "event": {
    "type": "Created",
    "timestamp": 1710000000000,
    "correlationId": "…",
    "propertyName": "email",
    "previousValue": "old@example.com",
    "newValue": "new@example.com"
  },
  "record": {
    "record": {
      "uuid": "…",
      "objectName": "candidate",
      "properties": { "email": "new@example.com", "name": "Ada" }
    },
    "relations": {}
  },
  "user": {
    "type": "user",
    "uuid": "…",
    "email": "ada@example.com",
    "firstname": "Ada",
    "lastname": "Lovelace",
    "companyUuid": "…"
  },
  "context": { "companyUuid": "…" },
  "appUuid": "…",
  "companyUuid": "…",
  "companyName": "Acme",
  "caraerApiBase": "https://api.caraer.com/api",
  "installationToken": "inst_…",
  "settingsSchema": [
    { "name": "display_name", "type": "SINGLE_LINE", "value": "Hello" }
  ],
  "scopes": ["records.candidate.all"],
  "secrets": {},
  "connections": []
}
```

`event.type` is `Created`, `Updated`, `Deleted`, `property_changed`,
`date_due`, `relation_created`, `relation_updated`, or `relation_deleted`.
`propertyName`, `previousValue`, and `newValue` are set for property and
date-due events. Relation events also set `relationName`, `fromRecord`,
`toRecord`, `fromRecordUuid`, and `toRecordUuid`. Form submissions set
`formName`.

`settingsSchema` is the installation settings, each field with its stored
`value`. Flatten it with `name → value`. `installationToken` is the
short-lived Bearer for `{caraerApiBase}`.

An app-bar click (`app.bar.triggered`) is a flat body. Dialog answers are
`appBarSettingsValues`. `settingsSchema` is still the installation settings,
not the dialog.

```json
{
  "event": "app.bar.triggered",
  "timestamp": 1710000000000,
  "appUuid": "…",
  "appName": "layout_v21",
  "appLabel": "Layout v21",
  "appBarUuid": "…",
  "appBarLabel": "Layout v21 ping",
  "location": "RECORD_OVERVIEW",
  "recordUuid": "…",
  "object": "candidate",
  "viewId": "…",
  "trait": "user",
  "companyUuid": "…",
  "companyName": "Acme",
  "userUuid": "…",
  "installationToken": "inst_…",
  "caraerApiBase": "https://api.caraer.com/api",
  "appBarSettingsValues": { "note": "Hello", "priority": "high" },
  "appBarSettingsSchema": [
    { "name": "note", "type": "SINGLE_LINE", "value": "Hello" }
  ],
  "settingsSchema": [
    { "name": "display_name", "type": "SINGLE_LINE", "value": "Hello" }
  ],
  "scopes": []
}
```

`recordUuid` and `object` are the open record. `viewId` and `trait` are set
when that location has them. `viewData` is the overview selection when the
bar is `RECORD_OVERVIEW`.

## Topics

Object and property names in the topic are lower case. There is no separate
filter object.

| Topic | When it fires |
|-------|----------------|
| `record.<object>.created` | A record is created |
| `record.<object>.updated` | A record is updated |
| `record.<object>.deleted` | A record is deleted |
| `record.<object>.property_changed.<property>` | One property changes |
| `record.<object>.date_due.<property>` | A date property comes due |
| `record.<object>.formsubmission[.<form>]` | A form is submitted |
| `record.<object>.relation_created` | A relation is created |
| `record.<object>.relation_updated` | A relation is updated |
| `record.<object>.relation_deleted` | A relation is deleted |

Append `.<relation>` when only one relation type should fire.

`<object>` and `<property>` can be a literal name (`candidate`, `email`) or the
same setting/trait placeholders as `requiredScopes`:

```js
exports.manifest = {
  webhooks: [{
    topic: "record.<setting:target_object>.created",
    label: "Record created",
    webhookFormat: "USER_FRIENDLY",
  }],
};
```

Caraer writes a company webhook with the concrete topic when the app is
installed or its settings are saved. The template keeps the placeholder. Pair
it with `records.<setting:target_object>.all` on `requiredScopes`. An empty
setting means no company copy. `record.<trait:user>.created` expands to every
object with that trait.

A path after the field name reads one key. A property single-select stores
`objectName` and `propertyName`. A mapping stores `mappingValue.objectName`.
A row is selected by its `fieldName`, so `field.email` is that key's target.

```js
exports.manifest = {
  webhooks: [{
    topic: "record.<setting:due_date.objectName>.date_due.<setting:due_date.propertyName>",
    label: "Due date",
    webhookFormat: "USER_FRIENDLY",
    triggerOffsetSeconds: 0,
    scheduleDirection: "BEFORE",
  }],
};
```

`date_due` requires `triggerOffsetSeconds` (including `0` for “when the date
is due”). When the company picks candidate / `availability_date`, Caraer
stores `record.candidate.date_due.availability_date` on that company's
webhook, titles it **Availability date due**, and builds the schedule from
the copy. The template is not scheduled. A missing key removes the company
copy, so nothing is scheduled. A fixed property stays literal:
`record.<setting:target_object>.date_due.interview_date`.

`<setting:field_map.objectName>` reads the mapping's object. A row is addressed
by its `fieldName`: `<setting:field_map.email>` is the property, record, or
literal the installer mapped to the `email` key.
`<setting:field_map.mappingValue.items.propertyName>` still reads every mapped
property. Mapping scopes stay on the object,
`records.<setting:field_map.objectName>.all`. A property single-select can
grant that property:
`records.<setting:due_date.objectName>.property.<setting:due_date.propertyName>.all`.

[`examples/layout-v21`](../examples/layout-v21) declares
`record.<setting:target_object>.created` on `hello-world` and the due-date path
on `due-date`.

## App bars

Record buttons are webhooks too. On `2026.2.1` declare the bar on a function
in `src/app/appbars/`. There is no `app-bars.yaml` and no
`serverlessFunction` reference:

```js
exports.manifest = {
  appBars: [
    {
      name: "ping_overview",
      location: "RECORD_OVERVIEW",
      label: "Ping",
      actionLabel: "Ping",
    },
  ],
};
```

Caraer sends topic `app.bar.triggered` to that function. Locations:
`RECORD_PREVIEW`, `RECORD_OVERVIEW`, `RECORD_TRAIT`, `RECORD_DETAIL`,
`TOOL_BAR`, `TRAIT_BAR`. `2026.2` still uses `src/app/app-bars/*.json`.

`RECORD_PREVIEW`, `RECORD_OVERVIEW`, and `RECORD_TRAIT` can show a dialog
first. Put that dialog's fields on the bar's own `settingsSchema`. The same
field types as installation settings work here: text, switch, selects
(static `options` or `optionsSource`), object and property pickers,
`MAPPING`, `FILE`, `MULTI_FILE`, `IMAGE`, `COLOR`, `SECRET`, `REPEATABLE`,
and `ACTION`. `visibleWhen`, `advanced`, `hidden`, `required`, `helpText`,
and `defaultValue` apply per field. `icon` is a Font Awesome name such as
`bolt`.

In the function the dialog arrives as `appBarSettingsValues`.
`settingsSchema` on the body is still the installation settings.
[`examples/layout-v21`](../examples/layout-v21/src/app/appbars/ping.js)
declares one bar per location and every dialog field on `ping_overview`.
`list-dialog-options.js` in that folder loads the Channel options.
