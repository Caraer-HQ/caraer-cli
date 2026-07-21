from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from caraer_cli.errors import ApiError, parse_api_error

# Serverless create/update can wait on GCP provisioning.
DEFAULT_TIMEOUT_SECONDS = 120.0


@dataclass
class RequestContext:
    base_url: str
    token: str | None
    company_uuid: str | None
    sandbox_uuid: str | None = None
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    verify_ssl: bool = True
    debug: bool = False


class CaraerApiClient:
    def __init__(self, context: RequestContext) -> None:
        self.context = context

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        allow_unauthenticated: bool = False,
        send_company_header: bool = True,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.context.token:
            headers["Authorization"] = f"Bearer {self.context.token}"
        if send_company_header and self.context.company_uuid:
            headers["X-Caraer-Company-Uuid"] = self.context.company_uuid
        if send_company_header and self.context.sandbox_uuid:
            headers["X-Caraer-Sandbox-Uuid"] = self.context.sandbox_uuid

        if not allow_unauthenticated and "Authorization" not in headers:
            raise ApiError(message="Not logged in. Run 'caraer auth login'.", status=401, payload=None)

        url = self.context.base_url.rstrip("/") + path
        timeout = timeout_seconds if timeout_seconds is not None else self.context.timeout_seconds
        try:
            with httpx.Client(timeout=timeout, verify=self.context.verify_ssl) as client:
                response = client.request(
                    method.upper(), url, headers=headers, params=params, json=json_body
                )
        except httpx.TimeoutException as exc:
            raise ApiError(
                message=(
                    f"Request timed out after {timeout:.0f}s ({method.upper()} {path}). "
                    "Serverless function create/update can take a while. "
                    "Retry, or raise the limit with "
                    "'caraer profile set --timeout-seconds 300'."
                ),
                status=408,
                payload=None,
            ) from exc
        except httpx.TransportError as exc:
            raise ApiError(
                message=f"Network error talking to {self.context.base_url}: {exc}",
                status=503,
                payload=None,
            ) from exc

        if response.status_code >= 400:
            payload = _safe_json(response)
            error = parse_api_error(response.status_code, payload)
            if error.message == "Company not found" and self.context.company_uuid:
                error.message = (
                    f"Company not found ({self.context.company_uuid}). "
                    "Run 'caraer company clear', then 'caraer company list' and "
                    "'caraer company select <uuid>'."
                )
            if self.context.debug:
                error.message += f"\n[debug] response body: {response.text}"
            raise error

        payload = _safe_json(response)
        if payload is None:
            return {}
        if isinstance(payload, dict):
            return payload
        return {"data": payload}


def _safe_json(response: httpx.Response) -> dict[str, Any] | None:
    try:
        payload = response.json()
    except ValueError:
        return None
    if isinstance(payload, dict):
        return payload
    return {"data": payload}
