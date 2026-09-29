# Layout 2026.2.1

Full Caraer app on the default `2026.2.1` source layout. Use this as a
reference; `caraer apps init` still creates a smaller starter.

## What it covers

| Piece | Where |
| --- | --- |
| Named functions | `src/app/functions/hello-world.js` |
| Shared helpers | `src/app/shared/index.js` (`require("../shared")`) |
| Settings list | `src/app/settings.yaml` (`section` cards) |
| Setting-targeted webhook | `record.<setting:target_object>.created` on `hello-world` |
| Inbound | `src/app/inbound/echo.js` |
| Schedule | `src/app/schedules/heartbeat.js` |
| App bar | `appBars` on `src/app/functions/hello-world.js` (every location, every dialog field) |
| Lifecycle | `src/app/lifecycle/*.js` |
| CMS module | `src/app/modules/hello_world/hello_world.astro` |
| Installation SQL | `POST .../installation/db` from install |

`records.<setting:target_object>.all` grants access. The same token on the
webhook topic (`record.<setting:target_object>.created`) selects which
object fires the function. See [docs/webhooks.md](../../docs/webhooks.md).

## Layout

```text
layout-v21/
  caraer.json
  src/app/
    app.caraer.yaml
    settings.yaml
    functions/hello-world.js
    shared/index.js
    lifecycle/{install,update,rotate,uninstall}.js
    inbound/echo.js
    schedules/heartbeat.js
    modules/hello_world/hello_world.astro
```

## Quick start

```bash
cd examples/layout-v21
caraer auth login
caraer company select <company-uuid>
caraer apps select .
caraer apps validate
caraer apps push
```

Then install the private app on that company, pick a record object, and:

```bash
curl -X POST "$INBOUND_URL?companyUuid=$COMPANY_UUID" \
  -H "Content-Type: application/json" \
  -d '{"hello":"caraer"}'
```

`$INBOUND_URL` is

`POST /api/v2/public/apps/{appUuid}/inbound/echo`

on the API host for the profile.

## Local

```bash
caraer apps local dev
caraer apps local test --function hello-world --sample-only
caraer apps local dev --invoke-schedule heartbeat
```
