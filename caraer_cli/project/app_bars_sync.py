"""Discover / write modular appBars files under src/app/app-bars/."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from caraer_cli.project.paths import app_bars_dir
from caraer_cli.project.schema import ProjectConfig

LOCAL_APP_BAR_KEYS = (
    "uuid",
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

ACTION_BASED_LOCATIONS = frozenset({"RECORD_PREVIEW", "RECORD_OVERVIEW"})


def _slug(value: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "app-bar"


def app_bar_filename(item: dict[str, Any]) -> str:
    location = _slug(str(item.get("location") or "bar"))
    label = _slug(str(item.get("label") or "app-bar"))
    return f"{location}-{label}.json"


def app_bar_identity(item: dict[str, Any]) -> str:
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
    base = app_bars_dir(root, config.srcDir)
    if not base.is_dir():
        return []
    found: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(base.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("label") and data.get("location"):
            found.append((path, sanitize_app_bar(data)))
    return found


def write_app_bars_files(
    root: Path, config: ProjectConfig, items: list[dict[str, Any]]
) -> int:
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


def resolve_app_bar_functions(
    item: dict[str, Any],
    *,
    fn_by_name: dict[str, str],
    strict: bool = True,
) -> dict[str, Any] | None:
    out = dict(item)
    out.pop("uuid", None)
    webhook = out.get("webhook")
    if not isinstance(webhook, dict):
        return out
    webhook = dict(webhook)
    webhook.pop("uuid", None)
    sf = webhook.get("serverlessFunction")
    if isinstance(sf, dict):
        if sf.get("uuid"):
            webhook["serverlessFunction"] = {"uuid": sf["uuid"]}
        else:
            name = sf.get("name")
            if name and name in fn_by_name:
                webhook["serverlessFunction"] = {"uuid": fn_by_name[name]}
            elif name:
                if strict:
                    raise ValueError(
                        f"App bar references function '{name}' but no UUID is known. "
                        "Push functions first."
                    )
                return None
    out["webhook"] = webhook
    return out
