from __future__ import annotations

from typing import Any

from caraer_cli.api.client import CaraerApiClient
from caraer_cli.errors import ApiError


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


def create_private_app(client: CaraerApiClient, payload: dict[str, Any]) -> dict[str, Any]:
    return client.request("POST", "/api/v2/apps/private", json_body=payload)


def update_private_app(client: CaraerApiClient, app_uuid: str, payload: dict[str, Any]) -> dict[str, Any]:
    return client.request("PUT", f"/api/v2/apps/private/{app_uuid}", json_body=payload)


def fetch_app(
    client: CaraerApiClient,
    app_uuid: str,
    *,
    private: bool | None = None,
) -> dict[str, Any]:
    """Load a remote app DTO.

    Public creator view is ``GET /apps/public/{uuid}``. That 404s for private
    apps, so those (or an unknown visibility) fall back to ``GET /apps/{uuid}``.
    """
    if private is True:
        return get_app(client, app_uuid)
    if private is False:
        return get_public_app(client, app_uuid)
    try:
        return get_public_app(client, app_uuid)
    except ApiError as exc:
        if exc.status == 404:
            return get_app(client, app_uuid)
        raise


def is_private_remote(data: dict[str, Any] | None) -> bool:
    return bool(isinstance(data, dict) and data.get("privateApp"))


def submit_for_review(client: CaraerApiClient, app_uuid: str) -> dict[str, Any]:
    return client.request("POST", f"/api/v2/apps/public/{app_uuid}/submit")


def review_public_app(
    client: CaraerApiClient,
    app_uuid: str,
    *,
    publish_state: str | None = None,
    feedback: str | None = None,
    reviewer_notes: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {}
    if publish_state is not None:
        body["publishState"] = publish_state
    if feedback is not None:
        body["feedback"] = feedback
    if reviewer_notes is not None:
        body["reviewerNotes"] = reviewer_notes
    return client.request(
        "POST",
        f"/api/v2/apps/public/{app_uuid}/review",
        json_body=body,
    )


def review_queue(
    client: CaraerApiClient,
    *,
    states: str | None = None,
    page: int = 1,
    limit: int = 50,
) -> dict[str, Any]:
    params: dict[str, Any] = {"page": page, "limit": limit}
    if states:
        params["states"] = states
    return client.request("GET", "/api/v2/apps/public/review-queue", params=params)
