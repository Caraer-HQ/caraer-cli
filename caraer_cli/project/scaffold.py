"""Scaffold a local Caraer app directory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from caraer_cli.project.app_manifest_template import render_app_manifest
from caraer_cli.project.paths import (
    WORKSPACE_FILE,
    functions_dir,
    webhooks_dir,
    workspace_file,
)
from caraer_cli.project.schema import PLATFORM_VERSION, ProjectConfig, save_project_config
from caraer_cli.project.state import set_project_uuid
from caraer_cli.project.sync import scaffold_function


def scaffold_webhook(
    root: Path,
    config: ProjectConfig,
    *,
    topic: str = "record.created",
    function_name: str | None = None,
    delivery_mode: str = "SERVERLESS",
    url: str | None = None,
    webhook_format: str = "USER_FRIENDLY",
    description: str | None = None,
    filename: str | None = None,
    force: bool = False,
) -> Path:
    """Write a webhook JSON under ``src/app/webhooks/``."""
    mode = (delivery_mode or "SERVERLESS").strip().upper()
    if mode not in {"SERVERLESS", "HTTP"}:
        raise ValueError("delivery_mode must be SERVERLESS or HTTP")
    if mode == "SERVERLESS" and (not function_name or not function_name.strip()):
        raise ValueError("function_name is required for SERVERLESS webhooks")
    if mode == "HTTP" and (not url or not url.strip()):
        raise ValueError("url is required for HTTP webhooks")

    base = webhooks_dir(root, config.srcDir)
    base.mkdir(parents=True, exist_ok=True)
    if filename:
        stem = filename.strip()
        if stem.endswith(".json"):
            stem = stem[: -len(".json")]
        path = base / f"{stem}.json"
    else:
        slug = topic.strip().lower().replace(".", "-").replace("_", "-")
        suffix = "serverless" if mode == "SERVERLESS" else "http"
        path = base / f"{slug}-{suffix}.json"

    if path.exists() and not force:
        raise FileExistsError(f"Webhook file already exists: {path}. Use --force to overwrite.")

    if mode == "SERVERLESS":
        resolved_description = description or f"Invoke {function_name} on {topic}"
        payload: dict[str, Any] = {
            "topic": topic,
            "deliveryMode": "SERVERLESS",
            "webhookFormat": webhook_format,
            "description": resolved_description,
            "enabled": True,
            "serverlessFunction": {"name": function_name},
        }
    else:
        resolved_description = description or f"HTTP webhook for {topic}"
        payload = {
            "topic": topic,
            "deliveryMode": "HTTP",
            "webhookFormat": webhook_format,
            "description": resolved_description,
            "enabled": True,
            "url": url.strip(),
        }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


GITIGNORE_CONTENTS = """\
.caraer/
.env
.env.*
!.env.example
__pycache__/
node_modules/
*.pyc
.DS_Store
"""


def resolve_project_root(path: str | Path, *, create: bool = False) -> Path:
    root = Path(path).expanduser().resolve()
    if create:
        root.mkdir(parents=True, exist_ok=True)
    return root


def write_app_manifest(
    root: Path,
    payload: dict[str, Any],
    *,
    src_dir: str = "src",
    include_examples: bool = True,
) -> Path:
    """Write the marketplace/app definition YAML (not function code)."""
    from caraer_cli.project.paths import APP_MANIFEST_YAML, app_dir

    functions_dir(root, src_dir).mkdir(parents=True, exist_ok=True)
    webhooks_dir(root, src_dir).mkdir(parents=True, exist_ok=True)
    # Always write preferred YAML for scaffolds / local edits.
    manifest = app_dir(root, src_dir) / APP_MANIFEST_YAML
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        render_app_manifest(payload, include_examples=include_examples),
        encoding="utf-8",
    )
    return manifest


def ensure_gitignore(root: Path) -> Path | None:
    path = root / ".gitignore"
    if path.exists():
        return None
    path.write_text(GITIGNORE_CONTENTS, encoding="utf-8")
    return path


def scaffold_app_project(
    root: Path | str,
    *,
    app_payload: dict[str, Any],
    project_name: str | None = None,
    app_uuid: str | None = None,
    project_uuid: str | None = None,
    src_dir: str = "src",
    sample_function: str | None = "hello-world",
    runtime: str = "nodejs22",
    platform_version: str = PLATFORM_VERSION,
    force: bool = False,
) -> dict[str, Any]:
    """
    Create a local app folder:

        <root>/
          caraer.json
          .gitignore
          src/app/
            app.caraer.yaml
            functions/<sample>/
            webhooks/
    """
    project_root = resolve_project_root(root, create=True)
    config_path = workspace_file(project_root)
    if config_path.exists() and not force:
        raise FileExistsError(
            f"{WORKSPACE_FILE} already exists in {project_root}. Use --force to overwrite."
        )

    name = (project_name or str(app_payload.get("name") or project_root.name)).strip()
    config = ProjectConfig(
        platformVersion=platform_version,
        name=name,
        appUuid=app_uuid,
        srcDir=src_dir,
        runtime=runtime if platform_version == PLATFORM_VERSION else None,
    )
    save_project_config(config_path, config)
    if project_uuid:
        set_project_uuid(project_root, project_uuid)

    manifest_payload = dict(app_payload)
    # Keep V2 app runtime on the marketplace manifest as well as caraer.json.
    if platform_version == PLATFORM_VERSION:
        manifest_payload["runtime"] = runtime or manifest_payload.get("runtime") or "nodejs22"
    elif "runtime" in manifest_payload:
        # V1: runtime lives on each function, not the app document.
        manifest_payload.pop("runtime", None)
    if not manifest_payload.get("authMethod"):
        manifest_payload["authMethod"] = "OAUTH2"
    if not manifest_payload.get("oauthRedirectUris"):
        manifest_payload["oauthRedirectUris"] = ["http://localhost:3000/oauth/callback"]

    app_file = write_app_manifest(project_root, manifest_payload, src_dir=src_dir)
    ensure_gitignore(project_root)

    function_folder: Path | None = None
    webhook_file: Path | None = None
    if sample_function:
        function_folder = scaffold_function(
            project_root,
            config,
            sample_function,
            runtime=runtime,
            force=force,
        )
        webhook_file = scaffold_webhook(
            project_root,
            config,
            function_name=sample_function,
            force=force,
        )

    return {
        "root": project_root,
        "project_file": config_path,
        "app_file": app_file,
        "functions_dir": functions_dir(project_root, src_dir),
        "webhooks_dir": webhooks_dir(project_root, src_dir),
        "sample_function": function_folder,
        "sample_webhook": webhook_file,
        "config": config,
    }
