"""Append marketplace items into app.caraer.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from caraer_cli.local_app import load_local_app
from caraer_cli.project.paths import app_manifest_path
from caraer_cli.project.scaffold import write_app_manifest
from caraer_cli.project.schema import ProjectConfig


def append_manifest_list_item(
    root: Path,
    config: ProjectConfig,
    *,
    list_key: str,
    item: dict[str, Any],
    identity: Callable[[dict[str, Any]], str],
    force: bool = False,
) -> Path:
    """Append (or replace) an item in a top-level list on ``app.caraer.yaml``.

    On 2026.2.1, ``settingsSchema`` items are written to ``settings.yaml``.
    """
    if config.is_layout_v21() and list_key == "settingsSchema":
        from caraer_cli.project.settings_sync import append_settings_yaml_field

        return append_settings_yaml_field(root, config, item, force=force)
    manifest_path = app_manifest_path(root, config.srcDir)
    if not manifest_path.is_file():
        raise FileNotFoundError(f"App manifest not found: {manifest_path}")
    payload = load_local_app(manifest_path)
    items = payload.get(list_key)
    if not isinstance(items, list):
        items = []
    key = identity(item)
    if not key:
        raise ValueError(f"Cannot determine identity for {list_key} item.")
    existing_idx = None
    for idx, current in enumerate(items):
        if isinstance(current, dict) and identity(current) == key:
            existing_idx = idx
            break
    if existing_idx is not None and not force:
        raise FileExistsError(
            f"{list_key} already has an item matching '{key}'. Use --force to replace."
        )
    next_items = list(items)
    if existing_idx is not None:
        next_items[existing_idx] = item
    else:
        next_items.append(item)
    payload[list_key] = next_items
    return write_app_manifest(
        root, payload, src_dir=config.srcDir, include_examples=False
    )
