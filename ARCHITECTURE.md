# Architecture

## Overview

The release notes generator is a standalone Python project with zero external dependencies. It consists of two main scripts:

- **`release_notes.py`** - Three-stage pipeline (Extract, Categorize, Render) that generates O3DE release notes from merged pull requests.
- **`generate_sbom.py`** - Generates a CycloneDX 1.5 SBOM for supply chain transparency.

Both scripts use only Python stdlib modules and interact with external systems (git, GitHub API) exclusively through the `gh` CLI and `git` commands via `subprocess` with list arguments.

```
                    ┌──────────────────────────────────────────────────────────────┐
                    │                     release_notes.py                        │
                    │                                                              │
                    │   ┌───────────┐     ┌──────────────┐     ┌──────────────┐   │
 Local git clones ─▶│   │  Extract  │────▶│  Categorize  │────▶│   Render     │   │
   (read-only,      │   │           │     │              │     │              │   │
    per-repo)       │   │ git log   │     │ 1. Labels    │     │ Markdown     │   │
                    │   │ PR #s     │     │ 2. Title     │     │ by SIG       │   │
                    │   │           │     │ 3. Files     │     │              │   │
                    │   └─────┬─────┘     └──────┬───────┘     └──────┬───────┘   │
                    │         │                  │                    │           │
                    │         ▼                  ▼                    ▼           │
                    │   ┌───────────┐     ┌──────────────┐     ┌──────────────┐   │
                    │   │  gh CLI   │     │ JSON cache   │     │  .md output  │   │
                    │   │  GraphQL  │     │ (editable)   │     │ + optional   │   │
                    │   └───────────┘     └──────────────┘     │ LLM summary │   │
                    │                                          └──────────────┘   │
                    └──────────────────────────────────────────────────────────────┘
                          │                     ▲                      │
                          ▼                     │                      ▼
                     GitHub API           Human / AI agent       Feature list /
                     (batched,            edits JSON for         release notes
                      auth via            manual overrides       (.md file)
                      gh CLI)
```

## Project Components

### `release_notes.py`

The main script. Three subcommands (`fetch`, `render`, `generate`) exposed via `argparse`. Approximately 1100 lines.

**Key data structures:**
- `SIG_TITLE_KEYWORDS` - Dict mapping SIG names to title keyword lists for heuristic categorization.
- `SIG_FILE_PATH_PATTERNS` - Dict mapping SIG names to file path prefixes for heuristic categorization.
- `SIG_CANONICAL_ORDER` - List defining the fixed section ordering in rendered markdown.

**Multi-repo support:** The `parse_repo_path_mappings()` function resolves per-repo local clone paths. Each repo can have its own clone via `--repo-path owner/repo=/path`, with `--default-repo-path` as the fallback.

**Summary generation:** The `generate_summary()` function builds a structured prompt from categorized PR data and passes it via stdin to a configurable LLM command via subprocess (list args, no `shell=True`). Default: `ollama run --nowordwrap qwen2.5:32b` (local); also supports `claude -p` (cloud). The `_clean_summary()` function strips LLM preamble text and dividers from the output. Command is parsed via `shlex.split()`. Optional `--summary-hint` injects release manager guidance into the prompt — accepts inline text or `@filepath` to read from a file (resolved via `_resolve_hint()`). Enabled via `--generate-summary`; disabled by default.

### `generate_sbom.py`

Generates a CycloneDX 1.5 JSON SBOM (`sbom.cdx.json`). Captures project metadata, Python stdlib module inventory, and SHA-256 hashes of all source files. Approximately 190 lines.

### `tests/test_release_notes.py`

143 unit tests using `pytest` and `unittest.mock`. Covers input validation (including injection attempts), multi-repo path parsing, SIG categorization (labels, title heuristics, file heuristics, priority ordering), summary prompt building, summary generation (success, failure, timeout), markdown rendering (with and without summary), incremental merging with manual override preservation, atomic file I/O, and JSON loading/validation.

### `.github/workflows/sbom.yml`

GitHub Action that regenerates `sbom.cdx.json` on every push to `main` that changes Python source files. Commits the updated SBOM back to the repository automatically.

## Data Flow

### Stage 1: Extract

**Input:** Local git repositories (read-only, one per repo), two git references (tag/branch).

**Process:**
1. Resolves per-repo local clone paths via `parse_repo_path_mappings()`.
2. For each repo, runs `git log --format=%s <from>..<to> --no-merges` via `subprocess.run()` with list arguments against that repo's local clone.
3. Parses PR numbers from commit subjects using regex `\(#(\d+)\)`.
4. Deduplicates and sorts per repo.

**Output:** Sorted list of PR numbers per repo.

**Trust boundary:** The git log output is from local repositories the user controls. PR numbers are parsed as integers, preventing injection. Repo path mappings are validated for format before use.

### Stage 2: Fetch + Categorize

**Input:** PR numbers per repo, GitHub repo slug(s).

**Process:**
1. For each repo, constructs GraphQL queries batching up to 30 PRs per request (~8 requests for a typical release of ~230 PRs). Queries fetch title, body, labels, files, author, and merge date.
2. Executes via `gh api graphql` (subprocess with list args). Each repo's PRs are fetched from the correct GitHub owner/repo.
3. PR descriptions are built from the PR body's first meaningful paragraph (skipping template headers, checklists, URLs, and noise). Falls back to the title if the body is empty or too short.
3. For each PR, categorizes by SIG using three methods in priority order:
   - **Label match:** Checks for `sig/*` GitHub labels. Highest confidence.
   - **Title heuristic:** Matches title keywords against per-SIG keyword maps.
   - **File path heuristic:** Matches changed file paths against directory-to-SIG maps.
4. Detects flags (cherry-pick, stabilization-sync) for filtering.
5. Merges with any existing JSON data, preserving manual overrides.

**Output:** Structured JSON with full PR metadata and categorization.

**Trust boundary:** PR data comes from the GitHub API (untrusted). Titles are sanitized before rendering. Labels and file paths are used for categorization only, not interpolated into shell commands.

### Stage 3: Render

**Input:** JSON data from Stage 2, version string, optional summary generation config.

**Process:**
1. If `--generate-summary` is enabled, builds a structured prompt from the PR data and passes it via stdin to the configured LLM command (default: `ollama run --nowordwrap qwen2.5:32b`; or `claude -p` for cloud) via subprocess with list args. LLM preamble text and dividers are stripped from the output.
2. Groups PRs by SIG category.
3. Filters out cherry-picks and stabilization sync PRs.
4. Renders markdown with fixed SIG ordering matching the established O3DE release notes format.
5. Inserts the LLM-generated narrative summary (or a placeholder if summary generation is disabled or fails).
6. Sanitizes PR titles for markdown (escapes special characters).

**Output:** Markdown file.

**Trust boundary:** Output is written atomically to prevent corruption. PR titles are sanitized to prevent markdown injection. The summary command is executed via subprocess with list args (no `shell=True`). The LLM's output is inserted as-is into the markdown intro section — it is not interpolated into shell commands or other untrusted contexts.

## Incremental Update Flow

The tool supports re-running throughout the pre-release cycle. On subsequent runs, only new PRs are fetched from GitHub, and any manual edits to the JSON (via `manual_override_sig` and `manual_override_description` fields) are preserved.

```
First run:                    Subsequent runs:

git log (per repo) ──▶ PR #s  git log (per repo) ──▶ PR #s (may have grown)
    │                             │
    ▼                             ▼
GitHub API ──▶ all PRs        GitHub API ──▶ new PRs only
    │                             │
    ▼                             ▼
categorize ──▶ JSON           merge with existing JSON
    │                         (preserve manual_override_* fields)
    ▼                             │
write JSON                        ▼
    │                         write updated JSON
    ▼                             │
(optional) LLM summary            ▼
    │                         (optional) LLM summary
    ▼                             │
render .md                        ▼
                              render updated .md
```

## SBOM Generation

The `generate_sbom.py` script produces a CycloneDX 1.5 JSON SBOM at `sbom.cdx.json`.

**Contents:**
- Project metadata (name, version, license, repo URL)
- 13 Python stdlib modules declared as framework dependencies with package URLs
- SHA-256 hashes of all source files (`release_notes.py`, `generate_sbom.py`, `tests/test_release_notes.py`)
- Explicit `cdx:externalDependencies: none` property
- Dependency graph linking the project to its stdlib modules

**Automation:** The `.github/workflows/sbom.yml` workflow regenerates the SBOM on every push to `main` that changes `*.py` files. The workflow uses `github-actions[bot]` to commit the updated SBOM, preventing infinite trigger loops (bot commits don't trigger workflows by default).

**Atomic writes:** Like the main script, the SBOM generator uses `tempfile.mkstemp()` + `os.replace()` for crash-safe file output.

## Security Model

### Threat Model

| Asset | Threat | Mitigation |
|-------|--------|------------|
| GitHub auth token | Exposure in logs or code | Delegated to `gh` CLI credential store; never handled directly |
| PR titles (untrusted) | Markdown injection in rendered output | Sanitized: `#`, `[`, `]`, `` ` ``, `\|` escaped; trailing PR refs stripped |
| Git refs (user input) | Command injection via subprocess | Validated against `^[a-zA-Z0-9._/-]+$`; must not start with `-` |
| Repo slugs (user input) | Command injection | Validated against `^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$` |
| Output file paths | Path traversal | Resolved via `pathlib.Path.resolve()`; optional base-dir containment check |
| JSON data files | Corruption from interrupted writes | Atomic writes via `tempfile` + `os.replace()` |
| GitHub API responses | Malformed data | Validated structure before use; missing fields default safely |
| LLM summary command | Command injection via `--summary-cmd` | Command parsed via `shlex.split()` (respects shell quoting), executed via subprocess with list args; executable checked via `shutil.which()` before invocation |
| LLM output | Prompt injection in generated narrative | Output is inserted into markdown intro only; not used in shell commands, file paths, or API calls |
| Supply chain | Undetected dependency changes | CycloneDX SBOM with source file hashes; auto-updated via CI |

### OWASP Top 10 Mapping

| OWASP Category | Applicability | Controls |
|----------------|--------------|----------|
| **A03:2021 Injection** | Subprocess calls, markdown output | All subprocess calls use list args (never `shell=True`). All user inputs validated with regex before use. PR titles sanitized for markdown. |
| **A04:2021 Insecure Design** | Overall architecture | Defense-in-depth: validate at input, sanitize at output. Atomic file writes. Fail-closed on validation errors. |
| **A05:2021 Security Misconfiguration** | Secret management | No hardcoded secrets. Auth delegated to `gh` CLI. Preflight check verifies auth status. |
| **A06:2021 Vulnerable and Outdated Components** | Dependencies | Zero external dependencies. Uses only Python stdlib. SBOM tracks all components with SHA-256 hashes. |
| **A07:2021 Identification and Authentication Failures** | GitHub API access | Auth fully managed by `gh` CLI. Script verifies `gh auth status` before making API calls. |
| **A08:2021 Software and Data Integrity Failures** | JSON data, file I/O, supply chain | JSON schema versioned (`schema_version` field). Atomic writes prevent partial/corrupt files. CycloneDX SBOM with file hashes for integrity verification. |
| **A09:2021 Security Logging and Monitoring Failures** | Operational logging | Structured logging (`[LEVEL] o3de.release_notes: message`). Never logs tokens, credentials, or full API response bodies. Logs all validation failures. |

### NIST SP 800-53 Controls

| Control | Implementation |
|---------|---------------|
| **SI-10 (Information Input Validation)** | All external inputs (git refs, repo slugs, file paths) validated with regex patterns and length limits before use. |
| **SI-15 (Information Output Filtering)** | PR titles sanitized for markdown special characters before rendering. Only whitelisted fields from API responses are used. |
| **AU-3 (Content of Audit Records)** | Structured log format with severity levels. Categorization summary logged on each run. |
| **SC-28 (Protection of Information at Rest)** | Atomic file writes via `tempfile.mkstemp()` + `os.replace()` prevent data corruption from interrupted writes. |
| **CM-7 (Least Functionality)** | Minimal stdlib-only implementation. No unnecessary network calls (only fetches new PRs on re-run). No write access to the O3DE repository. |
| **SA-8 (Security and Privacy Engineering Principles)** | CycloneDX SBOM generated and maintained for supply chain transparency. Source file integrity verified via SHA-256 hashes. |

### Input Validation Specifications

| Input | Pattern | Max Length | Additional Checks |
|-------|---------|------------|-------------------|
| Git ref | `^[a-zA-Z0-9._/-]+$` | 256 | Must not start with `-` |
| Repo slug | `^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$` | 128 | Exactly one `/` |
| Repo path mapping | `^(owner/repo)=(.+)$` | N/A | Repo slug validated separately; path resolved via `pathlib`; `.git` existence checked |
| Output path | N/A (uses pathlib) | OS limit | Parent must exist; optional base-dir containment |
| Version string | Free text (user-facing) | N/A | Used only in markdown heading |
| PR number | Parsed as `int()` | 999999 | Must be 1-999999; validated before GraphQL query construction |
| Summary command | Parsed via `shlex.split()` | N/A | Executable checked via `shutil.which()` before invocation |

### Subprocess Execution

Every subprocess call uses list arguments:

```python
subprocess.run(['git', 'log', '--format=%s', f'{from_ref}..{to_ref}'], ...)
subprocess.run(['gh', 'api', 'graphql', '-f', f'query={query}'], ...)
subprocess.run(['gh', 'auth', 'status'], ...)
subprocess.run(cmd_parts, input=prompt, ...)  # summary generation via stdin
```

No call uses `shell=True`. The `from_ref` and `to_ref` values are validated before interpolation into the argument list, preventing argument injection (e.g., a ref like `--exec=malicious` is rejected by the leading-hyphen check). The summary command is parsed via `shlex.split()` (respects shell quoting) and the executable is verified via `shutil.which()` before invocation. PR numbers are validated to be positive integers within bounds (1-999999) before inclusion in GraphQL queries.
