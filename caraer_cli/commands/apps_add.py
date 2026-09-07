"""Scaffold commands under `caraer apps add`."""

from __future__ import annotations

import typer

from caraer_cli.completion_callbacks import (
    complete_local_function,
    complete_runtime,
    complete_setting_field_type,
)
from caraer_cli.commands.deprecation import register_deprecated_leaf_alias
from caraer_cli.context import AppContext
from caraer_cli.formatters.output import print_success

add_app = typer.Typer(help="Scaffold local app resources.", no_args_is_help=True)

_ADD_ALIASES = (
    ("function", "add-function"),
    ("options-function", "add-options-function"),
    ("webhook", "add-webhook"),
    ("schedule", "add-schedule"),
    ("inbound", "add-inbound"),
    ("setting", "add-setting"),
    ("lifecycle-hook", "add-lifecycle-hook"),
    ("module", "add-module"),
)


def normalize_function_name(value: str) -> str:
    import re

    normalized = value.strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    return normalized


def parse_visible_when(raw: str) -> list[dict[str, object]]:
    """Parses `--visible-when` entries into settingsSchema conditions.

    Each comma-separated entry is `field[:operator[:value]]`; `IN` / `NOT_IN`
    values are split on `|`.
    """
    from caraer_cli.wizard.catalog import (
        LIST_CONDITION_OPERATORS,
        VALUELESS_CONDITION_OPERATORS,
    )

    conditions: list[dict[str, object]] = []
    for entry in raw.split(","):
        text = entry.strip()
        if not text:
            continue
        parts = text.split(":", 2)
        field = parts[0].strip()
        if not field:
            raise ValueError(f"visible-when entry '{text}' is missing a field name.")
        operator = (parts[1].strip().upper() if len(parts) > 1 and parts[1].strip() else "EQUALS")
        condition: dict[str, object] = {"field": field, "operator": operator}
        if operator not in VALUELESS_CONDITION_OPERATORS:
            if len(parts) < 3 or not parts[2].strip():
                raise ValueError(f"visible-when entry '{text}' needs a value for {operator}.")
            value = parts[2].strip()
            if operator in LIST_CONDITION_OPERATORS:
                condition["value"] = [p.strip() for p in value.split("|") if p.strip()]
            elif value.lower() in {"true", "false"}:
                condition["value"] = value.lower() == "true"
            else:
                condition["value"] = value
        conditions.append(condition)
    return conditions


def register_aliases(root: typer.Typer) -> None:
    """Register hidden flat aliases (e.g. add-function → add function)."""
    for source_name, alias_name in _ADD_ALIASES:
        register_deprecated_leaf_alias(
            root,
            add_app,
            source_name=source_name,
            alias_name=alias_name,
            old_path=f"caraer apps {alias_name}",
            new_path=f"caraer apps add {source_name}",
        )


@add_app.command("function")
def add_function(
    ctx: typer.Context,
    name: str | None = typer.Argument(
        None,
        help="Function name / folder (e.g. hello-world). Prompted if omitted.",
    ),
    runtime: str | None = typer.Option(
        None,
        "--runtime",
        help="nodejs22 or python312 (defaults to caraer.json runtime or nodejs22).",
        autocompletion=complete_runtime,
    ),
    description: str = typer.Option("", "--description", help="Function description."),
    template: str | None = typer.Option(
        None,
        "--template",
        help="Optional scaffold template: options (LOAD_SETTING_OPTIONS loader).",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite existing scaffold files."),
) -> None:
    """Scaffold a local function folder under src/app/functions/<name>/."""
    from caraer_cli.app_sync import resolve_app_root
    from caraer_cli.project.schema import load_workspace
    from caraer_cli.project.sync import scaffold_function
    from caraer_cli.wizard.prompts import require_text

    app_ctx: AppContext = ctx.obj
    name = require_text(name, "Function name", flag="name")
    root = resolve_app_root(app_file=app_ctx.pinned_app_file)
    config = load_workspace(root)
    normalized = normalize_function_name(name)
    if not normalized:
        raise ValueError("Function name must contain letters or digits.")
    resolved_runtime = (runtime or config.resolved_runtime("nodejs22")).strip().lower()
    if resolved_runtime not in {"nodejs22", "python312"}:
        raise ValueError("runtime must be nodejs22 or python312")
    resolved_template = (template or "").strip().lower() or None
    if resolved_template and resolved_template not in {"options"}:
        raise ValueError("Unknown --template. Supported: options")
    try:
        folder = scaffold_function(
            root,
            config,
            normalized,
            resolved_runtime,
            description=description or None,
            force=force,
            template=resolved_template,
        )
    except FileExistsError as exc:
        raise ValueError(str(exc)) from None
    print_success(f"Created function scaffold at {folder}")


@add_app.command("options-function")
def add_options_function(
    ctx: typer.Context,
    name: str | None = typer.Argument(
        None,
        help="Function name / folder (e.g. list-calendars). Prompted if omitted.",
    ),
    runtime: str | None = typer.Option(
        None,
        "--runtime",
        help="nodejs22 or python312 (defaults to caraer.json runtime or nodejs22).",
        autocompletion=complete_runtime,
    ),
    description: str = typer.Option(
        "",
        "--description",
        help="Function description (defaults to LOAD_SETTING_OPTIONS blurb).",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite existing scaffold files."),
) -> None:
    """Scaffold a LOAD_SETTING_OPTIONS function for dynamic setting selects."""
    from caraer_cli.app_sync import resolve_app_root
    from caraer_cli.project.schema import load_workspace
    from caraer_cli.project.sync import scaffold_options_function
    from caraer_cli.wizard.prompts import require_text

    app_ctx: AppContext = ctx.obj
    name = require_text(name, "Options function name", flag="name")
    root = resolve_app_root(app_file=app_ctx.pinned_app_file)
    config = load_workspace(root)
    normalized = normalize_function_name(name)
    if not normalized:
        raise ValueError("Function name must contain letters or digits.")
    resolved_runtime = (runtime or config.resolved_runtime("nodejs22")).strip().lower()
    if resolved_runtime not in {"nodejs22", "python312"}:
        raise ValueError("runtime must be nodejs22 or python312")
    try:
        folder = scaffold_options_function(
            root,
            config,
            normalized,
            resolved_runtime,
            description=description or None,
            force=force,
        )
    except FileExistsError as exc:
        raise ValueError(str(exc)) from None
    print_success(f"Created options-function scaffold at {folder}")
    print_success(
        "Wire it with settingsSchema optionsSource.serverlessFunctionName "
        f"= '{normalized}' (optional optionsSource.dependsOn for refetch)."
    )


@add_app.command("webhook")
def add_webhook(
    ctx: typer.Context,
    topic: str | None = typer.Option(
        None,
        "--topic",
        "-t",
        help="Webhook topic (e.g. record.candidate.created, app.bar.triggered). Prompted if omitted.",
    ),
    function: str | None = typer.Option(
        None,
        "--function",
        "-f",
        help="Local function name for SERVERLESS delivery.",
        autocompletion=complete_local_function,
    ),
    mode: str = typer.Option(
        "SERVERLESS",
        "--mode",
        help="SERVERLESS (default) or HTTP.",
    ),
    url: str | None = typer.Option(None, "--url", help="Destination URL when --mode HTTP."),
    webhook_format: str = typer.Option(
        "USER_FRIENDLY",
        "--format",
        help="Webhook payload format (e.g. USER_FRIENDLY, RAW).",
    ),
    description: str = typer.Option("", "--description", help="Webhook description."),
    filename: str | None = typer.Option(
        None,
        "--filename",
        help="Output file name under webhooks/ (default: <topic>-serverless.json).",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing webhook file."),
) -> None:
    """Scaffold a local webhook JSON under src/app/webhooks/."""
    from caraer_cli.app_sync import resolve_app_root
    from caraer_cli.project.scaffold import scaffold_webhook
    from caraer_cli.project.schema import load_workspace
    from caraer_cli.wizard.prompts import require_text

    app_ctx: AppContext = ctx.obj
    topic = require_text(topic, "Webhook topic", flag="--topic")
    root = resolve_app_root(app_file=app_ctx.pinned_app_file)
    config = load_workspace(root)
    resolved_mode = mode.strip().upper()
    function_name = normalize_function_name(function) if function else None
    if resolved_mode == "SERVERLESS" and not function_name:
        function_name = normalize_function_name(
            require_text(None, "Function name", flag="--function")
        )
    if resolved_mode == "HTTP" and not (url and url.strip()):
        url = require_text(None, "Webhook URL", flag="--url")
    if resolved_mode == "SERVERLESS" and not function_name:
        raise ValueError("SERVERLESS webhooks require --function <name>.")
    if resolved_mode == "HTTP" and not (url and url.strip()):
        raise ValueError("HTTP webhooks require --url <https://...>.")
    try:
        path = scaffold_webhook(
            root,
            config,
            topic=topic.strip(),
            function_name=function_name,
            delivery_mode=resolved_mode,
            url=url,
            webhook_format=webhook_format.strip() or "USER_FRIENDLY",
            description=description or None,
            filename=filename,
            force=force,
        )
    except FileExistsError as exc:
        raise ValueError(str(exc)) from None
    print_success(f"Created webhook scaffold at {path}")


@add_app.command("schedule")
def add_schedule(
    ctx: typer.Context,
    name: str | None = typer.Argument(None, help="Schedule name (e.g. renew-gmail-watch)."),
    function: str | None = typer.Option(
        None,
        "--function",
        "-f",
        help="Local function name to invoke.",
        autocompletion=complete_local_function,
    ),
    schedule: str | None = typer.Option(
        None,
        "--cron",
        help=(
            "Spring 5–6 field cron (e.g. '0 0 9 * * 1-5'). "
            "Prompted interactively when omitted on a TTY."
        ),
    ),
    description: str | None = typer.Option(
        None,
        "--description",
        help="Optional schedule description.",
    ),
    enabled: bool | None = typer.Option(
        None,
        "--enabled/--disabled",
        help="Whether the schedule is enabled (default: enabled).",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite existing file."),
) -> None:
    """Scaffold a local schedule JSON under src/app/schedules/."""
    from caraer_cli.app_sync import resolve_app_root
    from caraer_cli.project.paths import schedules_dir
    from caraer_cli.project.schema import load_workspace
    from caraer_cli.project.sync import list_local_function_names
    from caraer_cli.wizard.marketplace import prompt_schedule
    from caraer_cli.wizard.prompts import WizardCancelled

    app_ctx: AppContext = ctx.obj
    root = resolve_app_root(app_file=app_ctx.pinned_app_file)
    config = load_workspace(root)
    try:
        answers = prompt_schedule(
            name=name,
            function_name=function,
            cron=schedule,
            description=description,
            enabled=enabled,
            function_choices=list_local_function_names(root, config),
        )
    except WizardCancelled:
        raise typer.Exit(1) from None

    function_name = normalize_function_name(str(answers["function_name"]))
    schedule_key = normalize_function_name(str(answers["name"]))
    base = schedules_dir(root, config.srcDir)
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{schedule_key}.json"
    if path.exists() and not force:
        raise ValueError(f"Schedule file already exists: {path}")
    payload = {
        "name": schedule_key.replace("-", "_"),
        "schedule": answers["schedule"],
        "enabled": bool(answers.get("enabled", True)),
        "serverlessFunction": {"name": function_name},
    }
    if answers.get("description"):
        payload["description"] = answers["description"]
    from caraer_cli.project.json_schemas import SCHEDULE_SCHEMA_URL, dump_json_with_schema

    dump_json_with_schema(path, payload, SCHEDULE_SCHEMA_URL)
    print_success(f"Created schedule scaffold at {path}")


@add_app.command("inbound")
def add_inbound(
    ctx: typer.Context,
    name: str | None = typer.Argument(None, help="Inbound route name (e.g. gmail-push)."),
    function: str | None = typer.Option(
        None,
        "--function",
        "-f",
        help="Local function name to invoke.",
        autocompletion=complete_local_function,
    ),
    auth: str = typer.Option(
        "SHARED_SECRET",
        "--auth",
        help="NONE, SHARED_SECRET, or GOOGLE_OIDC.",
    ),
    enqueue: bool = typer.Option(True, "--enqueue/--sync", help="Enqueue as app job (default) or sync invoke."),
    force: bool = typer.Option(False, "--force", help="Overwrite existing file."),
) -> None:
    """Scaffold a local inbound route JSON under src/app/inbound/."""
    from caraer_cli.app_sync import resolve_app_root
    from caraer_cli.project.paths import inbound_dir
    from caraer_cli.project.schema import load_workspace
    from caraer_cli.wizard.prompts import require_text

    app_ctx: AppContext = ctx.obj
    name = require_text(name, "Inbound route name", flag="name")
    function_name = normalize_function_name(
        require_text(function, "Function name", flag="--function")
    )
    root = resolve_app_root(app_file=app_ctx.pinned_app_file)
    config = load_workspace(root)
    base = inbound_dir(root, config.srcDir)
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{normalize_function_name(name)}.json"
    if path.exists() and not force:
        raise ValueError(f"Inbound file already exists: {path}")
    payload = {
        "name": normalize_function_name(name),
        "authMode": auth.strip().upper(),
        "enqueue": enqueue,
        "serverlessFunction": {"name": function_name},
    }
    from caraer_cli.project.json_schemas import INBOUND_SCHEMA_URL, dump_json_with_schema

    dump_json_with_schema(path, payload, INBOUND_SCHEMA_URL)
    print_success(f"Created inbound scaffold at {path}")


@add_app.command("module")
def add_module(
    ctx: typer.Context,
    name: str | None = typer.Argument(None, help="Module name in snake_case (e.g. hero)."),
    label: str | None = typer.Option(None, "--label", help="Name shown in the builder library."),
    kind: str = typer.Option(
        "section",
        "--kind",
        help="section (composes into a page), page (a whole page), header, or footer.",
    ),
    framework: str | None = typer.Option(
        None,
        "--framework",
        help="Scaffold an interactive island: react, preact, solid, svelte or vue.",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing module."),
) -> None:
    """Scaffold a CMS module under src/app/modules/.

    A module is an Astro component the website builder can place on a page. The
    fields declared in the module's manifest become the inputs a content editor
    sees, and arrive in the component as Astro.props.fields.
    """
    import re

    from caraer_cli.app_sync import resolve_app_root
    from caraer_cli.project.modules_codegen import write_module_types
    from caraer_cli.project.modules_sync import (
        MODULE_KINDS,
        PINNED_FRAMEWORK_MAJORS,
        discover_local_modules,
    )
    from caraer_cli.project.modules_scaffold import scaffold_module
    from caraer_cli.project.schema import load_workspace
    from caraer_cli.wizard.prompts import require_text

    app_ctx: AppContext = ctx.obj
    raw_name = require_text(name, "Module name", flag="name")
    module_name = re.sub(r"[^a-z0-9]+", "_", raw_name.strip().lower()).strip("_")
    if not module_name:
        raise ValueError("Module name must contain at least one letter or digit.")

    kind_value = kind.strip().lower()
    if kind_value not in MODULE_KINDS:
        raise ValueError(f"kind must be one of {sorted(MODULE_KINDS)}, got '{kind}'.")

    framework_value = framework.strip().lower() if framework else None
    if framework_value and framework_value not in PINNED_FRAMEWORK_MAJORS:
        raise ValueError(
            f"framework must be one of {sorted(PINNED_FRAMEWORK_MAJORS)}, got '{framework}'."
        )

    root = resolve_app_root(app_file=app_ctx.pinned_app_file)
    config = load_workspace(root)

    directory = scaffold_module(
        root,
        config,
        name=module_name,
        label=label,
        kind=kind_value,
        framework=framework_value,
        force=force,
    )

    # Write the field types straight away so the scaffolded index.astro
    # type-checks in the editor without a separate validate run.
    for module in discover_local_modules(root, config):
        if module.name == module_name:
            write_module_types(module)
            break

    print_success(f"Created module scaffold at {directory}")


@add_app.command("setting")
def add_setting(
    ctx: typer.Context,
    name: str | None = typer.Argument(None, help="Setting field name (e.g. pubsub_topic)."),
    label: str | None = typer.Option(None, "--label", help="Display label."),
    field_type: str | None = typer.Option(
        None,
        "--type",
        help=(
            "Setting field type (SINGLE_LINE, OBJECT_SINGLE_SELECT, "
            "PROPERTY_SINGLE_SELECT, SINGLE_SELECT, …)."
        ),
        autocompletion=complete_setting_field_type,
    ),
    required: bool | None = typer.Option(
        None, "--required/--optional", help="Mark as required."
    ),
    help_text: str | None = typer.Option(None, "--help-text", help="Help text for installers."),
    default: str | None = typer.Option(None, "--default", help="Default value."),
    options_mode: str | None = typer.Option(
        None,
        "--options-mode",
        help="For SINGLE/MULTI_SELECT: static or dynamic.",
    ),
    options: str | None = typer.Option(
        None,
        "--options",
        help="Static options as comma-separated label=name (or name).",
    ),
    options_function: str | None = typer.Option(
        None,
        "--options-function",
        help="Local function name for optionsSource (dynamic selects).",
        autocompletion=complete_local_function,
    ),
    depends_on: str | None = typer.Option(
        None,
        "--depends-on",
        help="Comma-separated sibling setting names for optionsSource.dependsOn.",
    ),
    visible_when: str | None = typer.Option(
        None,
        "--visible-when",
        help=(
            "Conditional visibility as field[:operator[:value]] "
            "(repeat with commas, e.g. 'custom_mapping:EQUALS:true')."
        ),
    ),
    modular: bool = typer.Option(
        False,
        "--modular",
        help="Write src/app/settings/<name>.json instead of app.caraer.yaml.",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite existing entry/file."),
) -> None:
    """Add a settingsSchema field to app.caraer.yaml (wizard prompts when interactive)."""
    from caraer_cli.app_sync import resolve_app_root
    from caraer_cli.project.manifest_edit import append_manifest_list_item
    from caraer_cli.project.scaffold import scaffold_setting
    from caraer_cli.project.schema import load_workspace
    from caraer_cli.project.settings_sync import sanitize_setting
    from caraer_cli.project.sync import list_local_function_names, scaffold_options_function
    from caraer_cli.wizard.marketplace import prompt_setting_field

    app_ctx: AppContext = ctx.obj
    root = resolve_app_root(app_file=app_ctx.pinned_app_file)
    config = load_workspace(root)

    sibling_names: list[str] = []
    try:
        from caraer_cli.local_app import load_local_app
        from caraer_cli.project.marketplace_assemble import assemble_local_manifest
        from caraer_cli.project.paths import app_manifest_path
        from caraer_cli.project.settings_sync import discover_local_settings

        manifest_path = app_manifest_path(root, config.srcDir)
        manifest = load_local_app(manifest_path) if manifest_path.is_file() else {}
        assembled = assemble_local_manifest(
            root, config, manifest, resolve_functions=False, strict_function_refs=False
        )
        for item in assembled.get("settingsSchema") or []:
            if isinstance(item, dict) and item.get("name"):
                sibling_names.append(str(item["name"]))
        if not sibling_names:
            sibling_names = [
                str(item.get("name"))
                for _, item in discover_local_settings(root, config)
                if item.get("name")
            ]
    except Exception:
        sibling_names = []

    deps = (
        [p.strip() for p in depends_on.split(",") if p.strip()]
        if depends_on is not None
        else None
    )
    conditions = parse_visible_when(visible_when) if visible_when is not None else None
    raw = prompt_setting_field(
        name=name,
        label=label,
        field_type=field_type,
        required=required,
        help_text=help_text,
        default_value=default,
        function_choices=list_local_function_names(root, config),
        sibling_setting_names=sibling_names,
        offer_options_scaffold=True,
        options_mode=options_mode,
        options_function=(
            normalize_function_name(options_function) if options_function else None
        ),
        depends_on=deps,
        static_options=options,
        visible_when=conditions,
    )
    scaffold_fn = raw.pop("_scaffoldOptionsFunction", None)
    field = sanitize_setting(raw)
    if scaffold_fn:
        try:
            folder = scaffold_options_function(
                root,
                config,
                normalize_function_name(str(scaffold_fn)),
                config.resolved_runtime("nodejs22"),
                force=force,
            )
            print_success(f"Created options-function scaffold at {folder}")
        except FileExistsError:
            print_success(
                f"Options function '{scaffold_fn}' already exists — linking by name."
            )
    try:
        if modular:
            path = scaffold_setting(
                root,
                config,
                name=str(field["name"]),
                field=field,
                force=force,
            )
            print_success(f"Created setting file at {path}")
        else:
            path = append_manifest_list_item(
                root,
                config,
                list_key="settingsSchema",
                item=field,
                identity=lambda i: str(i.get("name") or "").strip().lower(),
                force=force,
            )
            print_success(f"Added setting '{field['name']}' to {path}")
    except FileExistsError as exc:
        raise ValueError(str(exc)) from None


@add_app.command("lifecycle-hook")
def add_lifecycle_hook(
    ctx: typer.Context,
    event: str | None = typer.Argument(
        None, help="install | uninstall | rotate | update"
    ),
    function: str | None = typer.Option(
        None,
        "--function",
        "-f",
        help="Function name (default: on-<event>).",
        autocompletion=complete_local_function,
    ),
    no_function: bool = typer.Option(
        False,
        "--no-function",
        help="Only write lifecycle/<event>.json (do not scaffold a function).",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite existing files."),
) -> None:
    """Scaffold a lifecycle hook under src/app/lifecycle/ (+ optional function)."""
    from caraer_cli.app_sync import resolve_app_root
    from caraer_cli.project.scaffold import scaffold_lifecycle_hook
    from caraer_cli.project.schema import load_workspace
    from caraer_cli.wizard.marketplace import prompt_lifecycle_hook

    app_ctx: AppContext = ctx.obj
    root = resolve_app_root(app_file=app_ctx.pinned_app_file)
    config = load_workspace(root)
    options = prompt_lifecycle_hook(
        event=event,
        function_name=normalize_function_name(function) if function else None,
        create_function=False if no_function else None,
    )
    try:
        result = scaffold_lifecycle_hook(
            root,
            config,
            event=str(options["event"]),
            function_name=options.get("function_name"),
            create_function=bool(options.get("create_function")),
            delivery_mode=str(options.get("deliveryMode") or "SERVERLESS"),
            url=options.get("url"),
            enabled=bool(options.get("enabled", True)),
            force=force,
        )
    except (FileExistsError, ValueError) as exc:
        raise ValueError(str(exc)) from None
    print_success(f"Created lifecycle hook at {result['lifecycleFile']}")
    if result.get("functionFolder"):
        print_success(f"Created function scaffold at {result['functionFolder']}")
