# Scheduled functions

A schedule runs on a cron. On `2026.2.1` it is a code file:

```js
// src/app/schedules/heartbeat.js
export const handler = async (req, res) => { res.status(200).json({ ok: true }); };
export const manifest = { schedule: "0 0 */12 * * *", enabled: true };
```

`2026.2` still uses one JSON file under `src/app/schedules/` that points at a
function by name.

## Add one

```bash
caraer apps add schedule
caraer apps add schedule heartbeat --cron "0 0 */6 * * *"
```

On `2026.2.1` that writes `src/app/schedules/<name>.js` (see
[`examples/example`](../examples/example/src/app/schedules/heartbeat.js)).
The filename is the schedule name and the handler. `--function` is only
used on `2026.2`, where the command writes JSON that points at a function.

Without flags, the command asks for a preset or a custom expression, the
function, a description, and whether it starts enabled.

A name with a hyphen is stored with underscores (`renew-watch` becomes
`renew_watch`). `--invoke-schedule` matches that stored name.

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
