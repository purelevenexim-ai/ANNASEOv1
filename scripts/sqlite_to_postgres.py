#!/usr/bin/env python3
"""
Simple SQLite -> Postgres migration helper.

Usage example:
  export DATABASE_URL=postgresql://annaseo:annaseo_password@127.0.0.1:5432/annaseo
  python3 scripts/sqlite_to_postgres.py --sqlite-file ./annaseo.db --tables strategy_jobs,serp_cache

Or migrate all tables:
  python3 scripts/sqlite_to_postgres.py --sqlite-file ./annaseo.db --all
"""
import os
import sys
import sqlite3
import argparse
import logging
import psycopg2
from psycopg2 import sql
from psycopg2.extras import execute_values

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("migrate")

TYPE_MAP = {
    "INT": "BIGINT",
    "INTEGER": "BIGINT",
    "BIGINT": "BIGINT",
    "TEXT": "TEXT",
    "CHAR": "TEXT",
    "CLOB": "TEXT",
    "REAL": "DOUBLE PRECISION",
    "FLOAT": "DOUBLE PRECISION",
    "DOUBLE": "DOUBLE PRECISION",
    "NUMERIC": "NUMERIC",
    "DECIMAL": "NUMERIC",
    "BLOB": "BYTEA",
}

def map_type(sqlite_type: str) -> str:
    if not sqlite_type:
        return "TEXT"
    t = sqlite_type.upper()
    for k, v in TYPE_MAP.items():
        if k in t:
            return v
    return "TEXT"

def list_sqlite_tables(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    return [r[0] for r in cur.fetchall()]

def get_table_columns(conn: sqlite3.Connection, table: str):
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info('{table}')")
    # returns: cid, name, type, notnull, dflt_value, pk
    return cur.fetchall()

def create_table_in_pg(pg_conn, table: str, cols):
    cols_sql = []
    pk_cols = []
    for col in cols:
        name = col[1]
        typ = col[2] or ""
        mapped = map_type(typ)
        column_sql = f'"{name}" {mapped}'
        if col[3]:
            column_sql += " NOT NULL"
        cols_sql.append(column_sql)
        if col[5]:
            pk_cols.append(f'"{name}"')
    pk_sql = f", PRIMARY KEY ({', '.join(pk_cols)})" if pk_cols else ""
    create_sql = f'CREATE TABLE IF NOT EXISTS "{table}" ({", ".join(cols_sql)}{pk_sql});'
    logger.info("Creating table in Postgres: %s", table)
    with pg_conn.cursor() as cur:
        cur.execute(create_sql)
    pg_conn.commit()

def copy_rows(conn_sqlite: sqlite3.Connection, conn_pg, table: str, batch: int = 1000):
    cols_def = get_table_columns(conn_sqlite, table)
    cols = [c[1] for c in cols_def]
    if not cols:
        logger.warning("Table %s has no columns; skipping", table)
        return
    col_list_sql = ", ".join([f'"{c}"' for c in cols])

    # Determine conflict clause if primary key exists
    pk_cols = [c[1] for c in cols_def if c[5]]
    conflict_sql = ""
    if pk_cols:
        conflict_sql = f" ON CONFLICT ({', '.join([f'"{c}"' for c in pk_cols])}) DO NOTHING"

    insert_sql = f'INSERT INTO "{table}" ({col_list_sql}) VALUES %s{conflict_sql}'

    cur_sql = conn_sqlite.cursor()
    cur_sql.execute(f'SELECT {", ".join([f'"{c}"' for c in cols])} FROM "{table}"')
    total = 0
    rows = cur_sql.fetchmany(batch)
    while rows:
        with conn_pg.cursor() as pg_cur:
            execute_values(pg_cur, insert_sql, rows, page_size=batch)
        conn_pg.commit()
        total += len(rows)
        logger.info("Inserted %d rows into %s", total, table)
        rows = cur_sql.fetchmany(batch)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite-file", required=True, help="Path to sqlite file")
    parser.add_argument("--tables", help="Comma-separated list of tables to migrate")
    parser.add_argument("--all", action="store_true", help="Migrate all non-system tables")
    parser.add_argument("--batch", type=int, default=1000)
    args = parser.parse_args()

    pg_url = os.getenv("DATABASE_URL")
    if not pg_url:
        print("DATABASE_URL must be set (postgres connection string)")
        sys.exit(2)

    sqlite_path = args.sqlite_file
    if not os.path.exists(sqlite_path):
        logger.error("sqlite file not found: %s", sqlite_path)
        sys.exit(1)

    conn_sqlite = sqlite3.connect(sqlite_path)
    conn_sqlite.row_factory = sqlite3.Row

    conn_pg = psycopg2.connect(pg_url)

    if args.all:
        tables = list_sqlite_tables(conn_sqlite)
    else:
        if not args.tables:
            logger.error("No tables specified and --all not set")
            sys.exit(1)
        tables = [t.strip() for t in args.tables.split(",") if t.strip()]

    for t in tables:
        logger.info("Migrating table: %s", t)
        cols = get_table_columns(conn_sqlite, t)
        create_table_in_pg(conn_pg, t, cols)
        copy_rows(conn_sqlite, conn_pg, t, batch=args.batch)

    conn_sqlite.close()
    conn_pg.close()
    logger.info("Migration complete")

if __name__ == "__main__":
    main()
