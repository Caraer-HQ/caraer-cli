"""JSON Schema URLs and helpers for Caraer app config files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCHEMA_REPO_BASE = (
    "https://raw.githubusercontent.com/caraer/caraer-cli/main/schemas"
)

APP_MANIFEST_SCHEMA_URL = f"{SCHEMA_REPO_BASE}/app.caraer.schema.json"
FUNCTION_SCHEMA_URL = f"{SCHEMA_REPO_BASE}/function.caraer.schema.json"
WEBHOOK_SCHEMA_URL = f"{SCHEMA_REPO_BASE}/webhook.caraer.schema.json"
SCHEDULE_SCHEMA_URL = f"{SCHEMA_REPO_BASE}/schedule.caraer.schema.json"
INBOUND_SCHEMA_URL = f"{SCHEMA_REPO_BASE}/inbound.caraer.schema.json"
LIFECYCLE_SCHEMA_URL = f"{SCHEMA_REPO_BASE}/lifecycle.caraer.schema.json"

YAML_LANGUAGE_SERVER_COMMENT = (
    f"# yaml-language-server: $schema={APP_MANIFEST_SCHEMA_URL}"
)

SCHEMA_FILENAMES = {
    "app": "app.caraer.schema.json",
    "function": "function.caraer.schema.json",
    "webhook": "webhook.caraer.schema.json",
    "schedule": "schedule.caraer.schema.json",
    "inbound": "inbound.caraer.schema.json",
    "lifecycle": "lifecycle.caraer.schema.json",
}


def schemas_dir() -> Path | None:
    """Locate the local ``schemas/`` directory when available."""
    here = Path(__file__).resolve()
    candidates = [
        # Packaged: caraer_cli/schemas (via hatch force-include)
        here.parents[1] / "schemas",
        # Dev checkout: <repo>/schemas
        here.parents[2] / "schemas",
    ]
    for path in candidates:
        if path.is_dir() and (path / "function.caraer.schema.json").is_file():
            return path
    return None


def with_json_schema(payload: dict[str, Any], schema_url: str) -> dict[str, Any]:
    """Return a copy of payload with ``$schema`` first."""
    out: dict[str, Any] = {"$schema": schema_url}
    for key, value in payload.items():
        if key == "$schema":
            continue
        out[key] = value
    return out


def dump_json_with_schema(
    path: Path, payload: dict[str, Any], schema_url: str
) -> None:
    """Write JSON with a leading ``$schema`` field."""
    path.write_text(
        json.dumps(with_json_schema(payload, schema_url), indent=2) + "\n",
        encoding="utf-8",
    )
