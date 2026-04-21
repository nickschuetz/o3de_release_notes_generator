# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0-beta] - 2026-04-21

### Added
- Multi-repo support: each repo can have its own local clone via `--repo-path owner/repo=/path/to/clone`
- `--default-repo-path` flag for setting the fallback clone path when no explicit mapping is given
- Automated narrative summary generation via `--generate-summary` flag (default: off)
- `--summary-cmd` flag to configure the LLM command (default: `ollama run qwen2.5:32b`)
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
