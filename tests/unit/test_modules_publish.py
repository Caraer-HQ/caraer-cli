from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from caraer_cli.project.modules_publish import (
    build_package_json,
    package_name,
    publish_modules,
    read_app_dependencies,
    stage_package,
)
from caraer_cli.project.schema import ProjectConfig


def test_public_package_name() -> None:
    assert package_name("caraer_core") == "@caraer/caraer_core"


def test_private_package_adds_company_prefix() -> None:
    assert package_name("notice", private=True, company="sem") == "@caraer/sem_notice"


def test_private_package_skips_existing_prefix() -> None:
    assert (
        package_name("sem_private_cms", private=True, company="sem")
        == "@caraer/sem_private_cms"
    )


def test_publish_modules_uses_caraer_api_not_env_tokens(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "app"
    modules = root / "src" / "app" / "modules" / "hero"
    modules.mkdir(parents=True)
    (root / "caraer.json").write_text(
        '{"platformVersion":"2026.2","name":"demo","srcDir":"src"}\n',
        encoding="utf-8",
    )
    (modules / "index.astro").write_text(
        "---\nexport const manifest = { name: 'hero', kind: 'section', "
        "label: 'Hero', category: 'content' };\n---\n<div></div>\n",
        encoding="utf-8",
    )

    client = MagicMock()
    monkeypatch.delenv("CARAER_REGISTRY_TOKEN", raising=False)
    monkeypatch.delenv("CARAER_REGISTRY_URL", raising=False)

    def fake_pack(staging: Path) -> Path:
        packed = staging / "demo-0.1.0.tgz"
        packed.write_bytes(b"tarball")
        return packed

    monkeypatch.setattr("caraer_cli.project.modules_publish.pack_tarball", fake_pack)
    monkeypatch.setattr(
        "caraer_cli.api.modules.publish_module_package",
        lambda _client, app_uuid, payload: {"data": {"appUuid": app_uuid, **payload}},
    )

    config = ProjectConfig(platformVersion="2026.2", name="demo", srcDir="src", appUuid="app-1")
    summary = publish_modules(
        root,
        config,
        app_name="demo",
        version="0.1.0",
        client=client,
    )

    assert summary["published"] is True
    assert summary["via"] == "api"
    assert summary["package"] == "@caraer/demo"
    assert "tarballBase64" not in summary


def test_published_package_includes_app_dependencies(tmp_path: Path) -> None:
    root = tmp_path / "app"
    modules = root / "src" / "app" / "modules" / "aurora"
    modules.mkdir(parents=True)
    (root / "package.json").write_text(
        json.dumps(
            {
                "name": "demo",
                "dependencies": {
                    "three": "^0.185.1",
                    "astro": "^7.0.0",
                    "@caraer/client": "^2.0.0",
                },
            }
        ),
        encoding="utf-8",
    )
    (modules / "index.astro").write_text(
        "---\nexport const manifest = { name: 'aurora', kind: 'section', "
        "label: 'Aurora', category: 'hero' };\n---\n<div></div>\n",
        encoding="utf-8",
    )

    config = ProjectConfig(platformVersion="2026.2", name="demo", srcDir="src")
    staging, _ = stage_package(
        root,
        config,
        app_name="demo",
        version="0.1.0",
        destination=tmp_path / "staged",
    )
    payload = json.loads((staging / "package.json").read_text(encoding="utf-8"))

    assert payload["dependencies"] == {"three": "^0.185.1"}
    assert "astro" not in payload["dependencies"]
    assert payload["peerDependencies"]["astro"] == "^7.0.0"


def test_published_package_includes_shared_settings(tmp_path: Path) -> None:
    root = tmp_path / "app"
    modules = root / "src" / "app" / "modules"
    hero = modules / "hero"
    hero.mkdir(parents=True)
    (modules / "settings.ts").write_text(
        "export const widthField = { name: 'width', type: 'SINGLE_SELECT' };\n",
        encoding="utf-8",
    )
    (modules / "_theme" / "colors.ts").parent.mkdir()
    (modules / "_theme" / "colors.ts").write_text("export const brand = '#111';\n", encoding="utf-8")
    (hero / "index.astro").write_text(
        "---\nexport const manifest = { name: 'hero', kind: 'section', "
        "label: 'Hero', category: 'content' };\n---\n<div></div>\n",
        encoding="utf-8",
    )

    config = ProjectConfig(platformVersion="2026.2", name="demo", srcDir="src")
    staging, _ = stage_package(
        root,
        config,
        app_name="demo",
        version="0.1.0",
        destination=tmp_path / "staged",
    )

    assert (staging / "modules" / "settings.ts").is_file()
    assert (staging / "modules" / "_theme" / "colors.ts").is_file()


def test_read_app_dependencies_skips_missing_package_json(tmp_path: Path) -> None:
    assert read_app_dependencies(tmp_path) == {}


def test_build_package_json_omits_empty_dependencies() -> None:
    payload = build_package_json("demo", "1.0.0", [])
    assert "dependencies" not in payload
