# Inbound routes

An inbound route is a public HTTP endpoint that calls a function. Use it when
an outside system (Gmail, a payment provider, your own service) needs to reach
the app. On `2026.2.1` it is a code file:

```js
// src/app/inbound/gmail-push.js
export const handler = async (req, res) => {
  const body = req.body || {};
  res.status(200).json({ ok: true, inbound: body.payload || body.body || body });
};

export const manifest = { authMode: "SHARED_SECRET", enqueue: true };
```

Keep `sharedSecret` out of the committed file; put it in installation secrets
or name it with `secretName`. `2026.2` still uses one JSON file under
`src/app/inbound/` that points at a function by name.

## Add one

```bash
caraer apps add inbound echo --auth NONE --sync
```

On `2026.2.1` that writes `src/app/inbound/<name>.js` (see
[`examples/example`](../examples/example/src/app/inbound/echo.js)).
`name` is the path segment and the handler. `enqueue: true` runs the
function as an installation job instead of on the request thread.

On `2026.2` the command still writes JSON that points at a function by name.

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
