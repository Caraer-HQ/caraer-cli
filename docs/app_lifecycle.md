# App lifecycle hooks

Caraer apps can run code when a company **installs**, **updates**, **uninstalls**, or
**rotates** credentials. Prefer modular files under `src/app/lifecycle/` that point
at a local serverless function.

## Quick start

`caraer apps init` always scaffolds all four hooks and matching functions:

```text
src/app/lifecycle/{install,uninstall,rotate,update}.json
src/app/functions/on-{install,uninstall,rotate,update}/
```

Edit the stubs, then push:

```bash
caraer apps push --deploy
```

To recreate a single hook (e.g. after deleting it):

```bash
caraer apps add lifecycle-hook uninstall
```

## Files

| File | Manifest field | Topic |
|------|----------------|-------|
| `lifecycle/install.json` | `installWebhook` | `app.installed` |
| `lifecycle/uninstall.json` | `uninstallWebhook` | `app.uninstalled` |
| `lifecycle/rotate.json` | `rotateWebhook` | `app.rotated` |
| `lifecycle/update.json` | `updateWebhook` | `app.updated` |

SERVERLESS example:

```json
{
  "topic": "app.installed",
  "deliveryMode": "SERVERLESS",
  "enabled": true,
  "waitUntilComplete": true,
  "serverlessFunction": { "name": "on-install" }
}
```

Set `waitUntilComplete: true` when the installer UI must show settings the hook
writes (object mappings, workspace ids). The install / settings-save request then
invokes the function on the request thread and returns the filled app. Leave it
off (the default) for fire-and-forget hooks that can finish after the UI returns.

HTTP receivers are also supported (`deliveryMode: HTTP`, `url`).

On `caraer apps push`, the CLI merges these files into the public app manifest and
resolves `serverlessFunction.name` to the remote function UUID (after functions are synced).

## When hooks fire

| Event | When |
|-------|------|
| **Installed** | First install for a company |
| **Updated** | Re-save of an already-installed app (settings / scopes / filters) |
| **Uninstalled** | Company uninstalls the app |
| **Rotated** | Installation token / credentials rotate |

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
| `settingsSchema` in YAML (or `settings/*.json` with `--modular`) | `caraer apps add setting` | Installation settings |
| `settingsSections` in YAML (or `settings-sections/*.json`) | edit manifest | Installer setting cards (title, subtitle, field names) |
| `appBars` in YAML | edit manifest | Record / tool / trait bars |

Validate with `caraer apps validate`.
