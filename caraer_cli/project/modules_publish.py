"""Publish CMS modules through the Caraer API.

Modules are distributed as an npm package rather than through the app build
archive, because the consumer is a per-company Astro build on Vercel that
already runs `pnpm install`. Developers authenticate with ``caraer auth login``;
the API holds the registry token and publishes the staged tarball.

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

PACKAGE_SCOPE = "@caraer"

#: Provided by the website build, not by the module package.
_PEER_ONLY = frozenset(
    {
        "astro",
        "@astrojs/react",
        "@astrojs/preact",
        "@astrojs/solid-js",
        "@astrojs/svelte",
        "@astrojs/vue",
        "@caraer/cms-runtime",
        "@caraer/cms-tokens",
        "@caraer/client",
        "react",
        "react-dom",
        "preact",
        "solid-js",
        "svelte",
        "vue",
    }
)

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


def package_name(
    app_name: str,
    *,
    private: bool = False,
    company: str | None = None,
) -> str:
    """npm package name for an app's modules.

    Public marketplace apps publish as ``@caraer/<app>``. Company-private apps
    add the company subdomain as a prefix (``@caraer/sem_notice``) so they
    cannot collide with a marketplace name. The prefix is skipped when the
    app name already starts with ``{company}_``.
    """
    slug = (app_name or "").strip()
    if not slug:
        raise ValueError("App name is required to name a module package.")
    if private:
        prefix_source = (company or os.environ.get("CARAER_SUBDOMAIN") or "").strip().lower()
        if prefix_source:
            prefix = f"{prefix_source}_"
            if not slug.startswith(prefix):
                slug = prefix + slug
    return f"{PACKAGE_SCOPE}/{slug}"


def read_app_dependencies(root: Path) -> dict[str, str]:
    """Libraries a module may import, from the app's root ``package.json``.

    ``three``, motion libraries, and similar belong in ``dependencies``. The
    published module package carries them so the company's website build
    installs them with the app. Frameworks and Caraer runtime packages stay
    peers: the build already hoists one copy.
    """
    path = root / "package.json"
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    raw = payload.get("dependencies")
    if not isinstance(raw, dict):
        return {}
    deps: dict[str, str] = {}
    for name, spec in raw.items():
        key = str(name)
        if key in _PEER_ONLY or not isinstance(spec, str) or not spec.strip():
            continue
        deps[key] = spec
    return deps


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
    private: bool = False,
    company: str | None = None,
    dependencies: dict[str, str] | None = None,
) -> dict[str, Any]:
    exports: dict[str, str] = {}
    for module in modules:
        # The manifest is a named export of the component, so one entry covers
        # both the markup and the field schema.
        entry_name = module.entry.name
        exports[f"./modules/{module.name}/{entry_name}"] = f"./modules/{module.name}/{entry_name}"
        if entry_name != "index.astro":
            exports[f"./modules/{module.name}/index.astro"] = f"./modules/{module.name}/{entry_name}"

    payload: dict[str, Any] = {
        "name": package_name(app_name, private=private, company=company),
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
    if dependencies:
        payload["dependencies"] = dict(sorted(dependencies.items()))
    return payload


def _copy_allowed_files(source_dir: Path, dest_dir: Path, *, skip_generated: bool = False) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    for source in source_dir.rglob("*"):
        if source.is_dir():
            continue
        if source.suffix not in _ALLOWED_SUFFIXES:
            continue
        if skip_generated and source.name in {GENERATED_TYPES_FILE, "fields.d.ts"}:
            continue
        relative = source.relative_to(source_dir)
        copy_to = dest_dir / relative
        copy_to.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, copy_to)


def _copy_shared_module_files(modules_src: Path, modules_root: Path) -> None:
    """Copy settings files and `_`-prefixed folders that modules import."""
    for child in modules_src.iterdir():
        if child.is_file() and child.suffix in _ALLOWED_SUFFIXES:
            shutil.copy2(child, modules_root / child.name)
        elif child.is_dir() and child.name.startswith("_"):
            _copy_allowed_files(child, modules_root / child.name)


def stage_package(
    root: Path,
    config: ProjectConfig,
    *,
    app_name: str,
    version: str,
    destination: Path,
    description: str | None = None,
    private: bool = False,
    company: str | None = None,
) -> tuple[Path, list[LocalModule]]:
    """Copy modules into a publishable package tree. Returns the staging dir."""
    modules = [m for m in discover_local_modules(root, config) if m.config and m.entry.is_file()]
    if not modules:
        raise ValueError("No publishable modules found under src/app/modules/.")

    destination.mkdir(parents=True, exist_ok=True)
    modules_root = destination / "modules"
    modules_root.mkdir(parents=True, exist_ok=True)

    for module in modules:
        _copy_allowed_files(
            module.directory,
            modules_root / module.name,
            skip_generated=True,
        )

    _copy_shared_module_files(modules[0].directory.parent, modules_root)

    payload = build_package_json(
        app_name,
        version,
        modules,
        description=description,
        private=private,
        company=company,
        dependencies=read_app_dependencies(root),
    )
    (destination / "package.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    readme = [
        f"# {package_name(app_name, private=private, company=company)}",
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


def pack_tarball(staging: Path) -> Path:
    """Create the npm tarball developers would have published themselves."""
    result = subprocess.run(
        ["npm", "pack", "--silent"],
        cwd=staging,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "npm pack failed").strip()[-2000:])
    filename = (result.stdout or "").strip().splitlines()[-1]
    packed = staging / filename
    if not packed.is_file():
        matches = list(staging.glob("*.tgz"))
        if not matches:
            raise RuntimeError("npm pack did not produce a tarball.")
        packed = matches[0]
    return packed


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
    private: bool = False,
    company: str | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    """Stage and publish an app's modules. Returns a summary for the caller.

    The default path uploads the tarball through the authenticated Caraer API.
    Developers only need ``caraer auth login``. Direct npm credentials are an
    operator override, not part of the developer setup.
    """
    import base64

    from caraer_cli.api import modules as modules_api

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
            private=private,
            company=company,
        )

        summary: dict[str, Any] = {
            "package": package_name(app_name, private=private, company=company),
            "version": version,
            "modules": [m.to_manifest_entry() for m in modules],
        }

        if dry_run:
            summary["published"] = False
            summary["dryRun"] = True
            return summary

        if config.appUuid and client is not None:
            tarball = pack_tarball(staging)
            modules_api.publish_module_package(
                client,
                config.appUuid,
                {
                    "package": summary["package"],
                    "version": version,
                    "modules": summary["modules"],
                    "tarballBase64": base64.b64encode(tarball.read_bytes()).decode("ascii"),
                    "filename": tarball.name,
                },
            )
            summary["published"] = True
            summary["catalog"] = True
            summary["via"] = "api"
            return summary

        if not registry_url or not token:
            summary["published"] = False
            summary["reason"] = (
                "Not logged in or the app has no remote UUID. "
                "Run 'caraer auth login' and 'caraer apps push' from an app folder."
            )
            return summary

        result = publish_package(staging, registry_url=registry_url, token=token, dry_run=False)
        summary["published"] = result.returncode == 0
        summary["via"] = "npm"
        if result.returncode != 0:
            summary["error"] = (result.stderr or result.stdout or "").strip()[-2000:]
        return summary
