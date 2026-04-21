#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0 OR MIT
# Copyright Contributors to the Open 3D Engine

"""
Generates a CycloneDX 1.5 SBOM (JSON) for the o3de_release_notes_generator project.

This project has zero external dependencies — only Python stdlib modules are used.
The SBOM captures:
  - The project as the top-level component
  - Python stdlib modules as framework dependencies
  - SHA-256 hashes of all source files for integrity verification
  - Tool and metadata information
"""

import hashlib
import json
import os
import pathlib
import platform
import sys
import tempfile
from datetime import datetime, timezone

PROJECT_NAME = 'o3de_release_notes_generator'
PROJECT_VERSION = '0.1.0-beta'
PROJECT_DESCRIPTION = 'Generates O3DE release notes from merged pull requests'
PROJECT_LICENSE_ID = 'Apache-2.0 OR MIT'
PROJECT_REPO = 'https://github.com/nickschuetz/o3de_release_notes_generator'

SOURCE_FILES = [
    'release_notes.py',
    'generate_sbom.py',
    'tests/test_release_notes.py',
]

STDLIB_MODULES_USED = [
    'argparse',
    'datetime',
    'hashlib',
    'json',
    'logging',
    'os',
    'pathlib',
    'platform',
    're',
    'shutil',
    'subprocess',
    'sys',
    'tempfile',
]


def sha256_file(filepath: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def generate_sbom(project_dir: pathlib.Path) -> dict:
    timestamp = datetime.now(timezone.utc).isoformat()

    file_components = []
    for relpath in SOURCE_FILES:
        filepath = project_dir / relpath
        if not filepath.exists():
            continue
        file_hash = sha256_file(filepath)
        file_components.append({
            'type': 'file',
            'name': relpath,
            'hashes': [{'alg': 'SHA-256', 'content': file_hash}],
        })

    stdlib_components = []
    for mod_name in STDLIB_MODULES_USED:
        stdlib_components.append({
            'type': 'library',
            'name': mod_name,
            'version': platform.python_version(),
            'scope': 'required',
            'purl': f'pkg:pypi/cpython-stdlib/{mod_name}@{platform.python_version()}',
            'description': f'Python stdlib module: {mod_name}',
            'properties': [
                {'name': 'cdx:source', 'value': 'python-stdlib'},
            ],
        })

    sbom = {
        '$schema': 'http://cyclonedx.org/schema/bom-1.5.schema.json',
        'bomFormat': 'CycloneDX',
        'specVersion': '1.5',
        'version': 1,
        'serialNumber': f'urn:uuid:{_generate_deterministic_uuid(timestamp)}',
        'metadata': {
            'timestamp': timestamp,
            'tools': {
                'components': [
                    {
                        'type': 'application',
                        'name': 'generate_sbom.py',
                        'version': '1.0.0',
                        'description': 'Built-in SBOM generator for o3de_release_notes_generator',
                    },
                ],
            },
            'component': {
                'type': 'application',
                'name': PROJECT_NAME,
                'version': PROJECT_VERSION,
                'description': PROJECT_DESCRIPTION,
                'licenses': [
                    {'expression': PROJECT_LICENSE_ID},
                ],
                'externalReferences': [
                    {
                        'type': 'vcs',
                        'url': PROJECT_REPO,
                    },
                ],
                'properties': [
                    {'name': 'cdx:python:minimumVersion', 'value': '3.10'},
                    {'name': 'cdx:externalDependencies', 'value': 'none'},
                ],
            },
            'lifecycles': [
                {'phase': 'build'},
            ],
        },
        'components': stdlib_components + file_components,
        'dependencies': [
            {
                'ref': PROJECT_NAME,
                'dependsOn': [mod for mod in STDLIB_MODULES_USED],
            },
        ],
    }

    return sbom


def _generate_deterministic_uuid(seed: str) -> str:
    h = hashlib.sha256(seed.encode()).hexdigest()
    return (
        f'{h[:8]}-{h[8:12]}-4{h[13:16]}-'
        f'{"89ab"[int(h[16], 16) % 4]}{h[17:20]}-{h[20:32]}'
    )


def write_sbom_atomic(sbom: dict, output_path: pathlib.Path) -> None:
    output_path = output_path.resolve()
    fd, tmp_path = tempfile.mkstemp(
        dir=str(output_path.parent),
        prefix='.sbom_',
        suffix='.json.tmp',
    )
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(sbom, f, indent=2, ensure_ascii=False)
            f.write('\n')
        os.replace(tmp_path, str(output_path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def main() -> int:
    project_dir = pathlib.Path(__file__).parent.resolve()
    output_path = project_dir / 'sbom.cdx.json'

    sbom = generate_sbom(project_dir)
    write_sbom_atomic(sbom, output_path)

    component_count = len(sbom['components'])
    print(f'SBOM generated: {output_path}')
    print(f'  Format: CycloneDX 1.5 (JSON)')
    print(f'  Components: {component_count} ({len(STDLIB_MODULES_USED)} stdlib, {component_count - len(STDLIB_MODULES_USED)} source files)')
    print(f'  External dependencies: 0')

    return 0


if __name__ == '__main__':
    sys.exit(main())
