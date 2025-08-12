#!/usr/bin/env python3
"""
select_key.py — pick a usable API key from the database safely.

- Loads DB creds from .postgres.env (POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST, POSTGRES_PORT)
- Chooses ONE available key from api_keys:
    * NOT quota_exhausted (or NULL)
    * disabled_until IS NULL or <= NOW()
  Ordered by: lowest daily_request_count, then daily_token_total, then oldest last_used.

- Transaction-safe: uses SELECT ... FOR UPDATE SKIP LOCKED to avoid races across multiple callers.

- Outputs in one of:
    * plain (default): just the API key value
    * env:  two lines   KEY_NAME=... and GEMINI_API_KEY=...
    * json: {"key_name":"...", "api_key":"..."}

- Options:
    --mark-use          increment daily_request_count and set last_used=NOW()
    --reserve SECONDS   sets disabled_until=NOW()+SECONDS (soft-reserve the key)
    --format {plain,env,json}
    --service NAME      ignored by default (reserved for multi-service tables)
    --require-enabled   fail if key.quota_exhausted is true (default behavior)
    --allow-exhausted   ignore quota_exhausted and still select unlocked keys
    --verbose

Exit codes:
    0 = success
    2 = no available key
    3 = schema missing or no secret column found
    4 = database error
"""

import os
import sys
import json
import argparse
import datetime as dt
import psycopg2
from psycopg2.extras import DictCursor
from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
dotenv_path = os.path.join(ROOT, ".postgres.env")
load_dotenv(dotenv_path=dotenv_path)

DB_NAME = os.getenv("POSTGRES_DB")
DB_USER = os.getenv("POSTGRES_USER")
DB_PASS = os.getenv("POSTGRES_PASSWORD")
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = int(os.getenv("POSTGRES_PORT", "5432"))


def _connect():
    try:
        return psycopg2.connect(
            dbname=DB_NAME, user=DB_USER, password=DB_PASS,
            host=DB_HOST, port=DB_PORT
        )
    except Exception as e:
        print(f"[select_key] DB connect failed: {e}", file=sys.stderr)
        sys.exit(4)


def _col_exists(cur, table, column):
    cur.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_name=%s AND column_name=%s
        """,
        (table, column),
    )
    return cur.fetchone() is not None


def _detect_secret_column(cur):
    """
    Determine which column stores the API secret:
    try 'api_key', then 'key_value', then 'key'.
    """
    for col in ("api_key", "key_value", "key"):
        if _col_exists(cur, "api_keys", col):
            return col
    return None


def _detect_optional_columns(cur):
    """Return a dict of column->bool for columns we use if present."""
    names = [
        "key_name", "daily_request_count", "daily_token_total", "last_used",
        "quota_exhausted", "disabled_until", "service_name", "tags"
    ]
    have = {}
    for n in names:
        have[n] = _col_exists(cur, "api_keys", n)
    return have


def select_key(conn, allow_exhausted=False, reserve_seconds=None, mark_use=False, service=None, verbose=False):
    """
    Pick a key in a transaction.
    Returns (key_name, api_key) or (None, None) if unavailable.
    """
    with conn:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            secret_col = _detect_secret_column(cur)
            if not secret_col:
                print("[select_key] Could not find API secret column in api_keys (tried: api_key, key_value, key).",
                      file=sys.stderr)
                sys.exit(3)

            have = _detect_optional_columns(cur)

            # Basic availability predicate
            preds = []
            params = []

            # quota_exhausted check
            if have.get("quota_exhausted", False) and not allow_exhausted:
                preds.append("(quota_exhausted IS NOT TRUE)")

            # disabled_until check
            if have.get("disabled_until", False):
                preds.append("(disabled_until IS NULL OR disabled_until <= NOW())")

            # service filter (if present)
            if service and have.get("service_name", False):
                preds.append("(service_name = %s)")
                params.append(service)

            where_sql = " AND ".join(preds) if preds else "TRUE"

            # ORDER BY priority: low requests/tokens, oldest last_used
            order_terms = []
            if have.get("daily_request_count", False):
                order_terms.append("COALESCE(daily_request_count,0) ASC")
            if have.get("daily_token_total", False):
                order_terms.append("COALESCE(daily_token_total,0) ASC")
            if have.get("last_used", False):
                order_terms.append("COALESCE(last_used, 'epoch') ASC")
            if not order_terms:
                order_terms.append("key_name ASC")  # fallback deterministic order

            order_sql = ", ".join(order_terms)

            # Try to grab one row and lock it so concurrent callers don't collide
            q = f"""
                SELECT key_name, {secret_col} AS secret
                FROM api_keys
                WHERE {where_sql}
                ORDER BY {order_sql}
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            """
            if verbose:
                print(f"[select_key] SQL:\n{q}\nparams={params}", file=sys.stderr)

            cur.execute(q, params)
            row = cur.fetchone()
            if not row:
                return None, None

            key_name = row["key_name"] if "key_name" in row and row["key_name"] is not None else None
            api_key = row["secret"]

            # Optionally mark usage / reserve
            updates = []
            up_params = []
            if mark_use and have.get("daily_request_count", False):
                updates.append("daily_request_count = COALESCE(daily_request_count,0) + 1")
            if have.get("last_used", False):
                updates.append("last_used = NOW()")
            if reserve_seconds and have.get("disabled_until", False):
                updates.append("disabled_until = NOW() + (%s || ' seconds')::interval")
                up_params.append(int(reserve_seconds))

            if updates:
                set_sql = ", ".join(updates)
                if key_name is not None and have.get("key_name", False):
                    cur.execute(
                        f"UPDATE api_keys SET {set_sql} WHERE key_name = %s",
                        up_params + [key_name],
                    )
                else:
                    # No key_name column present; try updating by secret value (last resort)
                    cur.execute(
                        f"UPDATE api_keys SET {set_sql} WHERE {secret_col} = %s",
                        up_params + [api_key],
                    )

            return key_name, api_key


def main():
    ap = argparse.ArgumentParser(description="Select a usable API key from the database.")
    ap.add_argument("--format", choices=["plain", "env", "json"], default="plain",
                    help="Output format. 'plain' prints only the API key (default).")
    ap.add_argument("--mark-use", action="store_true",
                    help="Increment daily_request_count and set last_used=NOW().")
    ap.add_argument("--reserve", type=int, default=0, metavar="SECONDS",
                    help="Soft-reserve the key by setting disabled_until=NOW()+SECONDS.")
    ap.add_argument("--allow-exhausted", action="store_true",
                    help="Ignore quota_exhausted and still select keys (default: false).")
    ap.add_argument("--service", default=None,
                    help="Optional service filter if api_keys.service_name exists.")
    ap.add_argument("--verbose", action="store_true", help="Verbose logging to stderr.")
    args = ap.parse_args()

    conn = _connect()
    try:
        key_name, api_key = select_key(
            conn,
            allow_exhausted=args.allow_exhausted,
            reserve_seconds=args.reserve if args.reserve > 0 else None,
            mark_use=args.mark_use,
            service=args.service,
            verbose=args.verbose,
        )
    except psycopg2.errors.UndefinedTable:
        print("[select_key] Table 'api_keys' does not exist. Create it first.", file=sys.stderr)
        sys.exit(3)
    except Exception as e:
        print(f"[select_key] DB error: {e}", file=sys.stderr)
        sys.exit(4)
    finally:
        conn.close()

    if not api_key:
        if args.verbose:
            print("[select_key] No available key.", file=sys.stderr)
        sys.exit(2)

    if args.format == "plain":
        print(api_key)
    elif args.format == "env":
        # keep names predictable for your wrappers
        print(f"KEY_NAME={key_name or ''}")
        print(f"GEMINI_API_KEY={api_key}")
    else:  # json
        print(json.dumps({"key_name": key_name, "api_key": api_key}))
    sys.exit(0)


if __name__ == "__main__":
    main()
