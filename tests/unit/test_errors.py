from caraer_cli.errors import ScopeError, ValidationError, parse_api_error


def test_parse_validation_error() -> None:
    error = parse_api_error(
        400,
        {
            "message": "Validation failed",
            "errors": [
                {
                    "field": "name",
                    "message": "Name is required",
                    "correctionSuggestion": "Please provide a valid value",
                }
            ],
        },
    )
    assert isinstance(error, ValidationError)
    assert "name: Name is required" in error.message


def test_parse_scope_error() -> None:
    error = parse_api_error(403, {"message": "Forbidden", "scopes": ["tools.apps.write"]})
    assert isinstance(error, ScopeError)
    assert "Missing scopes" in error.message
