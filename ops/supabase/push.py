"""
Create Spark's tables in Supabase, inside a dedicated ``spark`` schema.

The DDL is generated from ``api/models`` rather than written by hand, so the
Supabase schema cannot drift away from the ORM. Nothing is dropped: the script
only issues CREATE ... IF NOT EXISTS, so running it twice is safe and it will
never touch another application's tables.

The ``spark`` schema keeps Spark separate from anything else living in the same
project. The DDL itself is unqualified and a ``search_path`` places it, which
avoids having to rewrite every foreign key.

Usage:
    python -m ops.supabase.push            # show the plan, change nothing
    python -m ops.supabase.push --apply    # create the schema and tables
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request

from ops.paths import ROOT

from sqlalchemy import create_mock_engine  # noqa: E402

from api.database import Base  # noqa: E402

API = "https://api.supabase.com/v1"
SCHEMA = "spark"

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
            "User-Agent": "spark-ops/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{exc.code} {exc.read().decode()[:400]}") from None

def ddl() -> str:
    """Render every model as PostgreSQL DDL, without connecting to anything."""
    statements: list[str] = []

    def collect(sql, *_args, **_kw):
        statements.append(str(sql.compile(dialect=engine.dialect)).strip())

    engine = create_mock_engine("postgresql://", collect)
    Base.metadata.create_all(engine, checkfirst=False)

    out = [f'create schema if not exists "{SCHEMA}";', f'set search_path to "{SCHEMA}";']
    for s in statements:
        # checkfirst cannot reach a mock engine, so make it idempotent here.
        s = s.replace("CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ", 1)
        s = s.replace("CREATE INDEX ", "CREATE INDEX IF NOT EXISTS ", 1)
        s = s.replace("CREATE UNIQUE INDEX ", "CREATE UNIQUE INDEX IF NOT EXISTS ", 1)
        out.append(s.rstrip(";\n ") + ";")
    return "\n".join(out)

def existing(ref: str) -> list[str]:
    rows = call(
        f"/projects/{ref}/database/query",
        "POST",
        {"query": "select table_name from information_schema.tables "
                  f"where table_schema = '{SCHEMA}' order by table_name;"},
    )
    return [r["table_name"] for r in rows]

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually run the DDL")
    ap.add_argument("--ref", default=None, help="Supabase project ref")
    args = ap.parse_args()

    ref = args.ref or call("/projects")[0]["id"]
    sql = ddl()
    tables = sorted(Base.metadata.tables)

    print(f"project        {ref}")
    print(f"schema         {SCHEMA}")
    print(f"tables in ORM  {len(tables)}: {', '.join(tables)}")
    print(f"already there  {existing(ref) or 'none'}")

    if not args.apply:
        print("\nDry run. Pass --apply to create them.")
        return 0

    call(f"/projects/{ref}/database/query", "POST", {"query": sql})
    now = existing(ref)
    print(f"\ncreated. schema {SCHEMA} now holds {len(now)} tables:")
    for t in now:
        print(f"  {t}")
    missing = [t for t in tables if t not in now]
    if missing:
        print(f"\nMISSING: {missing}")
        return 1
    print("\nEvery ORM table is present.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
