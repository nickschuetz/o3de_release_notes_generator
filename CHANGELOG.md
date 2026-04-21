# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0-beta] - 2026-04-21

### Added
- `--summary-hint` flag to steer the LLM narrative — accepts inline text or `@filepath` to read from a file
- Clickable GitHub PR links in rendered markdown output
- LLM output cleaner (`_clean_summary()`) that strips preamble text and `---` dividers
- ANSI escape code stripping for terminal-based LLM tools (e.g., ollama)
- `--nowordwrap` in default ollama command to prevent word wrapping artifacts
- PR number bounds validation (1-999999) and batch_size validation (1-100)
- Consistent error message truncation via `_safe_stderr()` (200 char max)
- `shlex.split()` for safe summary command parsing (supports quoted arguments)
- `reports/` directory with example output from a full multi-repo run
- `_clean_summary()` function to strip LLM preamble text and `---` dividers
- 3 new tests for summary hint, plus tests for PR validation, ANSI stripping, edge cases

### Changed
- PR references now render as clickable markdown links (e.g., `[o3de#19709](https://github.com/o3de/o3de/pull/19709)`)
- Summary prompt passed via stdin instead of `-p` flag for universal LLM compatibility
- Default summary command updated to `ollama run --nowordwrap qwen2.5:32b`
- `generate` subcommand no longer requires `--input-json` (set automatically from `--output-json`)
- Version bumped to 0.3.0-beta

## [0.2.0-beta] - 2026-04-21

### Added
- Multi-repo support: each repo can have its own local clone via `--repo-path owner/repo=/path/to/clone`
- `--default-repo-path` flag for setting the fallback clone path when no explicit mapping is given
- Automated narrative summary generation via `--generate-summary` flag (default: off)
- `--summary-cmd` flag to configure the LLM command (default: `ollama run --nowordwrap qwen2.5:32b`)
- Summary prompt builder that groups PRs by SIG with truncation for large sections
- 18 new unit tests for multi-repo parsing, summary prompt building, and summary generation

### Changed
- `--repo-path` now accepts per-repo mappings in `owner/repo=/path` format
- Schema version bumped to 2 (v1 JSON files are still accepted for backward compatibility)
- JSON metadata now includes `repo_paths` mapping for traceability
- Version bumped to 0.2.0-beta

### Removed
- Single-path `--repo-path` positional behavior replaced by `--default-repo-path`

## [0.1.0-beta] - 2026-04-21

### Added
- Three-stage release notes pipeline: Extract (git log), Categorize (SIG labels/heuristics), Render (markdown)
- Three CLI subcommands: `fetch`, `render`, `generate`
- GraphQL batched PR fetching via `gh` CLI (zero external Python dependencies)
- SIG categorization by GitHub labels, title keyword heuristics, and file path heuristics
- Incremental update support with manual override preservation (`manual_override_sig`, `manual_override_description`)
- Cherry-pick and stabilization-sync PR detection and filtering
- AI-agent friendly JSON intermediate format with schema versioning
- CycloneDX 1.5 SBOM generation (`generate_sbom.py`) with source file SHA-256 hashes
- GitHub Action for automatic SBOM regeneration on push (`.github/workflows/sbom.yml`)
- 87 unit tests covering validation, categorization, rendering, merging, and I/O
- OWASP Top 10 and NIST SP 800-53 aligned security controls
- Atomic file writes for crash-safe output
- Input validation on all user-supplied values (git refs, repo slugs, file paths)
- PR title sanitization to prevent markdown injection
- Dual licensing (Apache-2.0 OR MIT) matching the O3DE project

### Known Limitations
- `--force-recategorize` flag is documented in the plan but not yet implemented
