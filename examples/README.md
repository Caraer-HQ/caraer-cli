# Example

The Caraer app example is [`example`](example/README.md). It uses the default
`2026.2.1` layout: named files, settings, inbound, a schedule, app bars, a CMS
module, and setting-targeted record webhooks.

```bash
cd examples/example
caraer auth login
caraer company select <company-uuid>
caraer apps select .
caraer apps push
```

For a blank app, prefer `caraer apps init` instead of copying this folder.
