"""Install the portable catalog capture helpers into the generated Astro harness."""
from pathlib import Path
import json
from copy import deepcopy


def sign_company_assets(client, company: dict) -> dict:
    """Resolve only this company's stored branding files with the ordinary file API."""
    prefix = str(company["uuid"]) + "/files/"
    signed = {}

    def visit(value):
        if isinstance(value, dict):
            return {key: visit(child) for key, child in value.items()}
        if isinstance(value, list):
            return [visit(child) for child in value]
        if isinstance(value, str) and value.startswith(prefix):
            if value not in signed:
                response = client.request("GET", "/api/v2/files/", company_uuid=company["uuid"],
                    send_sandbox_header=False, params={"key": value, "download": False, "expireAfter": 3600})
                signed[value] = response.get("data")
                if not isinstance(signed[value], str):
                    raise ValueError("Could not resolve company branding file")
            return signed[value]
        return value

    return visit(deepcopy(company))


def write_catalog_helpers(harness: Path, module_names: list[str]) -> None:
    target = harness / "src" / "catalog"
    target.mkdir(parents=True, exist_ok=True)
    for source in Path(__file__).with_name("catalog_assets").glob("*.mjs"):
        (target / source.name).write_bytes(source.read_bytes())
    (harness / "src" / "pages" / "caraer" / "asset.ts").write_text('''import { publicAssetFollowingRedirects } from '../../catalog/public-assets.mjs';
export const GET = async ({ url }) => {
  try {
    const asset = await publicAssetFollowingRedirects(new URL(url.searchParams.get('src')));
    return new Response(new Uint8Array(asset.body), { status: asset.status, headers: asset.headers });
  } catch { return new Response('Font asset unavailable.', { status: 400 }); }
};
''', encoding="utf-8")
    route = harness / "src" / "pages" / "api" / "catalog-image.ts"
    route.write_text('''import { captureCatalog } from '../../catalog/capture.mjs';
const modules = new Set(''' + json.dumps(module_names) + ''');
export const POST = async ({ request, url, locals }) => {
  if (request.headers.get('origin') !== url.origin) return new Response('Invalid export origin.', { status: 403 });
  try {
    const body = await request.json();
    if (!modules.has(body.module)) return new Response('Unknown module.', { status: 400 });
    const api = process.env.CARAER_HARNESS_API;
    const companies = api ? await fetch(api + '/companies', {
      headers: { Authorization: `Bearer ${process.env.CARAER_HARNESS_TOKEN}` },
    }).then(response => response.ok ? response.json() : []) : [];
    const company = companies.find(item => item.subdomain === body.company);
    if (!company) return new Response('Select an accessible company before exporting.', { status: 400 });
    // Do not derive the browser destination from Host, Origin, or caller-supplied URLs.
    const target = new URL('/', process.env.CARAER_CATALOG_ORIGIN);
    target.search = new URLSearchParams({ module: body.module, company: company.subdomain, catalog: '1', embed: '1' }).toString();
    const result = await captureCatalog({ url: target.href, installBrowser: true });
    const name = `${body.module}-${company.subdomain}-desktop.webp`.replace(/[^a-zA-Z0-9_.-]/g, '-');
    return new Response(new Uint8Array(result.full), { headers: { 'Content-Type': 'image/webp',
      'Content-Disposition': `attachment; filename="${name}"`, 'Cache-Control': 'no-store' } });
  } catch (error) {
    // Avoid leaking browser navigation URLs or signed company asset URLs.
    console.error('Catalog export failed:', error.name);
    return new Response('Image export failed. Check images, company fonts, and Chromium setup, then try again.', { status: 502 });
  }
};
''', encoding="utf-8")
