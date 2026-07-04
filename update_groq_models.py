"""Scan repos for deprecated Groq model IDs and migrate to current replacements.

Source: https://console.groq.com/docs/deprecations

Examples:
    python groq-update-repos/update_groq_models.py --scan
    python groq-update-repos/update_groq_models.py --dry-run
    python groq-update-repos/update_groq_models.py
    python groq-update-repos/update_groq_models.py --quiet
    python groq-update-repos/update_groq_models.py --only aifab-ticker-groq,bse-comb-e
    python groq-update-repos/update_groq_models.py --parent C:\\GitHub
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path


DEFAULT_TEXT_MODEL = "openai/gpt-oss-120b"
FAST_TEXT_MODEL = "openai/gpt-oss-20b"
MODERATION_MODEL = "openai/gpt-oss-safeguard-20b"

GROQ_DEPRECATED_REPLACEMENTS: dict[str, str] = {
    "llama-3.3-70b-versatile": DEFAULT_TEXT_MODEL,
    "lllama-3.3-70b-versatile": DEFAULT_TEXT_MODEL,
    "llama-3.1-8b-instant": FAST_TEXT_MODEL,
    "qwen/qwen3-32b": DEFAULT_TEXT_MODEL,
    "meta-llama/llama-4-scout-17b-16e-instruct": DEFAULT_TEXT_MODEL,
    "llama-3.2-90b-vision-preview": DEFAULT_TEXT_MODEL,
    "llama-3.2-90b-text-preview": DEFAULT_TEXT_MODEL,
    "llama-3.2-11b-vision-preview": DEFAULT_TEXT_MODEL,
    "llama-3.2-11b-text-preview": FAST_TEXT_MODEL,
    "llama-3.1-70b-versatile": DEFAULT_TEXT_MODEL,
    "llama-3.1-70b-specdec": DEFAULT_TEXT_MODEL,
    "llama3-70b-8192": DEFAULT_TEXT_MODEL,
    "llama3-8b-8192": FAST_TEXT_MODEL,
    "meta-llama/llama-4-maverick-17b-128e-instruct": DEFAULT_TEXT_MODEL,
    "moonshotai/kimi-k2-instruct-0905": DEFAULT_TEXT_MODEL,
    "moonshotai/kimi-k2-instruct": DEFAULT_TEXT_MODEL,
    "meta-llama/llama-guard-4-12b": MODERATION_MODEL,
    "llama-guard-3-8b": MODERATION_MODEL,
    "deepseek-r1-distill-llama-70b": DEFAULT_TEXT_MODEL,
    "deepseek-r1-distill-qwen-32b": DEFAULT_TEXT_MODEL,
    "deepseek-r1-distill-llama-70b-specdec": DEFAULT_TEXT_MODEL,
    "mistral-saba-24b": DEFAULT_TEXT_MODEL,
    "qwen-qwq-32b": DEFAULT_TEXT_MODEL,
    "qwen-2.5-32b": DEFAULT_TEXT_MODEL,
    "qwen-2.5-coder-32b": DEFAULT_TEXT_MODEL,
    "mixtral-8x7b-32768": DEFAULT_TEXT_MODEL,
    "gemma2-9b-it": FAST_TEXT_MODEL,
    "gemma-7b-it": FAST_TEXT_MODEL,
    "llava-v1.5-7b-4096-preview": DEFAULT_TEXT_MODEL,
    "llama-3.2-1b-preview": FAST_TEXT_MODEL,
    "llama-3.2-3b-preview": FAST_TEXT_MODEL,
    "llama-3.3-70b-specdec": DEFAULT_TEXT_MODEL,
    "llama3-groq-8b-8192-tool-use-preview": DEFAULT_TEXT_MODEL,
    "llama3-groq-70b-8192-tool-use-preview": DEFAULT_TEXT_MODEL,
    "playai-tts": "canopylabs/orpheus-v1-english",
    "playai-tts-arabic": "canopylabs/orpheus-arabic-saudi",
    "distil-whisper-large-v3-en": "whisper-large-v3-turbo",
}

DEPRECATION_SHUTDOWN_DATES: dict[str, str] = {
    "qwen/qwen3-32b": "2026-07-17",
    "meta-llama/llama-4-scout-17b-16e-instruct": "2026-07-17",
    "llama-3.3-70b-versatile": "2026-08-16",
    "lllama-3.3-70b-versatile": "2026-08-16",
    "llama-3.1-8b-instant": "2026-08-16",
    "meta-llama/llama-4-maverick-17b-128e-instruct": "2026-03-09",
    "moonshotai/kimi-k2-instruct-0905": "2026-04-15",
    "moonshotai/kimi-k2-instruct": "2025-10-10",
    "meta-llama/llama-guard-4-12b": "2026-03-05",
    "llama-guard-3-8b": "2025-06-06",
    "llama-3.2-90b-vision-preview": "2025-04-14",
    "llama-3.2-90b-text-preview": "2024-11-25",
    "llama3-70b-8192": "2025-08-30",
    "llama3-8b-8192": "2025-08-30",
    "llama-3.1-70b-versatile": "2025-01-24",
    "deepseek-r1-distill-llama-70b": "2025-10-02",
    "playai-tts": "2025-12-31",
    "playai-tts-arabic": "2025-12-31",
    "distil-whisper-large-v3-en": "2025-08-23",
    "mistral-saba-24b": "2025-07-30",
    "qwen-qwq-32b": "2025-07-14",
    "gemma2-9b-it": "2025-10-08",
    "mixtral-8x7b-32768": "2025-03-20",
}

DISPLAY_LABEL_REPLACEMENTS: dict[str, str] = {
    "Llama 3.3 70B Versatile": "GPT OSS 120B",
    "Qwen3 32B": "GPT OSS 120B",
}

VISION_MODEL_IDS = frozenset(
    {
        "llama-3.2-90b-vision-preview",
        "llama-3.2-11b-vision-preview",
        "llava-v1.5-7b-4096-preview",
    }
)

SCAN_EXTENSIONS = frozenset({".py", ".md", ".env", ".json", ".toml"})
ENV_EXAMPLE_SUFFIX = ".env.example"

DEFAULT_SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".cache",
        ".tox",
        "dist",
        "build",
        ".mypy_cache",
        ".pytest_cache",
    }
)

ARCHIVE_DIR_NAMES = frozenset({".hold", "hold"})
SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPT_PATH = Path(__file__).resolve()
DEFAULT_SEARCH_ROOT = SCRIPT_DIR.parent
DEFAULT_REPORT_NAME = "groq_model_migration_report.md"
SKIP_FILE_NAMES = frozenset({"openrouter_models.json", DEFAULT_REPORT_NAME})
DEPRECATIONS_URL = "https://console.groq.com/docs/deprecations"

GROQ_CONFIG_FILE_NAMES = frozenset({"config_vars.py", "groq_models.json"})
GROQ_CONFIG_FILE_SUFFIXES = (".env", ".env.example")

GROQ_CONTEXT_MARKERS = (
    "from groq import",
    "Groq(",
    "ChatGroq",
    "GROQ_",
    "AsyncGroq",
)

REPLACEMENT_KEYS_LONGEST_FIRST = sorted(
    list(GROQ_DEPRECATED_REPLACEMENTS.keys()) + list(DISPLAY_LABEL_REPLACEMENTS.keys()),
    key=len,
    reverse=True,
)


@dataclass
class ModelMatch:
    old_id: str
    new_id: str
    count: int


@dataclass
class FileResult:
    path: Path
    repo_name: str
    matches: list[ModelMatch] = field(default_factory=list)
    updated: bool = False
    error: str = ""


@dataclass
class RepoSummary:
    name: str
    path: Path
    files: list[FileResult] = field(default_factory=list)

    @property
    def has_vision(self) -> bool:
        return any(
            match.old_id in VISION_MODEL_IDS
            for file_result in self.files
            for match in file_result.matches
        )

    @property
    def model_mappings(self) -> dict[str, str]:
        mappings: dict[str, str] = {}
        for file_result in self.files:
            for match in file_result.matches:
                mappings[match.old_id] = match.new_id
        return mappings

    @property
    def earliest_shutdown(self) -> date | None:
        dates: list[date] = []
        for model_id in self.model_mappings:
            shutdown = DEPRECATION_SHUTDOWN_DATES.get(model_id)
            if shutdown:
                dates.append(date.fromisoformat(shutdown))
        return min(dates) if dates else None


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


def normalize_only_paths(root: Path, only_values: list[str]) -> list[Path]:
    paths: list[Path] = []
    for value in only_values:
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = root / candidate
        paths.append(candidate.resolve())
    return paths


def path_matches_exclude(path: Path, root: Path, patterns: list[str]) -> bool:
    rel = path.relative_to(root).as_posix()
    for pattern in patterns:
        if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(path.name, pattern):
            return True
    return False


def is_archive_path(path: Path) -> bool:
    for part in path.parts:
        if part in ARCHIVE_DIR_NAMES:
            return True
        if " - Copy" in part:
            return True
    return False


def should_skip_dir(dir_name: str, include_archive: bool) -> bool:
    if dir_name in DEFAULT_SKIP_DIR_NAMES:
        return True
    if not include_archive and dir_name in ARCHIVE_DIR_NAMES:
        return True
    return False


def is_scannable_file(path: Path) -> bool:
    if path.name in SKIP_FILE_NAMES:
        return False
    if path.name == ".env":
        return True
    if path.suffix.lower() in SCAN_EXTENSIONS:
        return True
    return path.name.endswith(ENV_EXAMPLE_SUFFIX)


def is_groq_config_file(path: Path) -> bool:
    if path.name in GROQ_CONFIG_FILE_NAMES:
        return True
    return any(path.name.endswith(suffix) for suffix in GROQ_CONFIG_FILE_SUFFIXES)


def is_groq_context(text: str, path: Path, *, repo_name: str, groq_repos: frozenset[str]) -> bool:
    lowered_path = path.as_posix().lower()
    if path.name == "groq_models.json":
        return True
    if "groq" in lowered_path:
        return True
    if any(marker in text for marker in GROQ_CONTEXT_MARKERS):
        return True
    if repo_name in groq_repos and is_groq_config_file(path) and find_model_matches(text):
        return True
    if (
        repo_name in groq_repos
        and path.suffix.lower() == ".md"
        and find_model_matches(text)
    ):
        return True
    return False


def discover_groq_repos(root: Path, files: list[Path]) -> frozenset[str]:
    repos: set[str] = set()
    for path in files:
        if path.resolve() == SCRIPT_PATH:
            continue
        try:
            text = read_text_file(path)
        except (OSError, UnicodeDecodeError):
            continue
        lowered_path = path.as_posix().lower()
        if (
            any(marker in text for marker in GROQ_CONTEXT_MARKERS)
            or "groq" in lowered_path
            or path.name == "groq_models.json"
        ):
            repos.add(repo_name_for_path(path, root))
    return frozenset(repos)


def find_model_matches(text: str) -> list[ModelMatch]:
    matches: list[ModelMatch] = []
    for old_id in REPLACEMENT_KEYS_LONGEST_FIRST:
        if old_id in GROQ_DEPRECATED_REPLACEMENTS:
            new_id = GROQ_DEPRECATED_REPLACEMENTS[old_id]
        else:
            new_id = DISPLAY_LABEL_REPLACEMENTS[old_id]
        count = text.count(old_id)
        if count:
            matches.append(ModelMatch(old_id=old_id, new_id=new_id, count=count))
    return matches


def apply_replacements(text: str) -> tuple[str, list[ModelMatch]]:
    updated = text
    matches = find_model_matches(text)
    for match in matches:
        updated = updated.replace(match.old_id, match.new_id)
    return updated, matches


def read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text_file(path: Path, content: str, original: str | None = None) -> None:
    newline = None
    if original is not None and "\r\n" in original:
        newline = "\r\n"
    path.write_text(content, encoding="utf-8", newline=newline)


def repo_name_for_path(file_path: Path, root: Path) -> str:
    try:
        rel = file_path.relative_to(root)
    except ValueError:
        return file_path.parent.name
    parts = rel.parts
    return parts[0] if parts else file_path.parent.name


def scan_file(path: Path, root: Path, groq_repos: frozenset[str]) -> FileResult | None:
    repo_name = repo_name_for_path(path, root)
    try:
        text = read_text_file(path)
    except (OSError, UnicodeDecodeError):
        return None

    if not is_groq_context(text, path, repo_name=repo_name, groq_repos=groq_repos):
        return None

    matches = find_model_matches(text)
    if not matches:
        return None

    return FileResult(path=path, repo_name=repo_name, matches=matches)


def update_file(path: Path, root: Path, groq_repos: frozenset[str], dry_run: bool) -> FileResult:
    repo_name = repo_name_for_path(path, root)
    try:
        text = read_text_file(path)
    except (OSError, UnicodeDecodeError):
        return FileResult(path=path, repo_name=repo_name)

    if not is_groq_context(text, path, repo_name=repo_name, groq_repos=groq_repos):
        return FileResult(path=path, repo_name=repo_name)

    updated_text, matches = apply_replacements(text)
    if not matches:
        return FileResult(path=path, repo_name=repo_name)

    result = FileResult(path=path, repo_name=repo_name, matches=matches)
    if updated_text != text and not dry_run:
        write_text_file(path, updated_text, original=text)
        result.updated = True
    elif updated_text != text:
        result.updated = True
    return result


def iter_scannable_files(
    root: Path,
    *,
    exclude_patterns: list[str],
    only_paths: list[Path],
    include_archive: bool,
) -> list[Path]:
    files: list[Path] = []
    only_resolved = {path.resolve() for path in only_paths}

    def under_only(path: Path) -> bool:
        if not only_resolved:
            return True
        resolved = path.resolve()
        return any(
            resolved == only_path or only_path in resolved.parents
            for only_path in only_resolved
        )

    def walk(current: Path) -> None:
        if not under_only(current):
            return
        try:
            entries = list(current.iterdir())
        except OSError:
            return
        for entry in entries:
            if entry.is_dir():
                if should_skip_dir(entry.name, include_archive):
                    continue
                rel = entry.relative_to(root)
                if not include_archive and is_archive_path(rel):
                    continue
                if path_matches_exclude(entry, root, exclude_patterns):
                    continue
                walk(entry)
                continue
            if not under_only(entry):
                continue
            if path_matches_exclude(entry, root, exclude_patterns):
                continue
            if not include_archive and is_archive_path(entry.relative_to(root)):
                continue
            if not is_scannable_file(entry):
                continue
            if entry.resolve() == SCRIPT_PATH:
                continue
            files.append(entry)

    walk(root)
    return sorted(files)


def group_by_repo(file_results: list[FileResult], root: Path) -> list[RepoSummary]:
    repos: dict[str, RepoSummary] = {}
    for file_result in file_results:
        repo = repos.get(file_result.repo_name)
        if repo is None:
            repo_path = root / file_result.repo_name
            if not repo_path.is_dir():
                repo_path = file_result.path.parent
            repos[file_result.repo_name] = RepoSummary(
                name=file_result.repo_name,
                path=repo_path,
            )
            repo = repos[file_result.repo_name]
        repo.files.append(file_result)
    return sorted(repos.values(), key=lambda item: item.name.lower())


def urgency_bucket(repo: RepoSummary, today: date) -> str:
    shutdown = repo.earliest_shutdown
    if shutdown is None:
        return "Already shut down (fix immediately)"
    if shutdown <= today:
        return "Already shut down (fix immediately)"
    if shutdown <= date(2026, 7, 17):
        return "Urgent (shutdown ≤ 2026-07-17)"
    if shutdown <= date(2026, 8, 16):
        return "Upcoming (shutdown 2026-08-16)"
    return "Other deprecated models"


def relative_link(path: Path, base: Path) -> str:
    return Path(os.path.relpath(path, base)).as_posix()


def build_repo_heading(repo: RepoSummary) -> str:
    suffix = " ⚠ vision" if repo.has_vision else ""
    return f"### {repo.name}{suffix}"


def format_model_lines(repo: RepoSummary) -> list[str]:
    lines: list[str] = []
    for old_id, new_id in sorted(repo.model_mappings.items()):
        shutdown = DEPRECATION_SHUTDOWN_DATES.get(old_id)
        if shutdown:
            lines.append(f"- `{old_id}` → `{new_id}` (shutdown {shutdown})")
        else:
            lines.append(f"- `{old_id}` → `{new_id}`")
    return lines


def write_migration_report(
    repos: list[RepoSummary],
    report_path: Path,
    *,
    mode: str,
    root: Path,
    files_updated: int,
) -> None:
    today = date.today()
    grouped: dict[str, list[RepoSummary]] = {}
    for repo in repos:
        bucket = urgency_bucket(repo, today)
        grouped.setdefault(bucket, []).append(repo)

    bucket_order = [
        "Urgent (shutdown ≤ 2026-07-17)",
        "Upcoming (shutdown 2026-08-16)",
        "Already shut down (fix immediately)",
        "Other deprecated models",
    ]

    total_files = sum(len(repo.files) for repo in repos)
    lines: list[str] = [
        "# Groq model migration report",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"Mode: {mode}",
        f"Source: {DEPRECATIONS_URL}",
        "",
        "## Summary",
        f"- Repos affected: {len(repos)}",
        f"- Files matched: {total_files}",
        f"- Files updated: {files_updated}",
        "",
    ]

    for bucket in bucket_order:
        bucket_repos = grouped.get(bucket)
        if not bucket_repos:
            continue
        lines.append(f"## {bucket}")
        lines.append("")
        for repo in sorted(bucket_repos, key=lambda item: item.name.lower()):
            lines.append(build_repo_heading(repo))
            folder_link = relative_link(repo.path, report_path.parent)
            lines.append(f"- [Open folder in Cursor]({folder_link}/)")
            lines.append(f"- Path: `{repo.path}`")
            lines.extend(format_model_lines(repo))
            lines.append("- Files:")
            for file_result in sorted(repo.files, key=lambda item: str(item.path)):
                if file_result.error:
                    lines.append(
                        f"  - `{file_result.path}` — error: {file_result.error}"
                    )
                    continue
                link = relative_link(file_result.path, report_path.parent)
                lines.append(f"  - [{link}]({link})")
            lines.append("")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    write_text_file(report_path, "\n".join(lines).rstrip() + "\n")


def print_file_result(file_result: FileResult, root: Path, verbose: bool, *, applied: bool) -> None:
    rel = file_result.path.relative_to(root)
    if file_result.error:
        print(f"[ERROR] {rel}: {file_result.error}")
        return
    model_bits = ", ".join(
        f"{match.old_id} ({match.count}x) -> {match.new_id}"
        for match in file_result.matches
    )
    if applied and file_result.updated:
        action = "updated"
    elif file_result.updated:
        action = "would update"
    else:
        action = "matched"
    print(f"[MATCH] {rel}: {action} — {model_bits}")
    if verbose:
        for match in file_result.matches:
            print(f"         {match.old_id} -> {match.new_id} x{match.count}")


def log_skipped_file(path: Path, root: Path, reason: str, verbose: bool) -> None:
    if not verbose:
        return
    rel = path.relative_to(root)
    print(f"[SKIP] {rel}: {reason}")


def print_console_summary(repos: list[RepoSummary], mode: str, *, verbose: bool) -> None:
    total_files = sum(len(repo.files) for repo in repos)
    total_replacements = sum(
        match.count
        for repo in repos
        for file_result in repo.files
        for match in file_result.matches
    )
    print()
    print(f"Summary ({mode}): {len(repos)} repos, {total_files} files, {total_replacements} replacements.")
    if verbose and repos:
        print()
        print("Repos:")
        for repo in repos:
            file_count = len(repo.files)
            vision = " [vision]" if repo.has_vision else ""
            bucket = urgency_bucket(repo, date.today())
            print(f"  - {repo.name}{vision}: {file_count} file(s) — {bucket}")
            for file_result in sorted(repo.files, key=lambda item: str(item.path)):
                rel = file_result.path.name
                if file_result.error:
                    print(f"      {rel}: ERROR {file_result.error}")
                    continue
                models = ", ".join(
                    f"{match.old_id} -> {match.new_id}"
                    for match in file_result.matches
                )
                status = "updated" if file_result.updated else "matched"
                print(f"      {rel}: {status} ({models})")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan repos for deprecated Groq model IDs and migrate replacements.",
    )
    parser.add_argument(
        "--parent",
        type=Path,
        help=f"Root folder to scan (default: {DEFAULT_SEARCH_ROOT})",
    )
    parser.add_argument(
        "--scan",
        action="store_true",
        help="Report matches only; do not modify files",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show planned replacements without writing files",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=True,
        help="Print detailed progress and per-repo breakdown (default: on)",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Minimal output (summary and matches only)",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="Limit to named repo folders (repeatable or comma-separated)",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Skip paths matching a glob (repeatable or comma-separated)",
    )
    parser.add_argument(
        "--include-archive",
        action="store_true",
        help="Include .hold, hold, and '* - Copy' folders",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help=f"Markdown report path (default: {DEFAULT_REPORT_NAME} next to script)",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Skip writing the markdown report",
    )
    parser.add_argument(
        "--fail-on-find",
        action="store_true",
        help="Exit with code 1 when deprecated models are found",
    )
    return parser.parse_args(argv)


def resolve_verbose(args: argparse.Namespace) -> bool:
    return args.verbose and not args.quiet


def resolve_search_root(args: argparse.Namespace) -> Path:
    if args.parent is not None:
        return args.parent.resolve()
    return DEFAULT_SEARCH_ROOT


def resolve_report_path(args: argparse.Namespace) -> Path:
    if args.report is not None:
        return args.report.resolve()
    return (SCRIPT_DIR / DEFAULT_REPORT_NAME).resolve()


def resolve_mode(args: argparse.Namespace) -> str:
    if args.scan:
        return "scan"
    if args.dry_run:
        return "dry-run"
    return "apply"


def process_files(
    root: Path,
    files: list[Path],
    groq_repos: frozenset[str],
    *,
    scan_only: bool,
    dry_run: bool,
    verbose: bool,
) -> list[FileResult]:
    results: list[FileResult] = []
    applied = not scan_only and not dry_run
    for path in files:
        if path.resolve() == SCRIPT_PATH:
            continue
        if scan_only:
            file_result = scan_file(path, root, groq_repos)
            if file_result is not None:
                results.append(file_result)
                print_file_result(file_result, root, verbose, applied=False)
            continue

        file_result = update_file(path, root, groq_repos, dry_run=dry_run)
        if file_result.matches or file_result.error:
            results.append(file_result)
            print_file_result(file_result, root, verbose, applied=applied)
    return results


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    root = resolve_search_root(args)
    verbose = resolve_verbose(args)
    if not root.is_dir():
        print(f"Path is not a directory: {root}", file=sys.stderr)
        return 1

    exclude_patterns = split_csv_values(args.exclude)
    only_paths = normalize_only_paths(root, split_csv_values(args.only))
    mode = resolve_mode(args)
    scan_only = args.scan
    dry_run = args.dry_run or args.scan

    log_verbose(verbose, f"Mode: {mode}")
    log_verbose(verbose, f"Scanning under {root}")
    if only_paths:
        log_verbose(verbose, f"Only: {', '.join(str(p) for p in only_paths)}")
    if exclude_patterns:
        log_verbose(verbose, f"Exclude: {', '.join(exclude_patterns)}")
    if args.include_archive:
        log_verbose(verbose, "Including archive folders (.hold, hold, * - Copy*)")

    files = iter_scannable_files(
        root,
        exclude_patterns=exclude_patterns,
        only_paths=only_paths,
        include_archive=args.include_archive,
    )
    log_verbose(verbose, f"Checking {len(files)} candidate files")
    groq_repos = discover_groq_repos(root, files)
    log_verbose(verbose, f"Groq repos detected ({len(groq_repos)}): {', '.join(sorted(groq_repos)) or '(none)'}")

    file_results = process_files(
        root,
        files,
        groq_repos,
        scan_only=scan_only,
        dry_run=dry_run,
        verbose=verbose,
    )
    repos = group_by_repo(file_results, root)
    files_updated = sum(1 for result in file_results if result.updated and not scan_only)

    print_console_summary(repos, mode, verbose=verbose)

    if repos and not args.no_report:
        report_path = resolve_report_path(args)
        write_migration_report(
            repos,
            report_path,
            mode=mode,
            root=root,
            files_updated=files_updated if not scan_only else 0,
        )
        print(f"Report written to {report_path}")

    if not repos:
        print("No deprecated Groq models found in Groq-context files.")
        return 0

    if args.fail_on_find:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
