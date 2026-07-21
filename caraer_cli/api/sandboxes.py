from __future__ import annotations

from typing import Any

from caraer_cli.api.client import CaraerApiClient

# Always operate against the owner company (never send X-Caraer-Sandbox-Uuid).
_OWNER_ONLY = {"send_sandbox_header": False}


def create_sandbox(client: CaraerApiClient, payload: dict[str, Any]) -> dict[str, Any]:
    return client.request(
        "POST",
        "/api/v2/developer-sandboxes",
        json_body=payload,
        **_OWNER_ONLY,
    )


def list_sandboxes(client: CaraerApiClient) -> dict[str, Any]:
    return client.request("GET", "/api/v2/developer-sandboxes", **_OWNER_ONLY)


def get_sandbox(client: CaraerApiClient, sandbox_uuid: str) -> dict[str, Any]:
    return client.request(
        "GET",
        f"/api/v2/developer-sandboxes/{sandbox_uuid}",
        **_OWNER_ONLY,
    )
