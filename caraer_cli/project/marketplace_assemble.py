"""Assemble modular marketplace/lifecycle files into the app manifest payload."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from caraer_cli.project.app_bars_sync import (
    app_bar_identity,
    discover_local_app_bars,
    resolve_app_bar_functions,
    write_app_bars_files,
)
from caraer_cli.project.lifecycle_sync import (
    LIFECYCLE_HOOKS,
    discover_local_lifecycle,
    resolve_lifecycle_functions,
    write_lifecycle_files,
)
from caraer_cli.project.pricing_sync import (
    discover_local_pricing,
    pricing_identity,
    write_pricing_files,
)
from caraer_cli.project.schema import ProjectConfig
from caraer_cli.project.settings_sync import discover_local_settings, resolve_setting_options_source, write_settings_files
from caraer_cli.project.state import load_state


def _fn_by_name(root: Path) -> dict[str, str]:
    state = load_state(root)
    fn_state = state.get("functions") or {}
    return {
        name: str(meta["uuid"])
        for name, meta in fn_state.items()
        if isinstance(meta, dict) and meta.get("uuid")
    }


def _fn_meta_by_name(root: Path) -> dict[str, dict[str, Any]]:
    state = load_state(root)
    fn_state = state.get("functions") or {}
    return {
        name: meta
        for name, meta in fn_state.items()
        if isinstance(meta, dict) and meta.get("uuid")
    }


def _merge_by_key(
    yaml_items: list[Any],
    file_items: list[dict[str, Any]],
    *,
    identity,
) -> list[dict[str, Any]]:
    """Merge YAML list with file list; files win on identity conflict."""
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for item in yaml_items:
        if not isinstance(item, dict):
            continue
        key = identity(item)
        if not key:
            continue
        if key not in merged:
            order.append(key)
        merged[key] = item
    for item in file_items:
        key = identity(item)
        if not key:
            continue
        if key not in merged:
            order.append(key)
        merged[key] = item
    return [merged[k] for k in order]


def assemble_local_manifest(
    root: Path,
    config: ProjectConfig,
    local: dict[str, Any],
    *,
    resolve_functions: bool = True,
    strict_function_refs: bool = True,
) -> dict[str, Any]:
    """Return a copy of ``local`` with modular disk files merged in.

    When ``resolve_functions`` is True, serverlessFunction name refs are replaced
    with UUIDs from ``.caraer/state.json`` (required before push).
    When ``strict_function_refs`` is False, hooks/bars that cannot resolve are omitted.
    """
    out = dict(local)
    fn_by_name = _fn_by_name(root) if resolve_functions else {}
    fn_meta_by_name = _fn_meta_by_name(root) if resolve_functions else {}
    default_runtime = (
        str(local.get("runtime") or config.runtime or "").strip() or None
    )

    yaml_settings = out.get("settingsSchema") if isinstance(out.get("settingsSchema"), list) else []
    file_settings = [item for _path, item in discover_local_settings(root, config)]
    out["settingsSchema"] = _merge_by_key(
        yaml_settings,
        file_settings,
        identity=lambda i: str(i.get("name") or "").strip().lower(),
    )
    if resolve_functions:
        resolved_settings: list[dict[str, Any]] = []
        for field in out["settingsSchema"]:
            if not isinstance(field, dict):
                continue
            resolved_settings.append(
                resolve_setting_options_source(
                    field, fn_by_name=fn_by_name, strict=strict_function_refs
                )
            )
        out["settingsSchema"] = resolved_settings

    yaml_pricing = out.get("pricingPlans") if isinstance(out.get("pricingPlans"), list) else []
    file_pricing = [item for _path, item in discover_local_pricing(root, config)]
    out["pricingPlans"] = _merge_by_key(
        yaml_pricing,
        file_pricing,
        identity=pricing_identity,
    )

    yaml_bars = out.get("appBars") if isinstance(out.get("appBars"), list) else []
    file_bars = [item for _path, item in discover_local_app_bars(root, config)]
    merged_bars = _merge_by_key(yaml_bars, file_bars, identity=app_bar_identity)
    if resolve_functions:
        resolved_bars: list[dict[str, Any]] = []
        for bar in merged_bars:
            resolved = resolve_app_bar_functions(
                bar, fn_by_name=fn_by_name, strict=strict_function_refs
            )
            if resolved is not None:
                resolved_bars.append(resolved)
        out["appBars"] = resolved_bars
    else:
        out["appBars"] = merged_bars

    file_hooks = discover_local_lifecycle(root, config)
    for _stem, (manifest_key, expected_topic) in LIFECYCLE_HOOKS.items():
        hook = file_hooks.get(manifest_key)
        if hook is None:
            continue
        payload = dict(hook)
        if not payload.get("topic"):
            payload["topic"] = expected_topic
        if resolve_functions:
            resolved = resolve_lifecycle_functions(
                payload,
                fn_by_name=fn_by_name,
                fn_meta_by_name=fn_meta_by_name,
                strict=strict_function_refs,
                default_runtime=default_runtime,
            )
            if resolved is None:
                out.pop(manifest_key, None)
                continue
            payload = resolved
        out[manifest_key] = payload

    return out


def split_marketplace_to_disk(
    root: Path,
    config: ProjectConfig,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Write modular files from a remote/local payload and clear arrays/hooks in YAML copy."""
    out = dict(payload)

    settings = out.get("settingsSchema") if isinstance(out.get("settingsSchema"), list) else []
    write_settings_files(root, config, [i for i in settings if isinstance(i, dict)])
    out["settingsSchema"] = []

    pricing = out.get("pricingPlans") if isinstance(out.get("pricingPlans"), list) else []
    write_pricing_files(root, config, [i for i in pricing if isinstance(i, dict)])
    out["pricingPlans"] = []

    bars = out.get("appBars") if isinstance(out.get("appBars"), list) else []
    write_app_bars_files(root, config, [i for i in bars if isinstance(i, dict)])
    out["appBars"] = []

    hooks = {
        key: out.get(key) if isinstance(out.get(key), dict) else None
        for _stem, (key, _topic) in LIFECYCLE_HOOKS.items()
    }
    write_lifecycle_files(root, config, hooks)
    for key in hooks:
        out.pop(key, None)

    return out
