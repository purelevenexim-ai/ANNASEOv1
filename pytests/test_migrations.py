import os
from pathlib import Path
import uuid
import sqlalchemy as sa
from sqlalchemy import create_engine, inspect


class OpShim:
    def __init__(self, engine):
        self.engine = engine

    def execute(self, sql: str):
        # For sqlite, use raw_connection.executescript to allow multiple statements
        if self.engine.dialect.name == 'sqlite':
            raw = self.engine.raw_connection()
            try:
                raw.executescript(sql)
                raw.commit()
            finally:
                raw.close()
        else:
            with self.engine.connect() as conn:
                conn.execute(sa.text(sql))

    def create_table(self, name, *columns, **kw):
        metadata = sa.MetaData()
        tbl = sa.Table(name, metadata, *columns)
        metadata.create_all(self.engine, tables=[tbl])

    def drop_table(self, name):
        # best-effort drop
        try:
            metadata = sa.MetaData()
            tbl = sa.Table(name, metadata)
            tbl.drop(self.engine)
        except Exception:
            with self.engine.connect() as conn:
                conn.execute(sa.text(f"DROP TABLE IF EXISTS {name}"))

    def create_index(self, name, table_name, columns, unique=False):
        cols = ", ".join(columns)
        sql = f"CREATE {'UNIQUE ' if unique else ''}INDEX IF NOT EXISTS {name} ON {table_name} ({cols})"
        self.execute(sql)

    def drop_index(self, name, table_name=None):
        self.execute(f"DROP INDEX IF EXISTS {name}")


def _apply_migration_file(engine, path: Path, op_shim: OpShim):
    src = path.read_text()
    # Replace `from alembic import op` with binding to our shim
    src = src.replace("from alembic import op", "op = __provided_op__")
    # Prepare namespace
    ns = {"__provided_op__": op_shim, "sa": sa, "__file__": str(path)}
    exec(compile(src, str(path), 'exec'), ns)
    # Call upgrade() if defined
    if 'upgrade' in ns and callable(ns['upgrade']):
        ns['upgrade']()


def test_migrations_apply_and_validate(tmp_path):
    db_file = tmp_path / "alembic_test.db"
    engine = create_engine(f"sqlite:///{db_file}")

    versions_dir = Path(__file__).resolve().parents[1] / 'alembic' / 'versions'
    # Apply full-schema then our migration
    mig1 = versions_dir / '20260401_001_full_schema.py'
    mig2 = versions_dir / '20260402_001_strategy_jobs_serp_cache.py'

    op_shim = OpShim(engine)
    _apply_migration_file(engine, mig1, op_shim)
    _apply_migration_file(engine, mig2, op_shim)

    insp = inspect(engine)
    tables = insp.get_table_names()
    assert 'strategy_jobs' in tables
    assert 'serp_cache' in tables

    # Columns
    cols = {c['name'] for c in insp.get_columns('strategy_jobs')}
    expected = {
        'id', 'project_id', 'status', 'progress', 'current_step',
        'input_payload', 'result_payload', 'error_message', 'retry_count',
        'created_at', 'started_at', 'completed_at'
    }
    assert expected.issubset(cols)

    # Indexes
    idxs = {i['name'] for i in insp.get_indexes('strategy_jobs')}
    assert any('ix_strategy_jobs' in n for n in idxs)

    # Unique constraint / index for serp_cache.hash (SQLite reports via indexes)
    serp_idxs = {i['name'] for i in insp.get_indexes('serp_cache')}
    assert any('serp_cache' in n and 'hash' in n or 'ix_serp_cache_hash' in n for n in serp_idxs)

    # Insert test
    conn = engine.connect()
    conn.execute(sa.text("INSERT INTO strategy_jobs (id, project_id, status, progress) VALUES (:id, :pid, :status, :progress)"),
                 {"id": str(uuid.uuid4()), "pid": str(uuid.uuid4()), "status": "pending", "progress": 0})
    conn.close()
