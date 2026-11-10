from caraer_cli.project.modules_catalog import sign_company_assets


class Client:
    def __init__(self):
        self.calls = []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return {"data": "https://assets.example/signed-font.woff2"}


def test_branding_files_are_signed_for_the_chosen_company_without_mutating_cached_data():
    client = Client()
    company = {"uuid": "company-a", "websiteSettings": {
        "logo": "company-a/files/brand.webp",
        "customFonts": [{"familyName": "Brand", "variants": [{"url": "company-a/files/font.woff2"}, {"url": "company-a/files/font.woff2"}]}],
    }}
    resolved = sign_company_assets(client, company)
    assert len(client.calls) == 2
    assert all(call[2]["company_uuid"] == "company-a" for call in client.calls)
    assert all(call[2]["send_sandbox_header"] is False for call in client.calls)
    assert resolved["websiteSettings"]["customFonts"][0]["variants"][0]["url"].startswith("https://")
    assert company["websiteSettings"]["logo"] == "company-a/files/brand.webp"


def test_branding_does_not_sign_other_company_keys_or_unrelated_strings():
    client = Client()
    source = {"uuid": "company-a", "name": "Example company", "websiteSettings": {"logo": "company-b/files/private.webp", "customFonts": []}}
    assert sign_company_assets(client, source) == source
    assert client.calls == []
