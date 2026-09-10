from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from caraer_cli.commands.apps import build_public_app_placeholder
from caraer_cli.local_app import (
    discover_local_app_files,
    load_local_app,
    looks_like_local_app_ref,
    looks_like_uuid,
    local_app_summary,
    resolve_app_file_path,
)
from caraer_cli.project.scaffold import (
    ensure_package_json,
    ensure_tsconfig,
    install_npm_dependencies,
    scaffold_app_project,
)


def test_looks_like_uuid() -> None:
    assert looks_like_uuid("550e8400-e29b-41d4-a716-446655440000")
    assert not looks_like_uuid("app.caraer.yaml")


def test_looks_like_local_app_ref(tmp_path) -> None:
    path = tmp_path / "app.caraer.yaml"
    path.write_text("label: Demo\n", encoding="utf-8")
    assert looks_like_local_app_ref(str(path))
    assert looks_like_local_app_ref("app.caraer.yaml")
    assert looks_like_local_app_ref("./apps/my.yaml")
    assert not looks_like_local_app_ref("550e8400-e29b-41d4-a716-446655440000")


def test_discover_and_summarize_local_app(tmp_path) -> None:
    path = tmp_path / "app.caraer.yaml"
    path.write_text("name: demo\nlabel: Demo\n", encoding="utf-8")
    found = discover_local_app_files(tmp_path)
    assert path.resolve() in found
    summary = local_app_summary(path)
    assert summary["source"] == "local"
    assert summary["name"] == "demo"
    assert summary["label"] == "Demo"


def test_scaffold_app_project_layout(tmp_path: Path) -> None:
    root = tmp_path / "my_app"
    payload = build_public_app_placeholder(label="My App", name="my_app")
    result = scaffold_app_project(
        root,
        app_payload=payload,
        sample_function="hello-world",
        runtime="python312",
    )

    assert (root / "caraer.json").is_file()
    assert not (root / "caraer.project.json").exists()
    manifest = root / "src" / "app" / "app.caraer.yaml"
    assert manifest.is_file()
    assert (root / "src" / "app" / "functions" / "hello-world" / "main.py").is_file()
    assert not (root / "src" / "app" / "functions" / "hello-world" / "function.caraer.json").exists()
    assert (root / "src" / "app" / "webhooks").is_dir()
    hello_module = root / "src" / "app" / "modules" / "hello_world"
    assert (hello_module / "index.astro").is_file()
    assert (hello_module / "fields.d.ts").is_file()
    assert result["sample_module"].resolve() == hello_module.resolve()
    webhook = root / "src" / "app" / "webhooks" / "record-candidate-created-serverless.json"
    assert webhook.is_file()
    webhook_json = json.loads(webhook.read_text(encoding="utf-8"))
    assert webhook_json["topic"] == "record.candidate.created"
    assert webhook_json["deliveryMode"] == "SERVERLESS"
    assert webhook_json["serverlessFunction"]["name"] == "hello-world"
    assert (root / ".gitignore").is_file()

    lifecycle = root / "src" / "app" / "lifecycle"
    assert result["lifecycle_dir"].resolve() == lifecycle.resolve()
    assert len(result["lifecycle_hooks"]) == 4
    for stem, topic in (
        ("install", "app.installed"),
        ("uninstall", "app.uninstalled"),
        ("rotate", "app.rotated"),
        ("update", "app.updated"),
    ):
        hook = lifecycle / f"{stem}.json"
        assert hook.is_file()
        hook_json = json.loads(hook.read_text(encoding="utf-8"))
        assert hook_json["topic"] == topic
        assert hook_json["serverlessFunction"]["name"] == f"on-{stem}"
        assert (root / "src" / "app" / "functions" / f"on-{stem}" / "main.py").is_file()

    workspace = json.loads((root / "caraer.json").read_text(encoding="utf-8"))
    assert "projectUuid" not in workspace
    assert workspace["platformVersion"] == "2026.2"
    assert workspace.get("runtime") == "python312"

    text = manifest.read_text(encoding="utf-8")
    assert "runtime: python312" in text
    assert "authMethod: OAUTH2" in text
    assert "hideApiKeyField: true" in text
    assert "oauthRedirectUris:" in text
    assert "http://localhost:3000/oauth/callback" in text
    assert "pricingPlans" not in text
    assert "# Edit appBars above when needed" in text
    assert "# Example scopes" in text
    assert "caraer apps add setting" in text
    assert "add lifecycle-hook" in text

    app_json = load_local_app(manifest)
    assert app_json["name"] == "my_app"
    assert "requiredScopes" in app_json
    assert "pricingPlans" not in app_json
    # Function code must not live inside the app YAML.
    assert "functions" not in app_json
    assert "serverlessFunctions" not in app_json

    resolved = resolve_app_file_path(root)
    assert resolved == result["app_file"].resolve()

    found = discover_local_app_files(tmp_path)
    assert result["app_file"].resolve() in found


def test_node_init_writes_tsconfig_and_module_package_json(tmp_path: Path) -> None:
    root = tmp_path / "cms_app"
    payload = build_public_app_placeholder(label="CMS App", name="cms_app")
    scaffold_app_project(
        root,
        app_payload=payload,
        sample_function=None,
        runtime="nodejs22",
    )

    tsconfig = json.loads((root / "tsconfig.json").read_text(encoding="utf-8"))
    assert tsconfig["compilerOptions"]["moduleResolution"] == "bundler"
    assert "src/**/*.ts" in tsconfig["include"]

    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    assert package["type"] == "module"
    assert "three" not in package.get("dependencies", {})
    assert "@types/three" not in package.get("devDependencies", {})
    assert package["devDependencies"]["@caraer/client"] == "^2.0.366"
    assert package["scripts"]["dev"] == "caraer apps local dev"
    assert package["scripts"]["push"] == "caraer apps push"
    assert package["dependencies"]["@caraer/cms-runtime"].startswith("github:Caraer-HQ/caraer-cms-runtime")
    assert package["dependencies"]["@caraer/cms-tokens"].startswith("github:Caraer-HQ/caraer-cms-tokens")
    assert (root / "src" / "app" / "modules" / "hello_world" / "index.astro").is_file()
    assert (root / "src" / "app" / "modules" / "hello_world" / "fields.d.ts").is_file()
    assert ensure_tsconfig(root) is None


def test_existing_package_json_is_left_alone(tmp_path: Path) -> None:
    root = tmp_path / "legacy"
    root.mkdir()
    (root / "package.json").write_text(
        json.dumps({"name": "legacy", "private": True, "devDependencies": {}}, indent=2)
        + "\n",
        encoding="utf-8",
    )

    assert ensure_package_json(root, "legacy") is None
    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    assert package["devDependencies"] == {}
    assert package["scripts"]["dev"] == "caraer apps local dev"


def test_existing_dev_script_is_left_alone(tmp_path: Path) -> None:
    root = tmp_path / "custom"
    root.mkdir()
    (root / "package.json").write_text(
        json.dumps({"name": "custom", "scripts": {"dev": "astro dev"}}, indent=2) + "\n",
        encoding="utf-8",
    )

    assert ensure_package_json(root, "custom") is None
    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    assert package["scripts"]["dev"] == "astro dev"


def test_legacy_json_manifest_still_loads(tmp_path: Path) -> None:
    path = tmp_path / "app.caraer.json"
    path.write_text('{"name":"legacy","label":"Legacy"}\n', encoding="utf-8")
    data = load_local_app(path)
    assert data["name"] == "legacy"


def test_install_npm_dependencies_skips_without_package_json(tmp_path: Path) -> None:
    assert install_npm_dependencies(tmp_path) is False


def test_install_npm_dependencies_runs_npm_install(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{}\n", encoding="utf-8")
    with (
        patch("caraer_cli.project.scaffold.shutil.which", return_value="/usr/bin/npm"),
        patch("caraer_cli.project.scaffold.subprocess.run") as run,
    ):
        run.return_value.returncode = 0
        run.return_value.stderr = ""
        run.return_value.stdout = ""
        assert install_npm_dependencies(tmp_path) is True
    run.assert_called_once()
    assert run.call_args.args[0] == ["/usr/bin/npm", "install"]
    assert run.call_args.kwargs["cwd"] == tmp_path


def test_install_npm_dependencies_requires_npm(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{}\n", encoding="utf-8")
    with patch("caraer_cli.project.scaffold.shutil.which", return_value=None):
        try:
            install_npm_dependencies(tmp_path)
        except RuntimeError as exc:
            assert "npm is required" in str(exc)
        else:
            raise AssertionError("expected RuntimeError")
