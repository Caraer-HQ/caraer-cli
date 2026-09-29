# Webhooks

A webhook runs a function when something happens in Caraer: a record is
created, a property changes, a form is submitted, or a relation is added.
On `2026.2.1` a webhook is not its own file. The function that should run
declares it:

```js
exports.manifest = {
  webhooks: [{ topic: "record.candidate.created" }],
};
```

`2026.2` still uses one JSON file under `src/app/webhooks/`.

## Add one

```bash
caraer apps add webhook --topic record.candidate.created --function my-action
caraer apps add webhook --topic app.bar.triggered --mode HTTP --url https://example.com/hook
```

`deliveryMode` is `SERVERLESS` (call a function in this app) or `HTTP` (POST
to a URL you own).

```json
{
  "topic": "record.candidate.created",
  "deliveryMode": "SERVERLESS",
  "webhookFormat": "USER_FRIENDLY",
  "enabled": true,
  "serverlessFunction": { "name": "my-action" }
}
```

`USER_FRIENDLY` is the normal payload. `RAW` is the platform event as stored.

The handler receives a [function body](functions.md) plus the event on
`payload`. Type it as `WebhookPayload` from `@caraer/client` or
`caraer-client`.

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

When the object or property is chosen at install time, do not hard-code the
topic in `webhooks/`. Create the webhook from the install or update
[lifecycle hook](app_lifecycle.md) with
`POST {caraerApiBase}/v2/apps/{appUuid}/webhooks`, and delete stale topics
when the app is updated or uninstalled.

## App bars

Record buttons are webhooks too. Declare them on `appBars` in
`src/app/app.caraer.yaml` (there is no `add` command). Locations:
`RECORD_PREVIEW`, `RECORD_OVERVIEW`, `RECORD_TRAIT`, `RECORD_DETAIL`,
`TOOL_BAR`, `TRAIT_BAR`.

`RECORD_PREVIEW`, `RECORD_OVERVIEW`, and `RECORD_TRAIT` can show a dialog
first. Put that dialog's fields on the bar's own `settingsSchema`. In the
function they arrive as `appBarSettingsValues`. `settingsSchema` on the body
is still the installation settings.
