"""Dynamic shell autocompletion callbacks."""

from __future__ import annotations

from typing import Any

import typer

from caraer_cli.completion import complete_from_pairs
from caraer_cli.local_app import discover_local_app_files, local_app_summary
from caraer_cli.state.config import load_config


def complete_profile(ctx: typer.Context, incomplete: str) -> list[tuple[str, str]]:
    try:
        cfg = load_config()
    except Exception:
        return []
    pairs = [(name, profile.base_url) for name, profile in cfg.profiles.items()]
    return complete_from_pairs(pairs, incomplete)


def complete_output_format(ctx: typer.Context, incomplete: str) -> list[tuple[str, str]]:
    return complete_from_pairs(
        [("table", "Human-readable table"), ("json", "JSON"), ("yaml", "YAML")],
        incomplete,
    )


def complete_local_app(ctx: typer.Context, incomplete: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    try:
        for path in discover_local_app_files():
            try:
                summary = local_app_summary(path)
                label = summary.get("label") or summary.get("name") or path.name
                pairs.append((str(path), str(label)))
                # Also offer project/dir style selection when nested.
                if path.parent.name == "app" and path.name.startswith("app.caraer."):
                    project_root = path.parents[2] if len(path.parents) >= 3 else path.parent
                    pairs.append((str(project_root), f"app: {label}"))
            except Exception:
                pairs.append((str(path), path.name))
    except Exception:
        return []
    return complete_from_pairs(pairs, incomplete)


def _completion_app_context() -> Any | None:
    """Build a lightweight AppContext for completion-time API lookups."""
    try:
        from caraer_cli.context import AppContext
        from caraer_cli.state.config import active_profile, load_config
        from caraer_cli.state.session import get_session_token

        cfg = load_config()
        profile_name, profile_cfg = active_profile(cfg)
        token = get_session_token(profile_name)
        if not token:
            return None
        return AppContext(
            config=cfg,
            profile_name=profile_name,
            profile=profile_cfg,
            token=token,
            output="json",
            debug=False,
        )
    except Exception:
        return None


def complete_app_ref(ctx: typer.Context, incomplete: str) -> list[tuple[str, str]]:
    """Complete remote app UUIDs and local app paths."""
    results = complete_local_app(ctx, incomplete)
    app_ctx = getattr(ctx, "obj", None) or _completion_app_context()
    if app_ctx is None:
        return results
    try:
        from caraer_cli.api import apps as apps_api

        response = apps_api.list_apps(
            app_ctx.api_client(),
            app_type="my",
            page=1,
            limit=50,
        )
        rows = response.get("data") if isinstance(response.get("data"), list) else []
        pairs: list[tuple[str, str]] = []
        for row in rows:
            if not isinstance(row, dict) or not row.get("uuid"):
                continue
            label = row.get("label") or row.get("name") or "app"
            pairs.append((str(row["uuid"]), str(label)))
        results.extend(complete_from_pairs(pairs, incomplete))
    except Exception:
        pass
    return results


def complete_company(ctx: typer.Context, incomplete: str) -> list[tuple[str, str]]:
    app_ctx = getattr(ctx, "obj", None) or _completion_app_context()
    if app_ctx is None:
        return []
    try:
        from caraer_cli.api import auth as auth_api

        response = auth_api.companies(app_ctx.api_client())
        companies = response.get("data") if isinstance(response.get("data"), list) else []
        pairs: list[tuple[str, str]] = []
        for company in companies:
            if not isinstance(company, dict) or not company.get("uuid"):
                continue
            pairs.append((str(company["uuid"]), str(company.get("name") or "company")))
        return complete_from_pairs(pairs, incomplete)
    except Exception:
        return []


def complete_runtime(ctx: typer.Context, incomplete: str) -> list[tuple[str, str]]:
    return complete_from_pairs(
        [("nodejs22", "Node.js 22"), ("python312", "Python 3.12")],
        incomplete,
    )


def complete_auth_method(ctx: typer.Context, incomplete: str) -> list[tuple[str, str]]:
    return complete_from_pairs(
        [("OAUTH2", "OAuth 2.0"), ("API_KEY", "API key")],
        incomplete,
    )


def complete_local_function(ctx: typer.Context, incomplete: str) -> list[tuple[str, str]]:
    try:
        from caraer_cli.app_sync import resolve_app_root
        from caraer_cli.project.schema import load_workspace
        from caraer_cli.project.sync import list_local_function_names
        from caraer_cli.state.config import active_profile, load_config

        cfg = load_config()
        _, profile = active_profile(cfg)
        root = resolve_app_root(app_file=profile.app_file)
        config = load_workspace(root)
        pairs = [(name, "local function") for name in list_local_function_names(root, config)]
        return complete_from_pairs(pairs, incomplete)
    except Exception:
        return []


def complete_app_list_type(ctx: typer.Context, incomplete: str) -> list[tuple[str, str]]:
    return complete_from_pairs(
        [
            ("my", "Apps you created"),
            ("private", "Private apps"),
            ("public", "Public marketplace apps"),
            ("native", "Native apps"),
            ("local", "Local project files"),
        ],
        incomplete,
    )

