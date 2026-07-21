"""Normalize API timestamps for CLI display."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

TIMESTAMP_KEYS = frozenset(
    {
        "createdAt",
        "updatedAt",
        "deletedAt",
        "activatedAt",
        "publishedAt",
        "submittedAt",
        "reviewedAt",
    }
)


def epoch_ms_to_iso(value: Any) -> str | None:
    """Convert epoch milliseconds (or seconds) to an ISO-8601 UTC string."""
    if value is None or value == "":
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z") or "+" in text[10:] or text.count("-") >= 2 and "T" in text:
            return text
        try:
            numeric = float(text)
        except ValueError:
            return text
        value = numeric
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        seconds = float(value)
        # Heuristic: values before year ~2001 in ms are treated as seconds.
        if seconds > 1e12:
            seconds = seconds / 1000.0
        dt = datetime.fromtimestamp(seconds, tz=timezone.utc)
        return dt.isoformat().replace("+00:00", "Z")
    return str(value)


def sort_key_for_timestamp(value: Any) -> float:
    """Sort key: newer first when used with reverse=True."""
    if value is None or value == "":
        return float("-inf")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        return number / 1000.0 if number > 1e12 else number
    if isinstance(value, str):
        text = value.strip()
        try:
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            return datetime.fromisoformat(text).timestamp()
        except ValueError:
            try:
                return sort_key_for_timestamp(float(text))
            except ValueError:
                return float("-inf")
    return float("-inf")


def normalize_payload(data: Any) -> Any:
    """Recursively convert timestamp fields to ISO and sort list rows by createdAt."""
    if isinstance(data, list):
        normalized = [normalize_payload(item) for item in data]
        if normalized and all(isinstance(item, dict) for item in normalized):
            if any("createdAt" in item for item in normalized):
                normalized.sort(
                    key=lambda item: sort_key_for_timestamp(item.get("createdAt")),
                    reverse=True,
                )
            elif any("activatedAt" in item for item in normalized):
                normalized.sort(
                    key=lambda item: sort_key_for_timestamp(item.get("activatedAt")),
                    reverse=True,
                )
            elif any("updatedAt" in item for item in normalized):
                normalized.sort(
                    key=lambda item: sort_key_for_timestamp(item.get("updatedAt")),
                    reverse=True,
                )
        return normalized
    if isinstance(data, dict):
        out: dict[str, Any] = {}
        for key, value in data.items():
            if key in TIMESTAMP_KEYS:
                out[key] = epoch_ms_to_iso(value)
            else:
                out[key] = normalize_payload(value)
        return out
    return data
