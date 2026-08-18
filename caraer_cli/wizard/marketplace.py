"""Interactive prompts for marketplace fields and local scaffolds (schedules, …)."""

from __future__ import annotations

import re
import sys
from typing import Any

from questionary import Choice
from rich.console import Console

from caraer_cli.project.lifecycle_sync import LIFECYCLE_HOOKS
from caraer_cli.project.validate_app import CRON_RE
from caraer_cli.wizard.catalog import (
    ACTION_BASED_LOCATIONS,
    APP_BAR_LOCATIONS,
    CONDITION_OPERATORS,
    DYNAMIC_OPTIONS_FIELD_TYPES,
    LIST_CONDITION_OPERATORS,
    SCHEMA_PICKER_FIELD_TYPES,
    SETTING_FIELD_TYPES,
    STATIC_OPTIONS_FIELD_TYPES,
    VALUELESS_CONDITION_OPERATORS,
)
from caraer_cli.wizard.prompts import (
    ask_checkbox,
    ask_confirm,
    ask_select,
    ask_text,
)

console = Console()

DEFAULT_SCHEDULE_CRON = "0 0 */6 * * *"

# Spring-style 6-field cron presets (sec min hour dom mon dow).
CRON_PRESETS: list[tuple[str, str | None]] = [
    ("Every hour", "0 0 * * * *"),
    ("Every 6 hours", "0 0 */6 * * *"),
    ("Every 12 hours", "0 0 */12 * * *"),
    ("Daily at 09:00", "0 0 9 * * *"),
    ("Weekdays at 09:00", "0 0 9 * * 1-5"),
    ("Every 15 minutes", "0 */15 * * * *"),
    ("Custom cron expression…", None),
]


def _is_tty() -> bool:
    return bool(sys.stdin.isatty() and sys.stdout.isatty())


def validate_cron_expression(value: str) -> str:
    """Return a stripped cron string, or raise ValueError if it looks invalid."""
    text = (value or "").strip()
    if not text:
        raise ValueError("Cron expression is required.")
    if not CRON_RE.match(text):
        raise ValueError(
            f"Cron expression '{text}' does not look like a 5–6 field expression "
            "(e.g. '0 0 9 * * 1-5' or '0 9 * * 1-5')."
        )
    return text


def prompt_cron_expression(*, default: str = DEFAULT_SCHEDULE_CRON) -> str:
    """Ask for a cron expression via presets, then optional custom input."""
    console.print(
        "[dim]Cron is Spring-style 5–6 fields "
        "(sec min hour dom mon dow). Example: [bold]0 0 9 * * 1-5[/bold] "
        "(weekdays at 09:00).[/dim]"
    )
    choices = [
        Choice(title=f"{label}  ({expr})" if expr else label, value=expr or "")
        for label, expr in CRON_PRESETS
    ]
    selected = ask_select("Schedule frequency", choices, default=default)
    if selected:
        return validate_cron_expression(selected)
    while True:
        custom = ask_text(
            "Cron expression (e.g. 0 0 9 * * 1-5)",
            default=default,
            required=True,
        )
        try:
            return validate_cron_expression(custom)
        except ValueError as exc:
            console.print(f"[yellow]{exc}[/yellow]")


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


def normalize_setting_field_name(value: str) -> str:
    """Lowercase identifier using only ``a-z``, with ``_`` for other characters."""
    normalized = value.strip().lower()
    normalized = re.sub(r"[^a-z]+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized


def _next_tier_start_units(previous_tiers: list[dict[str, Any]]) -> int | None:
    if not previous_tiers:
        return 0
    end_units = previous_tiers[-1].get("endUnits")
    if end_units is None:
        return None
    try:
        end_value = int(end_units) if not isinstance(end_units, float) else int(end_units)
    except (TypeError, ValueError):
        try:
            end_value = int(float(str(end_units).strip()))
        except (TypeError, ValueError):
            return None
    return end_value + 1


def _parse_static_options(raw: str) -> list[dict[str, str]]:
    """Parse ``label=name`` / ``name`` tokens into SettingOption-shaped dicts."""
    options: list[dict[str, str]] = []
    for part in raw.split(","):
        item = part.strip()
        if not item:
            continue
        if "=" in item:
            option_label, option_name = item.split("=", 1)
        else:
            option_label, option_name = item, item
        name = option_name.strip()
        label = option_label.strip() or name
        if name:
            options.append({"name": name, "label": label})
    return options


def _parse_depends_on(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def _prompt_depends_on(
    *,
    sibling_names: list[str] | None = None,
    exclude_name: str | None = None,
) -> list[str]:
    """Ask which sibling setting keys must be set before options load."""
    siblings = [
        n
        for n in (sibling_names or [])
        if n and n != exclude_name
    ]
    console.print(
        "[dim]dependsOn: option lists refetch when these sibling fields change "
        "(stored on optionsSource.dependsOn).[/dim]"
    )
    if siblings and _is_tty():
        if not ask_confirm(
            "Does this field depend on other settings?", default=False
        ):
            return []
        selected = ask_checkbox(
            "Depends on (space to toggle)",
            [Choice(title=n, value=n) for n in siblings],
        )
        return list(selected)
    raw = ask_text(
        "Depends on field names (comma-separated, optional)",
        default="",
    )
    return _parse_depends_on(raw)


def _coerce_condition_value(operator: str, raw: str) -> Any:
    """Parses the expected value a condition compares against."""
    text = (raw or "").strip()
    if operator in LIST_CONDITION_OPERATORS:
        return [part.strip() for part in text.split(",") if part.strip()]
    lowered = text.lower()
    if lowered in {"true", "yes", "y", "1"}:
        return True
    if lowered in {"false", "no", "n", "0"}:
        return False
    return text


def _prompt_visible_when(
    *,
    field_name: str,
    sibling_names: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Ask for the conditions that must hold before the field is shown."""
    siblings = [n for n in (sibling_names or []) if n and n != field_name]
    if not siblings or not _is_tty():
        return []
    console.print(
        "[dim]visibleWhen: the installer only sees this field while every "
        "condition holds (stored on settingsSchema[].visibleWhen).[/dim]"
    )
    if not ask_confirm("Show this field conditionally?", default=False):
        return []

    conditions: list[dict[str, Any]] = []
    while True:
        controlling = ask_select(
            "Controlling field",
            [Choice(title=n, value=n) for n in siblings],
            default=siblings[0],
        )
        operator = ask_select(
            "Condition",
            [Choice(title=f"{key} — {lbl}", value=key) for key, lbl in CONDITION_OPERATORS],
            default="EQUALS",
        )
        condition: dict[str, Any] = {"field": controlling, "operator": operator}
        if operator not in VALUELESS_CONDITION_OPERATORS:
            prompt = (
                "Expected values (comma-separated)"
                if operator in LIST_CONDITION_OPERATORS
                else "Expected value"
            )
            condition["value"] = _coerce_condition_value(
                operator, ask_text(prompt, required=True)
            )
        conditions.append(condition)
        if not ask_confirm("Add another condition?", default=False):
            break
    return conditions


def _prompt_options_source(
    *,
    field_name: str,
    function_choices: list[str] | None = None,
    sibling_names: list[str] | None = None,
    offer_scaffold: bool = False,
    options_function: str | None = None,
    depends_on: list[str] | None = None,
) -> tuple[dict[str, Any], str | None]:
    """Build optionsSource; returns (source, function_name_to_scaffold_or_None)."""
    names = list(function_choices or [])
    default_fn = f"list-{field_name.replace('_', '-')}"
    resolved_fn = (options_function or "").strip()
    scaffold_name: str | None = None

    if not resolved_fn:
        if names and _is_tty():
            choices = [
                Choice(title=n, value=n) for n in names
            ] + [
                Choice(
                    title=f"Create new options function ({default_fn})",
                    value="__new__",
                )
            ]
            picked = ask_select(
                "Options loader function",
                choices,
                default=names[0],
            )
            if picked == "__new__":
                resolved_fn = ask_text(
                    "New function name",
                    default=default_fn,
                    required=True,
                ).strip()
                scaffold_name = resolved_fn if offer_scaffold else None
            else:
                resolved_fn = picked
        else:
            resolved_fn = (
                ask_text(
                    "Options function name",
                    default=default_fn,
                    required=True,
                ).strip()
                if _is_tty()
                else default_fn
            )
            if offer_scaffold and _is_tty() and ask_confirm(
                f"Scaffold options function functions/{resolved_fn}/?",
                default=True,
            ):
                scaffold_name = resolved_fn

    if depends_on is not None:
        deps = [d.strip() for d in depends_on if d and str(d).strip()]
    else:
        deps = _prompt_depends_on(
            sibling_names=sibling_names,
            exclude_name=field_name,
        )

    searchable = True
    if _is_tty():
        searchable = ask_confirm("Searchable options?", default=True)

    source: dict[str, Any] = {
        "type": "SERVERLESS",
        "serverlessFunctionName": resolved_fn,
        "searchable": searchable,
    }
    if deps:
        source["dependsOn"] = deps
    return source, scaffold_name


def _prompt_mapping_value() -> dict[str, Any]:
    console.print(
        "[dim]MAPPING defines rows the installer maps to object properties.[/dim]"
    )
    object_name = ask_text(
        "Target object name (mappingValue.objectName)",
        required=True,
    )
    items: list[dict[str, Any]] = []
    console.print("[dim]Add at least one mapping row.[/dim]")
    while True:
        field_name = ask_text("Row fieldName (key)", required=True)
        field_label = ask_text("Row fieldLabel", default=field_name)
        field_help = ask_text("Row help text (optional)", default="")
        is_required = ask_confirm("Row required?", default=False)
        allowed_types = ask_text(
            "allowedPropertyTypes (comma-separated, optional)",
            default="",
        )
        allowed_formats = ask_text(
            "allowedPropertyFormats (comma-separated, optional)",
            default="",
        )
        row: dict[str, Any] = {
            "fieldName": field_name.strip(),
            "fieldLabel": (field_label or field_name).strip(),
            "isRequired": bool(is_required),
        }
        if _optional(field_help):
            row["fieldHelpText"] = field_help.strip()
        types = [p.strip() for p in allowed_types.split(",") if p.strip()]
        formats = [p.strip() for p in allowed_formats.split(",") if p.strip()]
        if types:
            row["allowedPropertyTypes"] = types
        if formats:
            row["allowedPropertyFormats"] = formats
        items.append(row)
        if not ask_confirm("Add another mapping row?", default=False):
            break
    return {"objectName": object_name.strip(), "items": items}


def prompt_setting_field(
    *,
    name: str | None = None,
    label: str | None = None,
    field_type: str | None = None,
    required: bool | None = None,
    help_text: str | None = None,
    default_value: str | None = None,
    function_choices: list[str] | None = None,
    sibling_setting_names: list[str] | None = None,
    offer_options_scaffold: bool = False,
    options_mode: str | None = None,
    options_function: str | None = None,
    depends_on: list[str] | None = None,
    static_options: str | None = None,
    visible_when: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Prompt for one settingsSchema field (wizard-style).

    Private key ``_scaffoldOptionsFunction`` may be set when the caller should
    create an options-loader function (stripped by sanitize_setting).
    """
    interactive = _is_tty()
    resolved_name = (name or "").strip()
    resolved_label = (label or "").strip() if label is not None else ""

    if interactive and not resolved_name:
        if not resolved_label:
            resolved_label = ask_text("Field label", required=True)
        default_name = normalize_setting_field_name(resolved_label) or "field"
        name_raw = ask_text(
            "Field name (Enter to keep default)",
            default=default_name,
            required=True,
        )
        resolved_name = normalize_setting_field_name(name_raw) or default_name
        if resolved_name != name_raw.strip():
            console.print(
                f"[dim]Normalized name to[/dim] [bold]{resolved_name}[/bold]"
            )
    elif not resolved_name:
        if resolved_label:
            resolved_name = normalize_setting_field_name(resolved_label) or "field"
        else:
            raise ValueError("Missing required value: name")
        if not resolved_label:
            resolved_label = resolved_name
    elif not resolved_label:
        resolved_label = (
            ask_text("Field label", default=resolved_name)
            if interactive
            else resolved_name
        )
    resolved_type = (field_type or "").strip().upper()
    if not resolved_type:
        if not interactive:
            raise ValueError("Missing required value: --type")
        resolved_type = ask_select(
            "Field type",
            [Choice(title=lbl, value=key) for key, lbl in SETTING_FIELD_TYPES],
            default="SINGLE_LINE",
        )
    known = {key for key, _ in SETTING_FIELD_TYPES}
    if resolved_type not in known:
        raise ValueError(
            f"Unknown setting type '{resolved_type}'. "
            f"Expected one of: {', '.join(sorted(known))}."
        )

    resolved_required = (
        required
        if required is not None
        else (ask_confirm("Required?", default=False) if interactive else False)
    )
    resolved_help = (
        help_text
        if help_text is not None
        else (ask_text("Help text (optional)", default="") if interactive else "")
    )

    field: dict[str, Any] = {
        "name": resolved_name.strip(),
        "label": (resolved_label or resolved_name).strip(),
        "type": resolved_type,
        "required": bool(resolved_required),
    }
    if _optional(resolved_help):
        field["helpText"] = resolved_help.strip()

    conditions = (
        visible_when
        if visible_when is not None
        else _prompt_visible_when(
            field_name=resolved_name.strip(),
            sibling_names=sibling_setting_names,
        )
    )
    if conditions:
        field["visibleWhen"] = conditions

    # SECRET: no defaultValue in schema (write-only at install time).
    if resolved_type != "SECRET":
        resolved_default = (
            default_value
            if default_value is not None
            else (
                ask_text("Default value (optional)", default="")
                if interactive
                else ""
            )
        )
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

    if resolved_type in SCHEMA_PICKER_FIELD_TYPES:
        console.print(
            "[dim]Installer picks the object/property at install time — "
            "no static options needed.[/dim]"
        )
        return field

    if resolved_type == "MAPPING":
        if interactive:
            field["mappingValue"] = _prompt_mapping_value()
        else:
            field["mappingValue"] = {"objectName": "", "items": []}
        return field

    if resolved_type in DYNAMIC_OPTIONS_FIELD_TYPES:
        mode = (options_mode or "").strip().lower()
        if not mode:
            if interactive:
                mode = ask_select(
                    "Options source",
                    [
                        Choice(
                            title="Static — comma-separated options",
                            value="static",
                        ),
                        Choice(
                            title="Dynamic — serverless options function",
                            value="dynamic",
                        ),
                    ],
                    default="static",
                )
            else:
                # Non-interactive: prefer dynamic when --options-function is set.
                mode = "dynamic" if options_function else "static"

        if mode == "dynamic":
            source, scaffold_name = _prompt_options_source(
                field_name=resolved_name,
                function_choices=function_choices,
                sibling_names=sibling_setting_names,
                offer_scaffold=offer_options_scaffold,
                options_function=options_function,
                depends_on=depends_on,
            )
            field["optionsSource"] = source
            if scaffold_name:
                field["_scaffoldOptionsFunction"] = scaffold_name
            return field

        if static_options is not None:
            options_raw = static_options
        elif interactive:
            options_raw = ask_text(
                "Options (comma-separated label=name or name)",
                required=True,
            )
        else:
            raise ValueError(
                "Select fields require --options (comma-separated label=name) "
                "or --options-mode dynamic with --options-function."
            )
        options = _parse_static_options(options_raw)
        if not options:
            raise ValueError("At least one option is required for select fields.")
        field["options"] = options
        return field

    if resolved_type in STATIC_OPTIONS_FIELD_TYPES:
        # RECORD_*_SELECT: static options only (no optionsSource).
        if static_options is not None:
            options_raw = static_options
        elif interactive:
            options_raw = ask_text(
                "Options (comma-separated label=name or name)",
                required=True,
            )
        else:
            raise ValueError(
                "RECORD select fields require --options "
                "(comma-separated label=name)."
            )
        options = _parse_static_options(options_raw)
        if not options:
            raise ValueError("At least one option is required for select fields.")
        field["options"] = options
    return field


def prompt_pricing_tier(
    *,
    previous_tiers: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    previous = list(previous_tiers or [])
    tier_index = len(previous) + 1
    resolved_label = ask_text(f"Tier {tier_index} label", required=True)
    default_name = normalize_setting_field_name(resolved_label) or f"tier_{tier_index}"
    name_raw = ask_text(
        "Tier name (Enter to keep default)",
        default=default_name,
        required=True,
    )
    resolved_name = normalize_setting_field_name(name_raw) or default_name
    if resolved_name != name_raw.strip():
        console.print(f"[dim]Normalized name to[/dim] [bold]{resolved_name}[/bold]")

    default_start = _next_tier_start_units(previous)
    if default_start is None and previous:
        console.print(
            "[yellow]Previous tier has no end units — set end units on the "
            "previous tier before adding another.[/yellow]"
        )
        default_start = 0

    while True:
        start_raw = ask_text(
            "Start units",
            default=str(default_start if default_start is not None else 0),
            required=True,
        )
        start_units = _coerce_number(start_raw)
        if not previous:
            break
        expected = _next_tier_start_units(previous)
        if expected is None:
            console.print(
                "[yellow]Previous tier must define end units before adding "
                "another tier.[/yellow]"
            )
            continue
        try:
            actual = int(start_units)
        except (TypeError, ValueError):
            try:
                actual = int(float(str(start_units).strip()))
            except (TypeError, ValueError):
                console.print("[yellow]Start units must be a whole number.[/yellow]")
                continue
        if actual == expected:
            break
        console.print(
            f"[yellow]Start units must be {expected} "
            f"(previous tier end units + 1).[/yellow]"
        )

    tier: dict[str, Any] = {
        "name": resolved_name,
        "label": resolved_label.strip(),
        "startUnits": start_units,
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
            tiers.append(prompt_pricing_tier(previous_tiers=tiers))
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


def prompt_schedule(
    *,
    name: str | None = None,
    function_name: str | None = None,
    cron: str | None = None,
    description: str | None = None,
    enabled: bool | None = None,
    function_choices: list[str] | None = None,
) -> dict[str, Any]:
    """Prompt for a local schedule scaffold (name, function, cron, …)."""
    interactive = _is_tty()

    resolved_name = (name or "").strip()
    if not resolved_name:
        if not interactive:
            raise ValueError("Missing required value: name")
        resolved_name = ask_text("Schedule name", required=True)

    names = list(function_choices or [])
    resolved_function = (function_name or "").strip()
    if not resolved_function:
        if not interactive:
            raise ValueError("Missing required value: --function")
        if names:
            resolved_function = ask_select(
                "Function to invoke",
                [Choice(title=n, value=n) for n in names],
                default=names[0],
            )
        else:
            resolved_function = ask_text("Function name", required=True)

    if cron is not None and str(cron).strip():
        try:
            resolved_cron = validate_cron_expression(str(cron))
        except ValueError as exc:
            if not interactive:
                raise
            console.print(f"[yellow]{exc}[/yellow]")
            resolved_cron = prompt_cron_expression()
    elif interactive:
        resolved_cron = prompt_cron_expression()
    else:
        resolved_cron = DEFAULT_SCHEDULE_CRON

    if description is not None:
        resolved_description = description.strip()
    elif interactive:
        resolved_description = ask_text("Description (optional)", default="")
    else:
        resolved_description = ""

    if enabled is not None:
        resolved_enabled = bool(enabled)
    elif interactive:
        resolved_enabled = ask_confirm("Enabled?", default=True)
    else:
        resolved_enabled = True

    result: dict[str, Any] = {
        "name": resolved_name.strip(),
        "schedule": resolved_cron,
        "enabled": resolved_enabled,
        "function_name": resolved_function.strip(),
    }
    if _optional(resolved_description):
        result["description"] = resolved_description.strip()
    return result


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
