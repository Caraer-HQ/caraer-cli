from __future__ import annotations

from pathlib import Path


WORKSPACE_FILE = "caraer.json"
LEGACY_PROJECT_FILE = "caraer.project.json"
# Back-compat alias used by older call sites.
PROJECT_FILE = WORKSPACE_FILE
STATE_DIR = ".caraer"
STATE_FILE = "state.json"


def app_file_unless_in_workspace(pinned: str | None) -> str | None:
    """Drop the pinned app while standing inside an app workspace.

    The pin lets commands run from anywhere. It is not a preference for that
    app over the one you are inside, so the directory wins whenever there is
    one: scaffolding a module into a different app than the folder you are in
    is never what you meant.

    Returning ``None`` leaves the caller resolving from the current directory.
    """
    try:
        find_project_root()
    except FileNotFoundError:
        return pinned
    return None


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


def schedules_dir(root: Path, src_dir: str = "src") -> Path:
    return app_dir(root, src_dir) / "schedules"


def inbound_dir(root: Path, src_dir: str = "src") -> Path:
    return app_dir(root, src_dir) / "inbound"


def settings_dir(root: Path, src_dir: str = "src") -> Path:
    return app_dir(root, src_dir) / "settings"


def settings_sections_dir(root: Path, src_dir: str = "src") -> Path:
    return app_dir(root, src_dir) / "settings-sections"


def app_bars_dir(root: Path, src_dir: str = "src") -> Path:
    return app_dir(root, src_dir) / "app-bars"


def lifecycle_dir(root: Path, src_dir: str = "src") -> Path:
    return app_dir(root, src_dir) / "lifecycle"


def modules_dir(root: Path, src_dir: str = "src") -> Path:
    """CMS v2 modules shipped by this app.

    Each subdirectory is one module: ``index.astro`` plus
    its ``export const manifest``. Unlike functions, modules are not executed by the
    app runtime; they are published to the Caraer npm registry and compiled
    into each installing company's website build.
    """
    return app_dir(root, src_dir) / "modules"


def shared_dir(root: Path, src_dir: str = "src") -> Path:
    """Source files shared by all functions (platform 2026.2 only).

    Deployed at ``shared/`` in the runtime archive root, so functions import
    them with the same relative path as locally, e.g.
    ``require("../../shared/utils")`` from ``functions/<name>/index.js``.
    """
    return app_dir(root, src_dir) / "shared"


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
