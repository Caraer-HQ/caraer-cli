from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from pathlib import Path

import pytest

from caraer_cli.project.local_dev import function_name_from_path, serve_functions
from caraer_cli.project.schema import ProjectConfig


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/hello-world", "hello-world"),
        ("/hello-world/", "hello-world"),
        ("/hello-world?x=1", "hello-world"),
        ("/", None),
        ("/a/b", None),
        ("", None),
    ],
)
def test_function_name_from_path(path: str, expected: str | None) -> None:
    assert function_name_from_path(path) == expected


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


def test_serve_functions_routes_by_name(tmp_path: Path) -> None:
    _write_node_function(tmp_path, "alpha", '{ ok: "alpha" }')
    _write_node_function(tmp_path, "beta", '{ ok: "beta" }')
    config = ProjectConfig(
        platformVersion="2026.2",
        name="demo",
        runtime="nodejs22",
    )

    thread = threading.Thread(
        target=serve_functions,
        kwargs={
            "root": tmp_path,
            "config": config,
            "host": "127.0.0.1",
            "port": 18787,
        },
        daemon=True,
    )
    thread.start()

    conn = HTTPConnection("127.0.0.1", 18787, timeout=5)
    try:
        # Wait until the server accepts connections.
        for _ in range(50):
            try:
                conn.request("GET", "/")
                index = conn.getresponse()
                index_body = json.loads(index.read().decode("utf-8"))
                break
            except OSError:
                conn.close()
                conn = HTTPConnection("127.0.0.1", 18787, timeout=5)
        else:
            pytest.fail("dev server did not start")

        assert index.status == 200
        assert set(index_body["functions"]) == {"alpha", "beta"}

        conn.request("POST", "/alpha", body="{}", headers={"Content-Type": "application/json"})
        alpha = conn.getresponse()
        assert alpha.status == 200
        assert json.loads(alpha.read().decode("utf-8")) == {
            "statusCode": 200,
            "body": {"ok": "alpha"},
        }

        conn.request("POST", "/missing", body="{}", headers={"Content-Type": "application/json"})
        missing = conn.getresponse()
        assert missing.status == 404
        assert "functions" in json.loads(missing.read().decode("utf-8"))
    finally:
        conn.close()
