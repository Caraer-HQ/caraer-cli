"""Create release evidence after a successful deployment or publication."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.parse
import urllib.request


def emit(repository, sha, kind, version=None, dist=None, openapi=None, package=None):
    receipt = {'repository': repository, 'sha': sha, 'available': True,
        'releasedAt': datetime.now(timezone.utc).isoformat(), 'version': version,
        'producer': os.environ['GITHUB_REPOSITORY'], 'runId': int(os.environ['GITHUB_RUN_ID']),
        'fingerprints': {}, 'distHashes': []}
    if openapi:
        receipt['fingerprints']['openapi'] = hashlib.sha256(openapi.read_bytes()).hexdigest()
    if kind == 'pypi':
        files = sorted(p for p in dist.glob('*') if p.suffix in {'.whl', '.gz'}) if dist else []
        if not files:
            raise ValueError('Published distributions are required as provenance')
        receipt['distHashes'] = [hashlib.sha256(p.read_bytes()).hexdigest() for p in files]
    if kind == 'npm':
        request = urllib.request.Request(f"https://registry.npmjs.org/{urllib.parse.quote(package, safe='')}/{version}", headers={'User-Agent': 'caraer-developer-docs'})
        with urllib.request.urlopen(request, timeout=30) as response:
            published = json.load(response)
        if published.get('gitHead') != sha:
            raise ValueError('Published npm version does not identify this source SHA; provide provenance before announcing it')
        receipt['distHashes'] = [published['dist']['integrity']]
    if kind == 'schema':
        # Schema main is itself the published public contract. Bind the receipt
        # to the actual public branch, not merely a successful checkout/build.
        request = urllib.request.Request(f'https://api.github.com/repos/{repository}/commits/main', headers={'User-Agent': 'caraer-developer-docs'})
        with urllib.request.urlopen(request, timeout=30) as response:
            public = json.load(response)
        if public['sha'] != sha:
            raise ValueError('Schema receipt must identify current publicly available main')
        paths = subprocess.check_output(['git', 'ls-files', 'schemas'], text=True).splitlines()
        receipt['fingerprints']['schemas'] = hashlib.sha256(b''.join(p.encode() + b'\0' + Path(p).read_bytes() for p in sorted(paths))).hexdigest()
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', default=os.environ.get('GITHUB_REPOSITORY'), required=False)
    parser.add_argument('--sha', default=os.environ.get('GITHUB_SHA'))
    parser.add_argument('--kind', choices=['deployment','npm','pypi','schema'], required=True)
    parser.add_argument('--version')
    parser.add_argument('--package')
    parser.add_argument('--dist', type=Path)
    parser.add_argument('--openapi', type=Path)
    parser.add_argument('--output', type=Path, default=Path('developer-release.json'))
    args = parser.parse_args()
    result = emit(args.repository, args.sha, args.kind, args.version, args.dist, args.openapi, args.package)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f"Recorded {result['repository']} {result['sha']} after {args.kind}")
