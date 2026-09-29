# Scheduled functions

A schedule runs a function on a cron. One file under `src/app/schedules/` is
one schedule.

## Add one

```bash
caraer apps add schedule
caraer apps add schedule heartbeat --function my-action --cron "0 0 */6 * * *"
```

Without flags, the command asks for a preset or a custom expression, the
function, a description, and whether it starts enabled.

```json
{
  "name": "heartbeat",
  "schedule": "0 0 */6 * * *",
  "enabled": true,
  "description": "Run every 6 hours",
  "serverlessFunction": { "name": "my-action" }
}
```

The `name` field is what `--invoke-schedule` matches. A name with a hyphen
is stored with underscores (`renew-watch` becomes `renew_watch`) while the
file stays `schedules/renew-watch.json`.

## Cron

The expression is Spring-style, 5 or 6 fields:

```text
second minute hour day-of-month month day-of-week
```

Seconds are optional. `0 0 */6 * * *` is second 0, minute 0, every 6th hour.
`0 0 */12 * * *` is every 12 hours.

The handler receives a [function body](functions.md). Type it as
`SchedulePayload` from `@caraer/client` or `caraer-client`.

## Try it locally

```bash
caraer apps local dev --invoke-schedule heartbeat
```

A disabled schedule (`"enabled": false`) is kept in the project and is not
invoked after push.
