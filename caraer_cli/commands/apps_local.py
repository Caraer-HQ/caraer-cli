"""Local development commands under `caraer apps local`."""

from __future__ import annotations

import typer

from caraer_cli.completion_callbacks import complete_local_function
from caraer_cli.commands.deprecation import register_deprecated_leaf_alias
from caraer_cli.context import AppContext
from caraer_cli.formatters.output import print_data, print_logs, print_success

local_app = typer.Typer(help="Local development and remote diagnostics.", no_args_is_help=True)

_LOCAL_ALIASES = (
    ("dev", "dev"),
    ("test", "test"),
    ("logs", "logs"),
)


def register_aliases(root: typer.Typer) -> None:
    """Register hidden flat aliases (e.g. dev → local dev)."""
    for source_name, alias_name in _LOCAL_ALIASES:
        register_deprecated_leaf_alias(
            root,
            local_app,
            source_name=source_name,
            alias_name=alias_name,
            old_path=f"caraer apps {alias_name}",
            new_path=f"caraer apps local {source_name}",
        )


@local_app.command("test")
def test_function_cmd(
    ctx: typer.Context,
    function: str | None = typer.Argument(
        None,
        help="Local function name (defaults to the only local function, or prompts).",
        autocompletion=complete_local_function,
    ),
    record_uuid: str = typer.Option(..., "--record", help="Record UUID for the sample payload."),
    event_type: str = typer.Option(
        "updated",
        "--event",
        help="Event type (created|updated|deleted).",
    ),
    sample_only: bool = typer.Option(
        False,
        "--sample-only",
        help="Only fetch a sample payload; do not invoke the remote function.",
    ),
    force_provision: bool = typer.Option(
        False,
        "--force-provision",
        help="V1 only: force Cloud Function provision before invoke.",
    ),
) -> None:
    """Remote-invoke a function with a sample webhook payload (or print the sample)."""
    from caraer_cli.api import functions as functions_api
    from caraer_cli.api import projects as projects_api
    from caraer_cli.app_sync import resolve_app_root
    from caraer_cli.project.schema import load_workspace
    from caraer_cli.project.state import load_state
    from caraer_cli.project.sync import resolve_local_function_name

    app_ctx: AppContext = ctx.obj
    root = resolve_app_root(app_file=app_ctx.profile.app_file)
    config = load_workspace(root)
    if not config.appUuid:
        raise ValueError("App has no remote UUID. Run 'caraer apps select' or 'caraer apps push'.")
    function_name = resolve_local_function_name(root, config, function)
    state = load_state(root)
    fn_meta = (state.get("functions") or {}).get(function_name) or {}
    function_uuid = fn_meta.get("uuid")
    client = app_ctx.api_client()
    if not function_uuid:
        remote = functions_api.list_functions(client, config.appUuid, page=1, limit=200)
        for item in remote.get("data") or []:
            if isinstance(item, dict) and item.get("name") == function_name and item.get("uuid"):
                function_uuid = item["uuid"]
                break
    if not function_uuid:
        raise ValueError(
            f"Function '{function_name}' is not tracked locally. Run 'caraer apps push' first."
        )

    if sample_only:
        response = projects_api.sample_payload(
            client,
            config.appUuid,
            record_uuid=record_uuid,
            event_type=event_type,
        )
        print_success(f"Sample payload for '{function_name}'")
        print_data(response.get("data"), app_ctx.output)
        return

    print_success(f"Testing remote function '{function_name}'…")
    response = functions_api.test_function(
        client,
        config.appUuid,
        str(function_uuid),
        record_uuid,
        event_type,
        force_provision=force_provision,
    )
    print_data(response.get("data"), app_ctx.output)


@local_app.command("logs")
def app_logs(
    ctx: typer.Context,
    function: str | None = typer.Option(
        None,
        "--function",
        "-f",
        help="Local function name (defaults to the only local function, or prompts).",
        autocompletion=complete_local_function,
    ),
    all_runtime: bool = typer.Option(
        False,
        "--all",
        help="Fetch app-level V2 container logs (no function filter).",
    ),
    since: str = typer.Option("1h", "--since", help="Lookback window, e.g. 15m, 1h, 24h."),
    follow: bool = typer.Option(
        False,
        "--follow",
        help="Follow new log lines (SSE for --all; poll otherwise).",
    ),
    limit: int = typer.Option(100, "--limit", help="Maximum log lines to return."),
) -> None:
    """Fetch remote logs for a local function (or the whole V2 runtime with --all)."""
    import time

    from caraer_cli.api import functions as functions_api
    from caraer_cli.api import projects as projects_api
    from caraer_cli.app_sync import resolve_app_root
    from caraer_cli.errors import ApiError, NotFoundError
    from caraer_cli.project.schema import load_workspace
    from caraer_cli.project.state import load_state
    from caraer_cli.project.sync import resolve_local_function_name

    app_ctx: AppContext = ctx.obj
    root = resolve_app_root(app_file=app_ctx.profile.app_file)
    config = load_workspace(root)
    if not config.appUuid:
        raise ValueError("App has no remote UUID. Run 'caraer apps select' or 'caraer apps push'.")

    client = app_ctx.api_client()
    function_uuid: str | None = None
    function_name: str | None = None
    if not all_runtime:
        function_name = resolve_local_function_name(root, config, function)
        state = load_state(root)
        fn_meta = (state.get("functions") or {}).get(function_name) or {}
        function_uuid = fn_meta.get("uuid")
        if not function_uuid:
            remote = functions_api.list_functions(client, config.appUuid, page=1, limit=200)
            for item in remote.get("data") or []:
                if isinstance(item, dict) and item.get("name") == function_name and item.get("uuid"):
                    function_uuid = item["uuid"]
                    break
        if not function_uuid:
            raise ValueError(
                f"Function '{function_name}' is not tracked locally. Run 'caraer apps push' first."
            )
        print_success(f"Fetching logs for '{function_name}'…")
    else:
        print_success("Fetching app runtime logs…")

    # Prefer SSE for app-level follow; fall back to polling.
    if all_runtime and follow and (app_ctx.output or "table").lower() == "table":
        try:
            print_success("Streaming runtime logs (SSE)…")
            for event in projects_api.stream_runtime_logs(
                client, config.appUuid, since=since
            ):
                if not isinstance(event, dict):
                    continue
                name = str(event.get("event") or "")
                if name in {"ready", "done"}:
                    continue
                print_logs({"entries": [event]}, seen=None, show_header=False)
            return
        except (ApiError, NotFoundError) as exc:
            print_success(f"SSE unavailable ({exc.status}); falling back to poll.")

    seen: set[str] = set()
    first = True
    while True:
        if all_runtime:
            response = projects_api.get_runtime_logs(
                client,
                config.appUuid,
                since=since,
                limit=limit,
            )
        else:
            response = projects_api.get_function_logs(
                client,
                config.appUuid,
                str(function_uuid),
                since=since,
                limit=limit,
            )
        payload = response.get("data")
        if (app_ctx.output or "table").lower() in {"json", "yaml"}:
            print_data(payload, app_ctx.output)
        else:
            print_logs(payload, seen=seen, show_header=first or not follow)
        first = False
        if not follow:
            break
        time.sleep(3)


@local_app.command("dev")
def app_dev(
    ctx: typer.Context,
    function: str | None = typer.Option(
        None,
        "--function",
        "-f",
        help="Optional: serve only this local function (default: all local functions).",
        autocompletion=complete_local_function,
    ),
    port: int = typer.Option(8787, "--port"),
    host: str = typer.Option("127.0.0.1", "--host"),
    invoke_schedule: str | None = typer.Option(
        None,
        "--invoke-schedule",
        help="Fire a local schedule's payloadTemplate at its function, then exit.",
    ),
    cms: bool = typer.Option(
        False,
        "--cms",
        help="Run the Astro harness for this app's CMS modules instead of the function server.",
    ),
    install: bool = typer.Option(
        False,
        "--install",
        help="Reinstall the CMS harness dependencies before starting.",
    ),
) -> None:
    """Run a local HTTP server matching the V2 container contract.

    Invoke via POST /functions/<name> (canonical), POST /<name>, header
    X-Caraer-Function, or body.functionName. Also emulates installation
    state/secrets/jobs and POST /inbound/<routeName>.

    With --cms, runs an Astro dev server rendering this app's CMS modules with
    an editable field sidebar, so you see the same inputs a content editor gets
    without needing a company or a deployed build.
    """
    from caraer_cli.app_sync import resolve_app_root

    if cms:
        _run_cms_harness(ctx, port=port if port != 8787 else 4321, host=host, install=install)
        return

    from caraer_cli.project.local_dev import serve_functions
    from caraer_cli.project.schema import load_workspace
    from caraer_cli.project.sync import list_local_function_names, resolve_local_function_name

    root = resolve_app_root(app_file=ctx.obj.profile.app_file)
    config = load_workspace(root)
    if function:
        names = [resolve_local_function_name(root, config, function, interactive=False)]
    else:
        names = list_local_function_names(root, config)
        if not names:
            raise ValueError(
                "No local functions found under src/app/functions/. "
                "Add a function folder first."
            )
    base = f"http://{host}:{port}"
    if invoke_schedule:
        print_success(f"Invoking schedule '{invoke_schedule}'…")
    else:
        print_success(f"Starting local dev server on {base}")
        for name in names:
            print_success(f"  POST {base}/functions/{name}")
        print_success(f"  installation shim: {base}/api/v2/apps/<uuid>/installation/…")
        print_success(f"  inbound: POST {base}/inbound/<routeName>")
    serve_functions(
        root,
        config,
        host=host,
        port=port,
        function_names=names,
        invoke_schedule=invoke_schedule,
    )


def _run_cms_harness(ctx: typer.Context, *, port: int, host: str, install: bool) -> None:
    """Generate and run the Astro harness for this app's CMS modules."""
    from caraer_cli.app_sync import resolve_app_root
    from caraer_cli.project.modules_dev import (
        resolve_runtime_specs,
        run_harness,
        write_harness,
    )
    from caraer_cli.project.schema import load_workspace

    root = resolve_app_root(app_file=ctx.obj.profile.app_file)
    config = load_workspace(root)

    # Prefers a local caraer-web checkout so the runtime and the modules can be
    # developed together, and so this works before the packages are published.
    runtime_spec, tokens_spec = resolve_runtime_specs(root)
    if runtime_spec.startswith("file:"):
        print_success(f"Using local runtime from {runtime_spec[5:]}")

    harness, modules = write_harness(
        root,
        config,
        app_name=config.name or "app",
        runtime_spec=runtime_spec,
        tokens_spec=tokens_spec,
    )

    print_success(f"Prepared CMS harness in {harness}")
    for module in modules:
        print_success(f"  {module.name} ({module.kind})")
    print_success(f"Starting Astro on http://{host}:{port}")

    code = run_harness(harness, port=port, host=host, install=install)
    if code != 0:
        raise typer.Exit(code)
