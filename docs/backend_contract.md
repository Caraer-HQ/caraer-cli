# Backend Contract Reference (App Lifecycle CLI)

This document maps the backend API surface currently used by the Python CLI.

## Authentication

- `POST /api/v2/auth/login`
- `POST /api/v2/auth/logout`
- `GET /api/v2/auth/me`
- `GET /api/v2/auth/companies`
- `POST /api/v2/auth/device/start` — device-code login; returns `{deviceCode, userCode, verificationUri, expiresIn, interval}`
- `POST /api/v2/auth/device/poll` — body `{deviceCode}` → `{status: pending|approved|expired|denied}` (+ tokens when approved)
- `GET /api/v2/auth/device/approve?userCode=` — browser HTML login/approve UI (public)
- `POST /api/v2/auth/device/approve` — authenticated JSON; body `{userCode}`
- `POST /api/v2/auth/refresh` — body `{refreshToken}` → new access (+ rotated refresh) token

Headers:

- `Authorization: Bearer <token>`
- `X-Caraer-Company-Uuid: <company_uuid>` on most protected endpoints
- `X-Request-Id` / `X-Correlation-Id` (optional); echoed on responses and included as `requestId` in error envelopes

## App lifecycle endpoints

- `POST /api/v2/apps/index?type=private|public|native`
- `GET /api/v2/apps/{uuid}`
- `POST /api/v2/apps/public`
- `GET /api/v2/apps/public/{uuid}`
- `PUT /api/v2/apps/public/{uuid}`
- `POST /api/v2/apps/private`
- `PUT /api/v2/apps/private/{uuid}`
- `POST /api/v2/apps/{uuid}/install`

## Publish and review

- `POST /api/v2/apps/public/{uuid}/submit`
- `POST /api/v2/apps/public/{uuid}/review`

## App webhooks

- `POST /api/v2/apps/{appUuid}/webhooks/index`
- `GET /api/v2/apps/{appUuid}/webhooks/formats`
- `GET /api/v2/apps/{appUuid}/webhooks/events`
- `GET /api/v2/apps/{appUuid}/webhooks/{webhookUuid}`
- `POST /api/v2/apps/{appUuid}/webhooks`
- `PUT /api/v2/apps/{appUuid}/webhooks/{webhookUuid}`
- `DELETE /api/v2/apps/{appUuid}/webhooks/{webhookUuid}`
- `POST /api/v2/apps/{appUuid}/webhooks/test`
- `POST /api/v2/apps/{appUuid}/webhooks/test/{webhookUuid}/{recordUuid}/{eventType}`

## App runtime (V2)

- `GET /api/v2/apps/{appUuid}/runtime/logs?since=&limit=` — shared container logs
- `GET /api/v2/apps/{appUuid}/runtime/logs/stream` — SSE stream of runtime logs (`text/event-stream`)
- `POST /api/v2/apps/{uuid}/migrate-v2` — body `{runtime?}` (ops/retry; V1→V2 batch
  migration is `run-migration apps-platform-v2 up` on the Java backend)

## App integration runtime

- `GET/PUT /api/v2/apps/{appUuid}/installation/state`
- `GET/PUT/DELETE /api/v2/apps/{appUuid}/installation/state/{key}`
- `GET /api/v2/apps/{appUuid}/installation/secrets`
- `PUT/DELETE /api/v2/apps/{appUuid}/installation/secrets/{name}`
- `POST /api/v2/apps/{appUuid}/installation/jobs`
- `GET /api/v2/apps/{appUuid}/installation/jobs/{jobId}`
- `GET /api/v2/apps/{appUuid}/installation/connections`
- `DELETE /api/v2/apps/{appUuid}/installation/connections/{providerOrConnectionId}`
- `POST /api/v2/apps/{appUuid}/installation/oauth/{provider}/start`
- `PUT /api/v2/apps/{appUuid}/installation/settings`
- `PUT /api/v2/apps/{appUuid}/installation/settings/user`
- CRUD `/api/v2/apps/{appUuid}/schedules`
- CRUD `/api/v2/apps/{appUuid}/inbound-routes`
- CRUD `/api/v2/apps/{appUuid}/external-oauth-providers`
- `POST /api/v2/public/apps/{appUuid}/inbound/{routeName}`
- `GET /api/v2/public/apps/{appUuid}/oauth/{provider}/authorize` (COMPANY providers; prefer authenticated start for USER)
- `GET /api/v2/public/apps/{appUuid}/oauth/{provider}/callback`

## CMS modules

- `POST /api/v2/apps/{appUuid}/cms-modules/package` — body
  `{package, version, modules, tarballBase64, filename?}`. The API publishes
  the tarball with the host registry token and replaces the catalog. Developers
  do not set `CARAER_REGISTRY_*`.
- `PUT /api/v2/apps/{appUuid}/cms-modules` — catalog only (operator / retry)
- `GET /api/v2/apps/{appUuid}/cms-modules`

## App serverless functions

- `POST /api/v2/apps/{appUuid}/serverless-functions/index`
- `GET /api/v2/apps/{appUuid}/serverless-functions/{uuid}`
- `POST /api/v2/apps/{appUuid}/serverless-functions`
- `PUT /api/v2/apps/{appUuid}/serverless-functions/{uuid}`
- `DELETE /api/v2/apps/{appUuid}/serverless-functions/{uuid}`
- `POST /api/v2/apps/{appUuid}/serverless-functions/{uuid}/test`
- `GET /api/v2/apps/{appUuid}/serverless-functions/{uuid}/logs?since=&limit=`
- `POST /api/v2/apps/{appUuid}/serverless-functions/sample-payload`

## Developer projects (creator-only)

- `POST /api/v2/developer-projects` — body `{appUuid, name, label}`
- `GET /api/v2/developer-projects/{uuid}`
- `POST /api/v2/developer-projects/{projectUuid}/builds` — body `{archiveBase64, filename, target, version?, releaseNotes?}`
  - `version` is `MAJOR.MINOR.PATCH`; omitted → auto patch-bump (first build `0.1.0`)
  - `releaseNotes` optional string stored on the build
  - Build DTO includes `version`, `releaseNotes`
  - Project DTO includes `activeVersion` (set when a build is deployed)
- `GET /api/v2/developer-projects/{projectUuid}/builds`
- `GET /api/v2/developer-projects/{projectUuid}/builds/{buildUuid}`
- `POST /api/v2/developer-projects/{projectUuid}/builds/{buildUuid}/deploy` — body `{target, prune?}`
  - Deploy reconciles functions, webhooks, schedules, inbound routes, and external OAuth from the archive
  - `prune: true` soft-deletes remote resources absent from the archive (`resultsJson.pruned`)
- `GET /api/v2/developer-projects/{projectUuid}/deploys`

## Developer sandboxes

- `POST /api/v2/developer-sandboxes` — clones the selected company's Neo4j database
  (max **3** active sandboxes per owner company). Does **not** create a Company node;
  stores `databaseId` on `DeveloperSandbox` linked via `OWNED_BY` to the owner.
- `GET /api/v2/developer-sandboxes`
- `GET /api/v2/developer-sandboxes/{uuid}`

Headers:

- `X-Caraer-Company-Uuid` — owning (production) company; required (identity stays this company)
- `X-Caraer-Sandbox-Uuid` — optional; when set, overrides the company `databaseid` for Neo4j routing

Access rules:

- Sandbox must be owned by the company in `X-Caraer-Company-Uuid`
- Caller must have `HAS_ACCESS_TO` that owner company
- Company identity and roles are unchanged; only the Neo4j database is swapped for the request

DTO fields: `ownerCompanyUuid`, `databaseId` (no sandbox `companyUuid`).

**Isolation scope:** sandboxes isolate Neo4j graph data only. Cloud Function / V2
container runtime code is shared with production. `caraer apps push --target sandbox`
and `caraer apps release deploy --target sandbox` warn about this; use a separate app or
careful versioning when experimenting with function code.

## Response envelope assumptions

Success envelopes:

- `{"message":"Success","data":...}`
- paginated endpoints also include `total`, `page`, `perPage`, `lastPage`

Error envelopes:

- `{"message":"...","status":<int>,"errors":[...],"roles":[...],"scopes":[...]}`

The CLI normalizes these in `caraer_cli.errors.parse_api_error`.
