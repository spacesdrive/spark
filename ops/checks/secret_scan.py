"""
Scan the project for credentials that must never be committed.

This looks at files Git would actually track, plus the built frontend bundle,
because a secret that reaches ``web/dist`` is served to every visitor.

The scan reports the file and line number and a short description. It never
prints the matched value, so running it can not itself leak anything.

Usage:
    python -m ops.checks.secret_scan
Exit code 1 means something was found.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from ops.paths import ROOT

#: Each pattern describes a credential shape, not a value.
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("AWS secret access key", re.compile(r"aws_secret_access_key\s*=\s*\S+", re.I)),
    ("private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----")),
    ("Supabase personal access token", re.compile(r"\bsbp_[0-9a-f]{40}\b")),
    ("Supabase service role JWT", re.compile(r"\bey[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}")),
    ("Cloudflare API token", re.compile(r"\bcfat[A-Za-z0-9_.-]{20,}")),
    ("Cloudflare global key", re.compile(r"\b[0-9a-f]{37}\b")),
    ("Google OAuth client secret", re.compile(r"\bGOCSPX-[A-Za-z0-9_-]{20,}")),
    ("Spark live API key", re.compile(r"\bsk_live_[A-Za-z0-9]{16,}")),
    # The value must look like a credential literal. Excluding whitespace and
    # path separators keeps shell snippets such as "grep '^SESSION_SECRET=' path"
    # from matching, without weakening the check on an actual embedded secret.
    ("generic hardcoded password", re.compile(
        r"(?:password|passwd|secret)\s*[:=]\s*[\"'][^\"'{$<\s/\\]{8,}[\"']", re.I)),
]

#: Placeholders and test fixtures that are meant to look like secrets.
ALLOWED = re.compile(
    r"your[-_]|example|placeholder|changeme|xxx|\.\.\.|<[a-z]|\$\{|"
    r"not[-_]a[-_]real|not[-_]used[-_]in[-_]production|test[-_]secret|"
    r"definitely[-_]not[-_]real|whsec_example|sk_test_",
    re.I,
)

SKIP_SUFFIX = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".woff",
               ".woff2", ".ttf", ".parquet", ".npy", ".joblib", ".pt", ".zip"}


def tracked_files() -> list[Path]:
    """
    Every file Git would put in a commit, plus the built bundle if one exists.

    Deliberately not plain ``git ls-files``: in a repository with no commits
    yet that returns nothing, and the scan would pass by scanning almost
    nothing. ``--others --exclude-standard`` adds the untracked but not
    ignored files, which is exactly the set at risk of a first commit.
    """
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT, capture_output=True, text=True,
    ).stdout.split("\n")
    files = [ROOT / f for f in out if f.strip()]

    dist = ROOT / "web" / "dist"
    if dist.exists():
        files += [p for p in dist.rglob("*") if p.is_file()]
    return files


def scan(path: Path) -> list[tuple[int, str]]:
    if path.suffix.lower() in SKIP_SUFFIX or not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    hits = []
    for number, line in enumerate(text.splitlines(), start=1):
        if ALLOWED.search(line):
            continue
        for label, pattern in PATTERNS:
            if pattern.search(line):
                hits.append((number, label))
    return hits


def main() -> int:
    print("Scanning tracked files and the built dashboard.\n")

    findings: list[str] = []
    for path in tracked_files():
        for number, label in scan(path):
            rel = path.relative_to(ROOT)
            findings.append(f"  {rel}:{number}  {label}")

    print("Secret files must be ignored by Git:")
    ignored_ok = True
    # The trailing slash matters. `git check-ignore` decides whether a bare
    # name is a directory by looking at the disk, so the key directories, which
    # exist on a maintainer's machine and never on a CI runner, matched the
    # `.aws-keys/` pattern locally and reported NOT IGNORED in CI. Naming them
    # as directories states the intent and gives the same answer everywhere.
    for name in (".env", ".aws-keys/", ".cloudflare-keys/", ".supabase-keys/"):
        r = subprocess.run(["git", "check-ignore", "-q", name], cwd=ROOT)
        state = "ignored" if r.returncode == 0 else "NOT IGNORED"
        if r.returncode != 0:
            ignored_ok = False
        print(f"  {name:20} {state}")

    print("\nSecret files must not be tracked:")
    tracked = subprocess.run(
        ["git", "ls-files", ".env", ".aws-keys", ".cloudflare-keys", ".supabase-keys"],
        cwd=ROOT, capture_output=True, text=True,
    ).stdout.strip()
    print(f"  {tracked or 'none tracked'}")

    print("\nCredential patterns:")
    if findings:
        for f in findings:
            print(f)
    else:
        print("  none found")

    failed = bool(findings) or not ignored_ok or bool(tracked)
    print("\n" + ("FAILED" if failed else "PASSED"))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
