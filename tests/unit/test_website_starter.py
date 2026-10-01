from pathlib import Path

import pytest

from caraer_cli.project.modules_publish import stage_package
from caraer_cli.project.modules_sync import discover_local_modules
from caraer_cli.project.scaffold import scaffold_app_project
from caraer_cli.project.validate_app import validate_local_app
from caraer_cli.project.website_scaffold import WEBSITE_TEMPLATE_MODULES, scaffold_website_modules
from caraer_cli.commands.apps import build_public_app_placeholder


@pytest.mark.parametrize('platform', ['2026.2', '2026.2.1'])
def test_full_starter_validates_and_packages_shared_component(tmp_path: Path, platform: str):
    root = tmp_path / 'starter'
    result = scaffold_app_project(
        root,
        app_payload=build_public_app_placeholder(label='Starter', name='starter'),
        platform_version=platform,
    )
    report = validate_local_app(root)
    assert report.ok, report.issues
    modules = discover_local_modules(root, result['config'])
    assert {module.name for module in modules} == {item[0] for item in WEBSITE_TEMPLATE_MODULES}
    assert {module.kind for module in modules} == {'header', 'section', 'footer', 'page'}
    assert all((module.directory / 'types.d.ts').is_file() for module in modules)
    features = next(module for module in modules if module.name == 'features')
    items = next(field for field in features.fields if field.get('name') == 'items')
    assert len(items['defaultValue']) == 3
    assert {field['name'] for field in items['itemFields']} == {'title', 'body'}
    package, _ = stage_package(root, result['config'], app_name='starter', version='1.0.0', destination=tmp_path / 'package')
    assert (package / 'modules' / '_components' / 'FeatureCard.astro').is_file()
    entry = 'index.astro' if platform == '2026.2' else 'home.astro'
    home = (root / 'src/app/modules/home' / entry).read_text()
    for name in ['hero', 'features', 'call_to_action']:
        entry = 'index.astro' if platform == '2026.2' else f'{name}.astro'
        assert f"../{name}/{entry}" in home
    assert '<main>' in home
    assert "fieldNames={{ heading: 'features_heading' }}" in home
    assert "button_label: 'contact_label'" in home
    assert 'README.md' in {path.name for path in root.iterdir()}


def test_starter_keeps_existing_readme_and_protects_shared_component(tmp_path: Path):
    root = tmp_path / 'starter'
    root.mkdir()
    readme = root / 'README.md'
    readme.write_text('Custom documentation')
    result = scaffold_app_project(root, app_payload=build_public_app_placeholder(label='Starter', name='starter'))
    assert readme.read_text() == 'Custom documentation'
    component = root / 'src/app/modules/_components/FeatureCard.astro'
    component.write_text('Custom component')
    with pytest.raises(FileExistsError):
        scaffold_website_modules(root, result['config'], force=False)
    assert component.read_text() == 'Custom component'
    scaffold_website_modules(root, result['config'], force=True)
    assert 'interface Props' in component.read_text()
    assert readme.read_text() == 'Custom documentation'
