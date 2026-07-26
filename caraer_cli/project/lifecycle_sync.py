"""Discover / write lifecycle webhook configs under src/app/lifecycle/."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from caraer_cli.project.paths import lifecycle_dir
from caraer_cli.project.schema import ProjectConfig

# filename stem → (manifest key, expected topic)
LIFECYCLE_HOOKS: dict[str, tuple[str, str]] = {
    "install": ("installWebhook", "app.installed"),
    "uninstall": ("uninstallWebhook", "app.uninstalled"),
    "rotate": ("rotateWebhook", "app.rotated"),
    "update": ("updateWebhook", "app.updated"),
}

MANIFEST_KEY_TO_FILE = {
    manifest_key: stem for stem, (manifest_key, _) in LIFECYCLE_HOOKS.items()
}

LOCAL_LIFECYCLE_KEYS = (
    "topic",
    "deliveryMode",
    "url",
    "description",
    "enabled",
    "webhookFormat",
    "secret",
    "serverlessFunction",
)


def sanitize_lifecycle(item: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key in LOCAL_LIFECYCLE_KEYS:
        if key in item and item[key] is not None:
            payload[key] = item[key]
    sf = payload.get("serverlessFunction")
    if isinstance(sf, dict):
        cleaned: dict[str, Any] = {}
        if sf.get("name"):
            cleaned["name"] = sf["name"]
        elif sf.get("uuid"):
            cleaned["uuid"] = sf["uuid"]
        if cleaned:
            payload["serverlessFunction"] = cleaned
        else:
            payload.pop("serverlessFunction", None)
    return payload


def discover_local_lifecycle(
    root: Path, config: ProjectConfig
) -> dict[str, dict[str, Any]]:
    """Return manifest_key → sanitized webhook dict for present lifecycle files."""
    base = lifecycle_dir(root, config.srcDir)
    if not base.is_dir():
        return {}
    found: dict[str, dict[str, Any]] = {}
    for stem, (manifest_key, _topic) in LIFECYCLE_HOOKS.items():
        path = base / f"{stem}.json"
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            found[manifest_key] = sanitize_lifecycle(data)
    return found


def write_lifecycle_files(
    root: Path, config: ProjectConfig, hooks: dict[str, dict[str, Any] | None]
) -> int:
    """Write lifecycle/*.json from manifest hook objects. Clears missing files."""
    base = lifecycle_dir(root, config.srcDir)
    base.mkdir(parents=True, exist_ok=True)
    count = 0
    for stem, (manifest_key, expected_topic) in LIFECYCLE_HOOKS.items():
        path = base / f"{stem}.json"
        raw = hooks.get(manifest_key)
        if not isinstance(raw, dict) or not raw:
            if path.exists():
                path.unlink()
            continue
        sanitized = sanitize_lifecycle(raw)
        if not sanitized.get("topic"):
            sanitized["topic"] = expected_topic
        path.write_text(json.dumps(sanitized, indent=2) + "\n", encoding="utf-8")
        count += 1
    return count


def resolve_lifecycle_functions(
    webhook: dict[str, Any],
    *,
    fn_by_name: dict[str, str],
    strict: bool = True,
) -> dict[str, Any] | None:
    out = dict(webhook)
    sf = out.get("serverlessFunction")
    if not isinstance(sf, dict):
        return out
    if sf.get("uuid"):
        out["serverlessFunction"] = {"uuid": sf["uuid"]}
        return out
    name = sf.get("name")
    if name and name in fn_by_name:
        out["serverlessFunction"] = {"uuid": fn_by_name[name]}
        return out
    if name:
        if strict:
            raise ValueError(
                f"Lifecycle webhook references function '{name}' but no UUID is known. "
                "Push functions first."
            )
        return None
    return out
