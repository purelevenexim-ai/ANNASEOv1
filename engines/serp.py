"""SERP engine: provider adapter + resilient cache.

This module exposes `SERPEngine` which is DB-backend-agnostic (accepts either
`sqlite3.Connection` or a SQLAlchemy engine). It supports provider injection
for testability and uses JSON/JSONB casts when possible for Postgres.
"""
import os
import json
import hashlib
import logging
import sqlite3
from datetime import datetime
from typing import Optional

import requests
from sqlalchemy import text

from services.db_session import engine as sa_engine

log = logging.getLogger("ruflo.serp")


class SerpAPIProvider:
    """Small adapter for SerpAPI HTTP provider."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("SERP_API_KEY") or os.getenv("SERPAPI_KEY", "")

    def fetch(self, query: str) -> dict:
        if not self.api_key:
            raise RuntimeError("SerpAPI key not configured")
        r = requests.get(
            "https://serpapi.com/search.json",
            params={"q": query, "api_key": self.api_key, "engine": "google"},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()


class SERPCache:
    """Thin cache helper used by tests: `engine.cache.set(...)`."""

    def __init__(self, engine: "SERPEngine"):
        self._engine = engine

    def set(self, keyword: str, response: dict):
        return self._engine._cache_insert(keyword, response)

    def get(self, keyword: str):
        return self._engine._cache_get(keyword)


class SERPEngine:
    def __init__(self, db_engine=None, api_key: Optional[str] = None, provider: Optional[object] = None):
        # db_engine may be either a sqlite3.Connection (from get_db()) or a
        # SQLAlchemy Engine (services.db_session.engine). Default to SA engine.
        self.db_engine = db_engine or sa_engine
        self.provider = provider
        self.api_key = api_key or os.getenv("SERP_API_KEY") or os.getenv("SERPAPI_KEY", "")
        self.cache = SERPCache(self)

    def _is_sqlite(self):
        return isinstance(self.db_engine, sqlite3.Connection)

    def _hash_obj(self, obj: object) -> str:
        return hashlib.sha256(json.dumps(obj, sort_keys=True).encode("utf-8")).hexdigest()

    def _get_table_columns(self, conn):
        cols = set()
        try:
            if self._is_sqlite():
                cur = conn.execute("PRAGMA table_info('serp_cache')")
                for r in cur.fetchall():
                    cols.add(r[1])
            else:
                rows = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'serp_cache'"))
                for r in rows.fetchall():
                    cols.add(r[0])
        except Exception:
            # Be tolerant; return what we have (may be empty)
            pass
        return cols

    def _choose_column(self, cols: set, candidates):
        for c in candidates:
            if c in cols:
                return c
        return None

    def _cache_get(self, keyword: str):
        """Return cached row dict or None."""
        try:
            if self._is_sqlite():
                conn = self.db_engine
                cols = self._get_table_columns(conn)
                key_col = self._choose_column(cols, ["query", "keyword"]) or None
                results_col = self._choose_column(cols, ["results", "response"]) or None
                fetched_col = self._choose_column(cols, ["fetched_at", "created_at"]) or None
                if not key_col or not results_col:
                    return None
                cur = conn.execute(f"SELECT {results_col}, {fetched_col} FROM serp_cache WHERE {key_col} = ?", (keyword,))
                row = cur.fetchone()
                if not row:
                    return None
                raw = row[0]
                fetched = row[1]
                try:
                    data = json.loads(raw) if raw and isinstance(raw, str) else raw
                except Exception:
                    data = raw
                return {"results": data, "fetched_at": fetched}
            else:
                with self.db_engine.connect() as conn:
                    cols = self._get_table_columns(conn)
                    key_col = self._choose_column(cols, ["query", "keyword"]) or None
                    results_col = self._choose_column(cols, ["results", "response"]) or None
                    fetched_col = self._choose_column(cols, ["fetched_at", "created_at"]) or None
                    if not key_col or not results_col:
                        return None
                    sel = f"SELECT {results_col} as results, {fetched_col} as fetched_at FROM serp_cache WHERE {key_col} = :q"
                    row = conn.execute(text(sel), {"q": keyword}).mappings().fetchone()
                    if not row:
                        return None
                    results = row.get("results")
                    fetched = row.get("fetched_at")
                    return {"results": results, "fetched_at": fetched}
        except Exception as e:
            log.warning("SERP cache read error: %s", e)
            return None

    def _cache_insert(self, keyword: str, data: dict):
        """Insert or replace cache row. Best-effort across schema variants."""
        dump = json.dumps(data)
        try:
            if self._is_sqlite():
                conn = self.db_engine
                cols = self._get_table_columns(conn)
                key_col = self._choose_column(cols, ["query", "keyword"]) or "keyword"
                results_col = self._choose_column(cols, ["results", "response"]) or "results"
                fetched_col = self._choose_column(cols, ["fetched_at", "created_at"]) or "fetched_at"
                # Build minimal column list
                cols_list = [key_col, results_col, fetched_col]
                placeholders = ",".join(["?" for _ in cols_list])
                cols_sql = ",".join(cols_list)
                sql = f"INSERT OR REPLACE INTO serp_cache ({cols_sql}) VALUES ({placeholders})"
                params = [keyword, dump, datetime.utcnow().isoformat()]
                conn.execute(sql, params)
                conn.commit()
                return True
            else:
                with self.db_engine.begin() as conn:
                    cols = self._get_table_columns(conn)
                    key_col = self._choose_column(cols, ["query", "keyword"]) or "query"
                    results_col = self._choose_column(cols, ["results", "response"]) or "results"
                    fetched_col = self._choose_column(cols, ["fetched_at", "created_at"]) or "fetched_at"
                    # Try JSONB cast upsert first
                    insert_cols = f"{key_col}, {results_col}, {fetched_col}"
                    sql = text(f"INSERT INTO serp_cache ({insert_cols}) VALUES (:q, CAST(:results AS jsonb), now()) ON CONFLICT ({key_col}) DO UPDATE SET {results_col}=EXCLUDED.{results_col}, {fetched_col}=EXCLUDED.{fetched_col}")
                    conn.execute(sql, {"q": keyword, "results": dump})
                    return True
        except Exception as e:
            log.warning("SERP cache upsert primary failed: %s", e)
            # Fallback: try without jsonb cast
            try:
                if not self._is_sqlite():
                    with self.db_engine.begin() as conn:
                        insert_cols = f"{key_col}, {results_col}"
                        sql = text(f"INSERT INTO serp_cache ({insert_cols}) VALUES (:q, :results) ON CONFLICT ({key_col}) DO UPDATE SET {results_col}=EXCLUDED.{results_col}")
                        conn.execute(sql, {"q": keyword, "results": dump})
                        return True
            except Exception as e2:
                log.warning("SERP cache upsert fallback failed: %s", e2)
        return False

    def _fetch_provider(self, query: str) -> dict:
        # Prefer an injected provider for testability
        if self.provider:
            try:
                # Provider may implement `fetch(query)` or be a callable
                if hasattr(self.provider, "fetch"):
                    return self.provider.fetch(query)
                return self.provider(query)
            except Exception as e:
                log.warning("Injected provider failed: %s", e)

        # If SerpAPI key present, call remote provider
        if self.api_key:
            try:
                provider = SerpAPIProvider(self.api_key)
                return provider.fetch(query)
            except Exception as e:
                log.warning("SerpAPI provider error: %s", e)

        # No provider configured; return empty results (safe default)
        return {"organic_results": []}

    def get_serp(self, query: str, ttl_seconds: int = 86400):
        """Return SERP JSON for `query` using cache when fresh.

        Behavior:
        - If a fresh cache row exists, return it.
        - Otherwise call provider. On success store and return provider data.
        - If provider fails and stale cache exists, return stale.
        - If provider fails and no cache, return empty results.
        """
        # Try read cache
        cached = None
        try:
            if self._is_sqlite():
                cached = self._cache_get(query)
            else:
                # For SA engine use a connection
                with self.db_engine.connect() as conn:
                    # _cache_get opens its own connection path for SA as well
                    cached = self._cache_get(query)
        except Exception as e:
            log.warning("SERP cache read overall failed: %s", e)

        if cached and cached.get("results") is not None:
            fetched_at = cached.get("fetched_at")
            is_fresh = False
            if fetched_at:
                try:
                    if isinstance(fetched_at, str):
                        fa = datetime.fromisoformat(fetched_at)
                    else:
                        fa = fetched_at
                    age = (datetime.utcnow() - (fa if fa.tzinfo is None else fa.replace(tzinfo=None))).total_seconds()
                    is_fresh = age < ttl_seconds
                except Exception:
                    is_fresh = False
            if is_fresh:
                return cached.get("results")

        # Cache miss or stale — fetch provider
        data = self._fetch_provider(query)
        if data and data.get("organic_results") is not None and len(data.get("organic_results", [])) > 0:
            # store fresh result
            try:
                self._cache_insert(query, data)
            except Exception as e:
                log.warning("SERP cache insert after fetch failed: %s", e)
            return data

        # Provider returned no results or failed — if stale cache exists return it
        if cached and cached.get("results") is not None:
            return cached.get("results")

        # Nothing available — safe empty
        return {"organic_results": []}

