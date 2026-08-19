from __future__ import annotations

from typing import Any

from caraer_cli.api.client import CaraerApiClient


def get_app_billing_status(client: CaraerApiClient, app_uuid: str) -> dict[str, Any]:
    return client.request("GET", f"/api/v2/apps/{app_uuid}/billing/status")


def get_platform_billing_status(
    client: CaraerApiClient,
    *,
    app_uuid: str | None = None,
    page: int = 1,
    limit: int = 50,
) -> dict[str, Any]:
    params: dict[str, Any] = {"page": page, "limit": limit}
    if app_uuid:
        params["appUuid"] = app_uuid
    return client.request("GET", "/api/v2/billing/status", params=params)


def get_installation_billing_status(client: CaraerApiClient, app_uuid: str) -> dict[str, Any]:
    return client.request("GET", f"/api/v2/apps/{app_uuid}/installation/billing/status")


def get_usage_periods(client: CaraerApiClient, app_uuid: str) -> dict[str, Any]:
    return client.request("GET", f"/api/v2/apps/{app_uuid}/installation/usage/periods")


def record_meter_event(
    client: CaraerApiClient,
    app_uuid: str,
    *,
    line_item_name: str,
    quantity: int,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "lineItemName": line_item_name,
        "quantity": quantity,
    }
    if idempotency_key:
        body["idempotencyKey"] = idempotency_key
    return client.request(
        "POST",
        f"/api/v2/apps/{app_uuid}/installation/meter-events",
        json_body=body,
    )


def get_subscription(client: CaraerApiClient, app_uuid: str) -> dict[str, Any]:
    return client.request("GET", f"/api/v2/apps/{app_uuid}/installation/subscription")


def schedule_subscription_change(
    client: CaraerApiClient,
    app_uuid: str,
    *,
    plan_uuid: str,
    commitment: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"targetPlanUuid": plan_uuid}
    if commitment:
        body["targetCommitment"] = commitment
    return client.request(
        "POST",
        f"/api/v2/apps/{app_uuid}/installation/subscription/change",
        json_body=body,
    )


def cancel_pending_subscription(client: CaraerApiClient, app_uuid: str) -> dict[str, Any]:
    return client.request(
        "DELETE",
        f"/api/v2/apps/{app_uuid}/installation/subscription/pending",
    )
