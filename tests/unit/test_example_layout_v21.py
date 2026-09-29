from pathlib import Path

from caraer_cli.project.schema import load_workspace
from caraer_cli.project.validate_app import validate_local_app

EXAMPLE_ROOT = Path(__file__).resolve().parents[2] / "examples" / "layout-v21"


def test_layout_v21_example_validates() -> None:
    config = load_workspace(EXAMPLE_ROOT)
    assert config.platformVersion == "2026.2.1"
    report = validate_local_app(EXAMPLE_ROOT)
    errors = [issue for issue in report.issues if issue.severity == "error"]
    assert errors == [], errors
    assert report.ok
