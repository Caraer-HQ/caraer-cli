from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

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
    assert package_name("library_test", private=True, company="fcg") == "@caraer/fcg_library_test"


def test_private_package_skips_existing_prefix() -> None:
    assert (
        package_name("sem_private_cms", private=True, company="sem")
        == "@caraer/sem_private_cms"
    )


@pytest.mark.parametrize("publish_to_all", [False, True])
def test_publish_modules_uses_caraer_api_not_env_tokens(
    tmp_path: Path, monkeypatch, publish_to_all: bool
) -> None:
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
    config = ProjectConfig(platformVersion="2026.2", name="demo", srcDir="src", appUuid="app-1")
    summary = publish_modules(
        root,
        config,
        app_name="demo",
        version="0.1.0",
        release_notes="Fixed the hero.",
        client=client,
        publish_to_all=publish_to_all,
    )

    assert summary["published"] is True
    assert summary["via"] == "api"
    assert summary["package"] == "@caraer/demo"
    assert "tarballBase64" not in summary
    assert summary.get("publishToAll", False) is publish_to_all
    path = "/api/v2/apps/app-1/cms-modules/package"
    if publish_to_all:
        path += "/publish-to-all"
    assert client.request.call_args.args == ("POST", path)
    assert client.request.call_args.kwargs["json_body"]["releaseNotes"] == "Fixed the hero."


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


@pytest.mark.parametrize("extension", ["png", "jpg", "jpeg", "gif", "webp", "avif", "ico", "svg", "PNG", "SVG"])
@pytest.mark.parametrize("asset_folder", [".", "_shared/assets/nested", "hero/assets/nested"])
def test_staged_package_preserves_image_assets(
    tmp_path: Path, extension: str, asset_folder: str
) -> None:
    root = tmp_path / "app"
    modules = root / "src" / "app" / "modules"
    hero = modules / "hero"
    hero.mkdir(parents=True)
    (hero / "index.astro").write_text(
        "---\nexport const manifest = { name: 'hero', kind: 'section', "
        "label: 'Hero', category: 'content' };\n---\n<div></div>\n",
        encoding="utf-8",
    )
    asset = modules / asset_folder / f"arbitrary-name.{extension}"
    asset.parent.mkdir(parents=True, exist_ok=True)
    content = b"image bytes preserved without transformation"
    asset.write_bytes(content)
    excluded = asset.with_name("private.pem")
    excluded.write_bytes(b"not a module asset")

    config = ProjectConfig(platformVersion="2026.2", name="demo", srcDir="src")
    staging, _ = stage_package(
        root, config, app_name="demo", version="0.1.0", destination=tmp_path / "staged"
    )

    assert (staging / "modules" / asset.relative_to(modules)).read_bytes() == content
    assert not (staging / "modules" / excluded.relative_to(modules)).exists()


def test_read_app_dependencies_skips_missing_package_json(tmp_path: Path) -> None:
    assert read_app_dependencies(tmp_path) == {}


def test_build_package_json_omits_empty_dependencies() -> None:
    payload = build_package_json("demo", "1.0.0", [])
    assert "dependencies" not in payload


def test_packed_asset_validation_reports_the_importer(tmp_path: Path) -> None:
    import tarfile

    from caraer_cli.project.modules_publish import validate_packed_asset_imports

    source = tmp_path / "index.astro"
    source.write_text("---\nimport cloud from '../_shared/cloud.webp';\n---\n", encoding="utf-8")
    archive = tmp_path / "modules.tgz"
    with tarfile.open(archive, "w:gz") as packed:
        packed.add(source, arcname="package/modules/hero/index.astro")
    with pytest.raises(ValueError, match=r"cloud\.webp.*modules/hero/index\.astro"):
        validate_packed_asset_imports(archive)

    cloud = tmp_path / "cloud.webp"
    cloud.write_bytes(b"webp-fixture")
    with tarfile.open(archive, "w:gz") as packed:
        packed.add(source, arcname="package/modules/hero/index.astro")
        packed.add(cloud, arcname="package/modules/_shared/cloud.webp")
    validate_packed_asset_imports(archive)
