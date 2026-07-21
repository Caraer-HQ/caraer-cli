from __future__ import annotations

import json
import runpy
import subprocess
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

from caraer_cli.project.paths import functions_dir
from caraer_cli.project.schema import ProjectConfig, load_function_manifest
from caraer_cli.project.sync import list_local_function_names


def _load_local_function(root: Path, config: ProjectConfig, function_name: str) -> tuple[str, Path]:
    folder = functions_dir(root, config.srcDir) / function_name
    manifest = load_function_manifest(folder / "function.caraer.json")
    entry = folder / manifest.resolved_entry()
    if not entry.is_file():
        raise FileNotFoundError(f"Missing entry file: {entry}")
    return manifest.runtime, entry


def invoke_local(runtime: str, entry: Path, payload: dict[str, Any]) -> dict[str, Any]:
    if runtime.startswith("python"):
        return _invoke_python(entry, payload)
    return _invoke_node(entry, payload)


def _invoke_python(entry: Path, payload: dict[str, Any]) -> dict[str, Any]:
    namespace = runpy.run_path(str(entry))
    handler = namespace.get("handler")
    if handler is None:
        raise ValueError(f"No handler() found in {entry}")
    # Mimic a minimal request object with .get_json()
    class _Req:
        def get_json(self, silent: bool = True):  # noqa: ARG002
            return payload

        def get_data(self, as_text: bool = False):
            raw = json.dumps(payload)
            return raw if as_text else raw.encode("utf-8")

    result = handler(_Req())
    if isinstance(result, dict):
        return result
    return {"result": result}


def _invoke_node(entry: Path, payload: dict[str, Any]) -> dict[str, Any]:
    script = f"""
const mod = require({json.dumps(str(entry))});
const payload = {json.dumps(payload)};
// Keep handler console.log off stdout so the CLI can parse the result JSON.
const _log = console.log.bind(console);
console.log = (...args) => console.error(...args);
const res = {{
  statusCode: 200,
  body: null,
  status(code) {{ this.statusCode = code; return this; }},
  json(body) {{ this.body = body; return this; }},
  send(body) {{ this.body = body; return this; }}
}};
const req = {{ body: payload, method: 'POST', headers: {{}} }};
Promise.resolve(mod.handler(req, res)).then(() => {{
  process.stdout.write(JSON.stringify({{ statusCode: res.statusCode, body: res.body }}));
}}).catch((err) => {{
  console.error(err && err.stack ? err.stack : String(err));
  process.exit(1);
}});
"""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as tmp:
        tmp.write(script)
        tmp_path = tmp.name
    try:
        completed = subprocess.run(
            ["node", tmp_path],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise RuntimeError(detail or f"node exited with status {completed.returncode}")
        # Handler may have logged to stdout before redirection in older runners;
        # take the last JSON object line when possible.
        stdout = (completed.stdout or "").strip()
        try:
            return json.loads(stdout or "{}")
        except json.JSONDecodeError:
            for line in reversed(stdout.splitlines()):
                line = line.strip()
                if line.startswith("{") and line.endswith("}"):
                    return json.loads(line)
            raise
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def function_name_from_path(path: str) -> str | None:
    """Extract `/<function_name>` from a request path (ignores query string)."""
    parsed = urlparse(path)
    parts = [unquote(part) for part in parsed.path.split("/") if part]
    if len(parts) != 1:
        return None
    return parts[0]


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: Any) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def serve_functions(
    root: Path,
    config: ProjectConfig,
    *,
    host: str,
    port: int,
    function_names: list[str] | None = None,
) -> None:
    """Serve all local functions at POST http://host:port/<function_name>."""
    load_dotenv(root / ".env")
    available = list_local_function_names(root, config)
    if function_names:
        unknown = [name for name in function_names if name not in available]
        if unknown:
            raise ValueError(
                f"Unknown function(s): {', '.join(unknown)}. "
                f"Available: {', '.join(available) or '(none)'}"
            )
        names = list(function_names)
    else:
        names = available
    if not names:
        raise ValueError(
            "No local functions found under src/app/functions/. "
            "Add a function folder first."
        )
    name_set = set(names)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            name = function_name_from_path(self.path)
            if name is None and urlparse(self.path).path in ("", "/"):
                _json_response(
                    self,
                    200,
                    {
                        "functions": names,
                        "invoke": "POST /<function_name> with a JSON body",
                    },
                )
                return
            if name is None or name not in name_set:
                _json_response(
                    self,
                    404,
                    {
                        "error": "function not found",
                        "functions": names,
                    },
                )
                return
            _json_response(
                self,
                200,
                {
                    "function": name,
                    "invoke": f"POST /{name} with a JSON body",
                },
            )

        def do_POST(self):  # noqa: N802
            name = function_name_from_path(self.path)
            if name is None or name not in name_set:
                _json_response(
                    self,
                    404,
                    {
                        "error": "function not found",
                        "functions": names,
                    },
                )
                return
            length = int(self.headers.get("Content-Length") or "0")
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                _json_response(self, 400, {"error": "invalid json"})
                return
            if not isinstance(payload, dict):
                _json_response(self, 400, {"error": "json body must be an object"})
                return
            try:
                runtime, entry = _load_local_function(root, config, name)
                result = invoke_local(runtime, entry, payload)
                _json_response(self, 200, result)
            except Exception as exc:  # noqa: BLE001
                _json_response(self, 500, {"error": str(exc)})

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return

    server = ThreadingHTTPServer((host, port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


def serve_function(
    root: Path,
    config: ProjectConfig,
    *,
    function_name: str,
    host: str,
    port: int,
) -> None:
    """Backward-compatible wrapper: serve one function at /<function_name>."""
    serve_functions(
        root,
        config,
        host=host,
        port=port,
        function_names=[function_name],
    )
