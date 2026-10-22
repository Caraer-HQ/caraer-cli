from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from caraer_cli.api import webhooks as webhook_api
from caraer_cli.project.push_plan import _plan_webhooks
from caraer_cli.project.schema import ProjectConfig
from caraer_cli.project.state import save_state
from caraer_cli.project.validate_app import _validate_webhooks
from caraer_cli.project.webhooks_sync import (
    discover_local_webhooks,
    pull_webhooks,
    push_webhooks,
)


@pytest.mark.parametrize('platform', ['2026.2', '2026.2.1'])
@pytest.mark.parametrize('mode', ['HTTP', 'SERVERLESS'])
@pytest.mark.parametrize('fields', ['firstname,email', '', None])
def test_selection_survives_pull_edit_push(tmp_path, monkeypatch, platform, mode, fields):
    config = ProjectConfig(name='demo', appUuid='app-1', platformVersion=platform)
    functions = tmp_path / 'src/app/functions'
    functions.mkdir(parents=True)
    if platform == '2026.2.1':
        (functions / 'handler.js').write_text('export const manifest = {};\nexport default async () => {};\n')
    else:
        folder = functions / 'handler'
        folder.mkdir()
        (folder / 'function.caraer.json').write_text(json.dumps({'name': 'handler', 'runtime': 'nodejs22'}))
        (folder / 'index.js').write_text('exports.handler = async () => {};\n')
    save_state(tmp_path, {'functions': {'handler': {'uuid': 'fn-1'}}})
    remote = {
        'uuid': 'hook-1', 'topic': 'record.candidate.created',
        'deliveryMode': mode, 'webhookFormat': 'MINIMAL', 'enabled': True,
    }
    if mode == 'HTTP':
        remote['url'] = 'https://example.com/hook'
    else:
        remote['serverlessFunction'] = {'uuid': 'fn-1', 'name': 'handler'}
    if fields is not None:
        remote['fields'] = fields
    monkeypatch.setattr(webhook_api, 'list_webhooks', lambda *a, **kw: {'data': [remote]})
    update = MagicMock(return_value={'data': {'uuid': 'hook-1'}})
    monkeypatch.setattr(webhook_api, 'update_webhook', update)

    pull_webhooks(MagicMock(), tmp_path, config)
    discovered = discover_local_webhooks(tmp_path, config)
    assert len(discovered) == 1
    path, local = discovered[0]
    assert local['webhookFormat'] == 'MINIMAL'
    assert local.get('fields') == fields
    assert ('fields' in local) is (fields is not None)
    push_webhooks(MagicMock(), tmp_path, config)
    payload = update.call_args.args[-1]
    assert payload['webhookFormat'] == 'MINIMAL'
    assert payload.get('fields') == fields
    assert ('fields' in payload) is (fields is not None)

    # A changed selection must appear in the preview, including explicit clear.
    changed = '' if fields else 'email'
    if platform == '2026.2.1' and mode == 'SERVERLESS':
        from caraer_cli.project.code_manifest import parse_code_manifest_file, write_code_manifest
        manifest = parse_code_manifest_file(path)
        manifest['webhooks'][0]['fields'] = changed
        write_code_manifest(path, manifest)
    elif path.suffix == '.json':
        local['fields'] = changed
        path.write_text(json.dumps(local))
    else:
        local['fields'] = changed
        path.write_text(yaml.safe_dump(local))
    plan = _plan_webhooks(MagicMock(), tmp_path, config, delete_missing=False)
    assert plan[0]['action'] == 'update'
    push_webhooks(MagicMock(), tmp_path, config)
    assert update.call_args.args[-1]['fields'] == changed


def test_create_sends_minimal_and_fields(tmp_path, monkeypatch):
    config = ProjectConfig(name='demo', appUuid='app-1')
    folder = tmp_path / 'src/app/webhooks'
    folder.mkdir(parents=True)
    (folder / 'candidate.yaml').write_text(yaml.safe_dump({
        'topic': 'record.candidate.created', 'deliveryMode': 'HTTP',
        'url': 'https://example.com/hook', 'webhookFormat': 'MINIMAL',
        'fields': 'firstname,email',
    }))
    monkeypatch.setattr(webhook_api, 'list_webhooks', lambda *a, **kw: {'data': []})
    create = MagicMock(return_value={'data': {'uuid': 'hook-1'}})
    monkeypatch.setattr(webhook_api, 'create_webhook', create)
    push_webhooks(MagicMock(), tmp_path, config)
    assert create.call_args.args[-1]['fields'] == 'firstname,email'
    assert create.call_args.args[-1]['webhookFormat'] == 'MINIMAL'


@pytest.mark.parametrize('format', ['MINIMAL', 'LEGACY', 'EXPANDED', 'USER_FRIENDLY', 'RAW'])
def test_bundled_schema_accepts_formats_and_string_fields(format):
    import jsonschema
    schema = json.loads((Path(__file__).parents[2] / 'schemas/webhook.caraer.schema.json').read_text())
    hook = {'topic': 'record.candidate.created', 'deliveryMode': 'HTTP',
            'webhookFormat': format, 'fields': 'firstname,email'}
    jsonschema.validate(hook, schema)
    hook['fields'] = ['email']
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(hook, schema)


def test_fields_array_is_rejected_without_optional_schema_validation(tmp_path):
    config = ProjectConfig(name='demo')
    folder = tmp_path / 'src/app/webhooks'
    folder.mkdir(parents=True)
    (folder / 'hook.yaml').write_text(yaml.safe_dump({
        'topic': 'record.candidate.created', 'deliveryMode': 'HTTP',
        'url': 'https://example.com', 'fields': ['email'],
    }))
    issues = []
    _validate_webhooks(tmp_path, config, issues)
    assert any(issue.severity == 'error' and issue.path.endswith(':fields') for issue in issues)
