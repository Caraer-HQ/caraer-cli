"""Scaffold a local Caraer app directory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from caraer_cli.project.app_manifest_template import render_app_manifest
from caraer_cli.project.lifecycle_sync import LIFECYCLE_HOOKS
from caraer_cli.project.paths import (
    WORKSPACE_FILE,
    app_bars_dir,
    functions_dir,
    lifecycle_dir,
    pricing_dir,
    settings_dir,
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


def scaffold_setting(
    root: Path,
    config: ProjectConfig,
    *,
    name: str,
    label: str | None = None,
    field_type: str = "SINGLE_LINE",
    required: bool = False,
    help_text: str | None = None,
    default_value: Any = None,
    force: bool = False,
) -> Path:
    """Write a settingsSchema field JSON under ``src/app/settings/``."""
    base = settings_dir(root, config.srcDir)
    base.mkdir(parents=True, exist_ok=True)
    from caraer_cli.project.settings_sync import setting_filename, sanitize_setting

    payload = sanitize_setting(
        {
            "name": name.strip(),
            "label": (label or name).strip(),
            "type": field_type.strip().upper() or "SINGLE_LINE",
            "required": required,
            "helpText": help_text,
            "defaultValue": default_value,
        }
    )
    path = base / setting_filename(payload)
    if path.exists() and not force:
        raise FileExistsError(f"Setting file already exists: {path}. Use --force to overwrite.")
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def scaffold_pricing_plan(
    root: Path,
    config: ProjectConfig,
    *,
    title: str,
    pricing_type: str = "FLAT",
    price_per_unit: float | int | None = 0,
    unit: str = "installations",
    description: str | None = None,
    force: bool = False,
) -> Path:
    """Write a pricing plan JSON under ``src/app/pricing/``."""
    from caraer_cli.project.pricing_sync import pricing_filename, sanitize_pricing

    base = pricing_dir(root, config.srcDir)
    base.mkdir(parents=True, exist_ok=True)
    ptype = pricing_type.strip().upper() or "FLAT"
    payload: dict[str, Any] = {
        "title": title.strip(),
        "description": description,
        "pricingType": ptype,
    }
    if ptype == "FLAT":
        payload["pricePerUnit"] = 0 if price_per_unit is None else price_per_unit
        payload["unit"] = unit.strip() or "installations"
    else:
        payload["tiers"] = [
            {
                "startUnits": 0,
                "endUnits": None,
                "pricePerMonth": 0,
                "pricePerYear": 0,
                "pricePerExtraUnit": 0,
            }
        ]
    sanitized = sanitize_pricing(payload)
    path = base / pricing_filename(sanitized)
    if path.exists() and not force:
        raise FileExistsError(f"Pricing file already exists: {path}. Use --force to overwrite.")
    path.write_text(json.dumps(sanitized, indent=2) + "\n", encoding="utf-8")
    return path


def scaffold_app_bar(
    root: Path,
    config: ProjectConfig,
    *,
    location: str,
    label: str,
    iframe_url: str | None = None,
    function_name: str | None = None,
    action_label: str | None = None,
    force: bool = False,
) -> Path:
    """Write an app bar JSON under ``src/app/app-bars/``."""
    from caraer_cli.project.app_bars_sync import (
        ACTION_BASED_LOCATIONS,
        app_bar_filename,
        sanitize_app_bar,
    )

    base = app_bars_dir(root, config.srcDir)
    base.mkdir(parents=True, exist_ok=True)
    loc = location.strip().upper()
    payload: dict[str, Any] = {
        "location": loc,
        "label": label.strip(),
    }
    if loc in ACTION_BASED_LOCATIONS:
        payload["actionLabel"] = (action_label or label).strip()
        payload["webhook"] = {
            "topic": "app.bar.triggered",
            "deliveryMode": "SERVERLESS",
            "enabled": True,
            "serverlessFunction": {
                "name": (function_name or "on-app-bar").strip(),
            },
        }
    else:
        if not iframe_url or not iframe_url.strip():
            raise ValueError("iframe_url is required for iframe app bar locations.")
        payload["iframeUrl"] = iframe_url.strip()
    sanitized = sanitize_app_bar(payload)
    path = base / app_bar_filename(sanitized)
    if path.exists() and not force:
        raise FileExistsError(f"App bar file already exists: {path}. Use --force to overwrite.")
    path.write_text(json.dumps(sanitized, indent=2) + "\n", encoding="utf-8")
    return path


def scaffold_lifecycle_hook(
    root: Path,
    config: ProjectConfig,
    *,
    event: str,
    function_name: str | None = None,
    runtime: str | None = None,
    create_function: bool = True,
    force: bool = False,
) -> dict[str, Any]:
    """Write ``lifecycle/<event>.json`` and optionally scaffold ``functions/on-<event>/``."""
    stem = event.strip().lower()
    if stem not in LIFECYCLE_HOOKS:
        raise ValueError(
            f"Unknown lifecycle event '{event}'. "
            f"Expected one of: {', '.join(sorted(LIFECYCLE_HOOKS))}."
        )
    manifest_key, topic = LIFECYCLE_HOOKS[stem]
    fn_name = (function_name or f"on-{stem}").strip()
    base = lifecycle_dir(root, config.srcDir)
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{stem}.json"
    if path.exists() and not force:
        raise FileExistsError(f"Lifecycle file already exists: {path}. Use --force to overwrite.")

    function_folder = None
    if create_function:
        resolved_runtime = (
            runtime or config.resolved_runtime("nodejs22")
        ).strip().lower()
        function_folder = scaffold_function(
            root,
            config,
            fn_name,
            resolved_runtime,
            description=f"Handle {topic}",
            force=force,
        )
        _write_lifecycle_function_entry(
            function_folder, resolved_runtime, stem=stem, topic=topic
        )

    payload = {
        "topic": topic,
        "deliveryMode": "SERVERLESS",
        "enabled": True,
        "serverlessFunction": {"name": fn_name},
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return {
        "event": stem,
        "manifestKey": manifest_key,
        "lifecycleFile": path,
        "functionName": fn_name,
        "functionFolder": function_folder,
    }


def _write_lifecycle_function_entry(
    folder: Path, runtime: str, *, stem: str, topic: str
) -> None:
    """Overwrite the scaffold entry with a lifecycle-aware stub."""
    from caraer_cli.project.schema import load_function_manifest

    manifest = load_function_manifest(folder / "function.caraer.json")
    entry = folder / manifest.resolved_entry()
    if runtime.startswith("python"):
        entry.write_text(
            f'def handler(request):\n'
            f'    """Handle {topic} (app lifecycle)."""\n'
            f'    body = request.get("body") if isinstance(request, dict) else {{}}\n'
            f'    if isinstance(body, str):\n'
            f'        import json\n'
            f'        try:\n'
            f'            body = json.loads(body or "{{}}")\n'
            f'        except Exception:\n'
            f'            body = {{}}\n'
            f'    return {{\n'
            f'        "statusCode": 200,\n'
            f'        "body": {{\n'
            f'            "ok": True,\n'
            f'            "hook": "{stem}",\n'
            f'            "event": (body or {{}}).get("event"),\n'
            f'            "companyUuid": (body or {{}}).get("companyUuid"),\n'
            f'            "appUuid": (body or {{}}).get("appUuid"),\n'
            f'        }},\n'
            f'    }}\n',
            encoding="utf-8",
        )
    else:
        entry.write_text(
            "/**\n"
            f" * Handle {topic} (app lifecycle).\n"
            " */\n"
            "exports.handler = async (req, res) => {\n"
            "  const body =\n"
            "    typeof req.body === \"string\"\n"
            "      ? JSON.parse(req.body || \"{}\")\n"
            "      : req.body || {};\n"
            "  res.status(200).json({\n"
            "    ok: true,\n"
            f'    hook: "{stem}",\n'
            "    event: body.event || null,\n"
            "    companyUuid: body.companyUuid || null,\n"
            "    appUuid: body.appUuid || null,\n"
            "  });\n"
            "};\n",
            encoding="utf-8",
        )


def scaffold_all_lifecycle_hooks(
    root: Path,
    config: ProjectConfig,
    *,
    runtime: str | None = None,
    force: bool = False,
) -> list[dict[str, Any]]:
    """Ensure all four lifecycle JSON files + on-* functions exist."""
    created: list[dict[str, Any]] = []
    resolved_runtime = (runtime or config.resolved_runtime("nodejs22")).strip().lower()
    for stem in ("install", "uninstall", "rotate", "update"):
        path = lifecycle_dir(root, config.srcDir) / f"{stem}.json"
        fn_name = f"on-{stem}"
        fn_folder = functions_dir(root, config.srcDir) / fn_name
        if force or not path.exists():
            created.append(
                scaffold_lifecycle_hook(
                    root,
                    config,
                    event=stem,
                    runtime=resolved_runtime,
                    create_function=True,
                    force=force,
                )
            )
            continue
        # Lifecycle JSON exists; still create a missing on-* function.
        if not fn_folder.exists():
            _, topic = LIFECYCLE_HOOKS[stem]
            function_folder = scaffold_function(
                root,
                config,
                fn_name,
                resolved_runtime,
                description=f"Handle {topic}",
                force=False,
            )
            _write_lifecycle_function_entry(
                function_folder, resolved_runtime, stem=stem, topic=topic
            )
            created.append(
                {
                    "event": stem,
                    "manifestKey": LIFECYCLE_HOOKS[stem][0],
                    "lifecycleFile": path,
                    "functionName": fn_name,
                    "functionFolder": function_folder,
                }
            )
    return created


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
    lifecycle_dir(root, src_dir).mkdir(parents=True, exist_ok=True)
    settings_dir(root, src_dir).mkdir(parents=True, exist_ok=True)
    pricing_dir(root, src_dir).mkdir(parents=True, exist_ok=True)
    app_bars_dir(root, src_dir).mkdir(parents=True, exist_ok=True)
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
            lifecycle/{install,uninstall,rotate,update}.json
            functions/on-{install,uninstall,rotate,update}/
            functions/<sample>/   (optional)
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

    lifecycle_hooks = scaffold_all_lifecycle_hooks(
        project_root,
        config,
        runtime=runtime,
        force=force,
    )

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
        "lifecycle_dir": lifecycle_dir(project_root, src_dir),
        "lifecycle_hooks": lifecycle_hooks,
        "sample_function": function_folder,
        "sample_webhook": webhook_file,
        "config": config,
    }
