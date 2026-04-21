# Architecture

## Overview

The release notes generator is a single-file Python script with three stages: **Extract**, **Categorize**, and **Render**. It uses a JSON intermediate format that supports both human editing and AI agent consumption.

```
                    ┌──────────────────────────────────────────────────────────────┐
                    │                     release_notes.py                        │
                    │                                                              │
                    │   ┌───────────┐     ┌──────────────┐     ┌──────────────┐   │
 Local git clone ──▶│   │  Extract  │────▶│  Categorize  │────▶│   Render     │   │
   (read-only)      │   │           │     │              │     │              │   │
                    │   │ git log   │     │ 1. Labels    │     │ Markdown     │   │
                    │   │ PR #s     │     │ 2. Title     │     │ by SIG       │   │
                    │   │           │     │ 3. Files     │     │              │   │
                    │   └─────┬─────┘     └──────┬───────┘     └──────┬───────┘   │
                    │         │                  │                    │           │
                    │         ▼                  ▼                    ▼           │
                    │   ┌───────────┐     ┌──────────────┐     ┌──────────────┐   │
                    │   │  gh CLI   │     │ JSON cache   │     │ .md output   │   │
                    │   │  GraphQL  │     │ (editable)   │     │              │   │
                    │   └───────────┘     └──────────────┘     └──────────────┘   │
                    └──────────────────────────────────────────────────────────────┘
                          │                     ▲                      │
                          ▼                     │                      ▼
                     GitHub API           Human / AI agent       Feature list /
                     (batched,            edits JSON for         release notes
                      auth via            manual overrides       (.md file)
                      gh CLI)
```

## Data Flow

### Stage 1: Extract

**Input:** Local git repository (read-only), two git references (tag/branch).

**Process:**
1. Runs `git log --format=%s <from>..<to> --no-merges` via `subprocess.run()` with list arguments.
2. Parses PR numbers from commit subjects using regex `\(#(\d+)\)`.
3. Deduplicates and sorts.

**Output:** Sorted list of PR numbers.

**Trust boundary:** The git log output is from a local repository the user controls. PR numbers are parsed as integers, preventing injection.

### Stage 2: Fetch + Categorize

**Input:** PR numbers, GitHub repo slug(s).

**Process:**
1. Constructs GraphQL queries batching up to 30 PRs per request.
2. Executes via `gh api graphql` (subprocess with list args).
3. For each PR, categorizes by SIG using three methods in priority order:
   - **Label match:** Checks for `sig/*` GitHub labels. Highest confidence.
   - **Title heuristic:** Matches title keywords against per-SIG keyword maps.
   - **File path heuristic:** Matches changed file paths against directory-to-SIG maps.
4. Detects flags (cherry-pick, stabilization-sync) for filtering.
5. Merges with any existing JSON data, preserving manual overrides.

**Output:** Structured JSON with full PR metadata and categorization.

**Trust boundary:** PR data comes from the GitHub API (untrusted). Titles are sanitized before rendering. Labels and file paths are used for categorization only, not interpolated into shell commands.

### Stage 3: Render

**Input:** JSON data from Stage 2, version string.

**Process:**
1. Groups PRs by SIG category.
2. Filters out cherry-picks and stabilization sync PRs.
3. Renders markdown with fixed SIG ordering matching the established O3DE release notes format.
4. Sanitizes PR titles for markdown (escapes special characters).

**Output:** Markdown file.

**Trust boundary:** Output is written atomically to prevent corruption. PR titles are sanitized to prevent markdown injection.

## Incremental Update Flow

```
First run:                    Subsequent runs:

git log ──▶ PR #s             git log ──▶ PR #s (may have grown)
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
render .md                        ▼
                              render updated .md
```

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

### OWASP Top 10 Mapping

| OWASP Category | Applicability | Controls |
|----------------|--------------|----------|
| **A03:2021 Injection** | Subprocess calls, markdown output | All subprocess calls use list args (never `shell=True`). All user inputs validated with regex before use. PR titles sanitized for markdown. |
| **A04:2021 Insecure Design** | Overall architecture | Defense-in-depth: validate at input, sanitize at output. Atomic file writes. Fail-closed on validation errors. |
| **A05:2021 Security Misconfiguration** | Secret management | No hardcoded secrets. Auth delegated to `gh` CLI. Preflight check verifies auth status. |
| **A06:2021 Vulnerable and Outdated Components** | Dependencies | Zero external dependencies. Uses only Python stdlib (`subprocess`, `json`, `re`, `pathlib`, `tempfile`, `argparse`, `logging`). |
| **A07:2021 Identification and Authentication Failures** | GitHub API access | Auth fully managed by `gh` CLI. Script verifies `gh auth status` before making API calls. |
| **A08:2021 Software and Data Integrity Failures** | JSON data, file I/O | JSON schema versioned (`schema_version` field). Atomic writes prevent partial/corrupt files. Manual overrides preserved across re-runs. |
| **A09:2021 Security Logging and Monitoring Failures** | Operational logging | Structured logging (`[LEVEL] o3de.release_notes: message`). Never logs tokens, credentials, or full API response bodies. Logs all validation failures. |

### NIST SP 800-53 Controls

| Control | Implementation |
|---------|---------------|
| **SI-10 (Information Input Validation)** | All external inputs (git refs, repo slugs, file paths) validated with regex patterns and length limits before use. |
| **SI-15 (Information Output Filtering)** | PR titles sanitized for markdown special characters before rendering. Only whitelisted fields from API responses are used. |
| **AU-3 (Content of Audit Records)** | Structured log format with severity levels. Categorization summary logged on each run. |
| **SC-28 (Protection of Information at Rest)** | Atomic file writes via `tempfile.mkstemp()` + `os.replace()` prevent data corruption from interrupted writes. |
| **CM-7 (Least Functionality)** | Minimal stdlib-only implementation. No unnecessary network calls (only fetches new PRs on re-run). No write access to the O3DE repository. |

### Input Validation Specifications

| Input | Pattern | Max Length | Additional Checks |
|-------|---------|------------|-------------------|
| Git ref | `^[a-zA-Z0-9._/-]+$` | 256 | Must not start with `-` |
| Repo slug | `^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$` | 128 | Exactly one `/` |
| Output path | N/A (uses pathlib) | OS limit | Parent must exist; optional base-dir containment |
| PR number | Parsed as `int()` | N/A | Must be positive integer (implicit) |
| Version string | Free text (user-facing) | N/A | Used only in markdown heading |

### Subprocess Execution

Every subprocess call uses list arguments:

```python
subprocess.run(['git', 'log', '--format=%s', f'{from_ref}..{to_ref}'], ...)
subprocess.run(['gh', 'api', 'graphql', '-f', f'query={query}'], ...)
subprocess.run(['gh', 'auth', 'status'], ...)
```

No call uses `shell=True`. The `from_ref` and `to_ref` values are validated before interpolation into the argument list, preventing argument injection (e.g., a ref like `--exec=malicious` is rejected by the leading-hyphen check).
