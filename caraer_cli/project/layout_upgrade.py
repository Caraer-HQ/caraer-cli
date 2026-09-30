"""Rewrite a 2026.2 workspace into the 2026.2.1 file layout."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from caraer_cli.project.paths import (
    app_bars_dir,
    functions_dir,
    inbound_dir,
    lifecycle_dir,
    modules_dir,
    schedules_dir,
    settings_dir,
    settings_sections_dir,
    webhooks_dir,
)
from caraer_cli.project.schema import (
    PLATFORM_VERSION,
    PLATFORM_VERSION_V2,
    ProjectConfig,
    load_workspace,
    save_project_config,
    workspace_file,
)
from caraer_cli.project.sync import _v21_function_source

UPGRADE_PROMPT = (
    "This app uses the 2026.2 folder layout. Rewrite it to 2026.2.1 "
    "(flat files) before deploy?"
)


def decide_layout_upgrade(
    config: ProjectConfig,
    *,
    upgrade: bool | None,
    yes: bool,
    dry_run: bool,
    interactive: bool,
) -> Literal["noop", "announce", "prompt", "apply"]:
    """How push should treat a workspace that may still be 2026.2."""
    if config.platformVersion != PLATFORM_VERSION_V2:
        return "noop"
    if upgrade is False:
        return "noop"
    if dry_run:
        return "announce"
    if upgrade is True or yes:
        return "apply"
    if interactive:
        return "prompt"
    return "announce"


def offer_layout_upgrade_on_push(
    root: Path,
    *,
    upgrade: bool | None = None,
    yes: bool = False,
    dry_run: bool = False,
    interactive: bool = False,
    confirm: Callable[[str], bool] | None = None,
) -> dict[str, Any]:
    """Rewrite a 2026.2 tree before push when the operator accepts.

    Interactive push prompts with default yes. ``--yes`` and ``--upgrade``
    apply the rewrite. ``--no-upgrade`` and a declined prompt leave 2026.2.
    Dry-run and non-interactive push without ``--yes`` only announce.
    """
    config = load_workspace(root)
    action = decide_layout_upgrade(
        config,
        upgrade=upgrade,
        yes=yes,
        dry_run=dry_run,
        interactive=interactive,
    )
    if action == "noop":
        return {"action": "noop"}
    if action == "announce":
        return {
            "action": "announce",
            "message": (
                "This workspace is 2026.2. A real push will offer to rewrite "
                "it to 2026.2.1 (default yes). Run 'caraer apps upgrade' or "
                "pass --upgrade / --no-upgrade."
            ),
        }
    accepted = True
    if action == "prompt":
        if confirm is None:
            raise ValueError("confirm is required when prompting for a layout upgrade.")
        accepted = confirm(UPGRADE_PROMPT)
    if not accepted:
        return {
            "action": "declined",
            "message": "Keeping 2026.2. Run 'caraer apps upgrade' later, or push with --upgrade.",
        }
    result = upgrade_layout_to_v21(root)
    return {"action": "applied", "result": result}


def upgrade_layout_to_v21(root: Path) -> dict[str, Any]:
    config = load_workspace(root)
    if config.is_layout_v21():
        return {"skipped": True, "reason": "already 2026.2.1"}
    if config.platformVersion != PLATFORM_VERSION_V2:
        raise ValueError("caraer apps upgrade only rewrites a 2026.2 tree to 2026.2.1.")

    moved: list[str] = []
    functions = _read_function_folders(root, config)
    webhook_topics = _webhooks_by_function(root, config)
    _upgrade_functions(root, config, functions, webhook_topics, moved)
    _upgrade_lifecycle(root, config, functions, moved)
    _upgrade_named_code_files(root, config, functions, "schedules", schedules_dir, moved)
    _upgrade_named_code_files(root, config, functions, "inbound", inbound_dir, moved)
    _upgrade_settings(root, config, moved)
    _upgrade_app_bars(root, config, moved)
    _upgrade_modules(root, config, moved)
    _strip_yaml_collections(root, config)
    _upgrade_http_webhooks(root, config, moved)

    config.platformVersion = PLATFORM_VERSION
    save_project_config(workspace_file(root), config)
    moved.append("caraer.json platformVersion=2026.2.1")
    return {"skipped": False, "moved": moved}


def _read_function_folders(root: Path, config: ProjectConfig) -> dict[str, dict[str, Any]]:
    from caraer_cli.project.sync import discover_local_functions

    found: dict[str, dict[str, Any]] = {}
    for manifest, entry, code, _extras in discover_local_functions(root, config):
        found[manifest.name] = {
            "runtime": manifest.runtime,
            "code": code,
            "entry": entry,
            "folder": entry.parent,
        }
    return found


def _webhooks_by_function(root: Path, config: ProjectConfig) -> dict[str, list[dict[str, Any]]]:
    from caraer_cli.project.webhooks_sync import discover_local_webhooks

    grouped: dict[str, list[dict[str, Any]]] = {}
    for _path, item in discover_local_webhooks(root, config):
        sf = item.get("serverlessFunction") if isinstance(item, dict) else None
        name = sf.get("name") if isinstance(sf, dict) else None
        if not name:
            continue
        grouped.setdefault(str(name), []).append(
            {k: v for k, v in item.items() if k in {"topic", "deliveryMode", "enabled", "webhookFormat"}}
        )
    return grouped


def _upgrade_functions(
    root: Path,
    config: ProjectConfig,
    functions: dict[str, dict[str, Any]],
    webhook_topics: dict[str, list[dict[str, Any]]],
    moved: list[str],
) -> None:
    from caraer_cli.project.lifecycle_sync import LIFECYCLE_HOOKS

    lifecycle_names = {f"on-{stem}" for stem in LIFECYCLE_HOOKS}
    dest = functions_dir(root, config.srcDir)
    dest.mkdir(parents=True, exist_ok=True)
    for name, item in functions.items():
        if name in lifecycle_names:
            continue
        suffix = ".py" if str(item["runtime"]).startswith("python") else ".js"
        path = dest / f"{name}{suffix}"
        manifest: dict[str, Any] = {}
        hooks = webhook_topics.get(name) or []
        if hooks:
            manifest["webhooks"] = hooks
        path.write_text(
            _with_manifest(str(item["code"]), manifest, runtime=str(item["runtime"])),
            encoding="utf-8",
        )
        folder = item["folder"]
        if folder.is_dir() and folder != dest:
            shutil.rmtree(folder)
        moved.append(f"functions/{name}{suffix}")


def _upgrade_lifecycle(
    root: Path,
    config: ProjectConfig,
    functions: dict[str, dict[str, Any]],
    moved: list[str],
) -> None:
    from caraer_cli.project.lifecycle_sync import LIFECYCLE_HOOKS, discover_local_lifecycle

    dest = lifecycle_dir(root, config.srcDir)
    dest.mkdir(parents=True, exist_ok=True)
    hooks = discover_local_lifecycle(root, config)
    for stem, (manifest_key, topic) in LIFECYCLE_HOOKS.items():
        hook = hooks.get(manifest_key) or {}
        sf = hook.get("serverlessFunction") if isinstance(hook, dict) else None
        fn_name = sf.get("name") if isinstance(sf, dict) else f"on-{stem}"
        source = functions.get(str(fn_name)) or functions.get(stem)
        runtime = str(source["runtime"]) if source else config.resolved_runtime("nodejs22")
        suffix = ".py" if runtime.startswith("python") else ".js"
        path = dest / f"{stem}{suffix}"
        code = str(source["code"]) if source else ""
        if not code.strip():
            code = _v21_function_source(runtime)
        path.write_text(
            _with_manifest(code, {"lifecycle": stem, "topic": hook.get("topic") or topic}, runtime),
            encoding="utf-8",
        )
        json_path = dest / f"{stem}.json"
        if json_path.is_file():
            json_path.unlink()
        if source and source["folder"].is_dir():
            shutil.rmtree(source["folder"])
        moved.append(f"lifecycle/{stem}{suffix}")


def _upgrade_named_code_files(
    root: Path,
    config: ProjectConfig,
    functions: dict[str, dict[str, Any]],
    role: str,
    directory_fn,
    moved: list[str],
) -> None:
    dest = directory_fn(root, config.srcDir)
    dest.mkdir(parents=True, exist_ok=True)
    if role == "schedules":
        from caraer_cli.project.schedules_sync import discover_local_schedules

        items = discover_local_schedules(root, config)
        extra_key = "schedule"
    else:
        from caraer_cli.project.inbound_sync import discover_local_inbound

        items = discover_local_inbound(root, config)
        extra_key = "inbound"
    for path, item in items:
        name = str(item.get("name") or path.stem).replace("_", "-")
        sf = item.get("serverlessFunction") if isinstance(item, dict) else None
        fn_name = sf.get("name") if isinstance(sf, dict) else name
        source = functions.get(str(fn_name))
        runtime = str(source["runtime"]) if source else config.resolved_runtime("nodejs22")
        suffix = ".py" if runtime.startswith("python") else ".js"
        dest_path = dest / f"{name}{suffix}"
        code = str(source["code"]) if source else ""
        if not code.strip():
            code = _v21_function_source(runtime)
        if extra_key == "schedule":
            manifest = {
                "schedule": item.get("schedule"),
                "enabled": item.get("enabled", True),
            }
        else:
            manifest = {
                "authMode": item.get("authMode") or "SHARED_SECRET",
                "enqueue": item.get("enqueue", True),
                "enabled": item.get("enabled", True),
            }
            if item.get("secretName"):
                manifest["secretName"] = item["secretName"]
        dest_path.write_text(_with_manifest(code, manifest, runtime), encoding="utf-8")
        if path.suffix == ".json" and path.is_file():
            path.unlink()
        moved.append(f"{role}/{name}{suffix}")


def _upgrade_settings(root: Path, config: ProjectConfig, moved: list[str]) -> None:
    from caraer_cli.local_app import load_local_app
    from caraer_cli.project.marketplace_assemble import assemble_local_manifest
    from caraer_cli.project.paths import app_manifest_path
    from caraer_cli.project.settings_sync import write_settings_yaml

    manifest_path = app_manifest_path(root, config.srcDir)
    local = load_local_app(manifest_path) if manifest_path.is_file() else {}
    assembled = assemble_local_manifest(
        root, config, local, resolve_functions=False, strict_function_refs=False
    )
    settings = assembled.get("settingsSchema") or []
    sections = assembled.get("settingsSections") or []
    write_settings_yaml(
        root,
        config,
        [item for item in settings if isinstance(item, dict)],
        [item for item in sections if isinstance(item, dict)],
    )
    for directory in (settings_dir(root, config.srcDir), settings_sections_dir(root, config.srcDir)):
        if directory.is_dir():
            shutil.rmtree(directory)
    moved.append("settings.yaml")


def _upgrade_app_bars(root: Path, config: ProjectConfig, moved: list[str]) -> None:
    from caraer_cli.project.app_bars_sync import (
        discover_local_app_bars,
        sanitize_app_bar,
        write_app_bars_to_function_manifests,
    )

    bars = [sanitize_app_bar(item) for _path, item in discover_local_app_bars(root, config)]
    if bars:
        write_app_bars_to_function_manifests(root, config, bars)
        moved.append("function appBars")
    directory = app_bars_dir(root, config.srcDir)
    if directory.is_dir():
        shutil.rmtree(directory)


def _upgrade_modules(root: Path, config: ProjectConfig, moved: list[str]) -> None:
    base = modules_dir(root, config.srcDir)
    if not base.is_dir():
        return
    for child in sorted(base.iterdir()):
        if not child.is_dir():
            continue
        named = child / f"{child.name}.astro"
        index = child / "index.astro"
        if named.is_file() or not index.is_file():
            continue
        index.rename(named)
        moved.append(f"modules/{child.name}/{child.name}.astro")


def _strip_yaml_collections(root: Path, config: ProjectConfig) -> None:
    from caraer_cli.project.paths import app_manifest_path

    path = app_manifest_path(root, config.srcDir)
    if not path.is_file():
        return
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return
    changed = False
    for key in ("settingsSchema", "settingsSections", "appBars"):
        if key in data:
            data.pop(key, None)
            changed = True
    if changed:
        path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _upgrade_http_webhooks(root: Path, config: ProjectConfig, moved: list[str]) -> None:
    """Keep HTTP subscriptions as YAML; drop serverless JSON already moved onto functions."""
    from caraer_cli.project.webhooks_sync import (
        discover_webhook_files,
        webhook_yaml_filename,
        write_webhook_yaml,
    )

    base = webhooks_dir(root, config.srcDir)
    if not base.is_dir():
        return
    for path, item in discover_webhook_files(root, config):
        mode = str(item.get("deliveryMode") or "").strip().upper()
        if mode == "HTTP":
            dest = path if path.suffix.lower() in {".yaml", ".yml"} else base / webhook_yaml_filename(item)
            if dest != path:
                write_webhook_yaml(dest, item)
                path.unlink()
                moved.append(f"webhooks/{dest.name}")
            continue
        if path.suffix.lower() == ".json":
            path.unlink()
    leftover = [entry for entry in base.iterdir() if entry.name != ".gitkeep"]
    if not leftover:
        shutil.rmtree(base)


def _with_manifest(code: str, manifest: dict[str, Any], runtime: str) -> str:
    if not manifest:
        return code if code.strip() else _v21_function_source(runtime)
    from caraer_cli.project.code_manifest import upsert_code_manifest

    suffix = ".py" if runtime.startswith("python") else ".js"
    source = code if code.strip() else _v21_function_source(runtime)
    return upsert_code_manifest(source, manifest, path=Path(f"file{suffix}"))
