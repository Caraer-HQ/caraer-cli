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

## Publish the CLI

The `publish.yml` workflow builds the wheel and source distribution, then
uploads them to PyPI using Trusted Publishing. Set up a GitHub Actions
[Trusted Publisher](https://docs.pypi.org/trusted-publishers/adding-a-publisher/)
under the Caraer organization's existing `caraer-cli` project settings on PyPI.

- GitHub owner: `Caraer-HQ`
- Repository: `caraer-cli`
- Workflow filename: `publish.yml`
- GitHub environment: `pypi`

For a release, bump the version in `pyproject.toml` and
`caraer_cli/__init__.py`, refresh `uv.lock`, and update the changelog. After
CI passes on the release commit, push a new matching tag such as `v0.1.18`.
A manual dispatch must also select a release tag. Verify the workflow and
install the exact version from PyPI in a fresh environment. After the first
successful trusted release, remove the legacy GitHub `API_TOKEN` secret and
revoke the old PyPI token if it was used only for this workflow.

After upload, the release job records the distributions and notifies
`Caraer-HQ/caraer-developer`. Store a fine-grained GitHub token as the
`DOCS_DISPATCH_TOKEN` Actions repository secret in `caraer-cli`. Give it
access to `caraer-developer` with **Contents: Read and write**. The release
receipt is still recorded if the notification is skipped or fails.

## Guidelines

- Keep the CLI thin: talk to Caraer REST APIs; do not require GCP credentials.
- Treat `caraer.json` + `src/app/` as a stable public contract.
- Prefer clear error messages over silent failures.
- Do not commit local scratch apps, `.caraer/` state, or `.env` files.
- Add unit tests for command/API behavior changes under `tests/unit/`.

## Security

Report vulnerabilities privately — see [SECURITY.md](SECURITY.md).
