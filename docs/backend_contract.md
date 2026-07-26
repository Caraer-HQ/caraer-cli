# Backend Contract Reference (App Lifecycle CLI)

This document maps the backend API surface currently used by the Python CLI.

## Authentication

- `POST /api/v2/auth/login`
- `POST /api/v2/auth/logout`
- `GET /api/v2/auth/me`
- `GET /api/v2/auth/companies`

Headers:

- `Authorization: Bearer <token>`
- `X-Caraer-Company-Uuid: <company_uuid>` on most protected endpoints

## App lifecycle endpoints

- `POST /api/v2/apps/index?type=private|public|native`
- `GET /api/v2/apps/{uuid}`
- `POST /api/v2/apps/public`
- `GET /api/v2/apps/public/{uuid}`
- `PUT /api/v2/apps/public/{uuid}`

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
- `POST /api/v2/apps/{uuid}/migrate-v2` — body `{runtime?}`

## App integration runtime

- `GET/PUT /api/v2/apps/{appUuid}/installation/state`
- `GET/PUT/DELETE /api/v2/apps/{appUuid}/installation/state/{key}`
- `GET /api/v2/apps/{appUuid}/installation/secrets`
- `PUT/DELETE /api/v2/apps/{appUuid}/installation/secrets/{name}`
- `POST /api/v2/apps/{appUuid}/installation/jobs`
- `GET /api/v2/apps/{appUuid}/installation/jobs/{jobId}`
- `GET /api/v2/apps/{appUuid}/installation/connections`
- `DELETE /api/v2/apps/{appUuid}/installation/connections/{provider}`
- CRUD `/api/v2/apps/{appUuid}/schedules`
- CRUD `/api/v2/apps/{appUuid}/inbound-routes`
- CRUD `/api/v2/apps/{appUuid}/external-oauth-providers`
- `POST /api/v2/public/apps/{appUuid}/inbound/{routeName}`
- `GET /api/v2/public/apps/{appUuid}/oauth/{provider}/authorize`
- `GET /api/v2/public/apps/{appUuid}/oauth/{provider}/callback`

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
- `POST /api/v2/developer-projects/{projectUuid}/builds/{buildUuid}/deploy` — body `{target}`
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

## Response envelope assumptions

Success envelopes:

- `{"message":"Success","data":...}`
- paginated endpoints also include `total`, `page`, `perPage`, `lastPage`

Error envelopes:

- `{"message":"...","status":<int>,"errors":[...],"roles":[...],"scopes":[...]}`

The CLI normalizes these in `caraer_cli.errors.parse_api_error`.
