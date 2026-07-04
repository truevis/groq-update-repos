# groq-update-repos

Tools to find deprecated [Groq](https://console.groq.com/docs/deprecations) model IDs across local repositories, replace them with current models, and push the changes to GitHub.

## Requirements

- Python 3.10+
- [Git](https://git-scm.com/) (for `git_push.py`)
- No third-party Python packages — both scripts use the standard library only

## Scripts

| Script | Purpose |
|--------|---------|
| `update_groq_models.py` | Scan repos under a parent folder, detect deprecated Groq model IDs, and optionally apply replacements |
| `git_push.py` | Read the migration report, commit changed files per repo, and push to `origin` |

By default, both scripts look at the **parent** of this folder (e.g. `C:\GitHub` when this repo lives at `C:\GitHub\groq-update-repos`).

## Typical workflow

### 1. Scan for deprecated models

Report matches without changing any files:

```bash
python update_groq_models.py --scan
```

### 2. Preview replacements

```bash
python update_groq_models.py --dry-run
```

### 3. Apply replacements

```bash
python update_groq_models.py
```

This writes `groq_model_migration_report.md` with affected repos, model mappings, shutdown dates, and file links.

### 4. Commit and push

```bash
python git_push.py --dry-run
python git_push.py
```

`git_push.py` reads `groq_model_migration_report.md`, stages only the listed files that have changes, commits with a default message, and pushes the current branch to `origin`. It writes `git_push_report.md` with per-repo results.

## `update_groq_models.py`

Scans `.py`, `.md`, `.env`, `.json`, `.toml`, and `.env.example` files in Groq-related context (imports, `GROQ_` env vars, paths containing `groq`, config files, and so on).

**Common options:**

| Flag | Description |
|------|-------------|
| `--parent PATH` | Root folder to scan (default: parent of this repo) |
| `--scan` | Report only; do not modify files |
| `--dry-run` | Show planned replacements without writing |
| `--only REPO` | Limit to one or more repo folders (comma-separated or repeatable) |
| `--exclude GLOB` | Skip paths matching a glob |
| `--include-archive` | Include `.hold`, `hold`, and `* - Copy` folders |
| `--quiet` / `-q` | Minimal output |
| `--no-report` | Skip writing the markdown report |
| `--fail-on-find` | Exit with code 1 when deprecated models are found |

**Examples:**

```bash
python update_groq_models.py --parent C:\GitHub
python update_groq_models.py --only aifab-ticker-groq,bse-comb-e
python update_groq_models.py --quiet
```

### Replacement targets

Deprecated IDs are mapped to current Groq models, for example:

- Most text models → `openai/gpt-oss-120b`
- Smaller / fast text models → `openai/gpt-oss-20b`
- Moderation / guard models → `openai/gpt-oss-safeguard-20b`
- TTS models → `canopylabs/orpheus-*`
- Whisper → `whisper-large-v3-turbo`

The full mapping and shutdown dates are defined in `update_groq_models.py`, sourced from [Groq deprecations](https://console.groq.com/docs/deprecations).

## `git_push.py`

**Common options:**

| Flag | Description |
|------|-------------|
| `--migration-report PATH` | Migration report to read (default: `groq_model_migration_report.md`) |
| `--report PATH` | Push report output (default: `git_push_report.md`) |
| `--dry-run` | Show planned commits and pushes without making changes |
| `--only REPO` | Limit to named repo folders |
| `--commit-message TEXT` | Commit message (default: `Migrate deprecated Groq models to current replacements`) |
| `--quiet` / `-q` | Minimal output |
| `--no-report` | Skip writing the push report |

**Examples:**

```bash
python git_push.py --dry-run
python git_push.py --only aifab-ticker-groq,bse-comb-e
```

Repos are skipped when they are not git repositories, have no changes in the listed migration files, or lack an `origin` remote. If a branch is already ahead of remote with no new file changes, the script pushes existing commits only.

## Generated reports

| File | Produced by | Contents |
|------|-------------|----------|
| `groq_model_migration_report.md` | `update_groq_models.py` | Affected repos grouped by deprecation urgency, model mappings, and file links |
| `git_push_report.md` | `git_push.py` | Per-repo commit/push status, branch, remote, and errors |

These reports are local artifacts and are not intended to be committed to this repository.
