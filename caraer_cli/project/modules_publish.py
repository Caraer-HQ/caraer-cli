"""Publish CMS modules to the Caraer private npm registry.

Modules are distributed as an npm package rather than through the app build
archive, because the consumer is a per-company Astro build on Vercel that
already runs `pnpm install`. Publishing this way gives version pinning,
lockfiles and rollback for free.

The package is assembled into a staging directory rather than published from
``src/app/modules`` directly, so the published tree contains only what a
website build needs and never the app's serverless code or ``.env``.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from caraer_cli.project.modules_sync import (
    GENERATED_TYPES_FILE,
    LocalModule,
    discover_local_modules,
)
from caraer_cli.project.schema import ProjectConfig

PACKAGE_SCOPE = "@caraer-app"

#: Files copied into the published package for each module.
_ALLOWED_SUFFIXES = {
    ".astro",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".css",
    ".json",
    ".svelte",
    ".vue",
    ".svg",
}


def package_name(app_name: str) -> str:
    """npm package name for an app's modules, e.g. ``@caraer-app/caraer_core``."""
    return f"{PACKAGE_SCOPE}/{app_name}"


def _peer_dependencies(modules: list[LocalModule]) -> dict[str, str]:
    """Frameworks the consuming build must provide.

    Declared as peers rather than dependencies so a website build hoists one
    copy per framework instead of installing a private copy per app.
    """
    peers: dict[str, str] = {"astro": "^7.0.0", "@caraer/cms-runtime": "*", "@caraer/cms-tokens": "*"}
    for module in modules:
        for framework, range_spec in module.frameworks.items():
            peers[framework] = range_spec
            if framework == "react":
                peers["react-dom"] = range_spec
    return peers


def build_package_json(
    app_name: str,
    version: str,
    modules: list[LocalModule],
    *,
    description: str | None = None,
) -> dict[str, Any]:
    exports: dict[str, str] = {}
    for module in modules:
        exports[f"./modules/{module.name}/index.astro"] = f"./modules/{module.name}/index.astro"
        exports[f"./modules/{module.name}/module.caraer.json"] = (
            f"./modules/{module.name}/module.caraer.json"
        )

    return {
        "name": package_name(app_name),
        "version": version,
        "type": "module",
        "private": False,
        "description": description or f"Caraer CMS modules shipped by the {app_name} app.",
        "license": "UNLICENSED",
        "exports": exports,
        "files": ["modules"],
        "peerDependencies": _peer_dependencies(modules),
        "peerDependenciesMeta": {
            framework: {"optional": True}
            for framework in ("react", "react-dom", "preact", "solid-js", "svelte", "vue")
        },
        "keywords": ["caraer", "caraer-cms-module"],
        "caraer": {
            "app": app_name,
            "modules": [module.to_manifest_entry() for module in modules],
        },
    }


def stage_package(
    root: Path,
    config: ProjectConfig,
    *,
    app_name: str,
    version: str,
    destination: Path,
    description: str | None = None,
) -> tuple[Path, list[LocalModule]]:
    """Copy modules into a publishable package tree. Returns the staging dir."""
    modules = [m for m in discover_local_modules(root, config) if m.config and m.entry.is_file()]
    if not modules:
        raise ValueError("No publishable modules found under src/app/modules/.")

    destination.mkdir(parents=True, exist_ok=True)
    modules_root = destination / "modules"
    modules_root.mkdir(parents=True, exist_ok=True)

    for module in modules:
        target = modules_root / module.name
        target.mkdir(parents=True, exist_ok=True)

        for source in module.directory.rglob("*"):
            if source.is_dir():
                continue
            if source.suffix not in _ALLOWED_SUFFIXES:
                continue
            # The generated declaration is for the developer's editor; the
            # consuming build derives types from the manifest instead.
            if source.name == GENERATED_TYPES_FILE:
                continue

            relative = source.relative_to(module.directory)
            copy_to = target / relative
            copy_to.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, copy_to)

    payload = build_package_json(app_name, version, modules, description=description)
    (destination / "package.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    readme = [
        f"# {package_name(app_name)}",
        "",
        "Caraer CMS v2 modules. Installed automatically into a company's website",
        "build; not intended to be added to a project by hand.",
        "",
        "| Module | Kind | Label |",
        "| --- | --- | --- |",
    ]
    readme.extend(f"| `{m.name}` | {m.kind} | {m.label} |" for m in modules)
    (destination / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")

    return destination, modules


def publish_package(
    staging: Path,
    *,
    registry_url: str,
    token: str,
    dry_run: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run `npm publish` against the Caraer registry."""
    host = registry_url.split("://", 1)[-1].rstrip("/")
    (staging / ".npmrc").write_text(
        f"{PACKAGE_SCOPE}:registry={registry_url}\n//{host}/:_authToken={token}\n",
        encoding="utf-8",
    )

    command = ["npm", "publish", "--registry", registry_url, "--access", "restricted"]
    if dry_run:
        command.append("--dry-run")

    try:
        return subprocess.run(
            command,
            cwd=staging,
            env={**os.environ, "npm_config_registry": registry_url},
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        # The token must not survive on disk, even if publish failed.
        (staging / ".npmrc").unlink(missing_ok=True)


def publish_modules(
    root: Path,
    config: ProjectConfig,
    *,
    app_name: str,
    version: str,
    registry_url: str | None = None,
    token: str | None = None,
    dry_run: bool = False,
    description: str | None = None,
) -> dict[str, Any]:
    """Stage and publish an app's modules. Returns a summary for the caller."""
    registry_url = registry_url or os.environ.get("CARAER_REGISTRY_URL") or ""
    token = token or os.environ.get("CARAER_REGISTRY_TOKEN") or ""

    with tempfile.TemporaryDirectory(prefix="caraer-modules-") as tmp:
        staging, modules = stage_package(
            root,
            config,
            app_name=app_name,
            version=version,
            destination=Path(tmp) / "package",
            description=description,
        )

        summary: dict[str, Any] = {
            "package": package_name(app_name),
            "version": version,
            "modules": [m.to_manifest_entry() for m in modules],
        }

        if not registry_url or not token:
            summary["published"] = False
            summary["reason"] = (
                "CARAER_REGISTRY_URL and CARAER_REGISTRY_TOKEN are not set; "
                "staged the package but did not publish."
            )
            return summary

        result = publish_package(staging, registry_url=registry_url, token=token, dry_run=dry_run)
        summary["published"] = result.returncode == 0
        summary["dryRun"] = dry_run
        if result.returncode != 0:
            summary["error"] = (result.stderr or result.stdout or "").strip()[-2000:]
        return summary
