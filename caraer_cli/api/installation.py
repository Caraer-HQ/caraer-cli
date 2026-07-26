"""API client for app installation state, secrets, jobs, and connections."""

from __future__ import annotations

from typing import Any

from caraer_cli.api.client import CaraerApiClient


def get_state(client: CaraerApiClient, app_uuid: str) -> dict[str, Any]:
    return client.request("GET", f"/api/v2/apps/{app_uuid}/installation/state")


def put_state(client: CaraerApiClient, app_uuid: str, payload: dict[str, Any]) -> dict[str, Any]:
    return client.request(
        "PUT",
        f"/api/v2/apps/{app_uuid}/installation/state",
        json_body=payload,
    )


def get_state_key(client: CaraerApiClient, app_uuid: str, key: str) -> dict[str, Any]:
    return client.request("GET", f"/api/v2/apps/{app_uuid}/installation/state/{key}")


def put_state_key(
    client: CaraerApiClient, app_uuid: str, key: str, value: Any
) -> dict[str, Any]:
    body = value if isinstance(value, dict) and set(value.keys()) == {"value"} else {"value": value}
    return client.request(
        "PUT",
        f"/api/v2/apps/{app_uuid}/installation/state/{key}",
        json_body=body,
    )


def delete_state_key(client: CaraerApiClient, app_uuid: str, key: str) -> dict[str, Any]:
    return client.request("DELETE", f"/api/v2/apps/{app_uuid}/installation/state/{key}")


def list_secrets(client: CaraerApiClient, app_uuid: str) -> dict[str, Any]:
    return client.request("GET", f"/api/v2/apps/{app_uuid}/installation/secrets")


def put_secret(
    client: CaraerApiClient, app_uuid: str, name: str, value: str
) -> dict[str, Any]:
    return client.request(
        "PUT",
        f"/api/v2/apps/{app_uuid}/installation/secrets/{name}",
        json_body={"value": value},
    )


def delete_secret(client: CaraerApiClient, app_uuid: str, name: str) -> dict[str, Any]:
    return client.request("DELETE", f"/api/v2/apps/{app_uuid}/installation/secrets/{name}")


def list_connections(client: CaraerApiClient, app_uuid: str) -> dict[str, Any]:
    return client.request("GET", f"/api/v2/apps/{app_uuid}/installation/connections")


def delete_connection(
    client: CaraerApiClient, app_uuid: str, provider: str
) -> dict[str, Any]:
    return client.request(
        "DELETE", f"/api/v2/apps/{app_uuid}/installation/connections/{provider}"
    )


def enqueue_job(
    client: CaraerApiClient,
    app_uuid: str,
    *,
    function_name: str,
    payload: dict[str, Any] | None = None,
    delay_seconds: float = 0,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "functionName": function_name,
        "payload": payload or {},
    }
    if delay_seconds:
        body["delaySeconds"] = delay_seconds
    return client.request(
        "POST",
        f"/api/v2/apps/{app_uuid}/installation/jobs",
        json_body=body,
    )


def get_job(client: CaraerApiClient, app_uuid: str, job_id: str) -> dict[str, Any]:
    return client.request("GET", f"/api/v2/apps/{app_uuid}/installation/jobs/{job_id}")
