# App lifecycle hooks

Caraer apps can run code when a company **installs**, **updates**, **uninstalls**, or
**rotates** credentials. On `2026.2.1` each hook is a named file under
`src/app/lifecycle/`. The file is a normal [serverless function](functions.md)
with `exports.manifest` (or Python `manifest = {...}`).

`2026.2` still uses `src/app/lifecycle/*.json` plus a matching
`functions/on-<hook>/` folder.

## Quick start

`caraer apps init` always scaffolds all four hooks:

```text
src/app/lifecycle/{install,uninstall,rotate,update}.js
```

Edit the stubs, then push:

```bash
caraer apps push
```

To recreate a single hook (e.g. after deleting it):

```bash
caraer apps add lifecycle-hook uninstall
```

## Files

| File | Manifest field | Topic | Default label |
|------|----------------|-------|---------------|
| `lifecycle/install.js` | `installWebhook` | `app.installed` | App installed |
| `lifecycle/uninstall.js` | `uninstallWebhook` | `app.uninstalled` | App uninstalled |
| `lifecycle/rotate.js` | `rotateWebhook` | `app.rotated` | Credentials rotated |
| `lifecycle/update.js` | `updateWebhook` | `app.updated` | App updated |

```js
// src/app/lifecycle/install.js
exports.handler = async (req, res) => {
  const body = typeof req.body === "string" ? JSON.parse(req.body || "{}") : req.body || {};
  res.status(200).json({ ok: true, event: body.event || null });
};

exports.manifest = {
  lifecycle: "install",
  topic: "app.installed",
  label: "App installed",
  waitUntilComplete: true,
};
```

`label` is the title on the app's Webhooks tab. The CLI fills it from the
topic when you omit it.

Set `waitUntilComplete: true` when the installer UI must show settings the hook
writes (object mappings, workspace ids). The install / settings-save request then
invokes the function on the request thread and returns the filled app. Leave it
off (the default) for fire-and-forget hooks that can finish after the UI returns.

HTTP receivers are also supported (`deliveryMode: HTTP`, `url`) on `2026.2`
JSON hooks.

On `caraer apps push`, the CLI merges these files into the app manifest.

## When hooks fire

| Event | When |
|-------|------|
| **Installed** | First install for a company |
| **Updated** | Re-save of an already-installed app (settings / scopes / filters) |
| **Uninstalled** | Company uninstalls the app |
| **Rotated** | Installation token / credentials rotate |

Uninstall removes one company's install. It does not delete the app.
`caraer apps delete` deletes a **private** app owned by the active company.

## Payload (SERVERLESS / HTTP)

Approximate body delivered to your handler:

```json
{
  "event": "Installed",
  "timestamp": 0,
  "appUuid": "...",
  "appName": "...",
  "appLabel": "...",
  "privateApp": false,
  "authMethod": "API_KEY",
  "userUuid": "...",
  "companyUuid": "...",
  "installationToken": "...",
  "oauthConnected": false,
  "settingsSchema": [
    {
      "name": "pubsub_topic",
      "label": "Gmail Pub/Sub topic",
      "type": "SINGLE_LINE",
      "value": "projects/.../topics/...",
      "hasValue": true
    }
  ],
  "scopes": []
}
```

Notes:

- `event` is the domain event simple name (`Installed`, `Updated`, `Uninstalled`, `Rotated`).
- `installationToken` is present for `API_KEY` apps (use it for installation state/secrets APIs).
- `settingsSchema` includes filled `value` / `hasValue` for the installation.
- **Updated** also includes booleans such as `settingsChanged`, `scopesChanged`, `filtersChanged`, `userSettingsChanged`.
- When USER-scoped settings are saved, `userSettingsChanged` is true and `userUuid` identifies the user. Payload may include `userSettings` (map of userUuid → field values) and `connections` (external OAuth connection instances with access tokens).

## Reading settings in a Node handler

```js
function flattenSettings(schema) {
  const out = {};
  for (const field of schema || []) {
    if (field && field.name) out[field.name] = field.value;
  }
  return out;
}

exports.handler = async (req, res) => {
  const body = typeof req.body === "string" ? JSON.parse(req.body || "{}") : req.body || {};
  const settings = flattenSettings(body.settingsSchema);
  // settings.pubsub_topic, body.installationToken, body.companyUuid, …
  res.status(200).json({ ok: true });
};
```

Install and update are also where you subscribe to a record object the
installer chose. Declare the placeholder on the function:

```js
webhooks: [{
  topic: "record.<setting:target_object>.created",
  label: "Record created",
}],
```

Caraer writes the concrete topic on that company's webhook when the app is
installed or settings are saved. The company list shows that copy (for example
`record.candidate.created` titled **Candidate created**), not the token
template. A path reads one key, such as
`<setting:due_date.propertyName>` or the mapping row `<setting:field_map.email>`.
POST a webhook from lifecycle only when the topic cannot be expressed as a
setting or trait reference. See [Webhooks](webhooks.md).

## What is not a lifecycle webhook today

OAuth **Connect** / **Disconnect** (`ConnectionConnected` / `ConnectionRevoked`) refresh
company config over websockets but are **not** delivered to `installWebhook` /
`updateWebhook`. That includes Connect during the post-install dialog (or Skip):
install still fires `app.installed` only for the install itself, not for OAuth.
Use the Connections card + runtime `body.connections` / legacy secrets
(`{provider}_access_token` for COMPANY providers). For USER-owned providers,
provision after the user saves USER-scoped settings (`userSettingsChanged`).

## Related marketplace modules

| Folder / field | Command | Purpose |
|----------------|---------|---------|
| `settings.yaml` field list (or `settings/*.json` on 2026.2) | `caraer apps add setting` | Installation settings |
| `section` / `sectionSubtitle` on a field (or `settings-sections/*.json` on 2026.2) | edit settings | Installer setting cards |
| `appBars` on a file in `src/app/appbars/` | edit that file | Record / tool / trait bars |

Validate with `caraer apps validate`.
