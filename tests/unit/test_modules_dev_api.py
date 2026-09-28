"""The loopback endpoint that feeds the module preview its company data."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from caraer_cli.project.modules_dev_api import start_company_api

COMPANIES = [
    {
        "uuid": "u-1",
        "name": "gartenLux",
        "subdomain": "gartenlux",
        "digitalIdentity": {"lightPrimaryColor": "#112A40"},
        "websiteSettings": {"subdomain": "gartenlux"},
    },
    {
        "uuid": "u-2",
        "name": "Argo360",
        "subdomain": "argo",
        "digitalIdentity": {"lightPrimaryColor": "#22387d"},
        "websiteSettings": {"subdomain": "argo"},
    },
]


def _get(api, path: str, *, token: str | None = None):
    request = urllib.request.Request(f"{api.url}{path}")
    request.add_header("Authorization", f"Bearer {token or api.token}")
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read())


@pytest.fixture
def api():
    calls: list[int] = []

    def fetch():
        calls.append(1)
        return COMPANIES

    served = start_company_api(fetch)
    served.calls = calls  # type: ignore[attr-defined]
    yield served
    served.shutdown()


def test_the_list_carries_no_branding(api) -> None:
    """Opening the preview should not pull branding for 18 companies."""
    listed = _get(api, "/companies")

    assert [c["name"] for c in listed] == ["gartenLux", "Argo360"]
    assert all("digitalIdentity" not in c for c in listed)


def test_branding_comes_from_the_per_company_route(api) -> None:
    company = _get(api, "/companies/gartenlux")

    assert company["digitalIdentity"]["lightPrimaryColor"] == "#112A40"


def test_nothing_is_fetched_until_something_is_asked_for(api) -> None:
    assert api.calls == []

    _get(api, "/companies")
    _get(api, "/companies/argo")

    # Fetched once and reused, rather than per request.
    assert api.calls == [1]


def test_an_unknown_company_is_a_404(api) -> None:
    with pytest.raises(urllib.error.HTTPError) as caught:
        _get(api, "/companies/nope")

    assert caught.value.code == 404


def test_forms_are_listed_for_the_preview_company() -> None:
    def fetch_forms(company_uuid: str):
        assert company_uuid == "u-1"
        return [{"uuid": "form-1", "name": "job-alert", "label": "Job alert"}]

    served = start_company_api(lambda: COMPANIES, fetch_forms=fetch_forms)
    try:
        forms = _get(served, "/forms/gartenlux")
        assert forms == [{"uuid": "form-1", "name": "job-alert", "label": "Job alert"}]
    finally:
        served.shutdown()


def test_an_unknown_company_forms_list_is_a_404(api) -> None:
    with pytest.raises(urllib.error.HTTPError) as caught:
        _get(api, "/forms/nope")

    assert caught.value.code == 404


def test_the_token_is_required(api) -> None:
    """Loopback is reachable by anything else on the machine, including a
    page open in the browser."""
    with pytest.raises(urllib.error.HTTPError) as caught:
        _get(api, "/companies", token="wrong")

    assert caught.value.code == 401


def test_a_failing_fetch_serves_an_empty_list(api) -> None:
    """Signed out or offline should mean sample data, not a broken preview."""

    def explode():
        raise RuntimeError("no session")

    served = start_company_api(explode)
    try:
        assert _get(served, "/companies") == []
    finally:
        served.shutdown()
