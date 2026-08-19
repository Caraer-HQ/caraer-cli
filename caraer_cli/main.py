from __future__ import annotations

import typer

from caraer_cli import __version__
from caraer_cli.commands import (
    apps,
    auth,
    billing,
    company,
    profile,
    publish,
    sandbox,
    skill,
    webhooks,
)
from caraer_cli.completion_callbacks import complete_output_format, complete_profile
from caraer_cli.context import AppContext
from caraer_cli.errors import ApiError
from caraer_cli.formatters.output import print_error
from caraer_cli.state.config import active_profile, load_config
from caraer_cli.state.session import get_session_token

app = typer.Typer(
    help="Caraer external developer CLI.",
    no_args_is_help=True,
    add_completion=False,
)
app.add_typer(auth.app, name="auth")
app.add_typer(company.app, name="company")
app.add_typer(apps.app, name="apps")
app.add_typer(webhooks.app, name="webhooks")
app.add_typer(publish.app, name="publish")
app.add_typer(sandbox.app, name="sandbox")
app.add_typer(profile.app, name="profile")
app.add_typer(skill.app, name="skill")
app.add_typer(billing.app, name="billing")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"caraer-cli {__version__}")
        raise typer.Exit()


@app.callback()
def root(
    ctx: typer.Context,
    profile: str = typer.Option(
        None,
        "--profile",
        help="Override config profile for this command.",
        autocompletion=complete_profile,
    ),
    output: str = typer.Option(
        None,
        "--output",
        help="table|json|yaml",
        autocompletion=complete_output_format,
    ),
    debug: bool = typer.Option(False, "--debug", help="Show debug details on API errors."),
    version: bool = typer.Option(
        False,
        "--version",
        help="Show the CLI version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """Caraer external developer CLI."""
    # During shell completion Click/Typer sets resilient_parsing; keep side effects light.
    if ctx.resilient_parsing:
        ctx.obj = None
        return

    cfg = load_config()
    profile_name, profile_cfg = active_profile(cfg, profile)
    selected_output = output or profile_cfg.output
    token = get_session_token(profile_name)
    ctx.obj = AppContext(
        config=cfg,
        profile_name=profile_name,
        profile=profile_cfg,
        token=token,
        output=selected_output,
        debug=debug,
    )


def run() -> None:
    try:
        app()
    except ApiError as exc:
        print_error(str(exc))
        raise SystemExit(2) from None
    except ValueError as exc:
        print_error(str(exc))
        raise SystemExit(2) from None
    except typer.Exit:
        raise
    except SystemExit:
        raise


if __name__ == "__main__":
    run()
