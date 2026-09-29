# Examples

## layout-v21

Full default-layout (`2026.2.1`) app: named files, settings list, inbound,
schedule, app bar, CMS module, setting-targeted record webhook, installation SQL.

```bash
cd examples/layout-v21
caraer auth login
caraer company select <company-uuid>
caraer apps select .
caraer apps push
```

See [`layout-v21/README.md`](layout-v21/README.md).

## webhook-inbox

`2026.2` folder layout. Catch HTTP webhooks into installation state.

```bash
cd examples/webhook-inbox
caraer auth login
caraer company select <company-uuid>
caraer apps select .
caraer apps push
```

See [`webhook-inbox/README.md`](webhook-inbox/README.md).

For a blank app, prefer `caraer apps init` instead of copying a folder.
