"""Install a pushed app on the selected company."""

from __future__ import annotations

from typing import Any

from caraer_cli.api import apps as apps_api
from caraer_cli.api.client import CaraerApiClient


def install_payload(
    *,
    settings: dict[str, Any] | None = None,
    scopes: list[str] | None = None,
) -> dict[str, Any]:
    """Build ``POST /apps/{uuid}/install`` body. Omit keys the caller did not set."""
    payload: dict[str, Any] = {}
    if settings is not None:
        payload["settings"] = [
            {"name": str(name), "value": value} for name, value in settings.items()
        ]
    if scopes is not None:
        payload["scopes"] = list(scopes)
    return payload


def install_app_on_company(
    client: CaraerApiClient,
    app_uuid: str,
    *,
    settings: dict[str, Any] | None = None,
    scopes: list[str] | None = None,
) -> dict[str, Any]:
    """Attach or update the app on the API client's selected company."""
    if not app_uuid:
        raise ValueError("App has no remote UUID. Run 'caraer apps push' first.")
    response = apps_api.install_app(
        client, app_uuid, install_payload(settings=settings, scopes=scopes)
    )
    data = response.get("data")
    return data if isinstance(data, dict) else {}
