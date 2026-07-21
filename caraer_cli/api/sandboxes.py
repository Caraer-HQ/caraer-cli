from __future__ import annotations

from typing import Any

from caraer_cli.api.client import CaraerApiClient


def create_sandbox(client: CaraerApiClient, payload: dict[str, Any]) -> dict[str, Any]:
    return client.request("POST", "/api/v2/developer-sandboxes", json_body=payload)


def list_sandboxes(client: CaraerApiClient) -> dict[str, Any]:
    return client.request("GET", "/api/v2/developer-sandboxes")


def get_sandbox(client: CaraerApiClient, sandbox_uuid: str) -> dict[str, Any]:
    return client.request("GET", f"/api/v2/developer-sandboxes/{sandbox_uuid}")
