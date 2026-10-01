"""A complete, token-styled CMS starter with independently usable modules."""

from __future__ import annotations

import json
from pathlib import Path

from caraer_cli.project.modules_codegen import write_module_types
from caraer_cli.project.modules_scaffold import _pascal_case
from caraer_cli.project.modules_sync import discover_local_modules
from caraer_cli.project.paths import modules_dir
from caraer_cli.project.schema import ProjectConfig


def _text_field(name: str, label: str, value: str, *, multiline: bool = False) -> dict:
    return {"name": name, "label": label, "type": "MULTI_LINE" if multiline else "SINGLE_LINE",
            "required": True, "defaultValue": value}


FEATURES = [
    {"title": "Make it yours", "body": "Use your company's colours and typography through Caraer design tokens."},
    {"title": "Build with sections", "body": "Add this section to a page or compose modules into a complete page template."},
    {"title": "Reuse components", "body": "Share a card component across modules without publishing it as a builder block."},
]

WEBSITE_TEMPLATE_MODULES = (
    ("site_header", "Site header", "header"),
    ("hero", "Hero", "section"),
    ("features", "Feature grid", "section"),
    ("call_to_action", "Call to action", "section"),
    ("site_footer", "Site footer", "footer"),
    ("home", "Home", "page"),
)

CARD_SOURCE = """---
import CaraerRichText from '@caraer/cms-runtime/CaraerRichText.astro';

interface Props { title: string; body: string | null; }
const { title, body } = Astro.props;
---

<article class="feature-card">
  <slot name="title"><h3>{title}</h3></slot>
  <div><slot>{body && <CaraerRichText value={body} />}</slot></div>
</article>

<style>
  .feature-card {
    padding: var(--caraer-space-lg);
    border: 1px solid var(--caraer-color-gray-300);
    border-radius: var(--caraer-radius-lg);
    background: var(--caraer-color-background);
    color: var(--caraer-color-font);
  }
  h3 { margin-block: 0 var(--caraer-space-md); font-size: var(--caraer-size-h3); font-family: var(--caraer-font-h3); }
</style>
"""

COMMON_STYLE = """
  .starter-section { padding-block: var(--caraer-space-2xl); color: var(--caraer-color-font); }
  h1, h2 { margin-block: 0 var(--caraer-space-md); }
  h1 { font-family: var(--caraer-font-h1); font-size: var(--caraer-size-h1); line-height: var(--caraer-leading-h1); }
  h2 { font-family: var(--caraer-font-h2); font-size: var(--caraer-size-h2); line-height: var(--caraer-leading-h2); }
  .starter-button { display: inline-flex; margin-block-start: var(--caraer-space-lg); padding: var(--caraer-space-md) var(--caraer-space-lg); background: var(--caraer-color-primary); color: var(--caraer-color-white); border-radius: var(--caraer-radius-md); text-decoration: none; }
  .starter-button:focus-visible { outline: 2px solid currentColor; outline-offset: 4px; }
"""


def _module_source(name: str, label: str, kind: str, *, legacy: bool) -> str:
    fields = []
    imports = []
    code = ""
    category = "content"
    style = COMMON_STYLE
    if name == "site_header":
        category = "layout"
        fields = [_text_field("brand", "Brand name", "Your company"), _text_field("link_label", "Navigation label", "Explore"), _text_field("link_url", "Navigation link", "#features")]
        markup = '''<header class="starter-section"><div class="caraer-container starter-header">
  <CaraerLink href="/" class="brand"><span data-caraer-field="brand">{fields.brand}</span></CaraerLink>
  <nav aria-label="Main navigation"><span data-caraer-field="link_label"><CaraerLink href={fields.link_url}>{fields.link_label}</CaraerLink></span></nav>
</div></header>'''
        style += ''' .starter-header { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--caraer-space-md); } .brand { font-weight: 700; color: inherit; text-decoration: none; }'''
    elif name == "hero":
        category = "hero"
        fields = [
            _text_field("heading", "Heading", "A great place to start"),
            _text_field("body", "Introduction", "Create a website that feels like your company. Start with these sections and make them your own.", multiline=True),
            {
                "group": "Button",
                "fields": [
                    _text_field("button_label", "Button label", "Explore the possibilities"),
                    _text_field("button_url", "Button link", "#features"),
                ],
            },
        ]
        markup = '''<section class="starter-section starter-hero"><div class="caraer-container">
  <h1 data-caraer-field={fieldNames ? fieldNames.heading : 'heading'}>{fields.heading}</h1>
  <div data-caraer-field={fieldNames ? fieldNames.body : 'body'}>{fields.body && <CaraerRichText value={fields.body} />}</div>
  <span data-caraer-field={fieldNames ? fieldNames.button_label : 'button_label'}><CaraerLink href={fields.button_url} class="starter-button">{fields.button_label}</CaraerLink></span>
</div></section>'''
        style += " .starter-hero { background: var(--caraer-color-primary-100); }"
    elif name == "features":
        imports = ["import FeatureCard from '../_components/FeatureCard.astro';"]
        fields = [_text_field("heading", "Heading", "Everything you need to get started"), {"name": "items", "label": "Feature cards", "type": "REPEATABLE", "defaultValue": FEATURES, "itemFields": [_text_field("title", "Title", "Your feature"), _text_field("body", "Description", "Describe what makes this feature useful.", multiline=True)]}]
        markup = '''<section id="features" class="starter-section"><div class="caraer-container">
  <h2 data-caraer-field={fieldNames ? fieldNames.heading : 'heading'}>{fields.heading}</h2>
  <div class="starter-grid" data-caraer-field={fieldNames ? fieldNames.items : 'items'}>
    {fields.items.map((item, index) => <div data-caraer-item={index}><FeatureCard title={item.title} body={item.body} /></div>)}
  </div>
</div></section>'''
        style += " .starter-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 16rem), 1fr)); gap: var(--caraer-space-lg); }"
    elif name == "call_to_action":
        category = "cta"
        imports = ["import FeatureCard from '../_components/FeatureCard.astro';"]
        fields = [_text_field("heading", "Heading", "Ready to make it yours?"), _text_field("body", "Text", "Tell your story, introduce your team, and invite visitors to take the next step.", multiline=True), _text_field("button_label", "Button label", "Get in touch"), _text_field("button_url", "Button link", "mailto:hello@example.com")]
        markup = '''<section id="contact" class="starter-section"><div class="caraer-container">
  <FeatureCard title={fields.heading} body={fields.body}>
    <h2 slot="title" data-caraer-field={fieldNames ? fieldNames.heading : 'heading'}>{fields.heading}</h2>
    <div data-caraer-field={fieldNames ? fieldNames.body : 'body'}>{fields.body && <CaraerRichText value={fields.body} />}</div>
    <span data-caraer-field={fieldNames ? fieldNames.button_label : 'button_label'}><CaraerLink href={fields.button_url} class="starter-button">{fields.button_label}</CaraerLink></span>
  </FeatureCard>
</div></section>'''
    elif name == "site_footer":
        category = "layout"
        fields = [_text_field("brand", "Brand name", "Your company"), _text_field("body", "Footer text", "A place for your company story and contact information.", multiline=True)]
        markup = '''<footer class="starter-section"><div class="caraer-container">
  <strong data-caraer-field="brand">{fields.brand}</strong>
  <div data-caraer-field={fieldNames ? fieldNames.body : 'body'}>{fields.body && <CaraerRichText value={fields.body} />}</div>
</div></footer>'''
    else:
        category = "layout"
        def entry(module: str) -> str:
            return "index.astro" if legacy else f"{module}.astro"
        imports = [f"import Hero from '../hero/{entry('hero')}';", f"import Features from '../features/{entry('features')}';", f"import CallToAction from '../call_to_action/{entry('call_to_action')}';"]
        fields = [_text_field("heading", "Page heading", "A great place to start"), _text_field("body", "Introduction", "Create a website that feels like your company. Start with these sections and make them your own.", multiline=True), _text_field("features_heading", "Features heading", "Everything you need to get started"), _text_field("contact_heading", "Contact heading", "Ready to make it yours?"), _text_field("contact_body", "Contact text", "Tell your story, introduce your team, and invite visitors to take the next step.", multiline=True), _text_field("contact_label", "Contact button label", "Get in touch"), _text_field("contact_url", "Contact button link", "mailto:hello@example.com")]
        code = "\n// A page owns its editable fields and passes the platform context to its sections.\n"
        markup = '''<main>
  <Hero {...Astro.props} fieldNames={{ heading: 'heading', body: 'body' }} fields={{ heading: fields.heading, body: fields.body, button_label: 'Explore the possibilities', button_url: '#features' }} />
  <Features {...Astro.props} fieldNames={{ heading: 'features_heading' }} fields={{ heading: fields.features_heading, items: exampleFeatures }} />
  <CallToAction {...Astro.props} fieldNames={{ heading: 'contact_heading', body: 'contact_body', button_label: 'contact_label' }} fields={{ heading: fields.contact_heading, body: fields.contact_body, button_label: fields.contact_label, button_url: fields.contact_url }} />
</main>'''
        code += "const exampleFeatures = " + json.dumps(FEATURES, indent=2) + ";\n"
        style = ""
    manifest = {"name": name, "label": label, "kind": kind, "category": category, "description": f"Example {label.lower()} for your company website.", "fields": fields}
    source = "---\n" + "\n".join(imports) + "\nimport CaraerLink from '@caraer/cms-runtime/CaraerLink.astro';\nimport CaraerRichText from '@caraer/cms-runtime/CaraerRichText.astro';\nimport type { ModuleManifest, ModuleProps } from '@caraer/cms-runtime';\n"
    source += f"import type {{ {_pascal_case(name)}Fields }} from './types.d.ts';\n\nexport const manifest = " + json.dumps(manifest, indent=2) + " satisfies ModuleManifest;\n"
    source += f"\ntype Props = ModuleProps<{_pascal_case(name)}Fields> & {{ fieldNames?: Partial<Record<keyof {_pascal_case(name)}Fields, string>> }};\nconst {{ fields, fieldNames }} = Astro.props;\n" + code + "---\n\n" + markup + "\n"
    return source + ("\n<style>" + style + "\n</style>\n" if style else "")


STARTER_README = """# Your Caraer starter

Run `npm run dev` and select **Home** in the module preview for a complete example.
Run `npm run validate` before pushing. Nothing is published by the preview.

## Files to explore

- `src/app/modules/home/`: a page composed from Hero, Features, and CallToAction.
- `src/app/modules/site_header/` and `site_footer/`: standalone site chrome.
- `src/app/modules/hero/`, `features/`, `call_to_action/`: editable sections that
  also work individually in the CMS builder.
- `src/app/modules/_components/FeatureCard.astro`: a typed reusable component,
  used by both Features and CallToAction. It has slots, but no module manifest.
  Folders starting with `_` are shared source, excluded from the library picker.
- `src/app/functions/` and `lifecycle/`: serverless and lifecycle examples.

Choose Home as the page module and configure Site header / Site footer as the
site's chrome in the CMS. Home renders the main content; chrome is added by the
site layout. The sample feature cards on Home are fixed example data: edit them
in Home or use the separate Features section for an editable repeatable list.
Composed sections receive the page's platform context and a `fieldNames` map
so clicking their content focuses the corresponding page field. Edit Home's fields in its
sidebar; the independent sections expose their own field lists.

## Customize

Edit `export const manifest` to change a module's labels, defaults, and fields.
Hero demonstrates a `{ group: "Button", fields: [...] }` entry inside `fields`:
it groups the button label and link in an expandable CMS sidebar panel. Grouped
values still arrive as `fields.button_label` and `fields.button_url`.
Validation regenerates `types.d.ts`; do not edit those declarations manually.
Use `--caraer-*` tokens so modules follow each company's branding. Use the
runtime link and rich-text components for locale-aware links and formatted text.
Replace the example email address before publishing your site.

`caraer apps add module <name> --kind section` adds another builder block.
`caraer apps init --template default` keeps the small hello-world starter.
"""


def scaffold_website_modules(root: Path, config: ProjectConfig, *, force: bool) -> list[Path]:
    base = modules_dir(root, config.srcDir)
    component = base / "_components" / "FeatureCard.astro"
    entries = [(base / name / (f"{name}.astro" if config.is_layout_v21() else "index.astro"), name, label, kind) for name, label, kind in WEBSITE_TEMPLATE_MODULES]
    for path in [component, *(item[0] for item in entries)]:
        if path.exists() and not force:
            raise FileExistsError(f"Starter file already exists: {path}. Use --force to overwrite.")
    component.parent.mkdir(parents=True, exist_ok=True)
    component.write_text(CARD_SOURCE, encoding="utf-8")
    for path, name, label, kind in entries:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_module_source(name, label, kind, legacy=not config.is_layout_v21()), encoding="utf-8")
    names = {item[1] for item in entries}
    for module in discover_local_modules(root, config):
        if module.name in names:
            write_module_types(module)
    readme = root / "README.md"
    if not readme.exists():
        readme.write_text(STARTER_README, encoding="utf-8")
    return [item[0].parent for item in entries]
