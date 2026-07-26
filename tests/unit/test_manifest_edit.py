from __future__ import annotations

from pathlib import Path

from caraer_cli.commands.apps import build_public_app_placeholder
from caraer_cli.local_app import load_local_app
from caraer_cli.project.manifest_edit import append_manifest_list_item
from caraer_cli.project.pricing_sync import pricing_identity
from caraer_cli.project.scaffold import scaffold_app_project
from caraer_cli.project.schema import load_workspace


def test_append_pricing_plan_to_yaml(tmp_path: Path) -> None:
    root = tmp_path / "demo"
    scaffold_app_project(
        root,
        app_payload=build_public_app_placeholder(label="Demo", name="demo"),
        sample_function=None,
        force=True,
    )
    config = load_workspace(root)
    path = append_manifest_list_item(
        root,
        config,
        list_key="pricingPlans",
        item={
            "title": "Free plan",
            "pricingType": "FLAT",
            "pricePerUnit": 0,
            "unit": "installations",
        },
        identity=pricing_identity,
    )
    data = load_local_app(path)
    assert len(data["pricingPlans"]) == 1
    assert data["pricingPlans"][0]["title"] == "Free plan"
