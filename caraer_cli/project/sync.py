from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from caraer_cli.api import functions as functions_api
from caraer_cli.api.client import CaraerApiClient
from caraer_cli.project.paths import functions_dir
from caraer_cli.project.schema import (
    FunctionManifest,
    ProjectConfig,
    load_function_manifest,
    save_function_manifest,
)
from caraer_cli.project.state import load_state, save_state


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def discover_local_functions(root: Path, config: ProjectConfig) -> list[tuple[FunctionManifest, Path, str]]:
    base = functions_dir(root, config.srcDir)
    if not base.is_dir():
        return []
    found: list[tuple[FunctionManifest, Path, str]] = []
    for child in sorted(base.iterdir()):
        if not child.is_dir():
            continue
        manifest_path = child / "function.caraer.json"
        if not manifest_path.is_file():
            continue
        manifest = load_function_manifest(manifest_path)
        entry_path = child / manifest.resolved_entry()
        if not entry_path.is_file():
            raise FileNotFoundError(f"Missing entry file for function '{manifest.name}': {entry_path}")
        code = entry_path.read_text(encoding="utf-8")
        found.append((manifest, entry_path, code))
    return found


def list_local_function_names(root: Path, config: ProjectConfig) -> list[str]:
    return [manifest.name for manifest, _, _ in discover_local_functions(root, config)]


def resolve_local_function_name(
    root: Path,
    config: ProjectConfig,
    function: str | None = None,
    *,
    interactive: bool = True,
) -> str:
    """Resolve a function name from an explicit arg or the local functions folder."""
    names = list_local_function_names(root, config)
    if function and function.strip():
        name = function.strip()
        if name not in names and names:
            raise ValueError(
                f"Unknown function '{name}'. Available: {', '.join(names)}"
            )
        return name
    if not names:
        raise ValueError(
            "No local functions found under src/app/functions/. "
            "Pass --function <name> or add a function folder."
        )
    if len(names) == 1:
        return names[0]
    if interactive:
        try:
            from caraer_cli.wizard.prompts import WizardCancelled, ask_select

            return ask_select("Select a function", names)
        except WizardCancelled:
            raise ValueError("No function selected.") from None
        except Exception:
            pass
    raise ValueError(
        "Multiple functions found; pass --function <name>. "
        f"Available: {', '.join(names)}"
    )


def upload_functions(
    client: CaraerApiClient,
    root: Path,
    config: ProjectConfig,
    *,
    delete_missing: bool = False,
) -> dict[str, Any]:
    if not config.appUuid:
        raise ValueError("App has no remote UUID. Run 'caraer apps select' or 'caraer apps push'.")

    remote = functions_api.list_functions(client, config.appUuid, page=1, limit=200)
    remote_items = remote.get("data") or []
    by_name = {str(item.get("name") or ""): item for item in remote_items if isinstance(item, dict)}
    by_uuid = {str(item.get("uuid") or ""): item for item in remote_items if isinstance(item, dict)}

    state = load_state(root)
    fn_state: dict[str, Any] = state.setdefault("functions", {})
    results: list[dict[str, Any]] = []
    local_names: set[str] = set()

    for manifest, _entry_path, code in discover_local_functions(root, config):
        local_names.add(manifest.name)
        content_hash = _hash_text(f"{manifest.runtime}\n{manifest.description}\n{code}")
        existing_state = fn_state.get(manifest.name) or {}
        existing_uuid = existing_state.get("uuid")
        remote_item = by_uuid.get(existing_uuid) if existing_uuid else by_name.get(manifest.name)

        payload = {
            "name": manifest.name,
            "label": manifest.name,
            "runtime": manifest.runtime,
            "code": code,
            "description": manifest.description or manifest.name,
        }

        if remote_item and remote_item.get("uuid"):
            uuid = str(remote_item["uuid"])
            if existing_state.get("hash") == content_hash and remote_item.get("code") == code:
                results.append({"name": manifest.name, "uuid": uuid, "action": "unchanged"})
            else:
                response = functions_api.update_function(client, config.appUuid, uuid, payload)
                data = response.get("data") or {}
                results.append({"name": manifest.name, "uuid": data.get("uuid", uuid), "action": "updated"})
                fn_state[manifest.name] = {"uuid": data.get("uuid", uuid), "hash": content_hash}
        else:
            response = functions_api.create_function(client, config.appUuid, payload)
            data = response.get("data") or {}
            uuid = data.get("uuid")
            results.append({"name": manifest.name, "uuid": uuid, "action": "created"})
            if uuid:
                fn_state[manifest.name] = {"uuid": uuid, "hash": content_hash}

    deleted: list[dict[str, Any]] = []
    if delete_missing:
        for name, meta in list(fn_state.items()):
            if name in local_names:
                continue
            uuid = meta.get("uuid")
            if uuid:
                functions_api.delete_function(client, config.appUuid, str(uuid))
                deleted.append({"name": name, "uuid": uuid, "action": "deleted"})
            fn_state.pop(name, None)

    save_state(root, state)
    return {"functions": results, "deleted": deleted}


def pull_functions(client: CaraerApiClient, root: Path, config: ProjectConfig) -> dict[str, Any]:
    if not config.appUuid:
        raise ValueError("App has no remote UUID. Run 'caraer apps select' or 'caraer apps push'.")

    remote = functions_api.list_functions(client, config.appUuid, page=1, limit=200)
    remote_items = remote.get("data") or []
    base = functions_dir(root, config.srcDir)
    base.mkdir(parents=True, exist_ok=True)
    state = load_state(root)
    fn_state: dict[str, Any] = state.setdefault("functions", {})
    pulled: list[dict[str, Any]] = []

    for item in remote_items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("uuid") or "function")
        runtime = str(item.get("runtime") or "nodejs22")
        description = str(item.get("description") or "")
        code = str(item.get("code") or "")
        uuid = str(item.get("uuid") or "")
        folder = base / name
        folder.mkdir(parents=True, exist_ok=True)
        manifest = FunctionManifest(name=name, runtime=runtime, description=description)
        save_function_manifest(folder / "function.caraer.json", manifest)
        entry = folder / manifest.resolved_entry()
        entry.write_text(code, encoding="utf-8")
        fn_state[name] = {"uuid": uuid, "hash": _hash_text(f"{runtime}\n{description}\n{code}")}
        pulled.append({"name": name, "uuid": uuid, "path": str(folder)})

    save_state(root, state)
    return {"functions": pulled}


def status_summary(client: CaraerApiClient, root: Path, config: ProjectConfig) -> dict[str, Any]:
    local = discover_local_functions(root, config)
    local_names = {m.name for m, _, _ in local}
    remote_items: list[dict[str, Any]] = []
    remote_app: dict[str, Any] = {}
    if config.appUuid:
        remote = functions_api.list_functions(client, config.appUuid, page=1, limit=200)
        remote_items = [i for i in (remote.get("data") or []) if isinstance(i, dict)]
        try:
            from caraer_cli.api import apps as apps_api

            app_response = apps_api.get_public_app(client, config.appUuid)
            if isinstance(app_response.get("data"), dict):
                remote_app = app_response["data"]
        except Exception:  # noqa: BLE001
            remote_app = {}
    remote_names = {str(i.get("name") or "") for i in remote_items}
    state = load_state(root)
    summary: dict[str, Any] = {
        "appUuid": config.appUuid,
        "projectUuid": state.get("projectUuid"),
        "platformVersion": config.platformVersion,
        "appPlatformVersion": remote_app.get("platformVersion") or config.api_platform_version(),
        "localFunctions": sorted(local_names),
        "remoteFunctions": sorted(n for n in remote_names if n),
        "onlyLocal": sorted(local_names - remote_names),
        "onlyRemote": sorted(remote_names - local_names),
        "tracked": state.get("functions") or {},
        "lastBuildUuid": state.get("lastBuildUuid"),
        "lastDeployUuid": state.get("lastDeployUuid"),
    }
    if config.is_app_platform_v2() or remote_app.get("platformVersion") == 2:
        summary["runtime"] = remote_app.get("runtime") or config.runtime
        summary["runtimeStatus"] = remote_app.get("runtimeStatus")
        summary["runtimeBaseUrl"] = remote_app.get("runtimeBaseUrl")
        summary["runtimeRevision"] = remote_app.get("runtimeRevision")
        summary["runtimeError"] = remote_app.get("runtimeError")
    return summary


def scaffold_function(root: Path, config: ProjectConfig, name: str, runtime: str = "nodejs22") -> Path:
    folder = functions_dir(root, config.srcDir) / name
    folder.mkdir(parents=True, exist_ok=True)
    manifest = FunctionManifest(name=name, runtime=runtime, description=name)
    save_function_manifest(folder / "function.caraer.json", manifest)
    entry = folder / manifest.resolved_entry()
    if runtime.startswith("python"):
        entry.write_text(
            'def handler(request):\n'
            '    """Caraer serverless entrypoint."""\n'
            '    return {"statusCode": 200, "body": {"ok": True}}\n',
            encoding="utf-8",
        )
    else:
        entry.write_text(
            "/**\n * Caraer serverless entrypoint.\n */\n"
            "exports.handler = async (req, res) => {\n"
            "  res.status(200).json({ ok: true });\n"
            "};\n",
            encoding="utf-8",
        )
    return folder
