"""Commit and push Groq model migration changes to GitHub.

Reads groq_model_migration_report.md to determine which repos to update,
commits the listed files, pushes to origin, and writes a push report.

Examples:
    python groq-update-repos/git_push.py --dry-run
    python groq-update-repos/git_push.py
    python groq-update-repos/git_push.py --only aifab-ticker-groq,bse-comb-e
    python groq-update-repos/git_push.py --quiet
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_MIGRATION_REPORT = SCRIPT_DIR / "groq_model_migration_report.md"
DEFAULT_PUSH_REPORT = SCRIPT_DIR / "git_push_report.md"
DEFAULT_COMMIT_MESSAGE = "Migrate deprecated Groq models to current replacements"

REPO_HEADING = re.compile(r"^### (.+?)(?: ⚠ vision)?$")
PATH_LINE = re.compile(r"^- Path: `(.+)`$")
FILE_LINK_LINE = re.compile(r"^  - \[([^\]]+)\]\([^)]+\)$")
FILE_ERROR_LINE = re.compile(r"^  - `(.+?)` — error:")


@dataclass
class RepoEntry:
    name: str
    path: Path
    files: list[Path] = field(default_factory=list)


@dataclass
class RepoPushResult:
    entry: RepoEntry
    status: str
    branch: str = ""
    remote_url: str = ""
    commit_hash: str = ""
    files_committed: list[str] = field(default_factory=list)
    message: str = ""
    error: str = ""


def log_verbose(enabled: bool, message: str) -> None:
    if enabled:
        print(message, flush=True)


def split_csv_values(values: list[str]) -> list[str]:
    items: list[str] = []
    for value in values:
        for part in value.split(","):
            part = part.strip()
            if part:
                items.append(part)
    return items


def run_git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    command = ["git", *args]
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return subprocess.CompletedProcess(
            command,
            returncode=127,
            stdout="",
            stderr="git executable not found",
        )


def format_git_output(result: subprocess.CompletedProcess[str]) -> str:
    parts = [part.strip() for part in (result.stdout, result.stderr) if part.strip()]
    return "\n".join(parts) if parts else "(no output)"


def is_git_repo(path: Path) -> bool:
    result = run_git(path, "rev-parse", "--git-dir")
    return result.returncode == 0


def get_current_branch(repo_path: Path) -> str:
    result = run_git(repo_path, "branch", "--show-current")
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def get_remote_url(repo_path: Path) -> str:
    result = run_git(repo_path, "remote", "get-url", "origin")
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def resolve_repo_file(repo_path: Path, file_ref: str) -> Path:
    candidate = Path(file_ref)
    if candidate.is_absolute():
        return candidate
    if candidate.parts and candidate.parts[0] == repo_path.name:
        return repo_path / Path(*candidate.parts[1:])
    return repo_path / candidate


def file_has_changes(repo_path: Path, file_path: Path) -> bool:
    if not file_path.is_file():
        return False
    rel = file_path.relative_to(repo_path).as_posix()
    result = run_git(repo_path, "status", "--porcelain", "--", rel)
    if result.returncode != 0:
        return False
    return bool(result.stdout.strip())


def stage_files(repo_path: Path, files: list[Path]) -> tuple[list[str], str]:
    staged: list[str] = []
    for file_path in files:
        if not file_path.is_file():
            continue
        rel = file_path.relative_to(repo_path).as_posix()
        result = run_git(repo_path, "add", "--", rel)
        if result.returncode != 0:
            return staged, format_git_output(result)
        staged.append(rel)
    return staged, ""


def commit_changes(repo_path: Path, message: str) -> tuple[str, str]:
    result = run_git(repo_path, "commit", "-m", message)
    if result.returncode != 0:
        return "", format_git_output(result)
    hash_result = run_git(repo_path, "rev-parse", "--short", "HEAD")
    commit_hash = hash_result.stdout.strip() if hash_result.returncode == 0 else ""
    return commit_hash, ""


def push_branch(repo_path: Path, branch: str) -> str:
    result = run_git(repo_path, "push", "origin", branch)
    if result.returncode != 0:
        return format_git_output(result)
    return ""


def is_ahead_of_remote(repo_path: Path, branch: str) -> bool:
    result = run_git(repo_path, "status", "--porcelain=v1", "-b")
    if result.returncode != 0:
        return False
    first_line = result.stdout.splitlines()[0] if result.stdout else ""
    return "ahead" in first_line


def parse_migration_report(report_path: Path) -> list[RepoEntry]:
    text = report_path.read_text(encoding="utf-8")
    entries: list[RepoEntry] = []
    current: RepoEntry | None = None
    in_files_section = False

    for line in text.splitlines():
        heading = REPO_HEADING.match(line)
        if heading:
            if current is not None:
                entries.append(current)
            current = RepoEntry(name=heading.group(1).strip(), path=Path())
            in_files_section = False
            continue

        if current is None:
            continue

        path_match = PATH_LINE.match(line)
        if path_match:
            current.path = Path(path_match.group(1))
            in_files_section = False
            continue

        if line.strip() == "- Files:":
            in_files_section = True
            continue

        if in_files_section:
            link_match = FILE_LINK_LINE.match(line)
            if link_match:
                current.files.append(resolve_repo_file(current.path, link_match.group(1)))
                continue
            error_match = FILE_ERROR_LINE.match(line)
            if error_match:
                current.files.append(resolve_repo_file(current.path, error_match.group(1)))

    if current is not None:
        entries.append(current)

    return [entry for entry in entries if entry.path]


def filter_entries(entries: list[RepoEntry], only_names: set[str]) -> list[RepoEntry]:
    if not only_names:
        return entries
    return [entry for entry in entries if entry.name in only_names]


def collect_changed_files(entry: RepoEntry) -> list[Path]:
    changed: list[Path] = []
    for file_path in entry.files:
        if file_has_changes(entry.path, file_path):
            changed.append(file_path)
    return changed


def process_repo(
    entry: RepoEntry,
    *,
    dry_run: bool,
    commit_message: str,
    verbose: bool,
) -> RepoPushResult:
    result = RepoPushResult(entry=entry, status="pending")

    if not entry.path.is_dir():
        result.status = "skipped"
        result.message = "repo path does not exist"
        return result

    if not is_git_repo(entry.path):
        result.status = "skipped"
        if (entry.path / ".git").exists():
            result.message = "invalid or broken git repository"
        else:
            result.message = "not a git repository"
        return result

    result.branch = get_current_branch(entry.path)
    result.remote_url = get_remote_url(entry.path)

    if not result.branch:
        result.status = "failed"
        result.error = "could not determine current branch"
        return result

    if not result.remote_url:
        result.status = "failed"
        result.error = "no origin remote configured"
        return result

    changed_files = collect_changed_files(entry)
    if not changed_files:
        if is_ahead_of_remote(entry.path, result.branch):
            result.status = "push_only"
            log_verbose(verbose, f"[PUSH] {entry.name}: no file changes; branch is ahead of remote")
            if dry_run:
                result.message = "would push existing commits"
                return result
            push_error = push_branch(entry.path, result.branch)
            if push_error:
                result.status = "failed"
                result.error = push_error
                return result
            hash_result = run_git(entry.path, "rev-parse", "--short", "HEAD")
            result.commit_hash = hash_result.stdout.strip() if hash_result.returncode == 0 else ""
            result.status = "pushed"
            result.message = "pushed existing commits"
            return result

        result.status = "skipped"
        result.message = "no changes in migration files"
        return result

    rel_paths = [path.relative_to(entry.path).as_posix() for path in changed_files]
    result.files_committed = rel_paths
    log_verbose(
        verbose,
        f"[COMMIT] {entry.name}: {len(rel_paths)} file(s) — {', '.join(rel_paths)}",
    )

    if dry_run:
        result.status = "dry-run"
        result.message = "would commit and push"
        return result

    _, stage_error = stage_files(entry.path, changed_files)
    if stage_error:
        result.status = "failed"
        result.error = f"git add failed: {stage_error}"
        return result

    commit_hash, commit_error = commit_changes(entry.path, commit_message)
    if commit_error:
        result.status = "failed"
        result.error = f"git commit failed: {commit_error}"
        return result

    result.commit_hash = commit_hash
    push_error = push_branch(entry.path, result.branch)
    if push_error:
        result.status = "failed"
        result.error = f"committed {commit_hash} but push failed: {push_error}"
        return result

    result.status = "pushed"
    result.message = f"committed and pushed {commit_hash}"
    return result


def write_push_report(
    results: list[RepoPushResult],
    report_path: Path,
    *,
    mode: str,
    source_report: Path,
) -> None:
    pushed = sum(1 for item in results if item.status == "pushed")
    push_only = sum(1 for item in results if item.status == "push_only")
    skipped = sum(1 for item in results if item.status == "skipped")
    failed = sum(1 for item in results if item.status == "failed")
    dry_run = sum(1 for item in results if item.status == "dry-run")

    lines: list[str] = [
        "# Groq model git push report",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"Mode: {mode}",
        f"Source: `{source_report}`",
        "",
        "## Summary",
        f"- Repos processed: {len(results)}",
        f"- Pushed: {pushed + push_only}",
        f"- Committed and pushed: {pushed}",
        f"- Pushed existing commits: {push_only}",
        f"- Skipped: {skipped}",
        f"- Failed: {failed}",
    ]
    if dry_run:
        lines.append(f"- Would push (dry-run): {dry_run}")
    lines.append("")

    status_order = {"failed": 0, "pushed": 1, "push_only": 2, "dry-run": 3, "skipped": 4, "pending": 5}
    sorted_results = sorted(
        results,
        key=lambda item: (status_order.get(item.status, 99), item.entry.name.lower()),
    )

    lines.append("## Results")
    lines.append("")
    for item in sorted_results:
        entry = item.entry
        lines.append(f"### {entry.name}")
        lines.append(f"- Path: `{entry.path}`")
        lines.append(f"- Status: **{item.status}**")
        if item.branch:
            lines.append(f"- Branch: `{item.branch}`")
        if item.remote_url:
            lines.append(f"- Remote: `{item.remote_url}`")
        if item.commit_hash:
            lines.append(f"- Commit: `{item.commit_hash}`")
        if item.files_committed:
            lines.append("- Files committed:")
            for file_path in item.files_committed:
                lines.append(f"  - `{file_path}`")
        if item.message:
            lines.append(f"- Detail: {item.message}")
        if item.error:
            lines.append(f"- Error: {item.error}")
        lines.append("")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def print_console_summary(results: list[RepoPushResult], mode: str) -> None:
    pushed = sum(1 for item in results if item.status in {"pushed", "push_only"})
    skipped = sum(1 for item in results if item.status == "skipped")
    failed = sum(1 for item in results if item.status == "failed")
    dry_run = sum(1 for item in results if item.status == "dry-run")
    print()
    print(
        f"Summary ({mode}): {len(results)} repos, "
        f"{pushed} pushed, {skipped} skipped, {failed} failed"
        + (f", {dry_run} dry-run" if dry_run else "")
        + ".",
    )
    for item in results:
        detail = item.message or item.error
        suffix = f" — {detail}" if detail else ""
        print(f"  - {item.entry.name}: {item.status}{suffix}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Commit and push Groq model migration changes to GitHub.",
    )
    parser.add_argument(
        "--migration-report",
        type=Path,
        default=DEFAULT_MIGRATION_REPORT,
        help=f"Migration report to read (default: {DEFAULT_MIGRATION_REPORT.name})",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_PUSH_REPORT,
        help=f"Push report output path (default: {DEFAULT_PUSH_REPORT.name})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show planned commits and pushes without making changes",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="Limit to named repo folders (repeatable or comma-separated)",
    )
    parser.add_argument(
        "--commit-message",
        default=DEFAULT_COMMIT_MESSAGE,
        help="Commit message for migration changes",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=True,
        help="Print detailed progress (default: on)",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Minimal output",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Skip writing the push report",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    verbose = args.verbose and not args.quiet
    migration_report = args.migration_report.resolve()
    mode = "dry-run" if args.dry_run else "apply"

    if not migration_report.is_file():
        print(f"Migration report not found: {migration_report}", file=sys.stderr)
        return 1

    entries = parse_migration_report(migration_report)
    only_names = set(split_csv_values(args.only))
    entries = filter_entries(entries, only_names)

    if not entries:
        print("No repos found in migration report.", file=sys.stderr)
        return 1

    log_verbose(verbose, f"Mode: {mode}")
    log_verbose(verbose, f"Reading repos from {migration_report}")
    log_verbose(verbose, f"Repos to process: {len(entries)}")

    results: list[RepoPushResult] = []
    for entry in entries:
        log_verbose(verbose, f"Processing {entry.name} ({entry.path})")
        result = process_repo(
            entry,
            dry_run=args.dry_run,
            commit_message=args.commit_message,
            verbose=verbose,
        )
        results.append(result)

    print_console_summary(results, mode)

    if not args.no_report:
        report_path = args.report.resolve()
        write_push_report(
            results,
            report_path,
            mode=mode,
            source_report=migration_report,
        )
        print(f"Report written to {report_path}")

    if any(item.status == "failed" for item in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
