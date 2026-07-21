from __future__ import annotations

from pathlib import Path

from caraer_cli.context import AppContext
from caraer_cli.local_app import resolve_app_file_path


def resolve_app_uuid(app_ctx: AppContext, app_uuid: str | None) -> str:
    """Resolve a remote app UUID from an explicit arg or the selected profile app."""
    resolved = (app_uuid or "").strip() or (app_ctx.profile.app_uuid or "").strip()
    if not resolved:
        local = (app_ctx.profile.app_file or "").strip()
        hint = (
            f" A local app file is selected ({local}); run 'caraer apps push' "
            "to create it remotely first."
            if local
            else ""
        )
        raise ValueError(
            "No remote app selected. Pass an app UUID, or run "
            "'caraer apps select <uuid>' (after 'caraer apps list')."
            + hint
        )
    return resolved


def resolve_app_file(app_ctx: AppContext, app_file: str | None = None) -> Path:
    """Resolve a local app file from an explicit arg or the selected profile file."""
    resolved = (app_file or "").strip() or (app_ctx.profile.app_file or "").strip()
    if not resolved:
        raise ValueError(
            "No local app file selected. Pass --file, or run "
            "'caraer apps select <uuid|path>' / 'caraer apps pull'."
        )
    return resolve_app_file_path(resolved)


def resolve_optional_file(
    app_ctx: AppContext,
    file: str | None,
    *,
    required_message: str | None = None,
) -> Path | None:
    """Resolve --file, falling back to the selected local app file."""
    if file:
        return resolve_app_file_path(file)
    if app_ctx.profile.app_file:
        try:
            return resolve_app_file_path(app_ctx.profile.app_file)
        except (FileNotFoundError, ValueError):
            pass
    if required_message:
        raise ValueError(required_message)
    return None
