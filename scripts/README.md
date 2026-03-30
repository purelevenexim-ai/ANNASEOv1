SQLite → Postgres migration helper

Usage

1. Start Postgres (example using the provided compose file):

```bash
docker compose -f docker-compose.postgres.yml up -d
```

2. Export `DATABASE_URL` to point at the Postgres instance:

```bash
export DATABASE_URL=postgresql://annaseo:annaseo_password@127.0.0.1:5432/annaseo
```

3. Run the helper to migrate specific tables:

```bash
python3 scripts/sqlite_to_postgres.py --sqlite-file ./annaseo.db --tables strategy_jobs,serp_cache
```

Or migrate all tables:

```bash
python3 scripts/sqlite_to_postgres.py --sqlite-file ./annaseo.db --all
```

Notes

- The helper maps common SQLite types to Postgres types; review created schemas before production use.
- For non-trivial schemas or large datasets prefer `pgloader` or a tested migration plan.
