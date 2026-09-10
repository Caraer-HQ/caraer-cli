"""Scaffold a local Caraer app directory."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from caraer_cli.project.app_manifest_template import render_app_manifest
from caraer_cli.project.lifecycle_sync import LIFECYCLE_HOOKS
from caraer_cli.project.paths import (
    WORKSPACE_FILE,
    functions_dir,
    lifecycle_dir,
    modules_dir,
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
    topic: str = "record.candidate.created",
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
    from caraer_cli.project.json_schemas import WEBHOOK_SCHEMA_URL, dump_json_with_schema

    dump_json_with_schema(path, payload, WEBHOOK_SCHEMA_URL)
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
    options: list[dict[str, Any]] | None = None,
    options_source: dict[str, Any] | None = None,
    mapping_value: dict[str, Any] | None = None,
    field: dict[str, Any] | None = None,
    force: bool = False,
) -> Path:
    """Write a settingsSchema field JSON under ``src/app/settings/``."""
    base = settings_dir(root, config.srcDir)
    base.mkdir(parents=True, exist_ok=True)
    from caraer_cli.project.settings_sync import setting_filename, sanitize_setting

    if field is not None:
        payload = sanitize_setting(field)
    else:
        payload = sanitize_setting(
            {
                "name": name.strip(),
                "label": (label or name).strip(),
                "type": field_type.strip().upper() or "SINGLE_LINE",
                "required": required,
                "helpText": help_text,
                "defaultValue": default_value,
                "options": options,
                "optionsSource": options_source,
                "mappingValue": mapping_value,
            }
        )
    path = base / setting_filename(payload)
    if path.exists() and not force:
        raise FileExistsError(f"Setting file already exists: {path}. Use --force to overwrite.")
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def scaffold_lifecycle_hook(
    root: Path,
    config: ProjectConfig,
    *,
    event: str,
    function_name: str | None = None,
    runtime: str | None = None,
    create_function: bool = True,
    delivery_mode: str = "SERVERLESS",
    url: str | None = None,
    enabled: bool = True,
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
    mode = (delivery_mode or "SERVERLESS").strip().upper()
    if mode not in {"SERVERLESS", "HTTP"}:
        raise ValueError("delivery_mode must be SERVERLESS or HTTP")
    fn_name = (function_name or f"on-{stem}").strip()
    base = lifecycle_dir(root, config.srcDir)
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{stem}.json"
    if path.exists() and not force:
        raise FileExistsError(f"Lifecycle file already exists: {path}. Use --force to overwrite.")

    function_folder = None
    if mode == "SERVERLESS" and create_function:
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

    payload: dict[str, Any] = {
        "topic": topic,
        "deliveryMode": mode,
        "enabled": enabled,
    }
    if mode == "HTTP":
        if not url or not url.strip():
            raise ValueError("url is required for HTTP lifecycle hooks")
        payload["url"] = url.strip()
    else:
        payload["serverlessFunction"] = {"name": fn_name}
    from caraer_cli.project.json_schemas import LIFECYCLE_SCHEMA_URL, dump_json_with_schema

    dump_json_with_schema(path, payload, LIFECYCLE_SCHEMA_URL)
    return {
        "event": stem,
        "manifestKey": manifest_key,
        "lifecycleFile": path,
        "functionName": fn_name if mode == "SERVERLESS" else None,
        "functionFolder": function_folder,
    }


def _write_lifecycle_function_entry(
    folder: Path, runtime: str, *, stem: str, topic: str
) -> None:
    """Overwrite the scaffold entry with a lifecycle-aware stub."""
    from caraer_cli.project.schema import load_function_manifest

    manifest_path = folder / "function.caraer.json"
    if manifest_path.is_file():
        entry = folder / load_function_manifest(manifest_path).resolved_entry()
    else:
        entry = folder / ("main.py" if runtime.startswith("python") else "index.js")
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

#: Same compiler options as ``caraer-core``. Module scripts import npm
#: packages listed in ``package.json``; without this file the editor
#: reports ``Cannot find module`` even after ``npm install``.
TSCONFIG_CONTENTS = """\
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "noEmit": true,
    "skipLibCheck": true
  },
  "include": ["src/**/*.ts"]
}
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
    # settings/ holds optional modular files; writers create it on demand.
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


APP_DEV_SCRIPT = "caraer apps local dev"


def ensure_dev_script(root: Path) -> bool:
    """Make ``npm run dev`` / ``pnpm dev`` start functions and the CMS preview.

    Existing ``scripts.dev`` values are left alone.
    """
    path = root / "package.json"
    if not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    if not isinstance(payload, dict):
        return False
    scripts = payload.setdefault("scripts", {})
    if not isinstance(scripts, dict) or scripts.get("dev"):
        return False
    scripts["dev"] = APP_DEV_SCRIPT
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return True


def ensure_package_json(root: Path, name: str) -> Path | None:
    """Scaffold a root package.json for Node app projects.

    New files get scripts, ``@caraer/client``, and the CMS module contract
    packages. Existing files keep their dependencies; a missing ``dev``
    script is filled in so ``npm run dev`` matches ``caraer apps local dev``.
    """
    path = root / "package.json"
    if path.exists():
        ensure_dev_script(root)
        return None
    payload = {
        "name": name,
        "private": True,
        "type": "module",
        "scripts": {
            "dev": APP_DEV_SCRIPT,
            "validate": "caraer apps validate",
            "push": "caraer apps push",
            "deploy": "caraer apps push",
            "logs": "caraer apps local logs --all",
        },
        "dependencies": {
            "@caraer/cms-runtime": "github:Caraer-HQ/caraer-cms-runtime#v0.1.1",
            "@caraer/cms-tokens": "github:Caraer-HQ/caraer-cms-tokens#v0.1.1",
        },
        "devDependencies": {
            "@caraer/client": "^2.0.366",
        },
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


CMS_PACKAGES_INSTALLED = "Installed @caraer/cms-runtime and @caraer/cms-tokens"


def install_npm_dependencies(root: Path) -> bool:
    """Install the app's ``package.json`` so module imports resolve after init.

    Returns True when ``npm install`` ran. ``apps init`` writes
    ``@caraer/cms-runtime`` and ``@caraer/cms-tokens`` with the default CMS
    module; the editor still reports missing packages until this has run.
    """
    if not (root / "package.json").is_file():
        return False
    npm = shutil.which("npm")
    if not npm:
        raise RuntimeError(
            "npm is required to install @caraer/cms-runtime after apps init. "
            "Install Node.js, then run `npm install` in the app directory."
        )
    result = subprocess.run(
        [npm, "install"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "npm install failed").strip()
        raise RuntimeError(detail[-2000:])
    return True


def ensure_tsconfig(root: Path) -> Path | None:
    """Write the CMS-module TypeScript project file used by caraer-core.

    Module entries import browser libraries from ``package.json``. The editor
    only resolves those when a tsconfig sits at the app root. Existing files
    are left alone.
    """
    path = root / "tsconfig.json"
    if path.exists():
        return None
    path.write_text(TSCONFIG_CONTENTS, encoding="utf-8")
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
    sample_module: str | None = "hello_world",
    runtime: str = "nodejs22",
    platform_version: str = PLATFORM_VERSION,
    private_app: bool = False,
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
            modules/<sample>/     (optional; default hello_world)
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
        privateApp=private_app,
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
    if "hideApiKeyField" not in manifest_payload:
        # Hide installation API key in the Caraer UI by default.
        manifest_payload["hideApiKeyField"] = True
    if not manifest_payload.get("oauthRedirectUris"):
        manifest_payload["oauthRedirectUris"] = ["http://localhost:3000/oauth/callback"]

    app_file = write_app_manifest(project_root, manifest_payload, src_dir=src_dir)
    ensure_gitignore(project_root)
    ensure_tsconfig(project_root)
    if sample_module or not str(runtime or "").startswith("python"):
        ensure_package_json(project_root, name)

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

    module_folder = _scaffold_sample_module(
        project_root, config, name=sample_module, force=force
    )

    return {
        "root": project_root,
        "project_file": config_path,
        "app_file": app_file,
        "functions_dir": functions_dir(project_root, src_dir),
        "webhooks_dir": webhooks_dir(project_root, src_dir),
        "modules_dir": modules_dir(project_root, src_dir),
        "lifecycle_dir": lifecycle_dir(project_root, src_dir),
        "lifecycle_hooks": lifecycle_hooks,
        "sample_function": function_folder,
        "sample_webhook": webhook_file,
        "sample_module": module_folder,
        "config": config,
    }


def _scaffold_sample_module(
    root: Path,
    config: ProjectConfig,
    *,
    name: str | None,
    force: bool,
) -> Path | None:
    """Write the starter CMS module that ``apps add module`` would create."""
    if not name:
        return None

    from caraer_cli.project.modules_codegen import write_module_types
    from caraer_cli.project.modules_scaffold import scaffold_module
    from caraer_cli.project.modules_sync import discover_local_modules

    directory = scaffold_module(
        root,
        config,
        name=name,
        label="Hello world",
        kind="section",
        force=force,
    )
    for module in discover_local_modules(root, config):
        if module.name == name:
            write_module_types(module)
            break
    return directory
