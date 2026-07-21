from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


def load_structured_file(path: str) -> dict[str, Any]:
    content = Path(path).read_text(encoding="utf-8")
    suffix = Path(path).suffix.lower()
    if suffix in (".yaml", ".yml"):
        payload = yaml.safe_load(content)
    else:
        payload = json.loads(content)
    if not isinstance(payload, dict):
        raise ValueError("Input file must contain a JSON/YAML object at the root.")
    return payload


def parse_patch(value: str) -> dict[str, Any]:
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("Patch must be a JSON object.")
    return parsed


def deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in patch.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged
