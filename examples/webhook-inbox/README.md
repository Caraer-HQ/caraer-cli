# Webhook Inbox

Minimal Caraer Apps V2 example: catch HTTP webhooks into **installation state**.

Demonstrates inbound routes, settings, lifecycle hooks, an app bar, and a
schedule — without external OAuth.

## Layout

```text
webhook-inbox/
  caraer.json
  src/app/
    app.caraer.yaml          # identity, settings, Clear inbox app bar
    inbound/catch.json       # SHARED_SECRET → catch
    schedules/heartbeat.json # optional 12h ping via catch
    lifecycle/*.json
    functions/
      catch/                 # store payload
      clear-inbox/           # app bar wipe
      heartbeat/             # 12h schedule tick
      on-install|update|…/
```

## Quick start

```bash
cd examples/webhook-inbox
caraer auth login
caraer company select <company-uuid>
caraer apps select .
caraer apps push --deploy
caraer apps install
```

Set a `sharedSecret` on the inbound route (CLI warns until you do), then:

```bash
curl -X POST "$INBOUND_URL" \
  -H "Content-Type: application/json" \
  -H "X-Caraer-Inbound-Secret: $SECRET" \
  -d '{"hello":"caraer"}'
```

Inspect state:

```bash
caraer apps state get
```

Clear via the **Clear inbox** app bar on a record preview, or:

```bash
caraer apps local test --function clear-inbox --record <any-uuid>
```

## Settings

| Setting | Purpose |
| --- | --- |
| Inbox label | Label stored with each event |
| Max events to keep | Ring buffer size (1–100, default 20) |

## Local dev

```bash
caraer apps local dev
# in another terminal:
caraer apps local dev --invoke-schedule heartbeat
```
