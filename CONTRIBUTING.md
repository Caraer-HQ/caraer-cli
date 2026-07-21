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

```bash
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
