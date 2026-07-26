"""Interactive prompts for marketplace fields (settings, pricing, app bars, lifecycle)."""

from __future__ import annotations

from typing import Any

from questionary import Choice
from rich.console import Console

from caraer_cli.project.lifecycle_sync import LIFECYCLE_HOOKS
from caraer_cli.wizard.catalog import (
    ACTION_BASED_LOCATIONS,
    APP_BAR_LOCATIONS,
    SETTING_FIELD_TYPES,
)
from caraer_cli.wizard.prompts import ask_confirm, ask_select, ask_text

console = Console()


def _optional(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def _coerce_number(raw: str) -> int | float | str:
    text = raw.strip()
    try:
        if "." in text:
            return float(text)
        return int(text)
    except ValueError:
        return text


def prompt_setting_field(
    *,
    name: str | None = None,
    label: str | None = None,
    field_type: str | None = None,
    required: bool | None = None,
    help_text: str | None = None,
    default_value: str | None = None,
) -> dict[str, Any]:
    """Prompt for one settingsSchema field (wizard-style)."""
    resolved_name = (name or "").strip() or ask_text("Field name", required=True)
    resolved_label = (
        label
        if label is not None and str(label).strip()
        else ask_text("Field label", default=resolved_name)
    )
    resolved_type = (
        (field_type or "").strip().upper()
        or ask_select(
            "Field type",
            [Choice(title=lbl, value=key) for key, lbl in SETTING_FIELD_TYPES],
            default="SINGLE_LINE",
        )
    )
    resolved_required = (
        required
        if required is not None
        else ask_confirm("Required?", default=False)
    )
    resolved_help = (
        help_text
        if help_text is not None
        else ask_text("Help text (optional)", default="")
    )
    resolved_default = (
        default_value
        if default_value is not None
        else ask_text("Default value (optional)", default="")
    )

    field: dict[str, Any] = {
        "name": resolved_name.strip(),
        "label": (resolved_label or resolved_name).strip(),
        "type": resolved_type,
        "required": bool(resolved_required),
    }
    if _optional(resolved_help):
        field["helpText"] = resolved_help.strip()
    if _optional(resolved_default):
        if resolved_type == "SWITCH":
            field["defaultValue"] = resolved_default.strip().lower() in {
                "1",
                "true",
                "yes",
                "y",
            }
        else:
            field["defaultValue"] = resolved_default.strip()

    if resolved_type in {"SINGLE_SELECT", "MULTI_SELECT"}:
        options_raw = ask_text(
            "Options (comma-separated label=value or label)",
            required=True,
        )
        options: list[dict[str, str]] = []
        for part in options_raw.split(","):
            item = part.strip()
            if not item:
                continue
            if "=" in item:
                option_label, option_value = item.split("=", 1)
            else:
                option_label, option_value = item, item
            options.append(
                {"label": option_label.strip(), "value": option_value.strip()}
            )
        field["options"] = options
    return field


def prompt_pricing_tier() -> dict[str, Any]:
    tier: dict[str, Any] = {
        "startUnits": _coerce_number(
            ask_text("Start units", default="0", required=True)
        ),
    }
    end_units = ask_text("End units (blank = unlimited)", default="")
    if _optional(end_units):
        tier["endUnits"] = _coerce_number(end_units)
    price_month = ask_text("Price per month (optional)", default="")
    price_year = ask_text("Price per year (optional)", default="")
    price_extra = ask_text("Price per extra unit (optional)", default="")
    if _optional(price_month):
        tier["pricePerMonth"] = _coerce_number(price_month)
    if _optional(price_year):
        tier["pricePerYear"] = _coerce_number(price_year)
    if _optional(price_extra):
        tier["pricePerExtraUnit"] = _coerce_number(price_extra)
    return tier


def prompt_pricing_plan(
    *,
    title: str | None = None,
    pricing_type: str | None = None,
    price_per_unit: float | None = None,
    unit: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Prompt for one pricing plan (wizard-style)."""
    resolved_type = (
        (pricing_type or "").strip().upper()
        or ask_select(
            "Pricing type",
            [
                Choice(title="FLAT — fixed price per unit", value="FLAT"),
                Choice(title="TIERED — volume tiers", value="TIERED"),
            ],
            default="FLAT",
        )
    )
    resolved_title = (title or "").strip() or ask_text("Plan title", required=True)
    plan: dict[str, Any] = {
        "title": resolved_title,
        "pricingType": resolved_type,
    }
    resolved_description = (
        description
        if description is not None
        else ask_text("Plan description (optional)", default="")
    )
    if _optional(resolved_description):
        plan["description"] = resolved_description.strip()

    if resolved_type == "FLAT":
        if price_per_unit is not None and title is not None and unit is not None:
            # Non-interactive-ish path with CLI flags.
            plan["pricePerUnit"] = price_per_unit
            plan["unit"] = (unit or "installations").strip() or "installations"
        else:
            price = ask_text(
                "Price per unit (e.g. 0 or 10.00)",
                default="" if price_per_unit is None else str(price_per_unit),
            )
            resolved_unit = ask_text(
                "Unit (e.g. installations, seats)",
                default=(unit or "installations"),
            )
            free_units = ask_text("Free units (optional)", default="")
            free_period = ask_text("Free units period (optional)", default="")
            if _optional(price):
                plan["pricePerUnit"] = _coerce_number(price)
            elif price_per_unit is not None:
                plan["pricePerUnit"] = price_per_unit
            else:
                plan["pricePerUnit"] = 0
            plan["unit"] = (resolved_unit or "installations").strip()
            if _optional(free_units):
                plan["freeUnits"] = _coerce_number(free_units)
            if _optional(free_period):
                plan["freeUnitsPeriod"] = free_period.strip()
    else:
        tiers: list[dict[str, Any]] = []
        console.print("[dim]Add at least one tier.[/dim]")
        while True:
            tiers.append(prompt_pricing_tier())
            if not ask_confirm("Add another tier?", default=False):
                break
        plan["tiers"] = tiers
    return plan


def prompt_app_bar(
    *,
    label: str | None = None,
    location: str | None = None,
    function_name: str | None = None,
    iframe_url: str | None = None,
    function_choices: list[str] | None = None,
) -> dict[str, Any]:
    """Prompt for one app bar (wizard-style)."""
    resolved_location = (
        (location or "").strip().upper()
        or ask_select(
            "Location",
            [Choice(title=lbl, value=key) for key, lbl in APP_BAR_LOCATIONS],
            default="RECORD_PREVIEW",
        )
    )
    resolved_label = (label or "").strip() or ask_text("Label", required=True)
    bar: dict[str, Any] = {
        "location": resolved_location,
        "label": resolved_label,
    }
    tooltip = ask_text("Tooltip label (optional)", default="")
    if _optional(tooltip):
        bar["tooltipLabel"] = tooltip.strip()

    if resolved_location in ACTION_BASED_LOCATIONS:
        description = ask_text("Description (optional)", default="")
        action_label = ask_text(
            "Action button label (optional)", default=resolved_label
        )
        if _optional(description):
            bar["description"] = description.strip()
        if _optional(action_label):
            bar["actionLabel"] = action_label.strip()

        delivery = ask_select(
            "Action delivery",
            [
                Choice(title="SERVERLESS — local function", value="SERVERLESS"),
                Choice(title="HTTP — external URL", value="HTTP"),
            ],
            default="SERVERLESS",
        )
        if delivery == "HTTP":
            url = ask_text("Webhook URL", required=True)
            bar["webhook"] = {
                "topic": "app.bar.triggered",
                "deliveryMode": "HTTP",
                "enabled": True,
                "url": url.strip(),
            }
        else:
            names = function_choices or []
            if function_name and function_name.strip():
                fn = function_name.strip()
            elif names:
                fn = ask_select(
                    "Function",
                    [Choice(title=n, value=n) for n in names],
                    default=names[0],
                )
            else:
                fn = ask_text(
                    "Function name",
                    default="on-app-bar",
                    required=True,
                )
            bar["webhook"] = {
                "topic": "app.bar.triggered",
                "deliveryMode": "SERVERLESS",
                "enabled": True,
                "serverlessFunction": {"name": fn},
            }
    else:
        url = (iframe_url or "").strip() or ask_text("Iframe URL", required=True)
        icon = ask_text("Icon (optional)", default="")
        bar["iframeUrl"] = url
        if _optional(icon):
            bar["icon"] = icon.strip()
    return bar


def prompt_lifecycle_hook(
    *,
    event: str | None = None,
    function_name: str | None = None,
    create_function: bool | None = None,
) -> dict[str, Any]:
    """Prompt for lifecycle hook options. Returns keys used by the scaffold."""
    events = sorted(LIFECYCLE_HOOKS.keys())
    resolved_event = (
        (event or "").strip().lower()
        or ask_select(
            "Lifecycle event",
            [
                Choice(title=f"{stem} ({LIFECYCLE_HOOKS[stem][1]})", value=stem)
                for stem in events
            ],
            default="install",
        )
    )
    if resolved_event not in LIFECYCLE_HOOKS:
        raise ValueError(
            f"Unknown lifecycle event '{resolved_event}'. "
            f"Expected one of: {', '.join(events)}."
        )
    _manifest_key, topic = LIFECYCLE_HOOKS[resolved_event]
    delivery = ask_select(
        "Delivery mode",
        [
            Choice(title="SERVERLESS — local function", value="SERVERLESS"),
            Choice(title="HTTP — external URL", value="HTTP"),
        ],
        default="SERVERLESS",
    )
    enabled = ask_confirm("Enabled?", default=True)
    result: dict[str, Any] = {
        "event": resolved_event,
        "topic": topic,
        "deliveryMode": delivery,
        "enabled": enabled,
        "create_function": False,
        "function_name": None,
        "url": None,
    }
    if delivery == "HTTP":
        result["url"] = ask_text("Webhook URL", required=True).strip()
    else:
        default_fn = f"on-{resolved_event}"
        result["function_name"] = (
            (function_name or "").strip()
            or ask_text("Function name", default=default_fn, required=True)
        )
        result["create_function"] = (
            create_function
            if create_function is not None
            else ask_confirm(
                f"Scaffold function folder functions/{result['function_name']}/?",
                default=True,
            )
        )
    return result
