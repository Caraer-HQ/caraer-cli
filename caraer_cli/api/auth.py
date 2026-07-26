from __future__ import annotations

from typing import Any

from caraer_cli.api.client import CaraerApiClient


def login(client: CaraerApiClient, email: str, password: str) -> dict[str, Any]:
    return client.request(
        "POST",
        "/api/v2/auth/login",
        json_body={"email": email, "password": password},
        allow_unauthenticated=True,
    )


def device_start(client: CaraerApiClient) -> dict[str, Any]:
    return client.request(
        "POST",
        "/api/v2/auth/device/start",
        allow_unauthenticated=True,
    )


def device_poll(client: CaraerApiClient, device_code: str) -> dict[str, Any]:
    return client.request(
        "POST",
        "/api/v2/auth/device/poll",
        json_body={"deviceCode": device_code},
        allow_unauthenticated=True,
    )


def refresh(client: CaraerApiClient, refresh_token: str) -> dict[str, Any]:
    return client.request(
        "POST",
        "/api/v2/auth/refresh",
        json_body={"refreshToken": refresh_token},
        allow_unauthenticated=True,
    )


def me(client: CaraerApiClient) -> dict[str, Any]:
    # /auth/me is company-optional; a stale company header causes "Company not found".
    return client.request("GET", "/api/v2/auth/me", send_company_header=False)


def companies(client: CaraerApiClient) -> dict[str, Any]:
    return client.request("GET", "/api/v2/auth/companies", send_company_header=False)


def logout(client: CaraerApiClient) -> dict[str, Any]:
    return client.request("POST", "/api/v2/auth/logout", send_company_header=False)
