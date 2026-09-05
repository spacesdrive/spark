"""
Fetch the Supabase values Spark needs and write them into the local ``.env``.

Secrets go from the Supabase API straight into ``.env``, which is gitignored.
Nothing is printed: the script reports which keys it set, never their values.

It also registers Spark's OAuth redirect URLs. That edit is additive. Existing
entries belonging to other applications in the same project are preserved, and
``site_url`` is never touched.

Usage:
    python -m ops.supabase.env            # report what would change
    python -m ops.supabase.env --apply
"""

from __future__ import annotations

import argparse
import re
import secrets
from pathlib import Path

from ops.paths import ROOT

from ops.supabase.push import call

SPARK_REDIRECTS = [
    "https://spark.spacesdrive.cc/**",
    "http://127.0.0.1:5173/**",
    "http://localhost:5173/**",
]

def set_env(path: Path, values: dict[str, str]) -> list[str]:
    """Rewrite only the named keys, leaving every other line untouched."""
    text = path.read_text() if path.exists() else ""
    changed = []
    for key, value in values.items():
        if not value:
            continue
        line = f"{key}={value}"
        pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
        if pattern.search(text):
            existing = pattern.search(text).group(0)
            if existing != line:
                text = pattern.sub(lambda _m: line, text, count=1)
                changed.append(key)
        else:
            text = text.rstrip("\n") + f"\n{line}\n"
            changed.append(key)
    path.write_text(text)
    return changed

def existing_env(path: Path, key: str) -> str:
    """Read one key out of .env so we never regenerate a secret already in use."""
    if not path.exists():
        return ""
    m = re.search(rf"^{re.escape(key)}=(.*)$", path.read_text(), re.MULTILINE)
    return m.group(1).strip() if m else ""

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    ref = call("/projects")[0]["id"]
    url = f"https://{ref}.supabase.co"

    keys = call(f"/projects/{ref}/api-keys?reveal=true")
    anon = next(
        (k.get("api_key") for k in keys if k.get("name") in {"anon", "anon_key"}), ""
    )
    print(f"project      {ref}")
    print(f"url          {url}")
    print(f"anon key     {'retrieved' if anon else 'NOT FOUND'} "
          f"(names seen: {[k.get('name') for k in keys]})")

    auth = call(f"/projects/{ref}/config/auth")
    current = [u for u in (auth.get("uri_allow_list") or "").split(",") if u]
    missing = [u for u in SPARK_REDIRECTS if u not in current]
    print(f"redirects    {len(current)} configured, {len(missing)} to add: {missing}")
    print(f"google auth  {'enabled' if auth.get('external_google_enabled') else 'DISABLED'}")
    print(f"site_url     {auth.get('site_url')} (left unchanged)")

    if not args.apply:
        print("\nDry run. Pass --apply to write .env and register redirects.")
        return 0

    # SESSION_SECRET keys the HMAC that hashes API keys. Regenerating it would
    # invalidate every key an organization has already issued, so it is only
    # created when there is not one already.
    session_secret = existing_env(ROOT / ".env", "SESSION_SECRET") or secrets.token_urlsafe(48)

    changed = set_env(
        ROOT / ".env",
        {
            "SUPABASE_URL": url,
            "SUPABASE_ANON_KEY": anon,
            "SESSION_SECRET": session_secret,
        },
    )
    print(f"\n.env updated: {changed or 'no change needed'}")

    if missing:
        call(
            f"/projects/{ref}/config/auth",
            "PATCH",
            {"uri_allow_list": ",".join(current + missing)},
        )
        print(f"redirects registered: {missing}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
