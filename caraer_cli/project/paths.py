from __future__ import annotations

from pathlib import Path


WORKSPACE_FILE = "caraer.json"
LEGACY_PROJECT_FILE = "caraer.project.json"
# Back-compat alias used by older call sites.
PROJECT_FILE = WORKSPACE_FILE
STATE_DIR = ".caraer"
STATE_FILE = "state.json"


def find_project_root(start: Path | None = None) -> Path:
    """Locate the app workspace root (caraer.json or legacy caraer.project.json)."""
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / WORKSPACE_FILE).is_file() or (
            candidate / LEGACY_PROJECT_FILE
        ).is_file():
            return candidate
    raise FileNotFoundError(
        f"No {WORKSPACE_FILE} found. Run 'caraer apps init' in your app directory."
    )


def workspace_file(root: Path) -> Path:
    """Preferred workspace config path (always caraer.json)."""
    return root / WORKSPACE_FILE


def project_file(root: Path) -> Path:
    """Return existing workspace file path (prefer caraer.json, else legacy)."""
    modern = root / WORKSPACE_FILE
    if modern.is_file():
        return modern
    legacy = root / LEGACY_PROJECT_FILE
    if legacy.is_file():
        return legacy
    return modern


def has_workspace_file(root: Path) -> bool:
    return (root / WORKSPACE_FILE).is_file() or (
        root / LEGACY_PROJECT_FILE
    ).is_file()


def state_path(root: Path) -> Path:
    return root / STATE_DIR / STATE_FILE


def app_dir(root: Path, src_dir: str = "src") -> Path:
    return root / src_dir / "app"


def functions_dir(root: Path, src_dir: str = "src") -> Path:
    return app_dir(root, src_dir) / "functions"


def webhooks_dir(root: Path, src_dir: str = "src") -> Path:
    return app_dir(root, src_dir) / "webhooks"


APP_MANIFEST_YAML = "app.caraer.yaml"
APP_MANIFEST_JSON = "app.caraer.json"


def app_manifest_path(root: Path, src_dir: str = "src") -> Path:
    """Preferred local app definition path (YAML). Falls back to legacy JSON if present."""
    base = app_dir(root, src_dir)
    yaml_path = base / APP_MANIFEST_YAML
    json_path = base / APP_MANIFEST_JSON
    if yaml_path.is_file():
        return yaml_path
    if json_path.is_file():
        return json_path
    return yaml_path
