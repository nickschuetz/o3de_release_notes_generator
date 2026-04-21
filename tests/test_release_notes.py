#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0 OR MIT
# Copyright 2026 Nick Schuetz

import json
import pathlib
import subprocess
import tempfile
from unittest import mock

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import release_notes


class TestValidateGitRef:
    def test_valid_tag(self):
        assert release_notes.validate_git_ref('2510.0') == '2510.0'

    def test_valid_branch(self):
        assert release_notes.validate_git_ref('development') == 'development'

    def test_valid_branch_with_slash(self):
        assert release_notes.validate_git_ref('stabilization/26050') == 'stabilization/26050'

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match='length must be'):
            release_notes.validate_git_ref('')

    def test_none_raises(self):
        with pytest.raises(ValueError):
            release_notes.validate_git_ref(None)

    def test_shell_injection_raises(self):
        with pytest.raises(ValueError, match='disallowed characters'):
            release_notes.validate_git_ref('; rm -rf /')

    def test_backtick_injection_raises(self):
        with pytest.raises(ValueError, match='disallowed characters'):
            release_notes.validate_git_ref('`whoami`')

    def test_flag_like_with_equals_raises(self):
        with pytest.raises(ValueError, match='disallowed characters'):
            release_notes.validate_git_ref('--exec=evil')

    def test_flag_like_raises(self):
        with pytest.raises(ValueError, match='must not start with a hyphen'):
            release_notes.validate_git_ref('--all')

    def test_too_long_raises(self):
        with pytest.raises(ValueError, match='length must be'):
            release_notes.validate_git_ref('a' * 257)

    def test_spaces_rejected(self):
        with pytest.raises(ValueError, match='disallowed characters'):
            release_notes.validate_git_ref('main branch')

    def test_dollar_sign_rejected(self):
        with pytest.raises(ValueError, match='disallowed characters'):
            release_notes.validate_git_ref('$HOME')


class TestValidateRepoSlug:
    def test_valid_slug(self):
        assert release_notes.validate_repo_slug('o3de/o3de') == 'o3de/o3de'

    def test_valid_slug_with_hyphens(self):
        assert release_notes.validate_repo_slug('nick-s/o3de-extras') == 'nick-s/o3de-extras'

    def test_missing_slash_raises(self):
        with pytest.raises(ValueError, match='owner/repo'):
            release_notes.validate_repo_slug('justarepo')

    def test_too_many_slashes_raises(self):
        with pytest.raises(ValueError, match='owner/repo'):
            release_notes.validate_repo_slug('a/b/c')

    def test_empty_raises(self):
        with pytest.raises(ValueError, match='length must be'):
            release_notes.validate_repo_slug('')

    def test_spaces_rejected(self):
        with pytest.raises(ValueError, match='owner/repo'):
            release_notes.validate_repo_slug('my org/my repo')


class TestValidateOutputPath:
    def test_valid_path(self, tmp_path):
        out = tmp_path / 'output.json'
        result = release_notes.validate_output_path(out)
        assert result == out.resolve()

    def test_traversal_detected(self, tmp_path):
        sneaky = tmp_path / '..' / '..' / 'etc' / 'passwd'
        with pytest.raises(ValueError, match='traversal'):
            release_notes.validate_output_path(sneaky, base_dir=tmp_path)

    def test_missing_parent_raises(self, tmp_path):
        bad = tmp_path / 'nonexistent' / 'dir' / 'file.json'
        with pytest.raises(ValueError, match='Parent directory'):
            release_notes.validate_output_path(bad)


class TestExtractPrNumbers:
    def test_extracts_numbers(self, tmp_path):
        git_output = (
            'Fix choppy mouse movement (#19709)\n'
            'Cherry pick fixes from stabilization (#19697)\n'
            'Remove system cmake dependency (#19704)\n'
            'Generic Asset Group (#19678)\n'
        )
        with mock.patch('release_notes.subprocess.run') as mock_run:
            mock_run.return_value = mock.Mock(
                returncode=0,
                stdout=git_output,
                stderr='',
            )
            result = release_notes.extract_pr_numbers_from_git_log(
                tmp_path, '2510.0', 'development'
            )
        assert result == [19678, 19697, 19704, 19709]

    def test_deduplicates(self, tmp_path):
        git_output = 'Same PR (#123)\nSame PR again (#123)\n'
        with mock.patch('release_notes.subprocess.run') as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout=git_output, stderr='')
            result = release_notes.extract_pr_numbers_from_git_log(tmp_path, 'a', 'b')
        assert result == [123]

    def test_no_prs_found(self, tmp_path):
        with mock.patch('release_notes.subprocess.run') as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout='no pr refs here\n', stderr='')
            result = release_notes.extract_pr_numbers_from_git_log(tmp_path, 'a', 'b')
        assert result == []

    def test_git_failure_raises(self, tmp_path):
        with mock.patch('release_notes.subprocess.run') as mock_run:
            mock_run.return_value = mock.Mock(returncode=128, stdout='', stderr='fatal: bad ref')
            with pytest.raises(RuntimeError, match='git log failed'):
                release_notes.extract_pr_numbers_from_git_log(tmp_path, 'bad', 'ref')


class TestCategorizeByLabels:
    def test_sig_label(self):
        assert release_notes._categorize_by_labels(['sig/build']) == 'sig/build'

    def test_multiple_sig_labels(self):
        result = release_notes._categorize_by_labels(['sig/core', 'sig/platform'])
        assert result in ('sig/core', 'sig/platform')

    def test_sig_release_deprioritized(self):
        result = release_notes._categorize_by_labels(['sig/release', 'sig/build'])
        assert result == 'sig/build'

    def test_only_sig_release(self):
        assert release_notes._categorize_by_labels(['sig/release']) == 'sig/release'

    def test_no_sig_labels(self):
        assert release_notes._categorize_by_labels(['bug', 'enhancement']) is None

    def test_empty_labels(self):
        assert release_notes._categorize_by_labels([]) is None


class TestCategorizeByTitle:
    @pytest.mark.parametrize('title,expected_sig', [
        ('Fix CMake warning in project build', 'sig/build'),
        ('Fix Vulkan crash on startup', 'sig/graphics-audio'),
        ('Update AzCore allocator', 'sig/core'),
        ('Fix prefab override in inspector', 'sig/content'),
        ('Add PhysX articulation offset', 'sig/simulation'),
        ('Initial Wayland support', 'sig/platform'),
        ('Security: Add bounds check on componentInputCount', 'sig/security'),
        ('Update GoogleTest to always build static', 'sig/testing'),
        ('Fix shader compilation error in Atom', 'sig/graphics-audio'),
        ('Asset Processor dependency fixes', 'sig/content'),
    ])
    def test_keyword_matching(self, title, expected_sig):
        result = release_notes._categorize_by_title(title)
        assert result == expected_sig, f'Expected {expected_sig} for {title!r}, got {result}'

    def test_no_match(self):
        assert release_notes._categorize_by_title('Miscellaneous cleanup') is None


class TestCategorizeByFiles:
    def test_azcore_files(self):
        files = ['Code/Framework/AzCore/AzCore/Module/Module.cpp']
        assert release_notes._categorize_by_files(files) == 'sig/core'

    def test_atom_files(self):
        files = ['Gems/Atom/RHI/Vulkan/Code/Source/RHI/Device.cpp']
        assert release_notes._categorize_by_files(files) == 'sig/graphics-audio'

    def test_cmake_files(self):
        files = ['cmake/Platform/Linux/CMakeLists.txt']
        assert release_notes._categorize_by_files(files) == 'sig/build'

    def test_mixed_files_majority_wins(self):
        files = [
            'Gems/Atom/RHI/Code/Source/A.cpp',
            'Gems/Atom/RHI/Code/Source/B.cpp',
            'Code/Framework/AzCore/AzCore/C.cpp',
        ]
        assert release_notes._categorize_by_files(files) == 'sig/graphics-audio'

    def test_no_match(self):
        files = ['some/random/path.txt']
        assert release_notes._categorize_by_files(files) is None

    def test_empty_files(self):
        assert release_notes._categorize_by_files([]) is None


class TestCategorizePriority:
    def test_label_takes_precedence(self):
        pr = {
            'labels': ['sig/core'],
            'title': 'Fix Vulkan crash',
            'files': ['Gems/Atom/RHI/Vulkan/Code/Source/Device.cpp'],
        }
        sig, source = release_notes.categorize_pr(pr)
        assert sig == 'sig/core'
        assert source == 'label'

    def test_title_over_files(self):
        pr = {
            'labels': [],
            'title': 'Fix CMake build error',
            'files': ['Code/Framework/AzCore/AzCore/Module.cpp'],
        }
        sig, source = release_notes.categorize_pr(pr)
        assert sig == 'sig/build'
        assert source == 'heuristic_title'

    def test_files_fallback(self):
        pr = {
            'labels': [],
            'title': 'Miscellaneous fix',
            'files': ['Gems/PhysX/Code/Source/RigidBody.cpp'],
        }
        sig, source = release_notes.categorize_pr(pr)
        assert sig == 'sig/simulation'
        assert source == 'heuristic_files'

    def test_uncategorized_fallback(self):
        pr = {
            'labels': [],
            'title': 'Miscellaneous cleanup',
            'files': ['random/path.txt'],
        }
        sig, source = release_notes.categorize_pr(pr)
        assert sig == 'uncategorized'
        assert source == 'uncategorized'


class TestDetectPrFlags:
    def test_cherry_pick(self):
        pr = {'title': 'Cherry pick fixes from stabilization/26050', 'labels': []}
        assert 'cherry-pick' in release_notes.detect_pr_flags(pr)

    def test_merge_stabilization(self):
        pr = {'title': 'Merge stabilization 26050 to dev', 'labels': []}
        assert 'cherry-pick' in release_notes.detect_pr_flags(pr)

    def test_sync_label(self):
        pr = {'title': 'Some fix', 'labels': ['sync/to-development']}
        assert 'stabilization-sync' in release_notes.detect_pr_flags(pr)

    def test_normal_pr(self):
        pr = {'title': 'Fix a bug in rendering', 'labels': []}
        assert release_notes.detect_pr_flags(pr) == []


class TestSanitizePrTitle:
    def test_removes_trailing_pr_ref(self):
        result = release_notes._sanitize_pr_title_for_markdown('Fix bug (#19709)')
        assert result == 'Fix bug.'

    def test_strips_leading_hash(self):
        result = release_notes._sanitize_pr_title_for_markdown('## Fix something')
        assert result == 'Fix something.'

    def test_escapes_brackets(self):
        result = release_notes._sanitize_pr_title_for_markdown('Fix [some] issue')
        assert '\\[' in result
        assert '\\]' in result

    def test_escapes_backticks(self):
        result = release_notes._sanitize_pr_title_for_markdown('Fix `code` issue')
        assert '\\`' in result

    def test_escapes_pipes(self):
        result = release_notes._sanitize_pr_title_for_markdown('Fix A | B issue')
        assert '\\|' in result

    def test_adds_period(self):
        result = release_notes._sanitize_pr_title_for_markdown('Fix something')
        assert result.endswith('.')

    def test_no_double_period(self):
        result = release_notes._sanitize_pr_title_for_markdown('Fix something.')
        assert not result.endswith('..')


class TestFormatPrReference:
    def test_main_repo(self):
        assert release_notes._format_pr_reference('o3de/o3de', 19709) == '[o3de#19709]'

    def test_extras_repo(self):
        assert release_notes._format_pr_reference('o3de/o3de-extras', 1045) == '[o3de-extras#1045]'

    def test_fork(self):
        assert release_notes._format_pr_reference('nickschuetz/o3de', 19709) == '[o3de#19709]'


class TestBuildGraphqlQuery:
    def test_single_pr(self):
        query = release_notes._build_graphql_query('o3de', 'o3de', [19709])
        assert 'pr_19709' in query
        assert 'pullRequest(number: 19709)' in query
        assert 'repository(owner: "o3de", name: "o3de")' in query

    def test_multiple_prs(self):
        query = release_notes._build_graphql_query('o3de', 'o3de', [100, 200, 300])
        assert 'pr_100' in query
        assert 'pr_200' in query
        assert 'pr_300' in query

    def test_includes_required_fields(self):
        query = release_notes._build_graphql_query('o3de', 'o3de', [1])
        for field in ['number', 'title', 'mergedAt', 'url', 'author', 'labels', 'files']:
            assert field in query


class TestRenderMarkdown:
    def _make_pr(self, number, sig, title='Fix something', repo='o3de/o3de', flags=None):
        return {
            'number': number,
            'repo': repo,
            'title': title,
            'sig_category': sig,
            'categorization_source': 'label',
            'description': release_notes._sanitize_pr_title_for_markdown(title),
            'flags': flags or [],
        }

    def test_basic_structure(self):
        prs = [self._make_pr(1, 'sig/build', 'Fix cmake')]
        result = release_notes.render_markdown(prs, '26.05.0')
        assert '# 26.05.0 Release Notes' in result
        assert '## SIG-Build' in result
        assert '[o3de#1]' in result

    def test_sig_ordering(self):
        prs = [
            self._make_pr(1, 'sig/simulation'),
            self._make_pr(2, 'sig/build'),
        ]
        result = release_notes.render_markdown(prs, '1.0')
        build_pos = result.index('SIG-Build')
        sim_pos = result.index('SIG-Simulation')
        assert build_pos < sim_pos

    def test_cherry_picks_filtered(self):
        prs = [
            self._make_pr(1, 'sig/build', 'Fix cmake'),
            self._make_pr(2, 'sig/build', 'Cherry pick fix', flags=['cherry-pick']),
        ]
        result = release_notes.render_markdown(prs, '1.0')
        assert '[o3de#1]' in result
        assert '[o3de#2]' not in result

    def test_uncategorized_hidden_by_default(self):
        prs = [self._make_pr(1, 'uncategorized')]
        result = release_notes.render_markdown(prs, '1.0')
        assert 'Uncategorized' not in result

    def test_uncategorized_shown_when_requested(self):
        prs = [self._make_pr(1, 'uncategorized')]
        result = release_notes.render_markdown(prs, '1.0', include_uncategorized=True)
        assert '## Uncategorized' in result

    def test_empty_sigs_omitted(self):
        prs = [self._make_pr(1, 'sig/build')]
        result = release_notes.render_markdown(prs, '1.0')
        assert 'SIG-Network' not in result


class TestMergeWithExisting:
    def test_no_existing(self):
        new = [{'number': 1, 'repo': 'o3de/o3de', 'sig_category': 'sig/build'}]
        result = release_notes.merge_with_existing(new, None)
        assert result == new

    def test_preserves_manual_override_sig(self, tmp_path):
        existing = {
            'metadata': {'schema_version': 1},
            'pull_requests': [{
                'number': 1,
                'repo': 'o3de/o3de',
                'sig_category': 'sig/core',
                'manual_override_sig': 'sig/core',
                'manual_override_description': None,
            }],
        }
        json_path = tmp_path / 'existing.json'
        json_path.write_text(json.dumps(existing))

        new = [{'number': 1, 'repo': 'o3de/o3de', 'sig_category': 'sig/build'}]
        result = release_notes.merge_with_existing(new, json_path)
        assert result[0]['sig_category'] == 'sig/core'
        assert result[0]['categorization_source'] == 'manual_override'

    def test_preserves_manual_override_description(self, tmp_path):
        existing = {
            'metadata': {'schema_version': 1},
            'pull_requests': [{
                'number': 1,
                'repo': 'o3de/o3de',
                'description': 'Custom description.',
                'manual_override_sig': None,
                'manual_override_description': 'Custom description.',
            }],
        }
        json_path = tmp_path / 'existing.json'
        json_path.write_text(json.dumps(existing))

        new = [{'number': 1, 'repo': 'o3de/o3de', 'description': 'Auto description.'}]
        result = release_notes.merge_with_existing(new, json_path)
        assert result[0]['description'] == 'Custom description.'

    def test_adds_new_prs(self, tmp_path):
        existing = {
            'metadata': {'schema_version': 1},
            'pull_requests': [{
                'number': 1, 'repo': 'o3de/o3de',
                'manual_override_sig': None, 'manual_override_description': None,
            }],
        }
        json_path = tmp_path / 'existing.json'
        json_path.write_text(json.dumps(existing))

        new = [
            {'number': 1, 'repo': 'o3de/o3de'},
            {'number': 2, 'repo': 'o3de/o3de'},
        ]
        result = release_notes.merge_with_existing(new, json_path)
        numbers = [p['number'] for p in result]
        assert 1 in numbers
        assert 2 in numbers


class TestAtomicWrite:
    def test_write_json(self, tmp_path):
        data = {'test': True}
        out = tmp_path / 'test.json'
        release_notes.write_json_atomic(data, out)
        assert out.exists()
        loaded = json.loads(out.read_text())
        assert loaded == {'test': True}

    def test_write_markdown(self, tmp_path):
        content = '# Test\nHello world\n'
        out = tmp_path / 'test.md'
        release_notes.write_markdown_atomic(content, out)
        assert out.exists()
        assert out.read_text() == content

    def test_overwrites_existing(self, tmp_path):
        out = tmp_path / 'test.json'
        out.write_text('{"old": true}')
        release_notes.write_json_atomic({'new': True}, out)
        loaded = json.loads(out.read_text())
        assert loaded == {'new': True}


class TestLoadExistingJson:
    def test_valid_file(self, tmp_path):
        data = {'metadata': {'schema_version': release_notes.SCHEMA_VERSION}, 'pull_requests': []}
        path = tmp_path / 'data.json'
        path.write_text(json.dumps(data))
        result = release_notes.load_existing_json(path)
        assert result is not None
        assert result['pull_requests'] == []

    def test_previous_schema_version_accepted(self, tmp_path):
        data = {'metadata': {'schema_version': release_notes.SCHEMA_VERSION - 1}, 'pull_requests': []}
        path = tmp_path / 'data.json'
        path.write_text(json.dumps(data))
        result = release_notes.load_existing_json(path)
        assert result is not None

    def test_missing_file(self, tmp_path):
        result = release_notes.load_existing_json(tmp_path / 'missing.json')
        assert result is None

    def test_corrupt_json(self, tmp_path):
        path = tmp_path / 'bad.json'
        path.write_text('{not valid json')
        result = release_notes.load_existing_json(path)
        assert result is None

    def test_wrong_schema_version(self, tmp_path):
        data = {'metadata': {'schema_version': 999}, 'pull_requests': []}
        path = tmp_path / 'data.json'
        path.write_text(json.dumps(data))
        result = release_notes.load_existing_json(path)
        assert result is None

    def test_missing_pull_requests_key(self, tmp_path):
        path = tmp_path / 'data.json'
        path.write_text('{"metadata": {}}')
        result = release_notes.load_existing_json(path)
        assert result is None


class TestParseRepoPathMappings:
    def test_default_path_for_all_repos(self):
        result = release_notes.parse_repo_path_mappings(
            None, '/default', ['o3de/o3de', 'o3de/o3de-extras']
        )
        assert result['o3de/o3de'] == pathlib.Path('/default').resolve()
        assert result['o3de/o3de-extras'] == pathlib.Path('/default').resolve()

    def test_explicit_mapping(self):
        result = release_notes.parse_repo_path_mappings(
            ['o3de/o3de-extras=/home/user/extras'],
            '/default',
            ['o3de/o3de', 'o3de/o3de-extras'],
        )
        assert result['o3de/o3de'] == pathlib.Path('/default').resolve()
        assert result['o3de/o3de-extras'] == pathlib.Path('/home/user/extras').resolve()

    def test_all_explicit(self):
        result = release_notes.parse_repo_path_mappings(
            ['o3de/o3de=/a', 'o3de/o3de-extras=/b'],
            '/default',
            ['o3de/o3de', 'o3de/o3de-extras'],
        )
        assert result['o3de/o3de'] == pathlib.Path('/a').resolve()
        assert result['o3de/o3de-extras'] == pathlib.Path('/b').resolve()

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError, match='Invalid --repo-path mapping'):
            release_notes.parse_repo_path_mappings(
                ['not-a-valid-mapping'],
                '/default',
                ['o3de/o3de'],
            )

    def test_empty_repo_paths(self):
        result = release_notes.parse_repo_path_mappings(
            [], '/default', ['o3de/o3de']
        )
        assert result['o3de/o3de'] == pathlib.Path('/default').resolve()


class TestBuildSummaryPrompt:
    def test_includes_version(self):
        prs = [{'title': 'Fix bug', 'sig_category': 'sig/build', 'flags': []}]
        prompt = release_notes._build_summary_prompt(prs, '26.05.0')
        assert '26.05.0' in prompt

    def test_includes_sig_groups(self):
        prs = [
            {'title': 'Fix cmake', 'sig_category': 'sig/build', 'flags': []},
            {'title': 'Fix vulkan', 'sig_category': 'sig/graphics-audio', 'flags': []},
        ]
        prompt = release_notes._build_summary_prompt(prs, '1.0')
        assert 'SIG-Build' in prompt
        assert 'SIG-Graphics-Audio' in prompt

    def test_excludes_cherry_picks(self):
        prs = [
            {'title': 'Fix cmake', 'sig_category': 'sig/build', 'flags': []},
            {'title': 'Cherry pick', 'sig_category': 'sig/build', 'flags': ['cherry-pick']},
        ]
        prompt = release_notes._build_summary_prompt(prs, '1.0')
        assert 'Fix cmake' in prompt
        assert 'Cherry pick' not in prompt

    def test_excludes_uncategorized(self):
        prs = [
            {'title': 'Fix cmake', 'sig_category': 'sig/build', 'flags': []},
            {'title': 'Unknown', 'sig_category': 'uncategorized', 'flags': []},
        ]
        prompt = release_notes._build_summary_prompt(prs, '1.0')
        assert 'Fix cmake' in prompt
        assert 'Unknown' not in prompt

    def test_truncates_long_sig(self):
        prs = [{'title': f'PR {i}', 'sig_category': 'sig/build', 'flags': []} for i in range(20)]
        prompt = release_notes._build_summary_prompt(prs, '1.0')
        assert '... and 5 more' in prompt


class TestGenerateSummary:
    def test_success(self):
        with mock.patch('release_notes.shutil.which', return_value='/usr/local/bin/ollama'):
            with mock.patch('release_notes.subprocess.run') as mock_run:
                mock_run.return_value = mock.Mock(
                    returncode=0,
                    stdout='This release is great.',
                    stderr='',
                )
                result = release_notes.generate_summary([], '1.0', 'ollama run qwen2.5:32b')
        assert result == 'This release is great.'

    def test_command_not_found(self):
        with mock.patch('release_notes.shutil.which', return_value=None):
            result = release_notes.generate_summary([], '1.0', 'nonexistent')
        assert result is None

    def test_command_failure(self):
        with mock.patch('release_notes.shutil.which', return_value='/usr/local/bin/ollama'):
            with mock.patch('release_notes.subprocess.run') as mock_run:
                mock_run.return_value = mock.Mock(returncode=1, stdout='', stderr='error')
                result = release_notes.generate_summary([], '1.0', 'ollama run qwen2.5:32b')
        assert result is None

    def test_timeout(self):
        with mock.patch('release_notes.shutil.which', return_value='/usr/local/bin/ollama'):
            with mock.patch('release_notes.subprocess.run', side_effect=subprocess.TimeoutExpired('cmd', 120)):
                result = release_notes.generate_summary([], '1.0', 'ollama run qwen2.5:32b')
        assert result is None

    def test_empty_output(self):
        with mock.patch('release_notes.shutil.which', return_value='/usr/local/bin/ollama'):
            with mock.patch('release_notes.subprocess.run') as mock_run:
                mock_run.return_value = mock.Mock(returncode=0, stdout='', stderr='')
                result = release_notes.generate_summary([], '1.0', 'ollama run qwen2.5:32b')
        assert result is None


class TestRenderMarkdownWithSummary:
    def _make_pr(self, number, sig, title='Fix something'):
        return {
            'number': number, 'repo': 'o3de/o3de', 'title': title,
            'sig_category': sig, 'categorization_source': 'label',
            'description': release_notes._sanitize_pr_title_for_markdown(title),
            'flags': [],
        }

    def test_with_summary(self):
        prs = [self._make_pr(1, 'sig/build')]
        result = release_notes.render_markdown(prs, '1.0', summary='Great release.')
        assert 'Great release.' in result
        assert 'TODO' not in result

    def test_without_summary(self):
        prs = [self._make_pr(1, 'sig/build')]
        result = release_notes.render_markdown(prs, '1.0')
        assert 'TODO' in result
