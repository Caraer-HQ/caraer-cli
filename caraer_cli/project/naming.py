"""Shared snake_case names for CMS modules and settings fields."""

from __future__ import annotations

import re

MODULE_NAME_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
MODULE_NAME_RULE = "snake_case (a-z, 0-9, underscore)"


def normalize_module_name(raw: str) -> str:
    """Collapse a typed name into lowercase snake_case segments."""
    return re.sub(r"[^a-z0-9]+", "_", raw.strip().lower()).strip("_")


def require_module_name(raw: str) -> str:
    """Normalize ``raw`` and reject names that are still not valid snake_case."""
    name = normalize_module_name(raw)
    if not name or not MODULE_NAME_RE.match(name):
        shown = raw.strip() or name
        raise ValueError(f"name '{shown}' must be {MODULE_NAME_RULE}.")
    return name
