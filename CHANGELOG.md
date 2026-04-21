# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
- Multi-repo support (`--repos`) queries the same local git clone for all repos; separate clones for o3de-extras are not yet handled
- No automated narrative summary generation (placeholder is inserted for manual writing)
- `--force-recategorize` flag is documented in the plan but not yet implemented
