from caraer_cli.formatters.output import print_app_detail


def test_print_app_detail_summary(capsys) -> None:
    print_app_detail(
        {
            "uuid": "ea418b35-b3ed-4cc0-886c-067434cffb99",
            "name": "affinda",
            "label": "Affinda",
            "description": "Parse CVs",
            "privateApp": False,
            "installed": True,
            "authMethod": "API_KEY",
            "details": {"category": "recruitment", "brandColor": "#E74363"},
            "appPublish": {"publishState": "CHANGES_REQUESTED"},
            "appBars": [{"label": "Test overview", "location": "RECORD_PREVIEW"}],
            "serverlessFunctions": [
                {"name": "options", "runtime": "nodejs22", "code": "exports.handler = () => {}"}
            ],
        }
    )
    out = capsys.readouterr().out
    assert "Affinda" in out
    assert "Overview" in out
    assert "Resources" in out
    assert "nodejs22" in out
    assert "exports.handler" not in out
