"""Discover / write modular appBars files under src/app/app-bars/."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from caraer_cli.project.paths import app_bars_dir, app_bars_yaml_path
from caraer_cli.project.schema import ProjectConfig

LOCAL_APP_BAR_KEYS = (
    "uuid",
    "name",
    "location",
    "label",
    "tooltipLabel",
    "description",
    "actionLabel",
    "iframeUrl",
    "icon",
    "settingsSchema",
    "webhook",
)

ACTION_BASED_LOCATIONS = frozenset(
    {"RECORD_PREVIEW", "RECORD_OVERVIEW", "RECORD_TRAIT"}
)


def _slug(value: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "app-bar"


def app_bar_filename(item: dict[str, Any]) -> str:
    location = _slug(str(item.get("location") or "bar"))
    label = _slug(str(item.get("label") or "app-bar"))
    return f"{location}-{label}.json"


def app_bar_identity(item: dict[str, Any]) -> str:
    name = str(item.get("name") or "").strip().lower()
    if name:
        return name
    location = str(item.get("location") or "").strip().upper()
    label = str(item.get("label") or "").strip().lower()
    return f"{location}|{label}"


def _sanitize_webhook(webhook: Any) -> dict[str, Any] | None:
    if not isinstance(webhook, dict):
        return None
    cleaned: dict[str, Any] = {}
    for key in (
        "uuid",
        "topic",
        "deliveryMode",
        "url",
        "description",
        "enabled",
        "webhookFormat",
        "serverlessFunction",
    ):
        if key in webhook and webhook[key] is not None:
            cleaned[key] = webhook[key]
    sf = cleaned.get("serverlessFunction")
    if isinstance(sf, dict):
        sf_out: dict[str, Any] = {}
        if sf.get("name"):
            sf_out["name"] = sf["name"]
        elif sf.get("uuid"):
            sf_out["uuid"] = sf["uuid"]
        if sf_out:
            cleaned["serverlessFunction"] = sf_out
        else:
            cleaned.pop("serverlessFunction", None)
    return cleaned or None


def sanitize_app_bar(item: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key in LOCAL_APP_BAR_KEYS:
        if key not in item or item[key] is None:
            continue
        if key == "webhook":
            webhook = _sanitize_webhook(item[key])
            if webhook:
                payload["webhook"] = webhook
        else:
            payload[key] = item[key]
    return payload


def discover_local_app_bars(
    root: Path, config: ProjectConfig
) -> list[tuple[Path, dict[str, Any]]]:
    if config.is_layout_v21():
        path = app_bars_yaml_path(root, config.srcDir)
        if not path.is_file():
            return []
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        items = data.get("appBars") if isinstance(data, dict) else data
        found: list[tuple[Path, dict[str, Any]]] = []
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and item.get("label") and item.get("location"):
                    found.append((path, sanitize_app_bar(item)))
        return found
    base = app_bars_dir(root, config.srcDir)
    if not base.is_dir():
        return []
    found = []
    for path in sorted(base.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("label") and data.get("location"):
            found.append((path, sanitize_app_bar(data)))
    return found


def write_app_bars_files(
    root: Path, config: ProjectConfig, items: list[dict[str, Any]]
) -> int:
    if config.is_layout_v21():
        import yaml

        path = app_bars_yaml_path(root, config.srcDir)
        path.parent.mkdir(parents=True, exist_ok=True)
        bars = []
        for item in items:
            if not isinstance(item, dict):
                continue
            sanitized = sanitize_app_bar(item)
            if not app_bar_identity(sanitized).strip("|"):
                continue
            bars.append(sanitized)
        path.write_text(
            yaml.safe_dump({"appBars": bars}, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        return len(bars)
    base = app_bars_dir(root, config.srcDir)
    base.mkdir(parents=True, exist_ok=True)
    for existing in base.glob("*.json"):
        existing.unlink()
    count = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        sanitized = sanitize_app_bar(item)
        if not app_bar_identity(sanitized).strip("|"):
            continue
        path = base / app_bar_filename(sanitized)
        path.write_text(json.dumps(sanitized, indent=2) + "\n", encoding="utf-8")
        count += 1
    return count


def stamp_app_bar_identities(
    local_bars: list[Any],
    remote_bars: list[Any],
) -> list[dict[str, Any]]:
    """Copy remote bar and webhook UUIDs onto local bars matched by location|label."""
    remote_by_identity: dict[str, dict[str, Any]] = {}
    for item in remote_bars:
        if not isinstance(item, dict):
            continue
        key = app_bar_identity(item)
        if not key.strip("|"):
            continue
        remote_by_identity[key] = item
    stamped: list[dict[str, Any]] = []
    for item in local_bars:
        if not isinstance(item, dict):
            continue
        copied = dict(item)
        remote = remote_by_identity.get(app_bar_identity(copied))
        if remote:
            if remote.get("uuid"):
                copied["uuid"] = remote["uuid"]
            local_webhook = copied.get("webhook")
            remote_webhook = remote.get("webhook")
            if isinstance(local_webhook, dict) and isinstance(remote_webhook, dict):
                if remote_webhook.get("uuid"):
                    webhook = dict(local_webhook)
                    webhook["uuid"] = remote_webhook["uuid"]
                    copied["webhook"] = webhook
        stamped.append(copied)
    return stamped


def persist_app_bar_identities(
    root: Path,
    config: ProjectConfig,
    remote_bars: list[Any],
) -> None:
    """Write remote bar/webhook UUIDs back into modular app-bar files.

    YAML manifests are left untouched so comments stay intact. The next push
    still stamps UUIDs from the live app before update.
    """
    if not remote_bars:
        return
    for path, item in discover_local_app_bars(root, config):
        stamped_items = stamp_app_bar_identities([item], remote_bars)
        if not stamped_items:
            continue
        stamped = stamped_items[0]
        if stamped == item:
            continue
        path.write_text(json.dumps(stamped, indent=2) + "\n", encoding="utf-8")


def resolve_app_bar_functions(
    item: dict[str, Any],
    *,
    fn_by_name: dict[str, str],
    strict: bool = True,
) -> dict[str, Any] | None:
    out = dict(item)
    webhook = out.get("webhook")
    if not isinstance(webhook, dict):
        return out
    webhook = dict(webhook)
    sf = webhook.get("serverlessFunction")
    if isinstance(sf, dict):
        name = sf.get("name")
        uuid = sf.get("uuid")
        if uuid:
            if not name:
                for candidate_name, candidate_uuid in fn_by_name.items():
                    if candidate_uuid == uuid:
                        name = candidate_name
                        break
            ref: dict[str, str] = {"uuid": str(uuid)}
            if name:
                ref["name"] = name
            webhook["serverlessFunction"] = ref
        else:
            if name and name in fn_by_name:
                webhook["serverlessFunction"] = {
                    "uuid": fn_by_name[name],
                    "name": name,
                }
            elif name:
                if strict:
                    raise ValueError(
                        f"App bar references function '{name}' but no UUID is known. "
                        "Push functions first."
                    )
                return None
    out["webhook"] = webhook
    return out
