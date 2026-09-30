"""Human titles for webhook topics that have no author label."""

from __future__ import annotations


def label_for_topic(topic: str | None) -> str | None:
    """Return the list title for a topic. Placeholders stay out of the title."""
    text = (topic or "").strip()
    if not text:
        return None
    parts = _segments(text)
    if not parts:
        return None
    if parts[0] == "app" or text.startswith("app."):
        if len(parts) >= 3 and parts[1] == "bar":
            return "App bar"
        action = parts[1] if len(parts) > 1 else ""
        named = {
            "installed": "App installed",
            "uninstalled": "App uninstalled",
            "updated": "App updated",
            "rotated": "Credentials rotated",
        }
        if action in named:
            return named[action]
        return f"App {action.replace('_', ' ')}" if action else None
    if len(parts) < 3 or parts[0] != "record":
        return None
    action = parts[2]
    extra = parts[3] if len(parts) > 3 else None
    if action == "date_due":
        prop = _titled(extra)
        return f"{prop} due" if prop else "Due date"
    if action == "property_changed":
        prop = _titled(extra)
        return f"{prop} changed" if prop else "Property changed"
    if action == "formsubmission":
        return "Form submitted"
    if action in {"relation_created", "relation_updated", "relation_deleted"}:
        return "Relation " + action.removeprefix("relation_")
    verb = action.replace("_", " ")
    if not verb:
        return None
    object_label = _titled(parts[1])
    return f"{object_label} {verb}" if object_label else f"Record {verb}"


def _segments(topic: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for char in topic:
        if char == "<":
            depth += 1
        elif char == ">" and depth:
            depth -= 1
        if char == "." and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    if current:
        parts.append("".join(current))
    return parts


def _titled(segment: str | None) -> str | None:
    if not segment or "<" in segment:
        return None
    text = segment.strip().replace("_", " ").replace("-", " ")
    if not text:
        return None
    return text[0].upper() + text[1:]
