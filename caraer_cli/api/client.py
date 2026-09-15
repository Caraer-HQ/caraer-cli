from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import httpx

from caraer_cli.errors import ApiError, AuthError, parse_api_error

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
    profile_name: str | None = None
    refresh_token: str | None = None
    on_tokens_refreshed: Callable[[str, str | None], None] | None = None


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
        send_sandbox_header: bool = True,
        timeout_seconds: float | None = None,
        company_uuid: str | None = None,
        _retried: bool = False,
    ) -> dict[str, Any]:
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "X-Request-Id": _new_request_id(),
        }
        if self.context.token:
            headers["Authorization"] = f"Bearer {self.context.token}"
        header_company = company_uuid or (
            self.context.company_uuid if send_company_header else None
        )
        if header_company:
            headers["X-Caraer-Company-Uuid"] = header_company
        # Sandbox management APIs must hit the owner company, not the clone.
        if send_company_header and send_sandbox_header and self.context.sandbox_uuid:
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
            # Transparent refresh on 401 when we have a refresh token.
            if (
                response.status_code == 401
                and not _retried
                and not allow_unauthenticated
                and self.context.refresh_token
                and path != "/api/v2/auth/refresh"
            ):
                if self._try_refresh():
                    return self.request(
                        method,
                        path,
                        params=params,
                        json_body=json_body,
                        allow_unauthenticated=allow_unauthenticated,
                        send_company_header=send_company_header,
                        send_sandbox_header=send_sandbox_header,
                        timeout_seconds=timeout_seconds,
                        company_uuid=company_uuid,
                        _retried=True,
                    )
            error = parse_api_error(response.status_code, payload)
            request_id = (
                (payload or {}).get("requestId")
                if isinstance(payload, dict)
                else None
            ) or response.headers.get("X-Request-Id")
            if request_id and "Request ID:" not in error.message:
                error.message = f"{error.message}\nRequest ID: {request_id}"
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

    def _try_refresh(self) -> bool:
        refresh_token = self.context.refresh_token
        if not refresh_token:
            return False
        try:
            response = self.request(
                "POST",
                "/api/v2/auth/refresh",
                json_body={"refreshToken": refresh_token},
                allow_unauthenticated=True,
                _retried=True,
            )
        except (ApiError, AuthError):
            return False
        data = response.get("data") if isinstance(response.get("data"), dict) else response
        if not isinstance(data, dict):
            return False
        access = data.get("accessToken")
        token_obj = data.get("token")
        if not access and isinstance(token_obj, dict):
            access = token_obj.get("token")
        if not access:
            return False
        new_refresh = data.get("refreshToken") or refresh_token
        self.context.token = str(access)
        self.context.refresh_token = str(new_refresh) if new_refresh else None
        if self.context.on_tokens_refreshed:
            self.context.on_tokens_refreshed(
                str(access),
                str(new_refresh) if new_refresh else None,
            )
        return True


def _new_request_id() -> str:
    import uuid

    return str(uuid.uuid4())


def _safe_json(response: httpx.Response) -> dict[str, Any] | None:
    try:
        payload = response.json()
    except ValueError:
        return None
    if isinstance(payload, dict):
        return payload
    return {"data": payload}
