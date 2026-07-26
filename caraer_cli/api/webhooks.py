from __future__ import annotations

from typing import Any

from caraer_cli.api.client import CaraerApiClient


def list_webhooks(client: CaraerApiClient, app_uuid: str, page: int, limit: int) -> dict[str, Any]:
    return client.request(
        "POST",
        f"/api/v2/apps/{app_uuid}/webhooks/index",
        json_body={
            "filters": [],
            "sort": [{"key": "createdAt", "direction": "desc"}],
            "show": [],
            "limit": limit,
            "page": page,
            "query": "",
        },
    )


def get_formats(client: CaraerApiClient, app_uuid: str) -> dict[str, Any]:
    return client.request("GET", f"/api/v2/apps/{app_uuid}/webhooks/formats")


def get_events(client: CaraerApiClient, app_uuid: str) -> dict[str, Any]:
    return client.request("GET", f"/api/v2/apps/{app_uuid}/webhooks/events")


def get_webhook(client: CaraerApiClient, app_uuid: str, webhook_uuid: str) -> dict[str, Any]:
    return client.request("GET", f"/api/v2/apps/{app_uuid}/webhooks/{webhook_uuid}")


def create_webhook(client: CaraerApiClient, app_uuid: str, payload: dict[str, Any]) -> dict[str, Any]:
    return client.request("POST", f"/api/v2/apps/{app_uuid}/webhooks", json_body=payload)


def update_webhook(
    client: CaraerApiClient, app_uuid: str, webhook_uuid: str, payload: dict[str, Any]
) -> dict[str, Any]:
    return client.request(
        "PUT",
        f"/api/v2/apps/{app_uuid}/webhooks/{webhook_uuid}",
        json_body=payload,
    )


def delete_webhook(client: CaraerApiClient, app_uuid: str, webhook_uuid: str) -> dict[str, Any]:
    return client.request("DELETE", f"/api/v2/apps/{app_uuid}/webhooks/{webhook_uuid}")


def test_webhook(
    client: CaraerApiClient, app_uuid: str, webhook_uuid: str, record_uuid: str, event: str
) -> dict[str, Any]:
    return client.request(
        "POST",
        f"/api/v2/apps/{app_uuid}/webhooks/test/{webhook_uuid}/{record_uuid}/{event}",
    )
