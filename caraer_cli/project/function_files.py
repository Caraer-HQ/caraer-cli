"""Discover 2026.2.1 function files across functions, appbars, lifecycle, schedules, inbound."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from caraer_cli.project.code_manifest import parse_code_manifest_file
from caraer_cli.project.modules_manifest import ManifestError
from caraer_cli.project.paths import (
    appbars_dir,
    functions_dir,
    inbound_dir,
    is_function_code_file,
    lifecycle_dir,
    schedules_dir,
)
from caraer_cli.project.schema import FunctionManifest, ProjectConfig

FUNCTION_ROLES = ("functions", "appbars", "lifecycle", "schedules", "inbound")
LIFECYCLE_NAMES = ("install", "uninstall", "rotate", "update")


@dataclass
class LocalFunctionFile:
    """One 2026.2.1 function file and the literal manifest on it."""

    name: str
    role: str
    path: Path
    runtime: str
    manifest: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_function_manifest(self) -> FunctionManifest:
        return FunctionManifest(
            name=self.name,
            runtime=self.runtime,
            entry=self.path.name,
            description=str(self.manifest.get("description") or ""),
        )


def _runtime_for(path: Path, config: ProjectConfig) -> str:
    if path.suffix.lower() == ".py":
        return "python312"
    return config.resolved_runtime("nodejs22")


def _scan_dir(directory: Path, role: str, config: ProjectConfig) -> list[LocalFunctionFile]:
    if not directory.is_dir():
        return []
    found: list[LocalFunctionFile] = []
    for path in sorted(directory.iterdir()):
        if not is_function_code_file(path):
            continue
        name = path.stem
        try:
            payload = parse_code_manifest_file(path)
            error = None
        except ManifestError as exc:
            payload = {}
            error = str(exc)
        found.append(
            LocalFunctionFile(
                name=name,
                role=role,
                path=path,
                runtime=_runtime_for(path, config),
                manifest=payload,
                error=error,
            )
        )
    return found


def discover_layout_v21_functions(
    root: Path, config: ProjectConfig
) -> list[LocalFunctionFile]:
    files: list[LocalFunctionFile] = []
    files.extend(_scan_dir(functions_dir(root, config.srcDir), "functions", config))
    files.extend(_scan_dir(appbars_dir(root, config.srcDir), "appbars", config))
    files.extend(_scan_dir(lifecycle_dir(root, config.srcDir), "lifecycle", config))
    files.extend(_scan_dir(schedules_dir(root, config.srcDir), "schedules", config))
    files.extend(_scan_dir(inbound_dir(root, config.srcDir), "inbound", config))
    return files


def function_file_by_name(
    root: Path, config: ProjectConfig, name: str
) -> LocalFunctionFile | None:
    for item in discover_layout_v21_functions(root, config):
        if item.name == name:
            return item
    return None


_ACTION_BAR_LOCATIONS = frozenset(
    {"RECORD_PREVIEW", "RECORD_OVERVIEW", "RECORD_TRAIT"}
)
_APP_BAR_FIELDS = (
    "name",
    "location",
    "label",
    "tooltipLabel",
    "description",
    "actionLabel",
    "iframeUrl",
    "icon",
    "settingsSchema",
)


def app_bar_items_from_files(
    files: list[LocalFunctionFile],
) -> list[tuple[Path, dict[str, Any]]]:
    """Build app bars from ``appBar`` / ``appBars`` on a function manifest.

    The function file is the handler. Action bars get ``app.bar.triggered``
    wired to that function, so the manifest does not name another function.
    """
    items: list[tuple[Path, dict[str, Any]]] = []
    for item in files:
        declared: list[Any] = []
        raw_list = item.manifest.get("appBars")
        if isinstance(raw_list, list):
            declared.extend(raw_list)
        single = item.manifest.get("appBar")
        if isinstance(single, dict):
            declared.append(single)
        for raw in declared:
            if not isinstance(raw, dict):
                continue
            payload = {
                key: raw[key]
                for key in _APP_BAR_FIELDS
                if key in raw and raw[key] is not None
            }
            if not payload.get("label") or not payload.get("location"):
                continue
            if not payload.get("name"):
                payload["name"] = item.name.replace("-", "_")
            location = str(payload["location"]).strip().upper()
            payload["location"] = location
            if location in _ACTION_BAR_LOCATIONS:
                payload["webhook"] = {
                    "topic": "app.bar.triggered",
                    "deliveryMode": "SERVERLESS",
                    "enabled": True,
                    "serverlessFunction": {"name": item.name},
                }
            items.append((item.path, payload))
    return items


def webhook_items_from_files(
    files: list[LocalFunctionFile],
) -> list[tuple[Path, dict[str, Any]]]:
    items: list[tuple[Path, dict[str, Any]]] = []
    for item in files:
        raw = item.manifest.get("webhooks")
        if not isinstance(raw, list):
            continue
        for webhook in raw:
            if not isinstance(webhook, dict):
                continue
            payload = dict(webhook)
            payload.setdefault("deliveryMode", "SERVERLESS")
            payload.setdefault("enabled", True)
            payload.setdefault("webhookFormat", "USER_FRIENDLY")
            payload["serverlessFunction"] = {"name": item.name}
            items.append((item.path, payload))
    return items


def schedule_items_from_files(
    files: list[LocalFunctionFile],
) -> list[tuple[Path, dict[str, Any]]]:
    items: list[tuple[Path, dict[str, Any]]] = []
    for item in files:
        if item.role != "schedules":
            continue
        raw = item.manifest.get("schedule")
        payload: dict[str, Any] = {
            "name": item.name.replace("-", "_"),
            "enabled": True,
            "serverlessFunction": {"name": item.name},
        }
        if isinstance(raw, str):
            payload["schedule"] = raw
        elif isinstance(raw, dict):
            payload.update({k: v for k, v in raw.items() if v is not None})
            payload["name"] = str(raw.get("name") or payload["name"])
            payload["schedule"] = raw.get("schedule") or raw.get("cron")
            if "enabled" in raw:
                payload["enabled"] = bool(raw["enabled"])
        if item.manifest.get("description"):
            payload.setdefault("description", item.manifest["description"])
        items.append((item.path, payload))
    return items


def inbound_items_from_files(
    files: list[LocalFunctionFile],
) -> list[tuple[Path, dict[str, Any]]]:
    items: list[tuple[Path, dict[str, Any]]] = []
    for item in files:
        if item.role != "inbound":
            continue
        payload = {
            "name": item.name,
            "authMode": str(item.manifest.get("authMode") or "SHARED_SECRET").upper(),
            "enqueue": bool(item.manifest.get("enqueue", True)),
            "enabled": bool(item.manifest.get("enabled", True)),
            "serverlessFunction": {"name": item.name},
        }
        if item.manifest.get("sharedSecret"):
            payload["sharedSecret"] = item.manifest["sharedSecret"]
        if item.manifest.get("secretName"):
            payload["secretName"] = item.manifest["secretName"]
        items.append((item.path, payload))
    return items


def lifecycle_items_from_files(
    files: list[LocalFunctionFile],
) -> dict[str, dict[str, Any]]:
    from caraer_cli.project.lifecycle_sync import LIFECYCLE_HOOKS, sanitize_lifecycle

    found: dict[str, dict[str, Any]] = {}
    for item in files:
        if item.role != "lifecycle":
            continue
        hook = str(item.manifest.get("lifecycle") or item.name).strip().lower()
        if hook not in LIFECYCLE_HOOKS:
            continue
        manifest_key, topic = LIFECYCLE_HOOKS[hook]
        payload = sanitize_lifecycle(
            {
                "topic": item.manifest.get("topic") or topic,
                "deliveryMode": "SERVERLESS",
                "enabled": bool(item.manifest.get("enabled", True)),
                "serverlessFunction": {"name": item.name},
                "waitUntilComplete": item.manifest.get("waitUntilComplete"),
            }
        )
        found[manifest_key] = payload
    return found
