from __future__ import annotations

from typing import Any

from caraer_cli.api.client import CaraerApiClient


def list_functions(client: CaraerApiClient, app_uuid: str, page: int, limit: int) -> dict[str, Any]:
    return client.request(
        "POST",
        f"/api/v2/apps/{app_uuid}/serverless-functions/index",
        json_body={
            "filters": [],
            "sort": [{"key": "createdAt", "direction": "desc"}],
            "show": [],
            "limit": limit,
            "page": page,
            "query": "",
        },
    )


def get_function(client: CaraerApiClient, app_uuid: str, function_uuid: str) -> dict[str, Any]:
    return client.request("GET", f"/api/v2/apps/{app_uuid}/serverless-functions/{function_uuid}")


def create_function(client: CaraerApiClient, app_uuid: str, payload: dict[str, Any]) -> dict[str, Any]:
    # GCP provisioning regularly exceeds short HTTP timeouts.
    return client.request(
        "POST",
        f"/api/v2/apps/{app_uuid}/serverless-functions",
        json_body=payload,
        timeout_seconds=max(client.context.timeout_seconds, 300.0),
    )


def update_function(
    client: CaraerApiClient, app_uuid: str, function_uuid: str, payload: dict[str, Any]
) -> dict[str, Any]:
    return client.request(
        "PUT",
        f"/api/v2/apps/{app_uuid}/serverless-functions/{function_uuid}",
        json_body=payload,
        timeout_seconds=max(client.context.timeout_seconds, 300.0),
    )


def delete_function(client: CaraerApiClient, app_uuid: str, function_uuid: str) -> dict[str, Any]:
    return client.request(
        "DELETE",
        f"/api/v2/apps/{app_uuid}/serverless-functions/{function_uuid}",
        timeout_seconds=max(client.context.timeout_seconds, 180.0),
    )


def test_function(
    client: CaraerApiClient,
    app_uuid: str,
    function_uuid: str,
    record_uuid: str,
    event_type: str,
    force_provision: bool = False,
) -> dict[str, Any]:
    return client.request(
        "POST",
        f"/api/v2/apps/{app_uuid}/serverless-functions/{function_uuid}/test",
        json_body={
            "recordUuid": record_uuid,
            "eventType": event_type,
            "forceProvision": force_provision,
        },
    )
