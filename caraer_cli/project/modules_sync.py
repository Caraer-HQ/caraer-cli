"""Discover CMS v2 modules under ``src/app/modules/``.

A module is an Astro component an app ships for the website builder. Unlike a
serverless function it never runs on the app runtime: ``caraer apps push``
publishes it to the Caraer npm registry, and each installing company's website
build compiles it in. Astro resolves components at build time, so "which
modules exist" is a build input rather than request data.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from caraer_cli.project.paths import modules_dir
from caraer_cli.project.schema import ProjectConfig

MODULE_CONFIG_FILE = "module.caraer.json"
MODULE_ENTRY_FILE = "index.astro"
GENERATED_TYPES_FILE = "fields.d.ts"

MODULE_KINDS = frozenset({"section", "page", "header", "footer"})

#: Frameworks whose islands share the ``.jsx``/``.tsx`` extensions. Astro can
#: only tell them apart by path, so these require the folder convention.
JSX_FRAMEWORKS = ("react", "preact", "solid")

#: Frameworks identified unambiguously by file extension.
EXTENSION_FRAMEWORKS = {"svelte": ".svelte", "vue": ".vue"}

ALL_FRAMEWORKS = (*JSX_FRAMEWORKS, *EXTENSION_FRAMEWORKS)

#: One major per framework is hoisted per build, so two installed apps cannot
#: pull different majors. Rejecting a mismatch at push time makes it one
#: developer's error instead of a broken build on a customer's live site.
PINNED_FRAMEWORK_MAJORS = {
    "react": 19,
    "preact": 10,
    "solid": 1,
    "svelte": 5,
    "vue": 3,
}

#: Field types valid on a module. `SECRET` would place a write-only credential
#: in a public page document and `ACTION` is a settings-screen button, so
#: neither is meaningful here.
MODULE_FIELD_TYPES = frozenset(
    {
        "SINGLE_LINE",
        "MULTI_LINE",
        "SINGLE_SELECT",
        "MULTI_SELECT",
        "RECORD_SINGLE_SELECT",
        "RECORD_MULTI_SELECT",
        "OBJECT_SINGLE_SELECT",
        "OBJECT_MULTI_SELECT",
        "PROPERTY_SINGLE_SELECT",
        "PROPERTY_MULTI_SELECT",
        "SWITCH",
        "MAPPING",
        "FILE",
        "MULTI_FILE",
    }
)

DISALLOWED_MODULE_FIELD_TYPES = frozenset({"SECRET", "ACTION"})


@dataclass
class LocalModule:
    """One module discovered on disk."""

    name: str
    directory: Path
    config: dict[str, Any] = field(default_factory=dict)

    @property
    def entry(self) -> Path:
        return self.directory / MODULE_ENTRY_FILE

    @property
    def config_path(self) -> Path:
        return self.directory / MODULE_CONFIG_FILE

    @property
    def kind(self) -> str:
        return str(self.config.get("kind") or "section")

    @property
    def label(self) -> str:
        return str(self.config.get("label") or self.name)

    @property
    def fields(self) -> list[dict[str, Any]]:
        raw = self.config.get("fields")
        return [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []

    @property
    def frameworks(self) -> dict[str, str]:
        raw = self.config.get("frameworks")
        if not isinstance(raw, dict):
            return {}
        return {str(k): str(v) for k, v in raw.items()}

    def island_files(self, framework: str) -> list[Path]:
        """Island source files this module ships for one framework."""
        folder = self.directory / framework
        if not folder.is_dir():
            return []
        if framework in EXTENSION_FRAMEWORKS:
            return sorted(folder.rglob(f"*{EXTENSION_FRAMEWORKS[framework]}"))
        return sorted(p for p in folder.rglob("*") if p.suffix in {".jsx", ".tsx", ".js", ".ts"})

    def to_manifest_entry(self) -> dict[str, Any]:
        """The catalog entry sent to the backend on push."""
        entry: dict[str, Any] = {
            "name": self.name,
            "label": self.label,
            "kind": self.kind,
            "fields": self.fields,
        }
        for key in ("description", "category", "icon", "preview", "uuid"):
            value = self.config.get(key)
            if value:
                entry[key] = value
        if self.frameworks:
            entry["frameworks"] = self.frameworks
        return entry


def discover_local_modules(root: Path, config: ProjectConfig) -> list[LocalModule]:
    """Read every module directory, sorted by name for stable output."""
    base = modules_dir(root, config.srcDir)
    if not base.is_dir():
        return []

    modules: list[LocalModule] = []
    for directory in sorted(p for p in base.iterdir() if p.is_dir()):
        if directory.name.startswith(".") or directory.name.startswith("_"):
            continue

        payload: dict[str, Any] = {}
        config_path = directory / MODULE_CONFIG_FILE
        if config_path.is_file():
            try:
                loaded = json.loads(config_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    payload = loaded
            except json.JSONDecodeError:
                # Left empty on purpose: validation reports the parse error with
                # a path, which is more useful than an exception here.
                payload = {}

        modules.append(LocalModule(name=directory.name, directory=directory, config=payload))

    return modules


def list_local_module_names(root: Path, config: ProjectConfig) -> list[str]:
    return [module.name for module in discover_local_modules(root, config)]


def parse_major(range_spec: str) -> int | None:
    """Extract the major version from a simple semver range such as ``^19.2.0``."""
    text = range_spec.strip().lstrip("^~>=< ").split(".")[0].strip()
    if not text or not text.isdigit():
        return None
    return int(text)
