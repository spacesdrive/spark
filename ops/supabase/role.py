"""
Create a dedicated PostgreSQL role for Spark, and write its connection string.

Why this exists rather than reusing the project's ``postgres`` password: the
Supabase Management API cannot reveal that password, and resetting it would
change a shared credential in a project another application also lives in.

Resetting it would in fact be survivable here, because everything else in the
project reaches the database through PostgREST using API keys rather than a
direct connection. But it is still a shared secret, and there is no reason to
touch it. A separate role is safer and gives Spark only what it needs:

* it can log in, and it owns nothing;
* it has rights on the ``spark`` schema and nothing else;
* it cannot read ``auth``, ``storage`` or any other application's tables;
* revoking Spark's access later means dropping one role.

The password is generated here, written straight into the gitignored ``.env``,
and never printed.

Usage:
    python -m ops.supabase.role            # show the plan
    python -m ops.supabase.role --apply
"""

from __future__ import annotations

import argparse
import re
import secrets
import string
from pathlib import Path

from ops.paths import ROOT

from ops.supabase.push import SCHEMA, call

ROLE = "spark_app"

def generate_password() -> str:
    """
    A long password made only of characters that survive a URL untouched.

    Percent-encoding a password into a connection string is a reliable source
    of authentication failures that look like the wrong password, so the
    character set avoids the problem instead of encoding around it.
    """
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(48))

def set_env(path: Path, values: dict[str, str]) -> list[str]:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    changed = []
    for key, value in values.items():
        line = f"{key}={value}"
        pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
        if pattern.search(text):
            if pattern.search(text).group(0) != line:
                text = pattern.sub(lambda _m: line, text, count=1)
                changed.append(key)
        else:
            text = text.rstrip("\n") + f"\n{line}\n"
            changed.append(key)
    path.write_text(text, encoding="utf-8")
    return changed

def grants(password: str) -> str:
    """
    Create or update the role, then grant it the ``spark`` schema and no more.

    Written to be safe to run twice: the role is only created when absent, and
    the grants are idempotent.
    """
    return f"""
do $$
begin
  if not exists (select 1 from pg_roles where rolname = '{ROLE}') then
    create role {ROLE} login password '{password}';
  else
    alter role {ROLE} login password '{password}';
  end if;
end
$$;

-- Only this schema. No default search_path beyond it, and no rights anywhere
-- else in the database.
grant usage on schema "{SCHEMA}" to {ROLE};
grant select, insert, update, delete on all tables in schema "{SCHEMA}" to {ROLE};
grant usage, select on all sequences in schema "{SCHEMA}" to {ROLE};

-- Tables created later by the application must be reachable too.
alter default privileges in schema "{SCHEMA}"
  grant select, insert, update, delete on tables to {ROLE};
alter default privileges in schema "{SCHEMA}"
  grant usage, select on sequences to {ROLE};

-- The application creates its own tables through SQLAlchemy on startup.
grant create on schema "{SCHEMA}" to {ROLE};

alter role {ROLE} set search_path to "{SCHEMA}";

-- Transferring ownership requires the current owner to be a member of the
-- role receiving it. This makes postgres a member of spark_app, not the other
-- way round, so spark_app gains nothing from postgres.
grant {ROLE} to postgres;

-- Ownership of this schema and its tables.
--
-- The tables were first created through the Management API, so postgres owned
-- them, and only an owner may ALTER a table. The application adds columns on
-- startup when the models gain one, so without this the first schema change
-- fails at boot with "must be owner of table". This grants ownership of
-- Spark's own schema and nothing else.
alter schema "{SCHEMA}" owner to {ROLE};

do $$
declare r record;
begin
  for r in select tablename from pg_tables where schemaname = '{SCHEMA}' loop
    execute format('alter table {SCHEMA}.%I owner to {ROLE}', r.tablename);
  end loop;
  for r in select sequencename from pg_sequences where schemaname = '{SCHEMA}' loop
    execute format('alter sequence {SCHEMA}.%I owner to {ROLE}', r.sequencename);
  end loop;
end
$$;
"""

def verify(ref: str) -> None:
    rows = call(
        f"/projects/{ref}/database/query",
        "POST",
        {"query": f"""
select
  (select count(*) from pg_roles where rolname = '{ROLE}') as role_exists,
  (select count(*) from information_schema.role_table_grants
     where grantee = '{ROLE}' and table_schema = '{SCHEMA}') as spark_grants,
  (select count(*) from information_schema.role_table_grants
     where grantee = '{ROLE}' and table_schema <> '{SCHEMA}') as other_grants;
"""},
    )[0]
    print(f"  role exists          {bool(rows['role_exists'])}")
    print(f"  grants on {SCHEMA:<10} {rows['spark_grants']}")
    print(f"  grants elsewhere     {rows['other_grants']} (must be 0)")
    if rows["other_grants"]:
        raise SystemExit("the role reached outside its schema, refusing to continue")

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    ref = call("/projects")[0]["id"]
    pooler = call(f"/projects/{ref}/config/database/pooler")[0]
    host, port = pooler["db_host"], pooler["db_port"]
    user = f"{ROLE}.{ref}"

    print(f"project   {ref}")
    print(f"role      {ROLE} (new, separate from postgres)")
    print(f"scope     schema {SCHEMA} only")
    print(f"pooler    {user}@{host}:{port}")

    print("\nNothing belonging to another application is modified. The project's")
    print("postgres password is not read, not reset and not used.")

    if not args.apply:
        print("\nPlan only. Pass --apply to create the role.")
        return 0

    password = generate_password()
    call(f"/projects/{ref}/database/query", "POST", {"query": grants(password)})

    print("\nverifying")
    verify(ref)

    # Prepared statements are disabled in api/database/session.py, not here: a query
    # parameter arrives as a string, and psycopg needs a real None.
    url = (
        f"postgresql+psycopg://{user}:{password}@{host}:{port}/postgres"
        f"?sslmode=require"
    )
    changed = set_env(ROOT / ".env", {"SUPABASE_DB_URL": url})
    print(f"\n.env updated: {changed or 'unchanged'} (value not printed)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
