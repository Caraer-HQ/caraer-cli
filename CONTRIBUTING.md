# Contributing

This repository is the Caraer developer CLI. External contributions may be
limited; if you have a fix or improvement, open an issue or pull request and we
will review it.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
./scripts/install.sh
```

## Checks

Install Node.js 22 and the TypeScript compiler used by CI. The scaffold
contract test reads `src/contract.ts` directly from `PUBLISHED_RUNTIME_TAG`
in a `caraer-cms-runtime` checkout. CI checks out that tag automatically.
Locally, use a sibling checkout or set `CARAER_CMS_RUNTIME_ROOT` to another
checkout containing the pinned tag. The working tree can stay on any branch.

```bash
npm install --global typescript@5.6.3
./scripts/ci.sh
# or: pytest tests/unit -q
```

## Guidelines

- Keep the CLI thin: talk to Caraer REST APIs; do not require GCP credentials.
- Treat `caraer.json` + `src/app/` as a stable public contract.
- Prefer clear error messages over silent failures.
- Do not commit local scratch apps, `.caraer/` state, or `.env` files.
- Add unit tests for command/API behavior changes under `tests/unit/`.

## Security

Report vulnerabilities privately — see [SECURITY.md](SECURITY.md).
