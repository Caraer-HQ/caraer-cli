import json
from pathlib import Path

import pytest

from caraer_cli.commands import skill


def test_install_discovers_new_canonical_tasks_with_their_supporting_files(tmp_path, monkeypatch):
    source=tmp_path/'source'
    names=['caraer-apps','caraer-cms','caraer-record-imports']
    for name in names:
        folder=source/name
        folder.mkdir(parents=True)
        (folder/'SKILL.md').write_text(f'---\nname: {name}\ndescription: A canonical task\n---\n')
        (folder/'reference.md').write_text('Supporting task instructions')
    (source/'canonical-source.json').write_text(json.dumps({'skills':dict.fromkeys(names,'digest')}))
    monkeypatch.setattr(skill,'_repo_skill_dir',lambda name=skill.SKILL_ID: source/name)
    monkeypatch.setattr(skill,'_copy_packaged_skill',lambda *args:False)
    installed=skill.install_all_skills(target_root=tmp_path/'installed')
    assert {path.name for path in installed}==set(names)
    assert (tmp_path/'installed/caraer-record-imports/reference.md').read_text()=='Supporting task instructions'


def test_invalid_canonical_names_cannot_escape_the_install_directory(tmp_path,monkeypatch):
    source=tmp_path/'source'
    (source/'caraer-apps').mkdir(parents=True)
    (source/'canonical-source.json').write_text(json.dumps({'skills':{'caraer-apps/../../outside':'digest'}}))
    monkeypatch.setattr(skill,'_repo_skill_dir',lambda name=skill.SKILL_ID:source/name)
    with pytest.raises(ValueError,match='invalid skill names'):
        skill.install_all_skills(target_root=tmp_path/'installed')
    assert not (tmp_path/'installed').exists()
