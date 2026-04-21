#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0 OR MIT
# Copyright 2026 Nick Schuetz

import argparse
import json
import logging
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

LOG_FORMAT = '[%(levelname)s] %(name)s: %(message)s'
logger = logging.getLogger('o3de.release_notes')

__version__ = '0.1.0-beta'

SCHEMA_VERSION = 1

GIT_REF_PATTERN = re.compile(r'^[a-zA-Z0-9._/\-]+$')
REPO_SLUG_PATTERN = re.compile(r'^[a-zA-Z0-9_.\-]+/[a-zA-Z0-9_.\-]+$')
PR_NUMBER_PATTERN = re.compile(r'\(#(\d+)\)')

DEFAULT_REPOS = ['o3de/o3de']

SIG_CANONICAL_ORDER = [
    'sig/build',
    'sig/content',
    'sig/core',
    'sig/docs-community',
    'sig/graphics-audio',
    'sig/network',
    'sig/platform',
    'sig/release',
    'sig/security',
    'sig/simulation',
    'sig/testing',
    'sig/ui-ux',
]

SIG_DISPLAY_NAMES = {
    'sig/build': 'SIG-Build',
    'sig/content': 'SIG-Content',
    'sig/core': 'SIG-Core',
    'sig/docs-community': 'SIG-Docs-Community',
    'sig/graphics-audio': 'SIG-Graphics-Audio',
    'sig/network': 'SIG-Network',
    'sig/platform': 'SIG-Platform',
    'sig/release': 'SIG-Release',
    'sig/security': 'SIG-Security',
    'sig/simulation': 'SIG-Simulation',
    'sig/testing': 'SIG-Testing',
    'sig/ui-ux': 'SIG-UI-UX',
}

SIG_TITLE_KEYWORDS = {
    'sig/build': [
        'cmake', 'compiler', ' ci ', ' ci/', 'ci:', 'automated review', ' ar ',
        'workflow', 'installer', 'ninja', 'build error', 'build fix', 'compile',
        'linker', 'linking', 'monolithic', 'ccache', 'sccache', 'gradle',
        'clang', 'msvc', 'gcc', 'xcode', 'msbuild', 'vcpkg', 'conan',
        'github actions', 'gha ', 'pipeline', '3p ', 'third-party',
        'third party', '3rdparty', 'fetchpackage', 'fetchcontent',
    ],
    'sig/content': [
        'editor', 'asset processor', 'asset browser', 'assetprocessor',
        'prefab', 'scriptcanvas', 'script canvas', 'lua editor', 'lua script',
        'outliner', 'inspector', 'lyshine', 'ui canvas', 'viewport',
        'entity inspector', 'component inspector', 'project manager',
        'material editor', 'scene settings', 'fbx', 'gltf', 'glb',
        'asset bundl', 'asset editor', 'asset import',
        'emotionx', 'emotionfx', 'emfx', 'motion', 'animation graph',
    ],
    'sig/core': [
        'azcore', 'azframework', 'aztoolsframework', 'azstd', 'az::',
        'settings registry', 'settingsregistry', 'allocator', 'rtti',
        'behaviorcontext', 'behavior context', 'serializ', 'reflect',
        'component descriptor', 'az_component', 'az_class', 'az_type',
        'json', 'xml', 'streamer', 'io scheduler', 'module',
        'gem.json', 'engine.json', 'o3de cli', 'register',
        'std::move', 'std::array', 'std::span',
    ],
    'sig/graphics-audio': [
        'atom', ' rhi', 'vulkan', 'dx12', 'directx', 'metal',
        'shader', 'material', 'render', 'pass ', 'pass:', 'passes',
        'light', 'lighting', 'shadow', 'texture', 'mesh',
        'ray trac', 'raytrac', 'tlas', 'blas', 'acceleration structure',
        'bloom', 'ssao', 'ssr', 'hdr', 'tonemapp', 'exposure',
        'srg', 'drawsrg', 'materialsrg', 'azsl',
        'diffuse probe', 'global illumination', 'skybox', 'sky atmosphere',
        'skyatmosphere', 'fog', 'particle', 'openparticle',
        'terrain', 'stars', 'miniaudio', 'audio',
        'imgui', 'meshlet', 'lod', 'occlusion', 'culling',
        'unlit', 'emissive', 'irradiance', 'parallax',
    ],
    'sig/network': [
        'network', 'multiplayer', 'netbind', 'replica', 'replication',
    ],
    'sig/platform': [
        'android', ' ios', 'macos', 'mac ', 'linux', 'wayland', 'xcb',
        'emscripten', 'wasm', 'webassembly', 'windows platform',
        'platform tab', 'arm64', 'aarch64', 'x86_64',
        'objective-c', 'apple',
    ],
    'sig/simulation': [
        'physx', 'physics', 'rigid body', 'collider', 'articulation',
        'recast', 'navigation', 'navmesh', 'detour',
        'hinge', 'joint', 'ragdoll', 'character controller',
    ],
    'sig/security': [
        'security', 'bounds check', 'cve', 'owasp', 'vulnerability',
        'buffer overflow', 'out of bounds', 'oom dos', 'sanitiz',
    ],
    'sig/testing': [
        'googletest', 'gtest', 'gmock', 'benchmark', 'unit test',
        'test fix', 'test compilation', 'ctest', 'asan', 'tsan',
    ],
}

SIG_FILE_PATH_PATTERNS = {
    'sig/core': [
        'Code/Framework/AzCore/',
        'Code/Framework/AzFramework/',
        'Code/Framework/AzToolsFramework/',
    ],
    'sig/graphics-audio': [
        'Gems/Atom/',
        'Gems/AtomLyIntegration/',
        'Gems/DiffuseProbeGrid/',
        'Gems/Stars/',
        'Gems/SkyAtmosphere/',
        'Gems/OpenParticleSystem/',
    ],
    'sig/build': [
        'cmake/',
        'CMakeLists.txt',
        '.github/workflows/',
        'scripts/build/',
    ],
    'sig/content': [
        'Gems/ScriptCanvas/',
        'Gems/LyShine/',
        'Code/Editor/',
        'Gems/EditorPythonBindings/',
        'Gems/EMotionFX/',
    ],
    'sig/simulation': [
        'Gems/PhysX/',
        'Gems/RecastNavigation/',
    ],
    'sig/platform': [
        'Code/Framework/AzFramework/Platform/',
        'cmake/Platform/',
        'restricted/',
    ],
    'sig/network': [
        'Gems/Multiplayer/',
        'Code/Framework/AzNetworking/',
    ],
}

CHERRY_PICK_PATTERNS = [
    re.compile(r'cherry[\s-]*pick', re.IGNORECASE),
    re.compile(r'merge\s+stabilization', re.IGNORECASE),
    re.compile(r'merge\s+from\s+stabilization', re.IGNORECASE),
    re.compile(r'merge\s+changes\s+from\s+stabilization', re.IGNORECASE),
    re.compile(r'\[stabilization\]', re.IGNORECASE),
    re.compile(r'sync.*to.*development', re.IGNORECASE),
]


def validate_git_ref(ref: str) -> str:
    if not ref or len(ref) > 256:
        raise ValueError(f'Invalid git reference: length must be 1-256, got {len(ref) if ref else 0}')
    if not GIT_REF_PATTERN.match(ref):
        raise ValueError(f'Invalid git reference: {ref!r} contains disallowed characters')
    if ref.startswith('-'):
        raise ValueError(f'Invalid git reference: {ref!r} must not start with a hyphen')
    return ref


def validate_repo_slug(slug: str) -> str:
    if not slug or len(slug) > 128:
        raise ValueError(f'Invalid repo slug: length must be 1-128, got {len(slug) if slug else 0}')
    if not REPO_SLUG_PATTERN.match(slug):
        raise ValueError(f'Invalid repo slug: {slug!r} must be in owner/repo format')
    return slug


def validate_output_path(path: pathlib.Path, base_dir: pathlib.Path | None = None) -> pathlib.Path:
    resolved = path.resolve()
    if base_dir is not None:
        base_resolved = base_dir.resolve()
        if not str(resolved).startswith(str(base_resolved)):
            raise ValueError(f'Path traversal detected: {resolved} is outside {base_resolved}')
    if not resolved.parent.exists():
        raise ValueError(f'Parent directory does not exist: {resolved.parent}')
    return resolved


def extract_pr_numbers_from_git_log(
    repo_path: pathlib.Path,
    from_ref: str,
    to_ref: str,
) -> list[int]:
    from_ref = validate_git_ref(from_ref)
    to_ref = validate_git_ref(to_ref)

    result = subprocess.run(
        ['git', 'log', '--format=%s', f'{from_ref}..{to_ref}', '--no-merges'],
        cwd=str(repo_path.resolve()),
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        logger.error('git log failed: %s', result.stderr.strip())
        raise RuntimeError(f'git log failed with exit code {result.returncode}')

    pr_numbers = set()
    for line in result.stdout.splitlines():
        for match in PR_NUMBER_PATTERN.finditer(line):
            pr_numbers.add(int(match.group(1)))

    return sorted(pr_numbers)


def _build_graphql_query(owner: str, repo: str, pr_numbers: list[int]) -> str:
    owner = validate_repo_slug(f'{owner}/{repo}').split('/')[0]

    fragments = []
    for num in pr_numbers:
        fragments.append(
            f'  pr_{num}: pullRequest(number: {int(num)}) {{\n'
            f'    number\n'
            f'    title\n'
            f'    mergedAt\n'
            f'    url\n'
            f'    author {{ login }}\n'
            f'    labels(first: 20) {{ nodes {{ name }} }}\n'
            f'    files(first: 100) {{ nodes {{ path }} }}\n'
            f'  }}'
        )

    return (
        '{\n'
        f'  repository(owner: "{owner}", name: "{repo}") {{\n'
        + '\n'.join(fragments) +
        '\n  }\n'
        '}'
    )


def _run_gh_command(args: list[str], timeout: int = 30) -> dict:
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if 'rate limit' in stderr.lower() or '403' in stderr:
            logger.error('GitHub API rate limit exceeded. Try again later.')
        else:
            logger.error('gh command failed: %s', stderr)
        raise RuntimeError(f'gh command failed with exit code {result.returncode}')

    return json.loads(result.stdout)


def _check_gh_available() -> bool:
    if not shutil.which('gh'):
        logger.error('gh CLI is required but not found. Install from https://cli.github.com/')
        return False

    result = subprocess.run(
        ['gh', 'auth', 'status'],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        logger.error('gh CLI is not authenticated. Run: gh auth login')
        return False

    return True


def fetch_pr_metadata_batch(
    repo_slug: str,
    pr_numbers: list[int],
    batch_size: int = 30,
) -> list[dict]:
    repo_slug = validate_repo_slug(repo_slug)
    owner, repo = repo_slug.split('/')

    all_prs = []
    total = len(pr_numbers)

    for i in range(0, total, batch_size):
        batch = pr_numbers[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total + batch_size - 1) // batch_size
        logger.info('Fetching PRs batch %d/%d (%d PRs)', batch_num, total_batches, len(batch))

        query = _build_graphql_query(owner, repo, batch)
        try:
            data = _run_gh_command(
                ['gh', 'api', 'graphql', '-f', f'query={query}'],
                timeout=60,
            )
        except RuntimeError:
            logger.warning('Batch %d failed, trying individual PRs', batch_num)
            for num in batch:
                try:
                    single_query = _build_graphql_query(owner, repo, [num])
                    data = _run_gh_command(
                        ['gh', 'api', 'graphql', '-f', f'query={single_query}'],
                        timeout=30,
                    )
                    pr_data = data.get('data', {}).get('repository', {}).get(f'pr_{num}')
                    if pr_data:
                        all_prs.append(_normalize_pr_data(pr_data, repo_slug))
                except RuntimeError:
                    logger.warning('Failed to fetch PR #%d, skipping', num)
            continue

        if 'errors' in data:
            for err in data['errors']:
                logger.warning('GraphQL error: %s', err.get('message', 'unknown'))

        repo_data = data.get('data', {}).get('repository', {})
        for num in batch:
            pr_data = repo_data.get(f'pr_{num}')
            if pr_data:
                all_prs.append(_normalize_pr_data(pr_data, repo_slug))
            else:
                logger.warning('PR #%d not found in %s', num, repo_slug)

    return all_prs


def _normalize_pr_data(raw: dict, repo_slug: str) -> dict:
    return {
        'number': raw['number'],
        'repo': repo_slug,
        'title': raw.get('title', ''),
        'url': raw.get('url', ''),
        'author': raw.get('author', {}).get('login', 'unknown') if raw.get('author') else 'unknown',
        'merged_at': raw.get('mergedAt', ''),
        'labels': [n['name'] for n in raw.get('labels', {}).get('nodes', [])],
        'files': [n['path'] for n in raw.get('files', {}).get('nodes', [])],
    }


def _categorize_by_labels(labels: list[str]) -> str | None:
    sig_labels = [l for l in labels if l.startswith('sig/') and l in SIG_CANONICAL_ORDER]
    if not sig_labels:
        return None
    if 'sig/release' in sig_labels and len(sig_labels) > 1:
        sig_labels = [l for l in sig_labels if l != 'sig/release']
    return sig_labels[0]


def _categorize_by_title(title: str) -> str | None:
    title_lower = f' {title.lower()} '
    best_sig = None
    best_count = 0
    for sig, keywords in SIG_TITLE_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw.lower() in title_lower)
        if count > best_count:
            best_count = count
            best_sig = sig
    return best_sig


def _categorize_by_files(file_paths: list[str]) -> str | None:
    sig_counts: dict[str, int] = {}
    for fpath in file_paths:
        for sig, patterns in SIG_FILE_PATH_PATTERNS.items():
            for pattern in patterns:
                if fpath.startswith(pattern):
                    sig_counts[sig] = sig_counts.get(sig, 0) + 1
                    break
    if not sig_counts:
        return None
    return max(sig_counts, key=sig_counts.get)


def categorize_pr(pr_data: dict) -> tuple[str, str]:
    sig = _categorize_by_labels(pr_data.get('labels', []))
    if sig:
        return sig, 'label'

    sig = _categorize_by_title(pr_data.get('title', ''))
    if sig:
        return sig, 'heuristic_title'

    sig = _categorize_by_files(pr_data.get('files', []))
    if sig:
        return sig, 'heuristic_files'

    return 'uncategorized', 'uncategorized'


def detect_pr_flags(pr_data: dict) -> list[str]:
    flags = []
    title = pr_data.get('title', '')
    for pattern in CHERRY_PICK_PATTERNS:
        if pattern.search(title):
            flags.append('cherry-pick')
            break

    labels = pr_data.get('labels', [])
    if any('sync' in l for l in labels):
        flags.append('stabilization-sync')

    return flags


def _sanitize_pr_title_for_markdown(title: str) -> str:
    title = title.strip()
    title = re.sub(r'\(#\d+\)\s*$', '', title).strip()
    title = title.lstrip('#').strip()
    sanitized = []
    for ch in title:
        if ch in '[]|`':
            sanitized.append(f'\\{ch}')
        else:
            sanitized.append(ch)
    result = ''.join(sanitized)
    if result and not result.endswith('.'):
        result += '.'
    return result


def _format_pr_reference(repo_slug: str, pr_number: int) -> str:
    repo_name = repo_slug.split('/')[-1]
    return f'[{repo_name}#{pr_number}]'


def merge_with_existing(
    new_prs: list[dict],
    existing_json_path: pathlib.Path | None,
) -> list[dict]:
    if existing_json_path is None or not existing_json_path.exists():
        return new_prs

    existing_data = load_existing_json(existing_json_path)
    if existing_data is None:
        return new_prs

    existing_by_key = {}
    for pr in existing_data.get('pull_requests', []):
        key = (pr.get('repo', ''), pr.get('number', 0))
        existing_by_key[key] = pr

    merged = []
    for pr in new_prs:
        key = (pr.get('repo', ''), pr.get('number', 0))
        existing = existing_by_key.pop(key, None)
        if existing:
            if existing.get('manual_override_sig'):
                pr['sig_category'] = existing['manual_override_sig']
                pr['categorization_source'] = 'manual_override'
                pr['manual_override_sig'] = existing['manual_override_sig']
            if existing.get('manual_override_description'):
                pr['description'] = existing['manual_override_description']
                pr['manual_override_description'] = existing['manual_override_description']
        merged.append(pr)

    for pr in existing_by_key.values():
        if pr.get('manual_override_sig') or pr.get('manual_override_description'):
            merged.append(pr)

    merged.sort(key=lambda p: (p.get('repo', ''), p.get('number', 0)))
    return merged


def render_markdown(
    pr_list: list[dict],
    version: str,
    include_uncategorized: bool = False,
) -> str:
    by_sig: dict[str, list[dict]] = {}
    uncategorized = []

    for pr in pr_list:
        flags = pr.get('flags', [])
        if 'cherry-pick' in flags or 'stabilization-sync' in flags:
            continue

        sig = pr.get('sig_category', 'uncategorized')
        if sig == 'uncategorized':
            uncategorized.append(pr)
        else:
            by_sig.setdefault(sig, []).append(pr)

    lines = []
    lines.append(f'# {version} Release Notes')
    lines.append('')
    lines.append(f'The O3DE {version} release includes bug fixes, performance enhancements, '
                 f'and new features across the engine.')
    lines.append('')
    lines.append('<!-- TODO: Write a narrative summary of the release highlights -->')
    lines.append('')
    lines.append('# Full list of changes')
    lines.append('')

    for sig in SIG_CANONICAL_ORDER:
        prs = by_sig.get(sig, [])
        if not prs:
            continue

        display_name = SIG_DISPLAY_NAMES.get(sig, sig)
        lines.append(f'## {display_name}')

        prs.sort(key=lambda p: p.get('number', 0))
        for pr in prs:
            desc = pr.get('description', '') or _sanitize_pr_title_for_markdown(pr.get('title', ''))
            ref = _format_pr_reference(pr.get('repo', ''), pr.get('number', 0))
            lines.append(f'- {desc} {ref}')

        lines.append('')

    if include_uncategorized and uncategorized:
        lines.append('## Uncategorized')
        lines.append('')
        lines.append('<!-- These PRs could not be automatically categorized. '
                     'Please assign them to the correct SIG section. -->')
        uncategorized.sort(key=lambda p: p.get('number', 0))
        for pr in uncategorized:
            desc = _sanitize_pr_title_for_markdown(pr.get('title', ''))
            ref = _format_pr_reference(pr.get('repo', ''), pr.get('number', 0))
            lines.append(f'- {desc} {ref}')
        lines.append('')

    return '\n'.join(lines) + '\n'


def write_json_atomic(data: dict, path: pathlib.Path) -> None:
    path = path.resolve()
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent),
        prefix='.release_notes_',
        suffix='.json.tmp',
    )
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=False)
            f.write('\n')
        os.replace(tmp_path, str(path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def write_markdown_atomic(content: str, path: pathlib.Path) -> None:
    path = path.resolve()
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent),
        prefix='.release_notes_',
        suffix='.md.tmp',
    )
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(content)
        os.replace(tmp_path, str(path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def load_existing_json(path: pathlib.Path) -> dict | None:
    if not path.exists():
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict) or 'pull_requests' not in data:
            logger.warning('Existing JSON at %s has unexpected structure, ignoring', path)
            return None
        sv = data.get('metadata', {}).get('schema_version', 0)
        if sv != SCHEMA_VERSION:
            logger.warning('Schema version mismatch (got %d, expected %d), re-fetching', sv, SCHEMA_VERSION)
            return None
        return data
    except (json.JSONDecodeError, OSError) as e:
        logger.warning('Failed to load existing JSON at %s: %s', path, e)
        return None


def _run_fetch(args: argparse.Namespace) -> int:
    if not _check_gh_available():
        return 1

    repo_path = pathlib.Path(args.repo_path).resolve()
    if not (repo_path / '.git').exists():
        logger.error('Not a git repository: %s', repo_path)
        return 1

    output_json = validate_output_path(pathlib.Path(args.output_json))

    all_prs = []
    for repo_slug in args.repos:
        try:
            validate_repo_slug(repo_slug)
        except ValueError as e:
            logger.error('%s', e)
            return 1

        logger.info('Extracting PR numbers from git log for %s (%s..%s)',
                     repo_slug, args.from_ref, args.to_ref)
        try:
            pr_numbers = extract_pr_numbers_from_git_log(repo_path, args.from_ref, args.to_ref)
        except (RuntimeError, ValueError) as e:
            logger.error('%s', e)
            return 1

        logger.info('Found %d PRs in %s', len(pr_numbers), repo_slug)

        if not pr_numbers:
            continue

        logger.info('Fetching PR metadata from GitHub for %s', repo_slug)
        fetched = fetch_pr_metadata_batch(repo_slug, pr_numbers)

        for pr in fetched:
            sig, source = categorize_pr(pr)
            pr['sig_category'] = sig
            pr['categorization_source'] = source
            pr['description'] = _sanitize_pr_title_for_markdown(pr.get('title', ''))
            pr['flags'] = detect_pr_flags(pr)
            pr['manual_override_sig'] = None
            pr['manual_override_description'] = None

        all_prs.extend(fetched)

    existing_path = output_json if output_json.exists() else None
    merged = merge_with_existing(all_prs, existing_path)

    cat_counts: dict[str, int] = {}
    for pr in merged:
        src = pr.get('categorization_source', 'unknown')
        cat_counts[src] = cat_counts.get(src, 0) + 1

    output_data = {
        'metadata': {
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'from_ref': args.from_ref,
            'to_ref': args.to_ref,
            'repos': args.repos,
            'schema_version': SCHEMA_VERSION,
            'pr_count': len(merged),
            'categorization_summary': cat_counts,
        },
        'pull_requests': merged,
    }

    write_json_atomic(output_data, output_json)
    logger.info('Wrote %d PRs to %s', len(merged), output_json)
    logger.info('Categorization: %s', ', '.join(f'{k}={v}' for k, v in sorted(cat_counts.items())))

    return 0


def _run_render(args: argparse.Namespace) -> int:
    input_json = pathlib.Path(args.input_json).resolve()
    if not input_json.exists():
        logger.error('Input JSON not found: %s', input_json)
        return 1

    output_md = validate_output_path(pathlib.Path(args.output_md))

    data = load_existing_json(input_json)
    if data is None:
        logger.error('Failed to load valid JSON from %s', input_json)
        return 1

    content = render_markdown(
        data['pull_requests'],
        args.release_version,
        include_uncategorized=args.include_uncategorized,
    )

    write_markdown_atomic(content, output_md)
    logger.info('Wrote release notes to %s', output_md)

    return 0


def _run_generate(args: argparse.Namespace) -> int:
    rc = _run_fetch(args)
    if rc != 0:
        return rc
    args.input_json = args.output_json
    return _run_render(args)


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose logging',
    )


def add_parser_args(parser: argparse.ArgumentParser) -> None:
    subparsers = parser.add_subparsers(dest='subcommand', required=True)

    fetch_parser = subparsers.add_parser('fetch', help='Fetch PR data from GitHub into JSON')
    fetch_parser.add_argument('--from-ref', required=True, help='Starting git reference (tag or commit)')
    fetch_parser.add_argument('--to-ref', required=True, help='Ending git reference (branch or tag)')
    fetch_parser.add_argument('--repos', nargs='+', default=DEFAULT_REPOS,
                              help='GitHub repos in owner/repo format (default: o3de/o3de)')
    fetch_parser.add_argument('--repo-path', default='.', help='Path to local git clone (default: current directory)')
    fetch_parser.add_argument('--output-json', required=True, help='Output JSON file path')
    _add_common_args(fetch_parser)
    fetch_parser.set_defaults(func=_run_fetch)

    render_parser = subparsers.add_parser('render', help='Render markdown from JSON')
    render_parser.add_argument('--input-json', required=True, help='Input JSON file path')
    render_parser.add_argument('--output-md', required=True, help='Output markdown file path')
    render_parser.add_argument('--release-version', required=True, dest='release_version',
                               help='Release version string (e.g. 26.05.0)')
    render_parser.add_argument('--include-uncategorized', action='store_true',
                               help='Include uncategorized PRs in output')
    _add_common_args(render_parser)
    render_parser.set_defaults(func=_run_render)

    gen_parser = subparsers.add_parser('generate', help='Fetch and render in one step')
    gen_parser.add_argument('--from-ref', required=True, help='Starting git reference (tag or commit)')
    gen_parser.add_argument('--to-ref', required=True, help='Ending git reference (branch or tag)')
    gen_parser.add_argument('--repos', nargs='+', default=DEFAULT_REPOS,
                            help='GitHub repos in owner/repo format (default: o3de/o3de)')
    gen_parser.add_argument('--repo-path', default='.', help='Path to local git clone (default: current directory)')
    gen_parser.add_argument('--output-json', required=True, help='Output JSON file path')
    gen_parser.add_argument('--output-md', required=True, help='Output markdown file path')
    gen_parser.add_argument('--release-version', required=True, dest='release_version',
                            help='Release version string (e.g. 26.05.0)')
    gen_parser.add_argument('--include-uncategorized', action='store_true',
                            help='Include uncategorized PRs in output')
    _add_common_args(gen_parser)
    gen_parser.set_defaults(func=_run_generate)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog='release_notes',
        description='Generate O3DE release notes from merged pull requests',
    )
    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')
    add_parser_args(parser)
    args = parser.parse_args()

    logging.basicConfig(format=LOG_FORMAT)
    logger.setLevel(logging.DEBUG if args.verbose else logging.INFO)

    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
