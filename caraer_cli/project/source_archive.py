"""Restore a project tree from the deployed build archive."""

from __future__ import annotations

import io
import shutil
import zipfile
from pathlib import Path

#: Directories the pull scaffold fills with samples. When the deployed archive
#: has its own copy, drop local children the archive does not contain.
_OWNED_DIRS = (
    "src/app/modules",
    "src/app/functions",
    "src/app/lifecycle",
    "src/app/webhooks",
    "src/app/schedules",
    "src/app/inbound",
    "src/app/shared",
    "src/app/settings",
    "src/app/settings-sections",
)


def extract_deployed_archive(root: Path, payload: bytes) -> int:
    """Write archive entries into ``root``. Returns the number of files written.

    Scaffold samples (for example ``hello_world``) are removed when the archive
    has that directory and does not include them.
    """
    root = root.resolve()
    written: list[str] = []
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for info in archive.infolist():
            name = _safe_entry_name(info.filename)
            if name is None or info.is_dir():
                continue
            target = (root / name).resolve()
            if target != root and root not in target.parents:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(info))
            written.append(name)
    _drop_files_absent_from_archive(root, written)
    return len(written)


def _safe_entry_name(name: str) -> str | None:
    normalized = name.replace("\\", "/").lstrip("/")
    if not normalized or normalized.endswith("/"):
        return None
    parts = normalized.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return None
    return normalized


def _drop_files_absent_from_archive(root: Path, names: list[str]) -> None:
    archived = set(names)
    for relative in _OWNED_DIRS:
        prefix = relative.rstrip("/") + "/"
        archived_children = {
            item[len(prefix) :].split("/", 1)[0]
            for item in archived
            if item.startswith(prefix)
        }
        if not archived_children:
            continue
        directory = root / relative
        if not directory.is_dir():
            continue
        for child in directory.iterdir():
            if child.name in archived_children or child.name == ".gitkeep":
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
