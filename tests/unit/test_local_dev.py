from __future__ import annotations

import json
import threading
import time
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from caraer_cli.project.local_dev import (
    function_name_from_path,
    resolve_function_name,
    serve_functions,
)
from caraer_cli.project.schema import ProjectConfig


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/hello-world", "hello-world"),
        ("/hello-world/", "hello-world"),
        ("/hello-world?x=1", "hello-world"),
        ("/functions/hello-world", "hello-world"),
        ("/functions/hello-world/", "hello-world"),
        ("/functions/hello-world?x=1", "hello-world"),
        ("/", None),
        ("/a/b", None),
        ("/functions", None),
        ("", None),
    ],
)
def test_function_name_from_path(path: str, expected: str | None) -> None:
    assert function_name_from_path(path) == expected


def test_resolve_function_name_header_and_body() -> None:
    class _Headers(dict):
        def get(self, key, default=None):  # noqa: ANN001
            for k, v in self.items():
                if k.lower() == key.lower():
                    return v
            return default

    assert resolve_function_name("/", headers=_Headers({"X-Caraer-Function": "alpha"})) == "alpha"
    assert resolve_function_name("/", body={"functionName": "beta"}) == "beta"
    assert resolve_function_name("/functions/gamma") == "gamma"


def _write_node_function(root: Path, name: str, body_expr: str) -> None:
    folder = root / "src" / "app" / "functions" / name
    folder.mkdir(parents=True)
    (folder / "function.caraer.json").write_text(
        json.dumps({"name": name, "runtime": "nodejs22", "entry": "index.js"}),
        encoding="utf-8",
    )
    (folder / "index.js").write_text(
        "exports.handler = async (req, res) => {\n"
        f"  res.status(200).json({body_expr});\n"
        "};\n",
        encoding="utf-8",
    )


def _wait_for_server(port: int) -> HTTPConnection:
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    for _ in range(50):
        try:
            conn.request("GET", "/")
            index = conn.getresponse()
            index.read()
            return conn
        except OSError:
            time.sleep(0.01)
            conn.close()
            conn = HTTPConnection("127.0.0.1", port, timeout=5)
    pytest.fail("dev server did not start")


def _free_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_serve_functions_v2_routes(tmp_path: Path) -> None:
    _write_node_function(tmp_path, "alpha", '{ ok: "alpha" }')
    _write_node_function(tmp_path, "beta", '{ ok: "beta" }')
    config = ProjectConfig(
        platformVersion="2026.2",
        name="demo",
        runtime="nodejs22",
        appUuid="app-local",
    )
    port = _free_port()

    thread = threading.Thread(
        target=serve_functions,
        kwargs={
            "root": tmp_path,
            "config": config,
            "host": "127.0.0.1",
            "port": port,
        },
        daemon=True,
    )
    thread.start()

    conn = _wait_for_server(port)
    try:
        conn.request("GET", "/")
        index = conn.getresponse()
        index_body = json.loads(index.read().decode("utf-8"))
        assert index.status == 200
        assert set(index_body["functions"]) == {"alpha", "beta"}
        assert any("/functions/" in inv for inv in index_body["invoke"])

        # Canonical V2 path
        conn.request(
            "POST",
            "/functions/alpha",
            body="{}",
            headers={"Content-Type": "application/json"},
        )
        alpha = conn.getresponse()
        assert alpha.status == 200
        assert json.loads(alpha.read().decode("utf-8")) == {
            "statusCode": 200,
            "body": {"ok": "alpha"},
        }

        # Legacy alias
        conn.request(
            "POST",
            "/beta",
            body="{}",
            headers={"Content-Type": "application/json"},
        )
        beta = conn.getresponse()
        assert beta.status == 200
        assert json.loads(beta.read().decode("utf-8"))["body"]["ok"] == "beta"

        # Header resolution on root
        conn.request(
            "POST",
            "/",
            body="{}",
            headers={
                "Content-Type": "application/json",
                "X-Caraer-Function": "alpha",
            },
        )
        via_header = conn.getresponse()
        assert via_header.status == 200
        assert json.loads(via_header.read().decode("utf-8"))["body"]["ok"] == "alpha"

        # Body functionName
        conn.request(
            "POST",
            "/",
            body=json.dumps({"functionName": "beta"}),
            headers={"Content-Type": "application/json"},
        )
        via_body = conn.getresponse()
        assert via_body.status == 200
        assert json.loads(via_body.read().decode("utf-8"))["body"]["ok"] == "beta"
    finally:
        conn.close()


def test_installation_shim_state_roundtrip(tmp_path: Path) -> None:
    _write_node_function(tmp_path, "alpha", '{ ok: true }')
    config = ProjectConfig(
        platformVersion="2026.2",
        name="demo",
        runtime="nodejs22",
        appUuid="app-shim",
    )
    port = _free_port()
    thread = threading.Thread(
        target=serve_functions,
        kwargs={
            "root": tmp_path,
            "config": config,
            "host": "127.0.0.1",
            "port": port,
        },
        daemon=True,
    )
    thread.start()
    conn = _wait_for_server(port)
    try:
        path = "/api/v2/apps/app-shim/installation/state/foo"
        conn.request(
            "PUT",
            path,
            body=json.dumps({"value": "bar"}),
            headers={"Content-Type": "application/json"},
        )
        put = conn.getresponse()
        assert put.status == 200
        put.read()

        conn.request("GET", path)
        get = conn.getresponse()
        assert get.status == 200
        body = json.loads(get.read().decode("utf-8"))
        assert body["data"]["foo"] == "bar"
    finally:
        conn.close()


def test_pull_aligns_platform_version(tmp_path: Path) -> None:
    from caraer_cli.app_sync import pull_app_full
    from caraer_cli.project.schema import load_workspace

    remote = {
        "uuid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "name": "pulled_app",
        "label": "Pulled",
        "platformVersion": 1,
        "runtime": "python312",
        "details": {
            "title": "Pulled",
            "description": "desc",
            "category": "developer_tools",
            "subcategories": ["apis"],
            "brandColor": "#E74363",
        },
    }

    client = MagicMock()
    with (
        patch(
            "caraer_cli.apps_local.apps_api.fetch_app",
            return_value={"data": remote},
        ),
        patch(
            "caraer_cli.app_sync.apps_api.fetch_app",
            return_value={"data": remote},
        ),
        patch("caraer_cli.app_sync.ensure_linked", side_effect=lambda c, r, cfg, **k: cfg),
        patch("caraer_cli.app_sync.pull_functions", return_value={"functions": []}),
        patch("caraer_cli.app_sync.pull_webhooks", return_value={"webhooks": []}),
        patch("caraer_cli.app_sync.pull_schedules", return_value=0),
        patch("caraer_cli.app_sync.pull_inbound", return_value=0),
        patch("caraer_cli.app_sync.pull_external_oauth_providers", return_value=0),
    ):
        result = pull_app_full(
            client,
            app_uuid="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            directory=tmp_path / "pulled_app",
        )

    root = Path(result["root"])
    config = load_workspace(root)
    assert config.platformVersion == "2026.1"
    assert result["platformVersion"] == "2026.1"


def test_deploy_wait_polls_v2(tmp_path: Path) -> None:
    from caraer_cli.app_sync import _poll_v2_runtime

    config = ProjectConfig(
        platformVersion="2026.2",
        name="demo",
        appUuid="app-1",
        runtime="nodejs22",
    )
    client = MagicMock()
    client_responses = [
        {"data": {"runtimeStatus": "PROVISIONING"}},
        {"data": {"runtimeStatus": "READY", "runtimeBaseUrl": "https://example.run"}},
    ]
    with patch(
        "caraer_cli.app_sync.apps_api.get_app",
        side_effect=client_responses,
    ):
        result = _poll_v2_runtime(client, config, timeout_s=5, interval_s=0.01)
    assert result["runtimeStatus"] == "READY"


@pytest.mark.parametrize("suffix", [".js", ".mjs"])
def test_invoke_es_module_with_shared_import_and_top_level_await(tmp_path: Path, suffix: str) -> None:
    from caraer_cli.project.local_dev import invoke_local

    (tmp_path / "package.json").write_text('{"type":"module"}')
    shared = tmp_path / "shared"
    shared.mkdir()
    (shared / "index.js").write_text('export const greeting = "hello";\n')
    entry = tmp_path / f"hello world{suffix}"
    entry.write_text(
        'import { greeting } from "./shared/index.js";\n'
        'const ready = await Promise.resolve(true);\n'
        'console.log("initializing");\n'
        'export const handler = async (req, res) => {\n'
        '  res.status(201).json({ greeting, ready, name: req.body.name });\n'
        '};\n'
    )
    assert invoke_local("nodejs22", entry, {"name": "Robin"}) == {
        "statusCode": 201,
        "body": {"greeting": "hello", "ready": True, "name": "Robin"},
    }


def test_invoke_commonjs_still_works(tmp_path: Path) -> None:
    from caraer_cli.project.local_dev import invoke_local

    entry = tmp_path / "legacy.cjs"
    entry.write_text('exports.handler = (req, res) => res.json({ ok: true });\n')
    assert invoke_local("nodejs22", entry, {})["body"] == {"ok": True}
