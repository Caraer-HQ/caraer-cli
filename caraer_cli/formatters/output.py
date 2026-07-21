from __future__ import annotations

import json
from typing import Any

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from caraer_cli.formatters.timestamps import normalize_payload


console = Console()

# Prefer these columns first when rendering list tables.
PREFERRED_COLUMNS = (
    "version",
    "live",
    "name",
    "active",
    "uuid",
    "label",
    "title",
    "status",
    "target",
    "releaseNotes",
    "platformVersion",
    "privateApp",
    "installed",
    "runtime",
    "description",
    "base_url",
    "createdAt",
    "updatedAt",
    "activatedAt",
)


def print_data(data: Any, output: str = "table") -> None:
    data = normalize_payload(data)
    mode = (output or "table").lower()
    if mode == "json":
        console.print_json(json.dumps(data, default=str))
        return
    if mode == "yaml":
        console.print(yaml.safe_dump(data, sort_keys=False))
        return
    print_table(data)


def print_logs(
    data: Any,
    *,
    seen: set[str] | None = None,
    show_header: bool = True,
) -> None:
    """Render Cloud Logging payloads: summary table, then one line per entry.

    When ``seen`` is provided (follow mode), only newly observed entries are
    printed so polls don't reprint the same window.
    """
    data = normalize_payload(data)
    if not isinstance(data, dict):
        print_data(data, "table")
        return

    entries = data.get("entries")
    if not isinstance(entries, list):
        entries = []

    readable_entries = [
        entry for entry in entries if isinstance(entry, dict) and _log_message(entry)
    ]

    if show_header:
        summary = {key: value for key, value in data.items() if key != "entries"}
        summary["entries"] = len(readable_entries)
        # Hide empty / error-only message noise in the summary.
        if not summary.get("message"):
            summary.pop("message", None)
        _print_kv(summary)
        if readable_entries:
            console.print(Text("Logs", style="bold magenta"))

    if not readable_entries:
        if show_header:
            console.print(Text("(no log entries)", style="dim"))
        return

    ordered = list(reversed(readable_entries))
    printed = 0
    for entry in ordered:
        ts = _format_log_timestamp(entry.get("timestamp"))
        severity = str(entry.get("severity") or "")
        message = _log_message(entry) or ""
        line = f"{ts}  {severity:<7}  {message}".rstrip()
        key = f"{entry.get('timestamp')}|{severity}|{message}"

        if seen is not None:
            if key in seen:
                continue
            seen.add(key)

        severity_upper = severity.upper()
        style = None
        if severity_upper in {"ERROR", "CRITICAL", "ALERT", "EMERGENCY"}:
            style = "red"
        elif severity_upper == "WARNING":
            style = "yellow"
        console.print(line, style=style, soft_wrap=True)
        printed += 1

    if show_header and printed == 0 and seen is not None:
        console.print(Text("(no new log entries)", style="dim"))


def _log_message(entry: dict[str, Any]) -> str | None:
    raw = entry.get("message")
    if raw is None or raw == "":
        raw = entry.get("textPayload")
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    # Drop protobuf Any dumps that older backends still return.
    if text.startswith("type_url:") or '\nvalue: "' in text or "\\nvalue:" in text:
        return None
    if len(text) > 2000:
        return text[:1999] + "…"
    return text


def _format_log_timestamp(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    # 2026-07-21T21:16:34.931628Z → 21:16:34
    if "T" in text:
        try:
            time_part = text.split("T", 1)[1]
            return time_part[:8]
        except Exception:
            return text[:19]
    return text[:19]


def print_success(message: str) -> None:
    console.print(f"[green]{message}[/green]")


def print_error(message: str) -> None:
    console.print(f"[red]{message}[/red]")


def print_table(data: Any) -> None:
    if isinstance(data, list):
        _print_rows(data)
        return
    if isinstance(data, dict):
        _print_kv(data)
        return
    console.print(str(data))


def project_rows(rows: list[Any], columns: list[str]) -> list[dict[str, Any]]:
    projected: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        projected.append({column: row.get(column) for column in columns})
    return projected


def print_app_detail(app: dict[str, Any], *, full: bool = False) -> None:
    """Human-friendly app detail view (table mode)."""
    if full:
        print_table(normalize_payload(app))
        return

    details = app.get("details") if isinstance(app.get("details"), dict) else {}
    publish = app.get("appPublish") if isinstance(app.get("appPublish"), dict) else {}

    overview = normalize_payload(
        {
            "uuid": app.get("uuid"),
            "name": app.get("name"),
            "label": app.get("label"),
            "description": app.get("description") or details.get("description"),
            "category": app.get("category") or details.get("category"),
            "url": app.get("url") or details.get("url"),
            "privateApp": app.get("privateApp"),
            "installed": app.get("installed"),
            "authMethod": app.get("authMethod"),
            "platformVersion": app.get("platformVersion"),
            "runtime": app.get("runtime"),
            "runtimeStatus": app.get("runtimeStatus"),
            "runtimeBaseUrl": app.get("runtimeBaseUrl"),
            "publishState": publish.get("publishState"),
            "webhookRateLimitPerMinute": app.get("webhookRateLimitPerMinute"),
            "createdAt": app.get("createdAt"),
            "updatedAt": app.get("updatedAt"),
        }
    )
    _print_section("Overview", overview)

    branding = {
        "brandColor": details.get("brandColor"),
        "textColor": details.get("textColor"),
        "image": details.get("image") or app.get("image"),
        "brandmark": app.get("brandmark"),
        "title": details.get("title"),
        "subcategories": details.get("subcategories"),
    }
    _print_section("Branding / details", branding)

    resources = {
        "appBars": _count_label(app.get("appBars"), item_label=_app_bar_label),
        "pricingPlans": _count_label(app.get("pricingPlans"), item_label=_pricing_label),
        "serverlessFunctions": _count_label(
            app.get("serverlessFunctions"), item_label=_function_label
        ),
        "requiredScopes": _count_label(app.get("requiredScopes")),
        "settingsSchema": _count_label(app.get("settingsSchema"), item_label=_schema_label),
        "oauthRedirectUris": _count_label(app.get("oauthRedirectUris")),
    }
    _print_section("Resources", resources)
    console.print(
        Text("Tip: use --full for the complete payload, or --output json.", style="dim")
    )


def _print_section(title: str, values: dict[str, Any]) -> None:
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Field", style="cyan", no_wrap=True)
    table.add_column("Value", overflow="fold")
    for key, value in values.items():
        if value is None or value == "" or value == []:
            continue
        table.add_row(key, _format_value(value))
    console.print(Panel(table, title=title, border_style="magenta"))


def _count_label(
    value: Any,
    *,
    item_label: Any | None = None,
) -> str | None:
    if not isinstance(value, list):
        return None if value in (None, "") else str(value)
    if not value:
        return "0"
    labels: list[str] = []
    for item in value[:5]:
        if item_label:
            labels.append(item_label(item))
        elif isinstance(item, dict):
            labels.append(str(item.get("name") or item.get("label") or item.get("uuid") or "item"))
        else:
            labels.append(str(item))
    suffix = ", ".join(labels)
    if len(value) > 5:
        suffix += ", …"
    return f"{len(value)} — {suffix}"


def _app_bar_label(item: Any) -> str:
    if not isinstance(item, dict):
        return str(item)
    return str(item.get("label") or item.get("location") or item.get("uuid") or "appBar")


def _pricing_label(item: Any) -> str:
    if not isinstance(item, dict):
        return str(item)
    return str(item.get("title") or item.get("name") or item.get("uuid") or "plan")


def _function_label(item: Any) -> str:
    if not isinstance(item, dict):
        return str(item)
    runtime = item.get("runtime") or "?"
    name = item.get("name") or item.get("description") or item.get("uuid") or "function"
    return f"{name} ({runtime})"


def _schema_label(item: Any) -> str:
    if not isinstance(item, dict):
        return str(item)
    return str(item.get("name") or item.get("label") or "field")


def _format_value(value: Any, *, max_len: int = 120) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        if not value:
            return "[]"
        if all(not isinstance(v, (dict, list)) for v in value):
            text = ", ".join(str(v) for v in value)
        else:
            text = _count_label(value) or "[]"
        return _truncate(text, max_len)
    if isinstance(value, dict):
        # Compact nested object: show a few scalar keys.
        parts: list[str] = []
        for key, nested in value.items():
            if isinstance(nested, (dict, list)) or nested in (None, ""):
                continue
            parts.append(f"{key}={nested}")
            if len(parts) >= 4:
                break
        text = ", ".join(parts) if parts else f"{{{len(value)} fields}}"
        return _truncate(text, max_len)
    return _truncate(str(value), max_len)


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def _cell_value(value: Any, *, max_len: int = 80) -> str:
    return _format_value(value, max_len=max_len)


def _print_rows(rows: list[Any]) -> None:
    if not rows:
        console.print("No results.")
        return
    if not isinstance(rows[0], dict):
        for row in rows:
            console.print(str(row))
        return

    # Skip nested objects/lists and blank keys — they blow up terminal tables.
    scalar_keys: set[str] = set()
    for row in rows:
        for key, value in row.items():
            if not key or not isinstance(key, str):
                continue
            if isinstance(value, (dict, list)):
                continue
            scalar_keys.add(key)

    preferred = [key for key in PREFERRED_COLUMNS if key in scalar_keys]
    remaining = sorted(key for key in scalar_keys if key not in preferred)
    # Keep tables readable: preferred fields + a few extras.
    headers = preferred + remaining[: max(0, 8 - len(preferred))]
    if not headers:
        console.print("No tabular fields to display. Use --output json.")
        return

    table = Table(show_header=True, header_style="bold magenta")
    for header in headers:
        table.add_column(header, overflow="fold")
    for row in rows:
        table.add_row(*[_cell_value(row.get(h)) for h in headers])
    console.print(table)


def _print_kv(item: dict[str, Any]) -> None:
    table = Table(show_header=False)
    table.add_column("Field", style="cyan", no_wrap=True)
    table.add_column("Value", overflow="fold")
    for key, value in item.items():
        if not key:
            continue
        table.add_row(str(key), _format_value(value, max_len=160))
    console.print(table)
