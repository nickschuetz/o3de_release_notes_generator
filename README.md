# O3DE Release Notes Generator

A standalone tool that generates [Open 3D Engine (O3DE)](https://o3de.org) release notes by extracting merged pull requests from GitHub, categorizing them by SIG (Special Interest Group), and rendering markdown in the established release notes format.

Designed to be run incrementally throughout the pre-release cycle so the release team can track progress as PRs land.

## Prerequisites

- Python 3.10+
- [GitHub CLI (`gh`)](https://cli.github.com/) installed and authenticated (`gh auth login`)
- A local clone of the O3DE repository (read-only reference)

## Quick Start

```bash
# Generate release notes for 26.05.0 (everything since 25.10.0)
python release_notes.py generate \
  --from-ref 2510.0 \
  --to-ref development \
  --repo-path /path/to/o3de \
  --output-json release_data.json \
  --output-md 26050_release_notes.md \
  --version 26.05.0
```

## CLI Reference

The tool has three subcommands: `fetch`, `render`, and `generate`.

### `fetch` - Extract PR data from GitHub into JSON

```bash
python release_notes.py fetch \
  --from-ref <start-tag> \
  --to-ref <end-branch> \
  --repo-path <path-to-local-clone> \
  --output-json <output.json> \
  [--repos owner/repo ...] \
  [-v]
```

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--from-ref` | Yes | - | Starting git reference (tag or commit) |
| `--to-ref` | Yes | - | Ending git reference (branch or tag) |
| `--repo-path` | No | `.` | Path to local O3DE git clone |
| `--output-json` | Yes | - | Output JSON file path |
| `--repos` | No | `o3de/o3de` | GitHub repos in `owner/repo` format |
| `-v` | No | - | Verbose logging |

### `render` - Generate markdown from JSON

```bash
python release_notes.py render \
  --input-json <input.json> \
  --output-md <output.md> \
  --version <version-string> \
  [--include-uncategorized]
```

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--input-json` | Yes | - | Path to JSON from `fetch` |
| `--output-md` | Yes | - | Output markdown file path |
| `--version` | Yes | - | Version string (e.g., `26.05.0`) |
| `--include-uncategorized` | No | - | Show PRs that couldn't be categorized |

### `generate` - Fetch and render in one step

Combines `fetch` and `render`. Accepts all flags from both subcommands.

## Examples

### Generate notes for a specific release

```bash
python release_notes.py generate \
  --from-ref 2510.0 \
  --to-ref development \
  --repo-path ~/PROJECTS/o3de \
  --output-json release_data.json \
  --output-md 26050_release_notes.md \
  --version 26.05.0
```

### Incremental update during pre-release

Re-run the same command. New PRs are fetched; existing data and any manual edits in the JSON are preserved.

```bash
# Week 1
python release_notes.py generate --from-ref 2510.0 --to-ref development \
  --repo-path ~/PROJECTS/o3de --output-json release_data.json \
  --output-md notes.md --version 26.05.0

# Week 2 (same command - only fetches new PRs)
python release_notes.py generate --from-ref 2510.0 --to-ref development \
  --repo-path ~/PROJECTS/o3de --output-json release_data.json \
  --output-md notes.md --version 26.05.0
```

### Fetch only (for AI agent consumption)

```bash
python release_notes.py fetch \
  --from-ref 2510.0 --to-ref development \
  --repo-path ~/PROJECTS/o3de \
  --output-json release_data.json
```

The JSON output is structured for programmatic consumption. See [JSON Schema](#json-schema) below.

### Multi-repo (include o3de-extras)

```bash
python release_notes.py generate \
  --from-ref 2510.0 --to-ref development \
  --repos o3de/o3de o3de/o3de-extras \
  --repo-path ~/PROJECTS/o3de \
  --output-json release_data.json \
  --output-md notes.md \
  --version 26.05.0
```

### Include uncategorized PRs for triage

```bash
python release_notes.py generate \
  --from-ref 2510.0 --to-ref development \
  --repo-path ~/PROJECTS/o3de \
  --output-json release_data.json \
  --output-md notes.md \
  --version 26.05.0 \
  --include-uncategorized
```

## JSON Schema

The intermediate JSON is the primary data format. It can be edited by humans or consumed by AI agents.

```json
{
  "metadata": {
    "generated_at": "2026-04-21T10:00:00+00:00",
    "from_ref": "2510.0",
    "to_ref": "development",
    "repos": ["o3de/o3de"],
    "schema_version": 1,
    "pr_count": 233,
    "categorization_summary": {
      "label": 120,
      "heuristic_title": 80,
      "heuristic_files": 20,
      "uncategorized": 13
    }
  },
  "pull_requests": [
    {
      "number": 19709,
      "repo": "o3de/o3de",
      "title": "Fix for choppy mouse movement in FlyCameraInputComponent",
      "url": "https://github.com/o3de/o3de/pull/19709",
      "author": "contributor",
      "merged_at": "2026-04-20T17:14:14Z",
      "labels": ["sig/content"],
      "files": ["Gems/AtomLyIntegration/.../FlyCameraInputComponent.cpp"],
      "sig_category": "sig/content",
      "categorization_source": "label",
      "description": "Fix for choppy mouse movement in FlyCameraInputComponent.",
      "flags": [],
      "manual_override_sig": null,
      "manual_override_description": null
    }
  ]
}
```

### Key Fields

| Field | Description |
|-------|-------------|
| `sig_category` | Assigned SIG. Set automatically, or via `manual_override_sig`. |
| `categorization_source` | How the SIG was assigned: `label`, `heuristic_title`, `heuristic_files`, `uncategorized`, `manual_override` |
| `flags` | Auto-detected flags: `cherry-pick`, `stabilization-sync`. Flagged PRs are excluded from rendered markdown. |
| `manual_override_sig` | Set this to reassign a PR to a different SIG. Preserved on re-runs. |
| `manual_override_description` | Set this to override the auto-generated description. Preserved on re-runs. |

## SIG Categorization

PRs are categorized using three methods in priority order:

1. **GitHub labels** - PRs with `sig/*` labels (e.g., `sig/build`, `sig/graphics-audio`) are categorized directly. Highest confidence.
2. **Title keywords** - PR titles are matched against keyword lists per SIG.
3. **File paths** - Changed file paths are matched against directory-to-SIG mappings.

If none match, the PR is marked `uncategorized` for manual triage.

### Updating Heuristics

The keyword maps (`SIG_TITLE_KEYWORDS`) and file path maps (`SIG_FILE_PATH_PATTERNS`) are data-driven dicts at the top of `release_notes.py`. To add or adjust mappings, edit these dicts directly.

## Running Tests

```bash
python -m pytest tests/ -v
```

## License

Apache-2.0
