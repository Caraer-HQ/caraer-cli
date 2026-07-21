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
