"""
Read-only inspection of the Supabase project Spark will use.

Run before any schema push so we know what is already there and never write
over somebody else's tables. Prints table names and key names only, never key
values.

Usage:  python -m ops.supabase.inspect
"""
from __future__ import annotations

import json
import sys
import urllib.request

from ops.paths import ROOT

API = "https://api.supabase.com/v1"


def token() -> str:
    return (ROOT / ".supabase-keys" / "access-token.pem").read_text().strip()


def call(path: str, method: str = "GET", body: dict | None = None):
    req = urllib.request.Request(
        f"{API}{path}",
        method=method,
        data=json.dumps(body).encode() if body else None,
        headers={
            "Authorization": f"Bearer {token()}",
            "Content-Type": "application/json",
            # Supabase rejects the default urllib agent with a bare 403.
            "User-Agent": "spark-ops/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def main() -> int:
    projects = call("/projects")
    print("projects:")
    for p in projects:
        print(f"  {p['id']}  {p['name']}  {p['region']}  {p['status']}")

    ref = sys.argv[1] if len(sys.argv) > 1 else projects[0]["id"]
    print(f"\ninspecting {ref}")

    rows = call(
        f"/projects/{ref}/database/query",
        "POST",
        {"query": "select table_schema, table_name from information_schema.tables "
                  "where table_schema not in ('pg_catalog','information_schema') "
                  "order by table_schema, table_name;"},
    )
    print(f"\nexisting tables ({len(rows)}):")
    for r in rows:
        print(f"  {r['table_schema']}.{r['table_name']}")

    print("\nauth providers configured:")
    try:
        cfg = call(f"/projects/{ref}/config/auth")
        for k, v in sorted(cfg.items()):
            if k.startswith("external_") and k.endswith("_enabled"):
                print(f"  {k[9:-8]}: {v}")
        print(f"  site_url: {cfg.get('site_url')}")
        print(f"  uri_allow_list: {cfg.get('uri_allow_list')}")
    except Exception as exc:  # noqa: BLE001
        print(f"  could not read auth config: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
