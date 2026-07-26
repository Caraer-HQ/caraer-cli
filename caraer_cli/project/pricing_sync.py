"""Discover / write modular pricingPlans files under src/app/pricing/."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from caraer_cli.project.paths import pricing_dir
from caraer_cli.project.schema import ProjectConfig

LOCAL_PRICING_KEYS = (
    "uuid",
    "name",
    "title",
    "description",
    "pricingType",
    "pricePerUnit",
    "unit",
    "freeUnits",
    "freeUnitsPeriod",
    "tiers",
)


def _slug(value: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "plan"


def pricing_filename(item: dict[str, Any]) -> str:
    key = str(item.get("name") or item.get("title") or "plan")
    return f"{_slug(key)}.json"


def sanitize_pricing(item: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key in LOCAL_PRICING_KEYS:
        if key in item and item[key] is not None:
            payload[key] = item[key]
    return payload


def pricing_identity(item: dict[str, Any]) -> str:
    return str(item.get("name") or item.get("title") or "").strip().lower()


def discover_local_pricing(
    root: Path, config: ProjectConfig
) -> list[tuple[Path, dict[str, Any]]]:
    base = pricing_dir(root, config.srcDir)
    if not base.is_dir():
        return []
    found: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(base.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and (data.get("title") or data.get("name")):
            found.append((path, sanitize_pricing(data)))
    return found


def write_pricing_files(
    root: Path, config: ProjectConfig, items: list[dict[str, Any]]
) -> int:
    base = pricing_dir(root, config.srcDir)
    base.mkdir(parents=True, exist_ok=True)
    for existing in base.glob("*.json"):
        existing.unlink()
    count = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        sanitized = sanitize_pricing(item)
        if not pricing_identity(sanitized):
            continue
        path = base / pricing_filename(sanitized)
        path.write_text(json.dumps(sanitized, indent=2) + "\n", encoding="utf-8")
        count += 1
    return count
