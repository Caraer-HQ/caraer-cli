"""API client for app schedules, inbound routes, and external OAuth providers."""

from __future__ import annotations

from typing import Any

from caraer_cli.api.client import CaraerApiClient


def list_schedules(client: CaraerApiClient, app_uuid: str) -> dict[str, Any]:
    return client.request("GET", f"/api/v2/apps/{app_uuid}/schedules")


def create_schedule(client: CaraerApiClient, app_uuid: str, payload: dict[str, Any]) -> dict[str, Any]:
    return client.request("POST", f"/api/v2/apps/{app_uuid}/schedules", json_body=payload)


def update_schedule(
    client: CaraerApiClient, app_uuid: str, schedule_uuid: str, payload: dict[str, Any]
) -> dict[str, Any]:
    return client.request(
        "PUT", f"/api/v2/apps/{app_uuid}/schedules/{schedule_uuid}", json_body=payload
    )


def delete_schedule(client: CaraerApiClient, app_uuid: str, schedule_uuid: str) -> dict[str, Any]:
    return client.request("DELETE", f"/api/v2/apps/{app_uuid}/schedules/{schedule_uuid}")


def list_inbound_routes(client: CaraerApiClient, app_uuid: str) -> dict[str, Any]:
    return client.request("GET", f"/api/v2/apps/{app_uuid}/inbound-routes")


def create_inbound_route(client: CaraerApiClient, app_uuid: str, payload: dict[str, Any]) -> dict[str, Any]:
    return client.request(
        "POST", f"/api/v2/apps/{app_uuid}/inbound-routes", json_body=payload
    )


def update_inbound_route(
    client: CaraerApiClient, app_uuid: str, route_uuid: str, payload: dict[str, Any]
) -> dict[str, Any]:
    return client.request(
        "PUT", f"/api/v2/apps/{app_uuid}/inbound-routes/{route_uuid}", json_body=payload
    )


def delete_inbound_route(client: CaraerApiClient, app_uuid: str, route_uuid: str) -> dict[str, Any]:
    return client.request("DELETE", f"/api/v2/apps/{app_uuid}/inbound-routes/{route_uuid}")


def list_external_oauth_providers(client: CaraerApiClient, app_uuid: str) -> dict[str, Any]:
    return client.request("GET", f"/api/v2/apps/{app_uuid}/external-oauth-providers")


def create_external_oauth_provider(
    client: CaraerApiClient, app_uuid: str, payload: dict[str, Any]
) -> dict[str, Any]:
    return client.request(
        "POST", f"/api/v2/apps/{app_uuid}/external-oauth-providers", json_body=payload
    )


def update_external_oauth_provider(
    client: CaraerApiClient, app_uuid: str, provider_uuid: str, payload: dict[str, Any]
) -> dict[str, Any]:
    return client.request(
        "PUT",
        f"/api/v2/apps/{app_uuid}/external-oauth-providers/{provider_uuid}",
        json_body=payload,
    )


def delete_external_oauth_provider(
    client: CaraerApiClient, app_uuid: str, provider_uuid: str
) -> dict[str, Any]:
    return client.request("DELETE", f"/api/v2/apps/{app_uuid}/external-oauth-providers/{provider_uuid}")
