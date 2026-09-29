# Inbound routes

An inbound route is a public HTTP endpoint that calls a function. Use it when
an outside system (Gmail, a payment provider, your own service) needs to reach
the app. One file under `src/app/inbound/` is one route.

## Add one

```bash
caraer apps add inbound gmail-push --function my-action --auth SHARED_SECRET
```

```json
{
  "name": "gmail-push",
  "authMode": "SHARED_SECRET",
  "enqueue": true,
  "enabled": true,
  "serverlessFunction": { "name": "my-action" }
}
```

`name` is the path segment. `enqueue: true` runs the function as an
installation job instead of on the request thread.

## URL

After the app is pushed and installed:

```text
POST /api/v2/public/apps/{appUuid}/inbound/{name}?companyUuid={companyUuid}
```

The host is the API for that environment (`https://api.caraer.com` in
production).

## Auth

| `authMode` | Caller must |
|------------|-------------|
| `NONE` | Nothing. Only for endpoints that carry their own signature check. |
| `SHARED_SECRET` | Send header `X-Caraer-Inbound-Secret` with the route's `sharedSecret`. |
| `INSTALLATION_TOKEN` | Send the installation Bearer token. |

`caraer apps validate` warns when `SHARED_SECRET` has no `sharedSecret`. Set
the secret before real traffic. Do not commit it; put it in a local file that
stays out of git, or set it on the installed app.

The handler receives the inbound body on the normal
[function payload](functions.md).
