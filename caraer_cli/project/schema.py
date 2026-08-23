from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, field_validator

from caraer_cli.project.paths import (
    LEGACY_PROJECT_FILE,
    WORKSPACE_FILE,
    project_file,
    workspace_file,
)
from caraer_cli.project.state import get_project_uuid, set_project_uuid


# Workspace schema versions. 2026.2 maps to App.platformVersion = 2 (container runtime).
PLATFORM_VERSION = "2026.2"
PLATFORM_VERSION_V1 = "2026.1"
SUPPORTED_PLATFORM_VERSIONS = frozenset({PLATFORM_VERSION_V1, PLATFORM_VERSION})


class FunctionManifest(BaseModel):
    name: str
    runtime: str = "nodejs22"
    entry: str | None = None
    description: str = ""

    @field_validator("runtime")
    @classmethod
    def validate_runtime(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"nodejs22", "python312"}:
            raise ValueError("runtime must be nodejs22 or python312")
        return normalized

    def resolved_entry(self) -> str:
        if self.entry:
            return self.entry
        return "main.py" if self.runtime.startswith("python") else "index.js"


class ProjectConfig(BaseModel):
    """Local app workspace config (caraer.json). projectUuid lives in .caraer/state.json."""

    platformVersion: str = PLATFORM_VERSION
    name: str
    appUuid: str | None = None
    srcDir: str = "src"
    autoDeploy: bool = False
    # App-level runtime for platform 2026.2 / App.platformVersion 2.
    runtime: str | None = None
    # Company-private apps use POST/PUT /api/v2/apps/private*.
    privateApp: bool = False

    @field_validator("platformVersion")
    @classmethod
    def validate_platform(cls, value: str) -> str:
        if not value:
            raise ValueError("platformVersion is required")
        if value not in SUPPORTED_PLATFORM_VERSIONS:
            raise ValueError(
                f"Unsupported platformVersion '{value}'. "
                f"Supported: {', '.join(sorted(SUPPORTED_PLATFORM_VERSIONS))}"
            )
        return value

    @field_validator("runtime")
    @classmethod
    def validate_optional_runtime(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        normalized = value.strip().lower()
        if normalized not in {"nodejs22", "python312"}:
            raise ValueError("runtime must be nodejs22 or python312")
        return normalized

    def is_app_platform_v2(self) -> bool:
        return self.platformVersion == PLATFORM_VERSION

    def api_platform_version(self) -> int:
        """Map workspace platformVersion to App.platformVersion integer."""
        return 2 if self.is_app_platform_v2() else 1

    def resolved_runtime(self, fallback: str = "nodejs22") -> str:
        if self.runtime:
            return self.runtime
        return fallback


# Public alias matching the plan naming.
AppWorkspaceConfig = ProjectConfig


def load_project_config(path: Path) -> ProjectConfig:
    data = json.loads(path.read_text(encoding="utf-8"))
    # Drop legacy projectUuid from file payload (moved to state).
    data.pop("projectUuid", None)
    return ProjectConfig.model_validate(data)


def save_project_config(path: Path, config: ProjectConfig) -> None:
    """Write caraer.json and remove legacy caraer.project.json if present."""
    target = path
    if path.name == LEGACY_PROJECT_FILE:
        target = path.parent / WORKSPACE_FILE
    payload = config.model_dump()
    # Omit null runtime for cleaner V1 files.
    if payload.get("runtime") is None:
        payload.pop("runtime", None)
    if not payload.get("privateApp"):
        payload.pop("privateApp", None)
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    legacy = target.parent / LEGACY_PROJECT_FILE
    if legacy.is_file() and legacy.resolve() != target.resolve():
        legacy.unlink(missing_ok=True)


def load_workspace(root: Path) -> ProjectConfig:
    """Load workspace config, migrating legacy projectUuid into state if needed."""
    path = project_file(root)
    if not path.is_file():
        raise FileNotFoundError(f"No {WORKSPACE_FILE} in {root}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    had_legacy_uuid = "projectUuid" in raw
    legacy_project_uuid = raw.pop("projectUuid", None)
    config = ProjectConfig.model_validate(raw)
    if legacy_project_uuid and not get_project_uuid(root):
        set_project_uuid(root, str(legacy_project_uuid))
    # Rewrite to caraer.json without projectUuid when loading legacy file.
    if path.name == LEGACY_PROJECT_FILE or had_legacy_uuid:
        save_project_config(workspace_file(root), config)
    return config


def get_cached_project_uuid(root: Path) -> str | None:
    return get_project_uuid(root)


def cache_project_uuid(root: Path, project_uuid: str | None) -> None:
    set_project_uuid(root, project_uuid)


def load_function_manifest(path: Path) -> FunctionManifest:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "name" not in data:
        data["name"] = path.parent.name
    return FunctionManifest.model_validate(data)


def save_function_manifest(path: Path, manifest: FunctionManifest) -> None:
    from caraer_cli.project.json_schemas import FUNCTION_SCHEMA_URL, dump_json_with_schema

    dump_json_with_schema(path, manifest.model_dump(), FUNCTION_SCHEMA_URL)


def default_app_manifest(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "label": name,
        "description": "",
        "scopes": [],
    }
