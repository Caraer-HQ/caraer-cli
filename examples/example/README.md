# Example

Reference Caraer app on the default `2026.2.1` source layout. Use this as a
guide; `caraer apps init` still creates a smaller starter with the same
folders.

This app is **private** (`privateApp: true` in `caraer.json`). Push installs
it on the selected company. It is not a marketplace listing.

If you already have a `2026.2` app (folders + JSON), `caraer apps push`
offers to rewrite it to this layout (default yes). Or run
`caraer apps upgrade` without deploying. See
[docs/platform_versioning.md](../../docs/platform_versioning.md).

## What it covers

| Piece | Where |
| --- | --- |
| Named functions | `src/app/functions/hello-world.js`, `due-date.js` |
| Shared helpers | `src/app/shared/index.js` (`require("../shared")`) |
| Settings list | `src/app/settings.yaml` (`section` cards) |
| Record-created webhook | `record.<setting:target_object>.created` on `hello-world` |
| HTTP webhook | `src/app/webhooks/candidate-updated.yaml` (POST, no function) |
| Due-date webhook | `due-date.js`: `record.<setting:due_date.objectName>.date_due.<setting:due_date.propertyName>` |
| Property scope | `records.<setting:due_date.objectName>.property.<setting:due_date.propertyName>.all` |
| Inbound | `src/app/inbound/echo.js` |
| Schedule | `src/app/schedules/heartbeat.js` |
| App bars | `src/app/appbars/ping.js` (every location) and `list-dialog-options.js` |
| Lifecycle | `src/app/lifecycle/*.js` |
| CMS module | `src/app/modules/hello_world/hello_world.astro` (`fields` mixes field objects and `{ group, fields }`) |
| Installation SQL | `POST .../installation/db` from install |

`records.<setting:target_object>.all` grants access to the object the installer
picked. `records.<setting:due_date.objectName>.property.<setting:due_date.propertyName>.all`
grants read and write for that one property. Mapping scopes stay on the object,
`records.<setting:field_map.objectName>.all`. See [docs/webhooks.md](../../docs/webhooks.md).

## Layout

```text
example/
  caraer.json
  src/app/
    app.caraer.yaml
    settings.yaml
    functions/{hello-world,due-date}.js
    appbars/{ping,list-dialog-options}.js
    shared/index.js
    lifecycle/{install,update,rotate,uninstall}.js
    inbound/echo.js
    schedules/heartbeat.js
    webhooks/candidate-updated.yaml
    modules/hello_world/hello_world.astro
```

## Quick start

```bash
cd examples/example
caraer auth login
caraer company select <company-uuid>
caraer apps select .
caraer apps validate
caraer apps push --dry-run
caraer apps push
```

`caraer apps push` creates the private app if `appUuid` is still empty, deploys
the functions, publishes the CMS module, and installs on the selected company.

### Required install settings

The installer must pick:

1. **Record object** (`target_object`) — hello-world listens to
   `record.<that object>.created`.
2. **Due date** (`due_date`) — an object + date property (`filterPropertyTypes:
   [date]`). due-date listens to `record.<object>.date_due.<property>` with
   `triggerOffsetSeconds: 0` (fires when the date is due).

**Field map** is optional. It shows a mapping setting and
`records.<setting:field_map.objectName>.all`. No webhook uses it.

Install from the Caraer app page, or let `push` open the install flow.

## What you see in Caraer

Open the app after install.

**Webhooks** lists the **company copies**, not the token templates:

| Title | Topic after a candidate / availability_date install |
| --- | --- |
| App installed | `app.installed` |
| App uninstalled | `app.uninstalled` |
| Credentials rotated | `app.rotated` |
| App updated | `app.updated` |
| Candidate created | `record.candidate.created` |
| Candidate updated | `record.candidate.updated` (HTTP, `webhooks/candidate-updated.yaml`) |
| Availability date due | `record.candidate.date_due.availability_date` |
| Example ping (and the other bars) | `app.bar.triggered` |

Each row shows a `USER_FRIENDLY` format chip. Source still has
`record.<setting:target_object>.created` and `label: "Record created"`. Caraer
writes the concrete topic and a resolved title on the company copy. An empty
setting means no copy, so that webhook is not listed and is not scheduled.

**App bars** shows the record / tool / trait bars from `appbars/ping.js`.

**Modules** (CMS v2 companies only) lists **Hello world**, even before the app
is installed. CMS v1 companies do not get this tab.

In `caraer apps local` (and the CMS page builder) click the heading or body
in the preview. The matching sidebar field focuses. That uses
`data-caraer-field` on the module markup.

## Delete vs uninstall

- **Uninstall** removes this company's install and leaves the app.
- **Delete** (`caraer apps delete --yes`) removes a private app owned by the
  company that created it. Public marketplace apps cannot be deleted this way.

## Try inbound

After push and install:

```bash
curl -X POST "$INBOUND_URL?companyUuid=$COMPANY_UUID" \
  -H "Content-Type: application/json" \
  -d '{"hello":"caraer"}'
```

`$INBOUND_URL` is

`https://api.caraer.com/api/v2/public/apps/{appUuid}/inbound/echo`

on the production profile (`caraer.json` `appUuid` is filled after the first
push). This route uses `authMode: NONE` so you can try it without a secret.

## Local

```bash
caraer apps local dev
caraer apps local test --function hello-world --sample-only
caraer apps local dev --invoke-schedule heartbeat
```
