from __future__ import annotations

from typing import Any

from caraer_cli.api.client import CaraerApiClient


def list_apps(
    client: CaraerApiClient,
    *,
    app_type: str,
    page: int,
    limit: int,
    query: str | None = None,
) -> dict[str, Any]:
    if app_type == "my":
        return client.request(
            "POST",
            "/api/v2/apps/my/index",
            json_body={
                "filters": [],
                "sort": [{"key": "name", "direction": "asc"}],
                "show": [],
                "limit": limit,
                "page": page,
                "query": query or "",
            },
        )
    return client.request(
        "POST",
        "/api/v2/apps/index",
        params={"type": app_type},
        json_body={
            "filters": [],
            "sort": [{"key": "name", "direction": "asc"}],
            "show": [],
            "limit": limit,
            "page": page,
            "query": query or "",
        },
    )


def get_app(client: CaraerApiClient, app_uuid: str) -> dict[str, Any]:
    return client.request("GET", f"/api/v2/apps/{app_uuid}")


def get_public_app(client: CaraerApiClient, app_uuid: str) -> dict[str, Any]:
    return client.request("GET", f"/api/v2/apps/public/{app_uuid}")


def create_public_app(client: CaraerApiClient, payload: dict[str, Any]) -> dict[str, Any]:
    return client.request("POST", "/api/v2/apps/public", json_body=payload)


def update_public_app(client: CaraerApiClient, app_uuid: str, payload: dict[str, Any]) -> dict[str, Any]:
    return client.request("PUT", f"/api/v2/apps/public/{app_uuid}", json_body=payload)


def migrate_app_to_v2(
    client: CaraerApiClient,
    app_uuid: str,
    *,
    runtime: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {}
    if runtime:
        body["runtime"] = runtime
    return client.request(
        "POST",
        f"/api/v2/apps/{app_uuid}/migrate-v2",
        json_body=body,
        timeout_seconds=max(client.context.timeout_seconds, 60.0),
    )


def submit_for_review(client: CaraerApiClient, app_uuid: str) -> dict[str, Any]:
    return client.request("POST", f"/api/v2/apps/public/{app_uuid}/submit")
