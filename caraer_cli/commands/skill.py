"""Install Cursor Agent skills shipped with caraer-cli."""

from __future__ import annotations

import shutil
from importlib import resources
from pathlib import Path

import typer

from caraer_cli.formatters.output import print_error, print_success, print_warning

app = typer.Typer(help="Cursor / AI IDE skill helpers.", no_args_is_help=True)

SKILL_ID = "caraer-apps"


def _repo_skill_dir() -> Path | None:
    """Dev checkout: <repo>/skills/caraer-apps next to the package."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "skills" / SKILL_ID
        if candidate.is_dir() and (candidate / "SKILL.md").is_file():
            return candidate
    return None


def _copy_packaged_skill(dest: Path) -> bool:
    try:
        root = resources.files("caraer_cli") / "skills" / SKILL_ID
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


def resolve_skill_source() -> Path:
    """Return a real filesystem path for read-only inspection (path command)."""
    repo = _repo_skill_dir()
    if repo is not None:
        return repo
    try:
        root = resources.files("caraer_cli") / "skills" / SKILL_ID
        with resources.as_file(root) as path:
            if path.is_dir() and (path / "SKILL.md").is_file():
                # as_file may be temporary; prefer reporting packaged logical path
                return Path(path)
    except (TypeError, FileNotFoundError, ModuleNotFoundError, OSError):
        pass
    raise FileNotFoundError(
        f"Skill '{SKILL_ID}' not found. Reinstall caraer-cli or clone "
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
) -> Path:
    root = target_root or (
        project_skills_dir() if project else default_user_skills_dir()
    )
    dest = root / SKILL_ID
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

    if _copy_packaged_skill(dest):
        return dest

    repo = _repo_skill_dir()
    if repo is not None:
        shutil.copytree(repo, dest)
        return dest

    raise FileNotFoundError(
        f"Skill '{SKILL_ID}' not found. Reinstall caraer-cli or clone "
        "Caraer-HQ/caraer-cli."
    )


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
        help="Replace an existing caraer-apps skill directory.",
    ),
    path: Path | None = typer.Option(
        None,
        "--path",
        help="Custom skills root directory (contains caraer-apps/).",
    ),
) -> None:
    """Install the Caraer Apps Cursor skill for AI IDEs."""
    try:
        dest = install_skill(project=project, target_root=path, force=force)
    except FileExistsError as exc:
        print_error(str(exc))
        raise typer.Exit(1) from exc
    except FileNotFoundError as exc:
        print_error(str(exc))
        raise typer.Exit(1) from exc

    print_success(f"Installed skill → {dest}")
    print_warning(
        "Restart Cursor or start a new agent chat so the skill is discovered."
    )


@app.command("path")
def path_cmd() -> None:
    """Print the on-disk source path for the shipped caraer-apps skill."""
    try:
        source = resolve_skill_source()
    except FileNotFoundError as exc:
        print_error(str(exc))
        raise typer.Exit(1) from exc
    typer.echo(str(source))


@app.command("list")
def list_cmd() -> None:
    """Show install locations and whether caraer-apps is present."""
    try:
        source = resolve_skill_source()
        typer.echo(f"source\t{source}")
    except FileNotFoundError as exc:
        typer.echo(f"source\tMISSING ({exc})")

    user = default_user_skills_dir() / SKILL_ID
    project = project_skills_dir() / SKILL_ID
    typer.echo(f"user\t{user}\t{'yes' if user.is_dir() else 'no'}")
    typer.echo(f"project\t{project}\t{'yes' if project.is_dir() else 'no'}")
