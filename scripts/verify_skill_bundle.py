"""Check packaged skill bytes against their canonical distribution manifest."""
import argparse
import hashlib
import json
from pathlib import Path


def verify(root, target):
    directory = root / ('skills' if target == 'cli' else 'chatgpt-plugin/skills')
    provenance = root / ('skills/canonical-source.json' if target == 'cli' else 'chatgpt-plugin/canonical-skills.json')
    if not provenance.exists():
        return  # pre-bootstrap consumer; its existing skill tests still apply
    manifest = json.loads(provenance.read_text())
    if manifest['repository'] != 'Caraer-HQ/caraer-docs':
        raise ValueError('Unexpected canonical skill source')
    digest = hashlib.sha256()
    for name, expected in sorted(manifest['skills'].items()):
        if not name.startswith('caraer-') or '/' in name or '\\' in name:
            raise ValueError('Unsafe packaged skill name')
        skill = directory / name
        if skill.is_symlink() or hashlib.sha256((skill / 'SKILL.md').read_bytes()).hexdigest() != expected:
            raise ValueError(f'{name}: entrypoint differs from its canonical source')
        for path in sorted(skill.rglob('*')):
            if path.is_symlink():
                raise ValueError('Symlink in skill bundle')
            if path.is_file():
                digest.update(('skills/' + path.relative_to(directory).as_posix()).encode() + b'\0' + path.read_bytes())
    if digest.hexdigest() != manifest['bundleVersion']:
        raise ValueError('Packaged supporting files differ from their canonical bundle')
    if target == 'plugin':
        package = json.loads((root / 'chatgpt-plugin/.codex-plugin/plugin.json').read_text())
        connection = json.loads((root / 'chatgpt-plugin/.mcp.json').read_text())
        if package.get('mcpServers') != './.mcp.json' or not connection.get('mcpServers'):
            raise ValueError('Existing plugin MCP association is missing')
    print(f'Canonical {target} bundle verified ({len(manifest["skills"])} skills)')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('.'))
    parser.add_argument('--target', choices=['cli','plugin'], required=True)
    args = parser.parse_args()
    verify(args.root, args.target)
