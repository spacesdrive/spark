"""
Point Spark's hostnames at the Spark origin, and touch no other record.

The script only ever reads the zone and then creates or updates the exact
names listed in ``NAMES``. Records belonging to other applications in the same
zone are listed for confirmation but never modified or deleted.

Usage:
    python -m ops.cloudflare.dns <origin-ip>            # plan only
    python -m ops.cloudflare.dns <origin-ip> --apply
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request

from ops.paths import ROOT

API = "https://api.cloudflare.com/client/v4"
ZONE_NAME = "spacesdrive.cc"
# docs-spark, not docs.spark: Cloudflare Universal SSL only covers the apex and
# one level of subdomain, so a two level name like docs.spark.spacesdrive.cc is
# served with a certificate no browser will accept.
NAMES = ["spark.spacesdrive.cc", "docs-spark.spacesdrive.cc"]


def token() -> str:
    return (ROOT / ".cloudflare-keys" / "access-token.pem").read_text().strip()


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
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read().decode())
    except urllib.error.HTTPError as exc:
        d = json.loads(exc.read().decode() or "{}")
    if not d.get("success"):
        raise RuntimeError(f"Cloudflare said: {d.get('errors')}")
    return d["result"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("origin", help="origin IPv4 address")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    zone = next(z for z in call("/zones") if z["name"] == ZONE_NAME)
    zid = zone["id"]
    records = call(f"/zones/{zid}/dns_records?per_page=200")

    print(f"zone {ZONE_NAME} ({zid}) holds {len(records)} records")
    print("records that will NOT be touched:")
    for r in records:
        if r["name"] not in NAMES:
            print(f"  {r['type']:6} {r['name']}")

    for name in NAMES:
        found = next((r for r in records if r["name"] == name and r["type"] == "A"), None)
        wrong_type = [r for r in records if r["name"] == name and r["type"] != "A"]
        if wrong_type:
            print(f"\n  {name}: existing {wrong_type[0]['type']} record is in the way. "
                  f"Left alone, resolve it by hand.")
            continue
        desired = {"type": "A", "name": name, "content": args.origin,
                   "ttl": 1, "proxied": True,
                   "comment": "Spark. Managed by ops/cloudflare/dns.py"}
        if found and found["content"] == args.origin and found["proxied"]:
            print(f"\n  {name}: already correct ({args.origin}, proxied)")
            continue
        action = "update" if found else "create"
        print(f"\n  {name}: {action} -> {args.origin}, proxied")
        if not args.apply:
            continue
        if found:
            call(f"/zones/{zid}/dns_records/{found['id']}", "PUT", desired)
        else:
            call(f"/zones/{zid}/dns_records", "POST", desired)
        print(f"  {name}: done")

    if not args.apply:
        print("\nPlan only. Pass --apply to write these records.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
