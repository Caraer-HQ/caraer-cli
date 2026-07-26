from __future__ import annotations

from pathlib import Path

from caraer_cli.commands.skill import install_skill, resolve_skill_source


def test_resolve_skill_source_from_repo() -> None:
    source = resolve_skill_source()
    assert source.is_dir()
    assert (source / "SKILL.md").is_file()
    assert (source / "reference.md").is_file()
    text = (source / "SKILL.md").read_text(encoding="utf-8")
    assert "name: caraer-apps" in text
    assert "caraer apps validate" in text


def test_install_skill_user(tmp_path: Path) -> None:
    dest = install_skill(target_root=tmp_path / "skills", force=False)
    assert dest == tmp_path / "skills" / "caraer-apps"
    assert (dest / "SKILL.md").is_file()
    assert (dest / "reference.md").is_file()


def test_install_skill_force_replaces(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    first = install_skill(target_root=root, force=False)
    (first / "marker.txt").write_text("old", encoding="utf-8")
    second = install_skill(target_root=root, force=True)
    assert second == first
    assert not (second / "marker.txt").exists()
    assert (second / "SKILL.md").is_file()
