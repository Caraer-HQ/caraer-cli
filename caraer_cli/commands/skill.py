"""Install Cursor Agent skills shipped with caraer-cli."""

from __future__ import annotations

import shutil
import json
import re
from importlib import resources
from pathlib import Path

import typer

from caraer_cli.formatters.output import print_error, print_success, print_warning

app = typer.Typer(help="Cursor / AI IDE skill helpers.", no_args_is_help=True)

SKILL_ID = "caraer-apps"
SHIPPED_SKILLS = ("caraer-apps", "caraer-cms")


def shipped_skill_ids() -> tuple[str, ...]:
    """Discover new canonical bundles while preserving existing CLI packages."""
    repo = _repo_skill_dir(SKILL_ID)
    manifest = repo.parent / "canonical-source.json" if repo else None
    if manifest is None or not manifest.is_file():
        manifest = resources.files("caraer_cli") / "skills" / "canonical-source.json"
    if not manifest.is_file():
        return SHIPPED_SKILLS
    value = json.loads(manifest.read_text(encoding="utf-8"))
    names = value.get("skills")
    if not isinstance(names, dict) or not names or any(
        not re.fullmatch(r"caraer-[a-z0-9-]{1,56}", name) for name in names
    ):
        raise ValueError("The canonical skill manifest contains invalid skill names")
    return tuple(sorted(names))


def _repo_skill_dir(skill_id: str = SKILL_ID) -> Path | None:
    """Dev checkout: <repo>/skills/<id> next to the package."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "skills" / skill_id
        if candidate.is_dir() and (candidate / "SKILL.md").is_file():
            return candidate
    return None


def _copy_packaged_skill(dest: Path, skill_id: str = SKILL_ID) -> bool:
    try:
        root = resources.files("caraer_cli") / "skills" / skill_id
    except (TypeError, FileNotFoundError, ModuleNotFoundError):
        return False
    try:
        if not root.is_dir():
            return False
        skill_md = root / "SKILL.md"
        if not skill_md.is_file():
            return False
        with resources.as_file(root) as path:
            shutil.copytree(path, dest)
        return True
    except (FileNotFoundError, OSError, NotADirectoryError):
        return False


def resolve_skill_source(skill_id: str = SKILL_ID) -> Path:
    """Return a real filesystem path for read-only inspection (path command)."""
    repo = _repo_skill_dir(skill_id)
    if repo is not None:
        return repo
    try:
        root = resources.files("caraer_cli") / "skills" / skill_id
        with resources.as_file(root) as path:
            if path.is_dir() and (path / "SKILL.md").is_file():
                return Path(path)
    except (TypeError, FileNotFoundError, ModuleNotFoundError, OSError):
        pass
    raise FileNotFoundError(
        f"Skill '{skill_id}' not found. Reinstall caraer-cli or clone "
        "Caraer-HQ/caraer-cli."
    )


def default_user_skills_dir() -> Path:
    return Path.home() / ".cursor" / "skills"


def project_skills_dir(cwd: Path | None = None) -> Path:
    return (cwd or Path.cwd()) / ".cursor" / "skills"


def install_skill(
    *,
    project: bool = False,
    target_root: Path | None = None,
    force: bool = False,
    skill_id: str = SKILL_ID,
) -> Path:
    root = target_root or (
        project_skills_dir() if project else default_user_skills_dir()
    )
    dest = root / skill_id
    if dest.exists():
        if not force:
            raise FileExistsError(
                f"{dest} already exists. Pass --force to replace it."
            )
        if dest.is_dir():
            shutil.rmtree(dest)
        else:
            dest.unlink()
    root.mkdir(parents=True, exist_ok=True)

    if _copy_packaged_skill(dest, skill_id):
        return dest

    repo = _repo_skill_dir(skill_id)
    if repo is not None:
        shutil.copytree(repo, dest)
        return dest

    raise FileNotFoundError(
        f"Skill '{skill_id}' not found. Reinstall caraer-cli or clone "
        "Caraer-HQ/caraer-cli."
    )


def install_all_skills(
    *,
    project: bool = False,
    target_root: Path | None = None,
    force: bool = False,
) -> list[Path]:
    return [
        install_skill(
            project=project,
            target_root=target_root,
            force=force,
            skill_id=skill_id,
        )
        for skill_id in shipped_skill_ids()
    ]


@app.command("install")
def install_cmd(
    project: bool = typer.Option(
        False,
        "--project",
        help="Install into ./.cursor/skills (current directory) instead of ~/.cursor/skills.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Replace existing shipped skill directories.",
    ),
    path: Path | None = typer.Option(
        None,
        "--path",
        help="Custom directory for the bundled canonical skills.",
    ),
) -> None:
    """Install all canonical Caraer skills bundled with this CLI."""
    try:
        installed = install_all_skills(
            project=project, target_root=path, force=force
        )
    except FileExistsError as exc:
        print_error(str(exc))
        raise typer.Exit(1) from exc
    except (FileNotFoundError, ValueError) as exc:
        print_error(str(exc))
        raise typer.Exit(1) from exc

    for dest in installed:
        print_success(f"Installed skill → {dest}")
    print_warning(
        "Restart Cursor or start a new agent chat so the skill is discovered."
    )


@app.command("path")
def path_cmd() -> None:
    """Print the on-disk source paths for the shipped skills."""
    missing = False
    for skill_id in shipped_skill_ids():
        try:
            source = resolve_skill_source(skill_id)
        except FileNotFoundError as exc:
            print_error(str(exc))
            missing = True
            continue
        typer.echo(f"{skill_id}\t{source}")
    if missing:
        raise typer.Exit(1)


@app.command("list")
def list_cmd() -> None:
    """Show install locations for each shipped skill."""
    for skill_id in shipped_skill_ids():
        try:
            source = resolve_skill_source(skill_id)
            typer.echo(f"{skill_id}\tsource\t{source}")
        except FileNotFoundError as exc:
            typer.echo(f"{skill_id}\tsource\tMISSING ({exc})")

        user = default_user_skills_dir() / skill_id
        project = project_skills_dir() / skill_id
        typer.echo(f"{skill_id}\tuser\t{user}\t{'yes' if user.is_dir() else 'no'}")
        typer.echo(
            f"{skill_id}\tproject\t{project}\t{'yes' if project.is_dir() else 'no'}"
        )
