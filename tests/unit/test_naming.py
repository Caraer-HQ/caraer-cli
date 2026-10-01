from __future__ import annotations

import pytest

from caraer_cli.project.naming import MODULE_NAME_RE, require_module_name


def test_module_name_allows_digits() -> None:
    assert MODULE_NAME_RE.match("hero_2")
    assert require_module_name("Hero 2") == "hero_2"
    assert require_module_name("hero-3") == "hero_3"


def test_module_name_rejects_leading_digit() -> None:
    with pytest.raises(ValueError, match="snake_case"):
        require_module_name("2hero")


def test_module_name_rejects_empty() -> None:
    with pytest.raises(ValueError, match="snake_case"):
        require_module_name("___")
