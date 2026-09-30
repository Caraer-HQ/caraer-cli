from caraer_cli.project.function_files import discover_layout_v21_functions, lifecycle_items_from_files
from caraer_cli.project.schema import load_workspace
from caraer_cli.project.webhook_label import label_for_topic

from tests.unit.test_layout_v21 import EXAMPLE


def test_label_for_topic_skips_placeholders() -> None:
    assert label_for_topic("app.installed") == "App installed"
    assert label_for_topic("app.rotated") == "Credentials rotated"
    assert label_for_topic("record.<setting:target_object>.created") == "Record created"
    assert (
        label_for_topic(
            "record.<setting:due_date.objectName>.date_due.<setting:due_date.propertyName>"
        )
        == "Due date"
    )
    assert label_for_topic("record.candidate.created") == "Candidate created"
    assert label_for_topic("") is None


def test_example_lifecycle_hooks_have_labels() -> None:
    config = load_workspace(EXAMPLE)
    hooks = lifecycle_items_from_files(discover_layout_v21_functions(EXAMPLE, config))
    assert hooks["installWebhook"]["label"] == "App installed"
    assert hooks["uninstallWebhook"]["label"] == "App uninstalled"
    assert hooks["updateWebhook"]["label"] == "App updated"
    assert hooks["rotateWebhook"]["label"] == "Credentials rotated"
