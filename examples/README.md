# Examples

## hello-function

Minimal app folder for `caraer apps` commands (platform V2 / `2026.2`).

```bash
caraer auth login --email you@example.com
caraer company select <company-uuid>

# Option A: scaffold a new app (recommended)
caraer apps init --name hello-function --label "Hello Function"
cd hello-function

# Option B: use this checked-in example folder against an existing app
# cd examples/hello-function
# caraer apps select <app-uuid>

caraer apps push --deploy
caraer apps status
caraer apps logs
caraer apps dev
```

For the legacy per-function Cloud Functions model, use
`caraer apps init --platform 2026.1` (or set `"platformVersion": "2026.1"` in
`caraer.json`) instead of this example’s default.

## gmail-sync

One-way Gmail → Caraer sync example (OAuth provider, inbound Pub/Sub route,
watch renewal schedule, history sync job). See `gmail-sync/README.md`.

```bash
export GMAIL_OAUTH_CLIENT_ID=...
export GMAIL_OAUTH_CLIENT_SECRET=...
caraer apps select examples/gmail-sync
caraer apps push --deploy
```

## todo-sync-python

Same shape as `hello-function`, but with `runtime: python312` and a
`sync-todo` function that reads installation state. See
`todo-sync-python/README.md`.

```bash
cd examples/todo-sync-python
caraer apps select .
caraer apps push --deploy
caraer apps dev
```
