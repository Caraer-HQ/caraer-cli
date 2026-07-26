# Examples

## webhook-inbox

Catch HTTP webhooks into installation state. Covers inbound routes, settings,
lifecycle hooks, an app bar, and a schedule.

```bash
cd examples/webhook-inbox
caraer auth login
caraer company select <company-uuid>
caraer apps select .
caraer apps push --deploy
caraer apps install
```

See [`webhook-inbox/README.md`](webhook-inbox/README.md).

For a blank app, prefer `caraer apps init` instead of copying this folder.
