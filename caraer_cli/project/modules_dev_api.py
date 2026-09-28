"""Serve the preview's company data from memory over loopback.

The module preview offers every company you can reach and restyles itself in
their branding. That comes from an authenticated endpoint, and the preview
holds no credentials, so the CLI fetches it and serves it here for as long as
the preview runs.

Deliberately not a file. This is real customer branding, and a few hundred
kilobytes of it has no business sitting in every app checkout after you stop
the dev server. It is also fetched lazily, so a preview you never point at a
company never asks for one.
"""

from __future__ import annotations

import json
import logging
import secrets
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import unquote, urlparse

log = logging.getLogger(__name__)

#: What the picker needs to render. Branding is fetched per company, so opening
#: the preview does not pull megabytes for companies you never look at.
LIST_FIELDS = ("uuid", "name", "subdomain")


@dataclass
class CompanyApi:
    """A running loopback server, and how to reach and stop it."""

    url: str
    token: str
    _server: ThreadingHTTPServer
    _thread: threading.Thread

    def shutdown(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)


def start_company_api(
    fetch: Callable[[], list[dict[str, Any]]],
    *,
    fetch_forms: Callable[[str], list[dict[str, Any]]] | None = None,
    fetch_form: Callable[[str, str], dict[str, Any] | None] | None = None,
    host: str = "127.0.0.1",
) -> CompanyApi:
    """Serve the company list and per-company branding on an ephemeral port.

    ``fetch`` is called at most once, on the first request that needs it, and
    its result is held in memory only. ``fetch_forms`` is keyed by company
    uuid so switching preview company lists that company's forms.
    ``fetch_form`` loads one form by uuid or name for ``CaraerForm``.
    """
    token = secrets.token_urlsafe(24)
    lock = threading.Lock()
    cache: dict[str, Any] = {}

    def companies() -> list[dict[str, Any]]:
        with lock:
            if "all" not in cache:
                try:
                    cache["all"] = fetch()
                except Exception as e:  # noqa: BLE001
                    log.debug("Could not list companies for the module preview: %s", e)
                    cache["all"] = []
            return cache["all"]

    def forms_for(company_uuid: str) -> list[dict[str, Any]]:
        if fetch_forms is None:
            return []
        with lock:
            key = f"forms:{company_uuid}"
            if key not in cache:
                try:
                    cache[key] = fetch_forms(company_uuid)
                except Exception as e:  # noqa: BLE001
                    log.debug("Could not list forms for the module preview: %s", e)
                    cache[key] = []
            return cache[key]

    def form_for(company_uuid: str, form_ref: str) -> dict[str, Any] | None:
        if fetch_form is None:
            return None
        with lock:
            key = f"form:{company_uuid}:{form_ref}"
            if key not in cache:
                try:
                    cache[key] = fetch_form(company_uuid, form_ref)
                except Exception as e:  # noqa: BLE001
                    log.debug("Could not load form '%s' for the module preview: %s", form_ref, e)
                    cache[key] = None
            return cache[key]

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:  # noqa: D102
            """Silent: the Astro server already logs the requests you care about."""

        def _send(self, status: int, payload: Any) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            # Loopback is not a permission boundary: anything else on this
            # machine, including a page open in your browser, can reach it.
            if self.headers.get("Authorization") != f"Bearer {token}":
                self._send(401, {"error": "unauthorized"})
                return

            path = urlparse(self.path).path.rstrip("/")

            if path == "/companies":
                self._send(
                    200,
                    [
                        {key: company.get(key) for key in LIST_FIELDS}
                        for company in companies()
                    ],
                )
                return

            if path.startswith("/companies/"):
                wanted = unquote(path[len("/companies/") :])
                for company in companies():
                    if company.get("subdomain") == wanted:
                        self._send(200, company)
                        return
                self._send(404, {"error": "unknown company"})
                return

            if path.startswith("/forms/"):
                rest = unquote(path[len("/forms/") :])
                company_key, _, form_ref = rest.partition("/")
                company_uuid = next(
                    (
                        company.get("uuid")
                        for company in companies()
                        if company.get("subdomain") == company_key
                        or company.get("uuid") == company_key
                    ),
                    None,
                )
                if not company_uuid:
                    self._send(404, {"error": "unknown company"})
                    return
                if not form_ref:
                    self._send(200, forms_for(str(company_uuid)))
                    return
                if fetch_form is None:
                    self._send(404, {"error": "form not found"})
                    return
                form = form_for(str(company_uuid), form_ref)
                if not form:
                    self._send(404, {"error": "form not found"})
                    return
                self._send(200, form)
                return

            self._send(404, {"error": "not found"})

    server = ThreadingHTTPServer((host, 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    port = server.server_address[1]
    return CompanyApi(url=f"http://{host}:{port}", token=token, _server=server, _thread=thread)
