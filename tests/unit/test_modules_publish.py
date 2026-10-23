from __future__ import annotations

import json
import tarfile
from pathlib import Path
from unittest.mock import MagicMock

from caraer_cli.project.modules_publish import (
    build_package_json,
    package_name,
    pack_tarball,
    publish_modules,
    read_app_dependencies,
    stage_package,
)
from caraer_cli.project.schema import ProjectConfig


def test_public_package_name() -> None:
    assert package_name("caraer_core") == "@caraer/caraer_core"


def test_private_package_adds_company_prefix() -> None:
    assert package_name("notice", private=True, company="sem") == "@caraer/sem_notice"
    assert package_name("library_test", private=True, company="fcg") == "@caraer/fcg_library_test"


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
    captured: dict = {}

    def fake_publish(_client, app_uuid, payload):
        captured.update(payload)
        return {"data": {"appUuid": app_uuid, **payload}}

    monkeypatch.setattr(
        "caraer_cli.api.modules.publish_module_package",
        fake_publish,
    )

    config = ProjectConfig(platformVersion="2026.2", name="demo", srcDir="src", appUuid="app-1")
    summary = publish_modules(
        root,
        config,
        app_name="demo",
        version="0.1.0",
        release_notes="Fixed the hero.",
        client=client,
    )

    assert summary["published"] is True
    assert summary["via"] == "api"
    assert summary["package"] == "@caraer/demo"
    assert "tarballBase64" not in summary
    assert captured["releaseNotes"] == "Fixed the hero."


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


def test_module_tarball_preserves_bundled_assets(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("npm_config_cache", str(tmp_path / "npm-cache"))
    root = tmp_path / "app"
    modules = root / "src" / "app" / "modules"
    hero = modules / "hero"
    hero.mkdir(parents=True)
    (hero / "index.astro").write_text(
        "---\nimport image from './assets/image.png';\n"
        "import shared from '../_shared/image.webp';\n"
        "export const manifest = { name: 'hero', kind: 'section', "
        "label: 'Hero', category: 'content' };\n---\n<img src={image.src} />\n",
        encoding="utf-8",
    )
    assets = [
        "hero/assets/image.png", "hero/assets/image.JPG", "hero/assets/image.jpeg",
        "hero/assets/image.gif", "hero/assets/image.avif", "hero/assets/icon.ico",
        "hero/assets/font.woff", "hero/assets/font.woff2", "hero/assets/font.ttf",
        "hero/assets/font.otf", "hero/assets/video.mp4", "hero/assets/video.webm",
        "hero/assets/audio.mp3", "hero/assets/audio.wav", "hero/assets/audio.ogg",
        "_shared/image.webp", "logo.png",
    ]
    for asset in assets:
        path = modules / asset
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"bundled asset")
    (hero / ".env").write_text("SECRET=excluded\n", encoding="utf-8")

    config = ProjectConfig(platformVersion="2026.2", name="demo", srcDir="src")
    staging, _ = stage_package(
        root, config, app_name="demo", version="0.1.0", destination=tmp_path / "staged",
    )
    with tarfile.open(pack_tarball(staging)) as archive:
        for asset in assets:
            member = archive.extractfile(f"package/modules/{asset}")
            assert member is not None
            assert member.read() == b"bundled asset"
        assert "package/modules/hero/.env" not in archive.getnames()


def test_build_package_json_omits_empty_dependencies() -> None:
    payload = build_package_json("demo", "1.0.0", [])
    assert "dependencies" not in payload
