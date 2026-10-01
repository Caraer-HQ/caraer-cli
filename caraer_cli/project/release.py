"""Release version + notes helpers for developer project builds."""

from __future__ import annotations

import re
from typing import Any

from caraer_cli.api import projects as projects_api
from caraer_cli.api.client import CaraerApiClient

SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def parse_semver(version: str) -> tuple[int, int, int]:
    match = SEMVER_RE.fullmatch(version.strip())
    if not match:
        raise ValueError("version must be MAJOR.MINOR.PATCH (e.g. 1.2.3)")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def is_semver(version: str | None) -> bool:
    return bool(version and SEMVER_RE.fullmatch(version.strip()))


def bump_patch(version: str) -> str:
    major, minor, patch = parse_semver(version)
    return f"{major}.{minor}.{patch + 1}"


def is_greater(candidate: str, previous: str) -> bool:
    return parse_semver(candidate) > parse_semver(previous)


def push_conflict_message(local_base: str | None, remote_version: str | None) -> str | None:
    """Warn when a push would replace a newer deployed version.

    ``local_base`` is the version this folder last pulled or built. ``remote_version``
    is the highest version already on the project.
    """
    remote = (remote_version or "").strip()
    if not is_semver(remote):
        return None
    local = (local_base or "").strip()
    if is_semver(local):
        if not is_greater(remote, local):
            return None
        base = f"v{local}"
    else:
        base = "an unrecorded local base"
    return (
        f"CONFLICT (content): remote v{remote} is newer than {base}.\n"
        f"Pushing replaces the deployed source at v{remote}.\n"
        "Pull first if you need that version: caraer apps pull"
    )


def next_version(previous: str | None) -> str:
    if previous and is_semver(previous):
        return bump_patch(previous)
    return "0.1.0"


def latest_build_version(client: CaraerApiClient, project_uuid: str) -> str | None:
    """Return the highest semver among project builds, if any."""
    response = projects_api.list_builds(client, project_uuid)
    rows = response.get("data") or []
    best: tuple[int, int, int] | None = None
    best_text: str | None = None
    if not isinstance(rows, list):
        return None
    for item in rows:
        if not isinstance(item, dict):
            continue
        value = str(item.get("version") or "").strip()
        if not is_semver(value):
            continue
        parsed = parse_semver(value)
        if best is None or parsed > best:
            best = parsed
            best_text = value
    return best_text


def prompt_release(
    *,
    previous: str | None,
    default_version: str | None = None,
    default_notes: str | None = None,
) -> tuple[str, str]:
    """Interactively ask for the next release version and notes."""
    from caraer_cli.wizard.prompts import ask_text

    suggested = default_version.strip() if default_version and is_semver(default_version) else None
    if suggested and previous and is_semver(previous) and not is_greater(suggested, previous):
        suggested = next_version(previous)
    if not suggested:
        suggested = next_version(previous)

    previous_label = previous if previous else "none"
    while True:
        version = ask_text(
            f"Release version (previous: {previous_label})",
            default=suggested,
            required=True,
        ).strip()
        if not is_semver(version):
            print("Version must be MAJOR.MINOR.PATCH (e.g. 1.2.3).")
            continue
        if previous and is_semver(previous) and not is_greater(version, previous):
            print(f"Version must be greater than previous ({previous}).")
            continue
        break

    notes = ask_text(
        "Release notes (optional)",
        default=(default_notes or "").strip(),
        required=False,
    ).strip()
    return version, notes


def resolve_release_for_build(
    client: CaraerApiClient,
    project_uuid: str,
    *,
    version: str | None = None,
    release_notes: str | None = None,
    interactive: bool = True,
) -> tuple[str, str]:
    """Resolve version + notes, prompting when interactive."""
    previous = latest_build_version(client, project_uuid)

    if not interactive:
        if not version or not is_semver(version):
            raise ValueError(
                "Non-interactive push requires --version MAJOR.MINOR.PATCH."
            )
        if previous and not is_greater(version, previous):
            raise ValueError(
                f"Version must be greater than previous ({previous})."
            )
        notes = (release_notes or "").strip()
        return version.strip(), notes

    return prompt_release(
        previous=previous,
        default_version=version,
        default_notes=release_notes,
    )
