"""CMS module catalog API.

The catalog is what the builder's module library reads and what a company's
website build resolves its dependencies from. Registering it is separate from
publishing the npm package: the package makes the code installable, the catalog
makes the modules discoverable and describes their fields to the builder.
"""

from __future__ import annotations

from typing import Any

from caraer_cli.api.client import CaraerApiClient


def publish_module_package(
    client: CaraerApiClient,
    app_uuid: str,
    payload: dict[str, Any],
    *,
    publish_to_all: bool = False,
) -> dict[str, Any]:
    """Upload a staged tarball. The API publishes it and registers the catalog."""
    path = f"/api/v2/apps/{app_uuid}/cms-modules/package"
    return client.request(
        "POST",
        f"{path}/publish-to-all" if publish_to_all else path,
        json_body=payload,
        timeout_seconds=180.0,
    )


def publish_module_catalog(
    client: CaraerApiClient,
    app_uuid: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Register this app's modules for a published package version.

    ``payload`` carries ``package``, ``version`` and the ``modules`` list built
    from each module's ``export const manifest``.
    """
    return client.request(
        "PUT",
        f"/api/v2/apps/{app_uuid}/cms-modules",
        json_body=payload,
    )


def list_module_catalog(client: CaraerApiClient, app_uuid: str) -> dict[str, Any]:
    """Read the modules currently registered for an app."""
    return client.request("GET", f"/api/v2/apps/{app_uuid}/cms-modules")


def website_build_status(
    client: CaraerApiClient, app_uuid: str, version: str, *, wait: bool,
) -> dict[str, Any]:
    """Read only the website build tied to the pushed module version."""
    import time

    deadline = time.monotonic() + (15 * 60 if wait else 0)
    last = {"appUuid": app_uuid, "packageVersion": version, "status": "pending"}
    while True:
        response = client.request(
            "GET", "/api/v2/webpages/v2/deployment-status",
            params={"appUuid": app_uuid, "packageVersion": version},
        )
        data = response.get("data") or {}
        for build in data.get("moduleBuilds") or []:
            if build.get("appUuid") == app_uuid and build.get("packageVersion") == version:
                last = build
                break
        if not wait or last["status"] in {"live", "failed", "cancelled", "blocked"}:
            return last
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return {**last, "status": "pending"}
        time.sleep(min(5, remaining))
