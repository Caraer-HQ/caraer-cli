"""CMS module catalog API.

The catalog is what the builder's module library reads and what a company's
website build resolves its dependencies from. Registering it is separate from
publishing the npm package: the package makes the code installable, the catalog
makes the modules discoverable and describes their fields to the builder.
"""

from __future__ import annotations

from typing import Any

from caraer_cli.api.client import CaraerApiClient


def publish_module_catalog(
    client: CaraerApiClient,
    app_uuid: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Register this app's modules for a published package version.

    ``payload`` carries ``package``, ``version`` and the ``modules`` list built
    from each module's ``module.caraer.json``.
    """
    return client.request(
        "PUT",
        f"/api/v2/apps/{app_uuid}/cms-modules",
        json_body=payload,
    )


def list_module_catalog(client: CaraerApiClient, app_uuid: str) -> dict[str, Any]:
    """Read the modules currently registered for an app."""
    return client.request("GET", f"/api/v2/apps/{app_uuid}/cms-modules")
