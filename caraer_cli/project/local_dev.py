from __future__ import annotations

import json
import os
import runpy
import subprocess
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

from caraer_cli.project.paths import functions_dir, inbound_dir, schedules_dir
from caraer_cli.project.schema import ProjectConfig, load_function_manifest
from caraer_cli.project.sync import list_local_function_names


def _load_local_function(root: Path, config: ProjectConfig, function_name: str) -> tuple[str, Path]:
    from caraer_cli.project.sync import load_or_conventional_manifest

    folder = functions_dir(root, config.srcDir) / function_name
    manifest = load_or_conventional_manifest(folder, config)
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
            env=os.environ.copy(),
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
    """Extract a function name from a V2-compatible request path.

    Accepted shapes (query string ignored):
    - `/functions/{name}` (canonical V2 container route)
    - `/{name}` (legacy local-dev alias)
    """
    parsed = urlparse(path)
    parts = [unquote(part) for part in parsed.path.split("/") if part]
    if len(parts) == 2 and parts[0] == "functions":
        return parts[1]
    if len(parts) == 1 and parts[0] != "functions":
        return parts[0]
    return None


def resolve_function_name(
    path: str,
    *,
    headers: Any = None,
    body: dict[str, Any] | None = None,
) -> str | None:
    """Resolve function name from path, X-Caraer-Function header, or body.functionName."""
    name = function_name_from_path(path)
    if name:
        return name
    if headers is not None:
        header_name = headers.get("X-Caraer-Function") or headers.get("x-caraer-function")
        if isinstance(header_name, str) and header_name.strip():
            return header_name.strip()
    if isinstance(body, dict):
        body_name = body.get("functionName")
        if isinstance(body_name, str) and body_name.strip():
            return body_name.strip()
    return None


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: Any) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any] | list[Any] | None:
    length = int(handler.headers.get("Content-Length") or "0")
    raw = handler.rfile.read(length) if length else b""
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return None


def _dev_state_path(root: Path) -> Path:
    return root / ".caraer" / "dev-state.json"


def _load_dev_store(root: Path) -> dict[str, Any]:
    path = _dev_state_path(root)
    if not path.is_file():
        return {"state": {}, "secrets": {}, "jobs": {}, "connections": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"state": {}, "secrets": {}, "jobs": {}, "connections": {}}
    if not isinstance(data, dict):
        return {"state": {}, "secrets": {}, "jobs": {}, "connections": {}}
    data.setdefault("state", {})
    data.setdefault("secrets", {})
    data.setdefault("jobs", {})
    data.setdefault("connections", {})
    return data


def _save_dev_store(root: Path, store: dict[str, Any]) -> None:
    path = _dev_state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store, indent=2) + "\n", encoding="utf-8")


def _seed_secrets_from_env(root: Path, store: dict[str, Any]) -> None:
    """Seed installation secrets from .env keys that look like SECRET_* or SECRETS_*."""
    env_path = root / ".env"
    if not env_path.is_file():
        return
    secrets = store.setdefault("secrets", {})
    if not isinstance(secrets, dict):
        secrets = {}
        store["secrets"] = secrets
    for line in env_path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, _, value = text.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key.startswith("SECRET_") and key not in secrets:
            secrets[key[len("SECRET_") :]] = value
        elif key.startswith("SECRETS_") and key not in secrets:
            secrets[key[len("SECRETS_") :]] = value


def _load_local_schedules(root: Path, config: ProjectConfig) -> list[dict[str, Any]]:
    base = schedules_dir(root, config.srcDir)
    if not base.is_dir():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(base.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(data, dict):
            items.append(data)
    return items


def _load_local_inbound(root: Path, config: ProjectConfig) -> list[dict[str, Any]]:
    base = inbound_dir(root, config.srcDir)
    if not base.is_dir():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(base.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(data, dict):
            items.append(data)
    return items


def _function_ref_name(ref: Any) -> str | None:
    if isinstance(ref, dict):
        name = ref.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    if isinstance(ref, str) and ref.strip():
        return ref.strip()
    return None


class _SourceWatcher:
    """Stat-based poll watcher for local app sources under ``src/``."""

    def __init__(self, root: Path, config: ProjectConfig) -> None:
        self.root = root
        self.config = config
        self.src = root / config.srcDir
        self._mtimes: dict[Path, float] = {}
        self._snapshot()

    def _iter_files(self) -> list[Path]:
        if not self.src.is_dir():
            return []
        files: list[Path] = []
        for path in self.src.rglob("*"):
            if not path.is_file():
                continue
            if path.name.startswith(".") or "__pycache__" in path.parts:
                continue
            if path.suffix.lower() in {
                ".js",
                ".mjs",
                ".cjs",
                ".ts",
                ".py",
                ".json",
                ".yaml",
                ".yml",
            }:
                files.append(path)
        return files

    def _snapshot(self) -> None:
        current: dict[Path, float] = {}
        for path in self._iter_files():
            try:
                current[path] = path.stat().st_mtime
            except OSError:
                continue
        self._mtimes = current

    def poll(self) -> list[Path]:
        previous = self._mtimes
        current: dict[Path, float] = {}
        changed: list[Path] = []
        for path in self._iter_files():
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            current[path] = mtime
            if previous.get(path) != mtime:
                changed.append(path)
        for path in previous:
            if path not in current:
                changed.append(path)
        self._mtimes = current
        return changed

    def function_name_for(self, path: Path) -> str | None:
        try:
            rel = path.relative_to(functions_dir(self.root, self.config.srcDir))
        except ValueError:
            return None
        if not rel.parts:
            return None
        return rel.parts[0]


def serve_functions(
    root: Path,
    config: ProjectConfig,
    *,
    host: str,
    port: int,
    function_names: list[str] | None = None,
    invoke_schedule: str | None = None,
    enable_installation_shim: bool = True,
) -> None:
    """Serve local functions with the V2 container invoke contract.

    Canonical invoke: POST /functions/{name}
    Also accepts: POST /{name}, X-Caraer-Function header, or body.functionName.
    When enable_installation_shim is True, also serves local installation APIs.
    Reloads function discovery when files under src/ change (hot reload).
    """
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
        lock_names = True
    else:
        names = available
        lock_names = False
    if not names:
        raise ValueError(
            "No local functions found under src/app/functions/. "
            "Add a function folder first."
        )
    name_set = set(names)

    app_uuid = str(config.appUuid or "local-dev-app")
    store = _load_dev_store(root)
    _seed_secrets_from_env(root, store)
    _save_dev_store(root, store)

    # Env injection so example apps that call Caraer installation APIs work locally.
    base_url = f"http://{host}:{port}"
    os.environ.setdefault("CARAER_DEV_BASE_URL", base_url)
    os.environ.setdefault("CARAER_API_BASE_URL", base_url)
    os.environ.setdefault("CARAER_INSTALLATION_TOKEN", "local-dev-installation-token")
    os.environ.setdefault("CARAER_APP_UUID", app_uuid)

    schedules = _load_local_schedules(root, config)
    inbound_routes = _load_local_inbound(root, config)
    job_lock = threading.Lock()
    watcher = _SourceWatcher(root, config)
    reload_lock = threading.Lock()

    def _refresh_from_disk(*, announce: bool = True) -> list[str]:
        nonlocal names, name_set, schedules, inbound_routes
        changed = watcher.poll()
        if not changed:
            return []
        reloaded_functions: list[str] = []
        with reload_lock:
            if not lock_names:
                names = list_local_function_names(root, config)
                name_set = set(names)
            schedules = _load_local_schedules(root, config)
            inbound_routes = _load_local_inbound(root, config)
            for path in changed:
                fn_name = watcher.function_name_for(path)
                if fn_name and fn_name in name_set and fn_name not in reloaded_functions:
                    reloaded_functions.append(fn_name)
        if announce:
            for fn_name in reloaded_functions:
                print(f"reloaded {fn_name}", flush=True)
            if changed and not reloaded_functions:
                print(f"reloaded config ({len(changed)} file(s))", flush=True)
        return reloaded_functions

    def _run_function(fn_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        _refresh_from_disk(announce=True)
        runtime, entry = _load_local_function(root, config, fn_name)
        return invoke_local(runtime, entry, payload)

    def _enqueue_job(
        fn_name: str,
        payload: dict[str, Any],
        *,
        delay_seconds: float = 0,
    ) -> dict[str, Any]:
        job_id = str(uuid.uuid4())
        job = {
            "jobId": job_id,
            "status": "QUEUED",
            "functionName": fn_name,
            "payload": payload,
            "createdAt": time.time(),
        }
        with job_lock:
            store_local = _load_dev_store(root)
            jobs = store_local.setdefault("jobs", {})
            jobs[job_id] = job
            _save_dev_store(root, store_local)

        def _worker() -> None:
            if delay_seconds > 0:
                time.sleep(delay_seconds)
            with job_lock:
                current = _load_dev_store(root)
                jobs_map = current.setdefault("jobs", {})
                entry = jobs_map.get(job_id) or job
                entry["status"] = "RUNNING"
                jobs_map[job_id] = entry
                _save_dev_store(root, current)
            try:
                result = _run_function(fn_name, payload)
                status = "SUCCEEDED"
                error = None
            except Exception as exc:  # noqa: BLE001
                result = None
                status = "FAILED"
                error = str(exc)
            with job_lock:
                current = _load_dev_store(root)
                jobs_map = current.setdefault("jobs", {})
                entry = jobs_map.get(job_id) or job
                entry["status"] = status
                entry["result"] = result
                if error:
                    entry["error"] = error
                jobs_map[job_id] = entry
                _save_dev_store(root, current)

        threading.Thread(target=_worker, daemon=True).start()
        return {"jobId": job_id, "status": "QUEUED"}

    def _handle_installation(
        handler: BaseHTTPRequestHandler,
        method: str,
        parts: list[str],
        body: dict[str, Any] | list[Any] | None,
    ) -> bool:
        """Handle /api/v2/apps/{uuid}/installation/... Returns True if handled."""
        # parts: ["api", "v2", "apps", "{uuid}", "installation", ...]
        if len(parts) < 5 or parts[0:3] != ["api", "v2", "apps"] or parts[4] != "installation":
            return False
        rest = parts[5:]
        current = _load_dev_store(root)

        if not rest:
            _json_response(
                handler,
                200,
                {
                    "state": current.get("state") or {},
                    "secrets": sorted((current.get("secrets") or {}).keys()),
                    "connections": current.get("connections") or {},
                },
            )
            return True

        resource = rest[0]

        if resource == "state":
            state = current.setdefault("state", {})
            if not isinstance(state, dict):
                state = {}
                current["state"] = state
            if len(rest) == 1:
                if method == "GET":
                    _json_response(handler, 200, {"message": "Success", "data": state})
                    return True
                if method == "PUT" and isinstance(body, dict):
                    state.update(body)
                    _save_dev_store(root, current)
                    _json_response(handler, 200, {"message": "Success", "data": state})
                    return True
            if len(rest) == 2:
                key = rest[1]
                if method == "GET":
                    _json_response(
                        handler,
                        200,
                        {"message": "Success", "data": {key: state.get(key)}},
                    )
                    return True
                if method == "PUT" and isinstance(body, dict):
                    value = body.get("value", body)
                    state[key] = value
                    _save_dev_store(root, current)
                    _json_response(
                        handler,
                        200,
                        {"message": "Success", "data": {key: state.get(key)}},
                    )
                    return True
                if method == "DELETE":
                    state.pop(key, None)
                    _save_dev_store(root, current)
                    _json_response(handler, 200, {"message": "Success", "data": True})
                    return True

        if resource == "secrets":
            secrets = current.setdefault("secrets", {})
            if not isinstance(secrets, dict):
                secrets = {}
                current["secrets"] = secrets
            if len(rest) == 1 and method == "GET":
                _json_response(
                    handler,
                    200,
                    {"message": "Success", "data": sorted(secrets.keys())},
                )
                return True
            if len(rest) == 2:
                name = rest[1]
                if method == "PUT" and isinstance(body, dict):
                    secrets[name] = body.get("value", "")
                    _save_dev_store(root, current)
                    _json_response(handler, 200, {"message": "Success", "data": {"name": name}})
                    return True
                if method == "DELETE":
                    secrets.pop(name, None)
                    _save_dev_store(root, current)
                    _json_response(handler, 200, {"message": "Success", "data": True})
                    return True

        if resource == "connections":
            connections = current.setdefault("connections", {})
            if not isinstance(connections, dict):
                connections = {}
                current["connections"] = connections
            if len(rest) == 1 and method == "GET":
                _json_response(handler, 200, {"message": "Success", "data": connections})
                return True
            if len(rest) == 2 and method == "DELETE":
                connections.pop(rest[1], None)
                _save_dev_store(root, current)
                _json_response(handler, 200, {"message": "Success", "data": True})
                return True

        if resource == "jobs":
            jobs = current.setdefault("jobs", {})
            if not isinstance(jobs, dict):
                jobs = {}
                current["jobs"] = jobs
            if len(rest) == 1 and method == "POST" and isinstance(body, dict):
                fn_name = str(body.get("functionName") or "").strip()
                if fn_name not in name_set:
                    _json_response(handler, 404, {"error": f"function not found: {fn_name}"})
                    return True
                payload = body.get("payload") if isinstance(body.get("payload"), dict) else {}
                delay = float(body.get("delaySeconds") or 0)
                result = _enqueue_job(fn_name, payload, delay_seconds=delay)
                _json_response(handler, 200, {"message": "Success", "data": result})
                return True
            if len(rest) == 2 and method == "GET":
                job = jobs.get(rest[1])
                if not job:
                    _json_response(handler, 404, {"error": "job not found"})
                    return True
                _json_response(handler, 200, {"message": "Success", "data": job})
                return True

        _json_response(handler, 404, {"error": "installation route not found"})
        return True

    def _handle_inbound(
        handler: BaseHTTPRequestHandler,
        parts: list[str],
        body: dict[str, Any] | list[Any] | None,
    ) -> bool:
        """Handle POST /inbound/{routeName} or public inbound path."""
        route_name: str | None = None
        if len(parts) == 2 and parts[0] == "inbound":
            route_name = parts[1]
        elif (
            len(parts) >= 6
            and parts[0:3] == ["api", "v2", "public", "apps"]
            and parts[4] == "inbound"
        ):
            route_name = parts[5]
        if not route_name:
            return False

        route = next(
            (
                item
                for item in inbound_routes
                if str(item.get("name") or "") == route_name
            ),
            None,
        )
        if route is None:
            _json_response(handler, 404, {"error": f"inbound route not found: {route_name}"})
            return True

        auth_mode = str(route.get("authMode") or "NONE").upper()
        if auth_mode == "SHARED_SECRET":
            expected = str(route.get("sharedSecret") or "")
            provided = (
                handler.headers.get("X-Caraer-Inbound-Secret")
                or handler.headers.get("Authorization")
                or ""
            )
            if provided.startswith("Bearer "):
                provided = provided[len("Bearer ") :]
            if expected and provided != expected:
                _json_response(handler, 401, {"error": "invalid inbound secret"})
                return True

        fn_name = _function_ref_name(route.get("serverlessFunction"))
        if not fn_name or fn_name not in name_set:
            _json_response(
                handler,
                400,
                {"error": f"inbound route '{route_name}' has no local function"},
            )
            return True

        payload = body if isinstance(body, dict) else {"body": body}
        if route.get("enqueue"):
            result = _enqueue_job(fn_name, payload)
            _json_response(handler, 200, {"message": "Success", "data": result})
            return True
        try:
            result = _run_function(fn_name, payload)
            _json_response(handler, 200, result)
        except Exception as exc:  # noqa: BLE001
            _json_response(handler, 500, {"error": str(exc)})
        return True

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            parsed = urlparse(self.path)
            parts = [unquote(part) for part in parsed.path.split("/") if part]
            if enable_installation_shim and _handle_installation(self, "GET", parts, None):
                return

            if not parts:
                _refresh_from_disk(announce=True)
                _json_response(
                    self,
                    200,
                    {
                        "functions": names,
                        "invoke": [
                            "POST /functions/<function_name>",
                            "POST /<function_name>",
                            "POST / with X-Caraer-Function header or body.functionName",
                        ],
                        "installation": (
                            f"/api/v2/apps/{app_uuid}/installation/..."
                            if enable_installation_shim
                            else None
                        ),
                        "inbound": "POST /inbound/<routeName>",
                        "hotReload": True,
                    },
                )
                return

            name = resolve_function_name(self.path, headers=self.headers)
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
                    "invoke": [
                        f"POST /functions/{name}",
                        f"POST /{name}",
                    ],
                },
            )

        def do_PUT(self):  # noqa: N802
            parsed = urlparse(self.path)
            parts = [unquote(part) for part in parsed.path.split("/") if part]
            body = _read_json_body(self)
            if body is None:
                _json_response(self, 400, {"error": "invalid json"})
                return
            if enable_installation_shim and _handle_installation(self, "PUT", parts, body):
                return
            _json_response(self, 404, {"error": "not found"})

        def do_DELETE(self):  # noqa: N802
            parsed = urlparse(self.path)
            parts = [unquote(part) for part in parsed.path.split("/") if part]
            if enable_installation_shim and _handle_installation(self, "DELETE", parts, None):
                return
            _json_response(self, 404, {"error": "not found"})

        def do_POST(self):  # noqa: N802
            parsed = urlparse(self.path)
            parts = [unquote(part) for part in parsed.path.split("/") if part]
            body = _read_json_body(self)
            if body is None:
                _json_response(self, 400, {"error": "invalid json"})
                return
            if not isinstance(body, dict):
                # inbound may accept non-objects; installation/functions need objects
                if not _handle_inbound(self, parts, body):
                    _json_response(self, 400, {"error": "json body must be an object"})
                return

            if enable_installation_shim and _handle_installation(self, "POST", parts, body):
                return
            if _handle_inbound(self, parts, body):
                return

            name = resolve_function_name(self.path, headers=self.headers, body=body)
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
            try:
                result = _run_function(name, body)
                _json_response(self, 200, result)
            except Exception as exc:  # noqa: BLE001
                _json_response(self, 500, {"error": str(exc)})

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return

    if invoke_schedule:
        schedule = next(
            (item for item in schedules if str(item.get("name") or "") == invoke_schedule),
            None,
        )
        if schedule is None:
            available_names = [str(s.get("name") or "") for s in schedules]
            raise ValueError(
                f"Unknown schedule '{invoke_schedule}'. "
                f"Available: {', '.join(n for n in available_names if n) or '(none)'}"
            )
        fn_name = _function_ref_name(schedule.get("serverlessFunction"))
        if not fn_name or fn_name not in name_set:
            raise ValueError(
                f"Schedule '{invoke_schedule}' references unknown function '{fn_name}'."
            )
        payload = schedule.get("payloadTemplate")
        if not isinstance(payload, dict):
            payload = {}
        result = _run_function(fn_name, payload)
        print(json.dumps({"schedule": invoke_schedule, "function": fn_name, "result": result}))
        return

    def _watch_loop() -> None:
        while True:
            time.sleep(1.0)
            try:
                _refresh_from_disk(announce=True)
            except Exception:  # noqa: BLE001
                continue

    threading.Thread(target=_watch_loop, daemon=True).start()
    print(
        f"Local dev server on {base_url} (hot reload enabled). "
        f"Functions: {', '.join(names)}",
        flush=True,
    )
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
    """Backward-compatible wrapper: serve one function at /functions/<name>."""
    serve_functions(
        root,
        config,
        host=host,
        port=port,
        function_names=[function_name],
    )
