"""Discover / write lifecycle webhook configs under src/app/lifecycle/."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from caraer_cli.project.paths import lifecycle_dir
from caraer_cli.project.schema import ProjectConfig

# filename stem → (manifest key, expected topic)
LIFECYCLE_HOOKS: dict[str, tuple[str, str]] = {
    "install": ("installWebhook", "app.installed"),
    "uninstall": ("uninstallWebhook", "app.uninstalled"),
    "rotate": ("rotateWebhook", "app.rotated"),
    "update": ("updateWebhook", "app.updated"),
}

MANIFEST_KEY_TO_FILE = {
    manifest_key: stem for stem, (manifest_key, _) in LIFECYCLE_HOOKS.items()
}

LOCAL_LIFECYCLE_KEYS = (
    "topic",
    "deliveryMode",
    "url",
    "description",
    "enabled",
    "webhookFormat",
    "secret",
    "serverlessFunction",
    "waitUntilComplete",
    "label",
)


def sanitize_lifecycle(item: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key in LOCAL_LIFECYCLE_KEYS:
        if key in item and item[key] is not None:
            payload[key] = item[key]
    sf = payload.get("serverlessFunction")
    if isinstance(sf, dict):
        cleaned: dict[str, Any] = {}
        if sf.get("uuid"):
            cleaned["uuid"] = sf["uuid"]
        if sf.get("name"):
            cleaned["name"] = sf["name"]
        if cleaned:
            payload["serverlessFunction"] = cleaned
        else:
            payload.pop("serverlessFunction", None)
    return payload


def discover_local_lifecycle(
    root: Path, config: ProjectConfig
) -> dict[str, dict[str, Any]]:
    """Return manifest_key → sanitized webhook dict for present lifecycle files."""
    if config.is_layout_v21():
        from caraer_cli.project.function_files import (
            discover_layout_v21_functions,
            lifecycle_items_from_files,
        )

        return lifecycle_items_from_files(discover_layout_v21_functions(root, config))
    base = lifecycle_dir(root, config.srcDir)
    if not base.is_dir():
        return {}
    found: dict[str, dict[str, Any]] = {}
    for stem, (manifest_key, _topic) in LIFECYCLE_HOOKS.items():
        path = base / f"{stem}.json"
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            found[manifest_key] = sanitize_lifecycle(data)
    return found


def write_lifecycle_files(
    root: Path, config: ProjectConfig, hooks: dict[str, dict[str, Any] | None]
) -> int:
    """Write lifecycle files from manifest hook objects. Clears missing files."""
    if config.is_layout_v21():
        return _write_lifecycle_v21(root, config, hooks)
    base = lifecycle_dir(root, config.srcDir)
    base.mkdir(parents=True, exist_ok=True)
    count = 0
    for stem, (manifest_key, expected_topic) in LIFECYCLE_HOOKS.items():
        path = base / f"{stem}.json"
        raw = hooks.get(manifest_key)
        if not isinstance(raw, dict) or not raw:
            if path.exists():
                path.unlink()
            continue
        sanitized = sanitize_lifecycle(raw)
        if not sanitized.get("topic"):
            sanitized["topic"] = expected_topic
        path.write_text(json.dumps(sanitized, indent=2) + "\n", encoding="utf-8")
        count += 1
    return count


def _write_lifecycle_v21(
    root: Path, config: ProjectConfig, hooks: dict[str, dict[str, Any] | None]
) -> int:
    from caraer_cli.project.code_manifest import parse_code_manifest_file, write_code_manifest
    from caraer_cli.project.function_files import function_file_by_name
    from caraer_cli.project.sync import _v21_function_source

    count = 0
    for stem, (manifest_key, expected_topic) in LIFECYCLE_HOOKS.items():
        raw = hooks.get(manifest_key)
        existing = function_file_by_name(root, config, stem)
        if not isinstance(raw, dict) or not raw:
            continue
        runtime = config.resolved_runtime("nodejs22")
        suffix = existing.path.suffix if existing else (".py" if runtime.startswith("python") else ".js")
        path = existing.path if existing else lifecycle_dir(root, config.srcDir) / f"{stem}{suffix}"
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(_v21_function_source(runtime), encoding="utf-8")
        current = parse_code_manifest_file(path)
        current["lifecycle"] = stem
        current["topic"] = raw.get("topic") or expected_topic
        current["enabled"] = raw.get("enabled", True)
        if isinstance(raw.get("label"), str) and raw["label"].strip():
            current["label"] = raw["label"].strip()
        write_code_manifest(path, current)
        count += 1
    return count


def _serverless_ref(
    uuid: str,
    name: str | None = None,
    *,
    runtime: str | None = None,
    label: str | None = None,
) -> dict[str, str]:
    """UUID + identity fields so App.update depth>=2 does not wipe the SF node."""
    ref: dict[str, str] = {"uuid": uuid}
    if name:
        ref["name"] = name
    if label or name:
        ref["label"] = label or name or ""
    if runtime:
        ref["runtime"] = runtime
    return ref


def resolve_lifecycle_functions(
    webhook: dict[str, Any],
    *,
    fn_by_name: dict[str, str],
    fn_meta_by_name: dict[str, dict[str, Any]] | None = None,
    strict: bool = True,
    default_runtime: str | None = None,
) -> dict[str, Any] | None:
    out = dict(webhook)
    sf = out.get("serverlessFunction")
    if not isinstance(sf, dict):
        return out
    meta_by_name = fn_meta_by_name or {}
    name = sf.get("name")
    uuid = sf.get("uuid")
    if uuid and not name:
        for candidate_name, candidate_uuid in fn_by_name.items():
            if candidate_uuid == uuid:
                name = candidate_name
                break

    def _ref_for(resolved_uuid: str, resolved_name: str | None) -> dict[str, str]:
        meta = meta_by_name.get(resolved_name or "") if resolved_name else {}
        runtime = (
            (sf.get("runtime") if isinstance(sf.get("runtime"), str) else None)
            or (meta.get("runtime") if isinstance(meta, dict) else None)
            or default_runtime
        )
        label = (
            (sf.get("label") if isinstance(sf.get("label"), str) else None)
            or (meta.get("label") if isinstance(meta, dict) else None)
            or resolved_name
        )
        return _serverless_ref(
            str(resolved_uuid),
            resolved_name,
            runtime=runtime if isinstance(runtime, str) else None,
            label=label if isinstance(label, str) else None,
        )

    if uuid:
        out["serverlessFunction"] = _ref_for(str(uuid), name)
        return out
    if name and name in fn_by_name:
        out["serverlessFunction"] = _ref_for(fn_by_name[name], name)
        return out
    if name:
        if strict:
            raise ValueError(
                f"Lifecycle webhook references function '{name}' but no UUID is known. "
                "Push functions first."
            )
        return None
    return out
