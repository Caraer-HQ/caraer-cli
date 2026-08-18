"""Interactive public-app JSON wizard."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from questionary import Choice
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from caraer_cli.wizard.catalog import (
    MAIN_CATEGORIES,
    find_main_category,
)
from caraer_cli.wizard.marketplace import (
    prompt_app_bar as _prompt_app_bar,
    prompt_pricing_plan as _prompt_pricing_plan,
    prompt_setting_field as _prompt_setting_field,
)
from caraer_cli.wizard.prompts import (
    WizardCancelled,
    ask_checkbox,
    ask_confirm,
    ask_select,
    ask_text,
)
from caraer_cli.wizard.scope_macros import (
    COMMON_OBJECT_NAMES,
    EXACT_SCOPE_EXAMPLES,
    KNOWN_TOOL_NAMES,
    SCOPE_MACRO_PRESETS,
    find_preset,
    materialize_macro,
)

console = Console()

DEFAULT_BRAND_COLOR = "#E74363"
DEFAULT_TEXT_COLOR = "#FFFFFF"
DEFAULT_APP_FILE = "app.caraer.yaml"


def normalize_app_name(value: str) -> str:
    normalized = value.strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized


def _print_section(title: str) -> None:
    console.print()
    console.print(Panel(title, expand=False, border_style="magenta"))


def _print_overview(title: str, rows: list[dict[str, Any]], columns: list[str]) -> None:
    console.print()
    if not rows:
        console.print(f"[dim]{title}: (none yet)[/dim]")
        return
    table = Table(title=title, show_header=True, header_style="bold")
    for column in columns:
        table.add_column(column)
    for index, row in enumerate(rows, start=1):
        values = [str(index)]
        for column in columns[1:]:
            value = row.get(column, "")
            if isinstance(value, list):
                value = ", ".join(str(item) for item in value)
            values.append("" if value is None else str(value))
        table.add_row(*values)
    console.print(table)


def _optional(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def _prompt_core() -> tuple[str, str]:
    _print_section("Core")
    label = ask_text("Label", required=True)
    default_name = normalize_app_name(label) or "my_app"
    name_raw = ask_text("Name (Enter to keep default)", default=default_name, required=True)
    name = normalize_app_name(name_raw) or default_name
    if name != name_raw.strip():
        console.print(f"[dim]Normalized name to[/dim] [bold]{name}[/bold]")
    return label, name


def _prompt_details() -> tuple[dict[str, Any], str]:
    _print_section("Marketplace details")
    title = ask_text("Title", default="")
    description = ask_text("Description", default="")

    category_key = ask_select(
        "Main category",
        [Choice(title=f"{c.label}", value=c.key) for c in MAIN_CATEGORIES],
        default=MAIN_CATEGORIES[0].key,
    )
    category = find_main_category(category_key)
    assert category is not None

    subcategory_keys = ask_checkbox(
        "Subcategories (space to toggle, enter to confirm)",
        [Choice(title=s.label, value=s.key) for s in category.subcategories],
        min_selected=1,
    )

    url = ask_text("Details URL (optional)", default="")
    image = ask_text("Logo SVG URL", required=True)
    brandmark = ask_text("Brandmark SVG URL", required=True)
    brand_color = ask_text("Brand color (#RRGGBB)", default=DEFAULT_BRAND_COLOR)
    text_color = ask_text("Text color (#RRGGBB)", default=DEFAULT_TEXT_COLOR)

    details: dict[str, Any] = {
        "title": title or None,
        "description": description or None,
        "category": category_key,
        "subcategories": subcategory_keys,
        "image": image.strip(),
        "brandColor": brand_color or DEFAULT_BRAND_COLOR,
        "textColor": text_color or DEFAULT_TEXT_COLOR,
    }
    if _optional(url):
        details["url"] = url.strip()
    return (
        {key: value for key, value in details.items() if value is not None},
        brandmark.strip(),
    )


def _print_scope_overview(scopes: list[str]) -> None:
    rows = [{"scope": scope, "kind": _scope_kind(scope)} for scope in scopes]
    _print_overview("Required scopes", rows, ["#", "scope", "kind"])


def _scope_kind(scope: str) -> str:
    parts = scope.split(".")
    if scope == "global.all":
        return "macro"
    if len(parts) == 3 and parts[0] == "tools" and parts[2] == "all":
        return "macro"
    if len(parts) == 3 and parts[0] == "records" and parts[2] in {
        "all",
        "properties_all",
        "relations_all",
    }:
        return "macro"
    return "exact"


def _print_macro_help(preset_id: str) -> None:
    preset = find_preset(preset_id)
    if preset is None:
        return
    console.print(
        Panel(
            f"[bold]{preset.title}[/bold]\n"
            f"Pattern: [cyan]{preset.pattern}[/cyan]\n"
            f"Example: [cyan]{preset.example}[/cyan]\n\n"
            f"{preset.description}\n\n"
            f"[dim]When to use:[/dim] {preset.when_to_use}",
            title="Macro help",
            border_style="cyan",
            expand=False,
        )
    )


def _ask_tool_name() -> str:
    choice = ask_select(
        "Tool name",
        [
            *[Choice(title=name, value=name) for name in KNOWN_TOOL_NAMES],
            Choice(title="Other (type custom tool name)…", value="__custom__"),
        ],
        default="forms",
    )
    if choice == "__custom__":
        return ask_text("Custom tool name (e.g. forms)", required=True)
    return choice


def _ask_object_name() -> str:
    choice = ask_select(
        "Object name",
        [
            *[Choice(title=name, value=name) for name in COMMON_OBJECT_NAMES],
            Choice(title="Other (type custom object name)…", value="__custom__"),
        ],
        default="candidate",
    )
    if choice == "__custom__":
        return ask_text("Custom object name (e.g. candidate)", required=True)
    return choice


def _add_unique(scopes: list[str], items: list[str]) -> list[str]:
    existing = set(scopes)
    for item in items:
        normalized = item.strip()
        if normalized and normalized not in existing:
            scopes.append(normalized)
            existing.add(normalized)
    return scopes


def _prompt_add_macro(scopes: list[str]) -> list[str]:
    preset_id = ask_select(
        "Choose a scope macro",
        [
            Choice(
                title=f"{preset.title}  ({preset.pattern})",
                value=preset.id,
            )
            for preset in SCOPE_MACRO_PRESETS
        ],
    )
    _print_macro_help(preset_id)
    preset = find_preset(preset_id)
    assert preset is not None

    tool: str | None = None
    object_name: str | None = None
    if preset.needs_tool:
        tool = _ask_tool_name()
    if preset.needs_object:
        object_name = _ask_object_name()

    added = materialize_macro(preset, tool=tool, object_name=object_name)
    console.print(f"[dim]Adding:[/dim] {', '.join(added)}")
    return _add_unique(scopes, added)


def _prompt_add_exact_scopes(scopes: list[str]) -> list[str]:
    mode = ask_select(
        "How do you want to add exact scopes?",
        [
            Choice(title="Pick from common examples", value="pick"),
            Choice(title="Type one scope string", value="type"),
        ],
        default="pick",
    )
    if mode == "pick":
        selected = ask_checkbox(
            "Exact scopes (space to toggle)",
            [Choice(title=scope, value=scope) for scope in EXACT_SCOPE_EXAMPLES],
        )
        return _add_unique(scopes, selected)

    while True:
        scope = ask_text(
            "Exact scope (e.g. tools.forms.read or records.contact.property.email.read)",
            required=True,
        )
        scopes = _add_unique(scopes, [scope])
        if not ask_confirm("Add another exact scope?", default=False):
            break
    return scopes


def _prompt_scopes() -> list[str]:
    _print_section("Scopes")
    console.print(
        "[dim]Prefer macros (e.g. tools.forms.all, records.candidate.properties_all) "
        "over long exact lists. Macros expand per tenant at install time.[/dim]"
    )
    if not ask_confirm("Configure required scopes?", default=True):
        return []

    scopes: list[str] = []
    while True:
        if scopes:
            _print_scope_overview(scopes)
        action = ask_select(
            "Scopes action",
            [
                Choice(title="Add a macro (recommended)", value="macro"),
                Choice(title="Add exact scope(s)", value="exact"),
                Choice(title="Remove a scope", value="remove"),
                Choice(title="Done with scopes", value="done"),
            ],
            default="macro" if not scopes else "done",
        )
        if action == "done":
            break
        if action == "macro":
            scopes = _prompt_add_macro(scopes)
            continue
        if action == "exact":
            scopes = _prompt_add_exact_scopes(scopes)
            continue
        if action == "remove":
            if not scopes:
                console.print("[yellow]No scopes to remove.[/yellow]")
                continue
            to_remove = ask_checkbox(
                "Select scopes to remove",
                [Choice(title=scope, value=scope) for scope in scopes],
                min_selected=1,
            )
            scopes = [scope for scope in scopes if scope not in set(to_remove)]

    if scopes:
        _print_scope_overview(scopes)
    return scopes


def _prompt_settings_schema() -> list[dict[str, Any]]:
    _print_section("Settings schema")
    fields: list[dict[str, Any]] = []
    while ask_confirm("Add a settings field?", default=False):
        fields.append(_prompt_setting_field())
        _print_overview(
            "Settings schema",
            fields,
            ["#", "name", "label", "type", "required", "defaultValue"],
        )
    return fields


def _prompt_pricing_plans() -> list[dict[str, Any]]:
    _print_section("Pricing plans")
    plans: list[dict[str, Any]] = []
    while ask_confirm("Add a pricing plan?", default=False):
        plans.append(_prompt_pricing_plan())
        _print_overview(
            "Pricing plans",
            plans,
            ["#", "title", "pricingType", "pricePerUnit", "unit", "freeUnits"],
        )
    return plans


def _prompt_app_bars() -> list[dict[str, Any]]:
    _print_section("App bars")
    bars: list[dict[str, Any]] = []
    while ask_confirm("Add an app bar?", default=False):
        bars.append(_prompt_app_bar())
        _print_overview(
            "App bars",
            bars,
            ["#", "label", "location", "iframeUrl", "tooltipLabel"],
        )
    return bars


def _prompt_webhook_controls() -> dict[str, Any]:
    _print_section("Webhook controls")
    controls: dict[str, Any] = {}
    rate = ask_text("Webhook rate limit per minute (optional)", default="100")
    if _optional(rate):
        try:
            controls["webhookRateLimitPerMinute"] = int(rate.strip())
        except ValueError:
            console.print("[yellow]Ignored invalid rate limit; leaving unset.[/yellow]")
    bill_failed = ask_select(
        "Bill failed webhook requests?",
        [
            Choice(title="No", value="false"),
            Choice(title="Yes", value="true"),
            Choice(title="Skip / leave unset", value=""),
        ],
        default="false",
    )
    if bill_failed:
        controls["billFailedWebhookRequests"] = bill_failed == "true"
    return controls


def build_public_app_payload_from_answers(
    *,
    label: str,
    name: str,
    details: dict[str, Any],
    brandmark: str,
    required_scopes: list[str],
    settings_schema: list[dict[str, Any]],
    pricing_plans: list[dict[str, Any]],
    app_bars: list[dict[str, Any]],
    webhook_controls: dict[str, Any],
    runtime: str = "nodejs22",
    auth_method: str = "OAUTH2",
    oauth_redirect_uris: list[str] | None = None,
) -> dict[str, Any]:
    from caraer_cli.commands.apps import DEFAULT_OAUTH_CALLBACK

    method = (auth_method or "OAUTH2").strip().upper()
    redirects = [
        uri.strip()
        for uri in (oauth_redirect_uris or [DEFAULT_OAUTH_CALLBACK])
        if uri and uri.strip()
    ]
    payload: dict[str, Any] = {
        "label": label,
        "name": name,
        "runtime": runtime,
        "authMethod": method,
        "hideApiKeyField": True,
        "oauthRedirectUris": redirects,
        "brandmark": brandmark,
        "details": details,
        "requiredScopes": required_scopes,
        "settingsSchema": settings_schema,
        "pricingPlans": pricing_plans,
        "appBars": app_bars,
    }
    payload.update(webhook_controls)
    return payload


def run_public_app_wizard(
    *,
    output_dir: str | Path | None = None,
    force: bool = False,
    sample_function: str | None = "hello-world",
    runtime: str = "nodejs22",
) -> Path:
    """Run the interactive public-app wizard and scaffold a local app folder.

    Returns the path to ``src/app/app.caraer.yaml`` inside the new app folder.
    """
    from caraer_cli.project.scaffold import scaffold_app_project

    console.print(Panel.fit("Create Public App Wizard", border_style="magenta"))

    from caraer_cli.commands.apps import DEFAULT_OAUTH_CALLBACK

    label, name = _prompt_core()
    details, brandmark = _prompt_details()
    required_scopes = _prompt_scopes()
    settings_schema = _prompt_settings_schema()
    pricing_plans = _prompt_pricing_plans()
    app_bars = _prompt_app_bars()
    webhook_controls = _prompt_webhook_controls()

    auth_method = ask_select(
        "Auth method",
        [
            Choice(title="OAuth 2.0", value="OAUTH2"),
            Choice(title="API key", value="API_KEY"),
        ],
        default="OAUTH2",
    )
    oauth_redirect_uris = [
        ask_text(
            "OAuth callback / redirect URL",
            default=DEFAULT_OAUTH_CALLBACK,
            required=True,
        )
    ]

    _print_section("App")
    console.print(
        f"- label: [bold]{label}[/bold]\n"
        f"- name: [bold]{name}[/bold]\n"
        f"- settings: {len(settings_schema)}\n"
        f"- pricingPlans: {len(pricing_plans)}\n"
        f"- appBars: {len(app_bars)}"
    )
    console.print(
        "[dim]App definition goes in src/app/app.caraer.yaml. "
        "Functions live under src/app/functions/; webhooks under src/app/webhooks/.[/dim]"
    )

    default_dir = str(output_dir or name)
    project_dir = Path(ask_text("App directory", default=default_dir, required=True))
    runtime = ask_select(
        "App runtime",
        [
            Choice(title="Node.js 22", value="nodejs22"),
            Choice(title="Python 3.12", value="python312"),
            Choice(title="Skip sample function", value=""),
        ],
        default=runtime if sample_function else "",
    )
    function_name = sample_function if runtime else None
    if runtime and sample_function:
        function_name = ask_text("Sample function name", default=sample_function, required=True)

    resolved_runtime = runtime or "nodejs22"
    payload = build_public_app_payload_from_answers(
        label=label,
        name=name,
        details=details,
        brandmark=brandmark,
        required_scopes=required_scopes,
        settings_schema=settings_schema,
        pricing_plans=pricing_plans,
        app_bars=app_bars,
        webhook_controls=webhook_controls,
        runtime=resolved_runtime,
        auth_method=auth_method,
        oauth_redirect_uris=oauth_redirect_uris,
    )

    if project_dir.exists() and any(project_dir.iterdir()) and not force:
        if not ask_confirm(
            f"{project_dir} already exists and is not empty. Continue / overwrite app files?",
            default=False,
        ):
            raise WizardCancelled()

    result = scaffold_app_project(
        project_dir,
        app_payload=payload,
        project_name=name,
        sample_function=function_name,
        runtime=resolved_runtime,
        force=True,
    )
    app_file: Path = result["app_file"]
    console.print()
    console.print(f"[green]Created app at {result['root']}[/green]")
    console.print(f"[dim]App definition:[/dim] {app_file}")
    console.print(f"[dim]Functions:[/dim]     {result['functions_dir']}")
    console.print(f"[dim]Webhooks:[/dim]      {result['webhooks_dir']}")
    console.print(
        "[dim]Next:[/dim] cd "
        f"{result['root'].name} && caraer apps push"
    )
    return app_file
