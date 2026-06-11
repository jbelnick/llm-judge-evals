#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys


SECRET_PATTERNS = {
    "openai_style_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{30,}\b"),
    "generic_assignment_secret": re.compile(r"(?i)\b(api[_-]?key|token|secret|password)\s*[:=]\s*['\"][^'\"]{8,}['\"]"),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "private_home_path": re.compile(r"/Users/[A-Za-z0-9._-]+/"),
    "private_log_filename": re.compile(r"\b(?:agent|gateway|errors)\.log\b", re.IGNORECASE),
}
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".venv", "venv"}
BINARY_SUFFIXES = {".ico", ".png", ".jpg", ".jpeg", ".gif", ".pdf", ".m4a", ".mp3", ".mp4"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan project files for public-safety issues.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--term", action="append", default=[], help="Banned term supplied at runtime.")
    args = parser.parse_args()

    env_terms = [
        term.strip()
        for term in re.split(r"[,:\n]", os_environ_terms())
        if term.strip()
    ]
    terms = [term for term in [*args.term, *env_terms] if term]
    findings = scan(args.root, terms)
    if findings:
        for finding in findings:
            print(finding, file=sys.stderr)
        return 1
    print(f"public safety scan ok: files={len(list(iter_files(args.root)))} terms={len(terms)}")
    return 0


def scan(root: Path, banned_terms: list[str]) -> list[str]:
    findings: list[str] = []
    for path in iter_files(root):
        text = read_text(path)
        if text is None:
            continue
        relative = path.relative_to(root)
        for term in banned_terms:
            if term.casefold() in text.casefold():
                findings.append(f"{relative}: banned term present")
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                findings.append(f"{relative}: possible secret pattern {label}")
    return findings


def iter_files(root: Path):
    tracked = tracked_files(root)
    if tracked:
        for relative in tracked:
            path = root / relative
            if path.is_file() and not should_skip(path):
                yield path
        return

    for path in root.rglob("*"):
        if path.is_file() and not should_skip(path):
            yield path


def tracked_files(root: Path) -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return []
    return [Path(raw.decode("utf-8")) for raw in result.stdout.split(b"\0") if raw]


def should_skip(path: Path) -> bool:
    if path.suffix.lower() in BINARY_SUFFIXES:
        return True
    return any(part in SKIP_DIRS for part in path.parts)


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def os_environ_terms() -> str:
    import os

    return os.environ.get("PUBLIC_SAFETY_TERMS", "")


if __name__ == "__main__":
    raise SystemExit(main())
