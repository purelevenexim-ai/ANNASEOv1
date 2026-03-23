
import os
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

config = context.config
fileConfig(config.config_file_name)

# Use ANNASEO_DB env var or sqlite default
db_url = os.getenv("DATABASE_URL",
                    f"sqlite:///{os.getenv('ANNASEO_DB','./annaseo.db')}")
config.set_main_option("sqlalchemy.url", db_url)

def run_migrations_offline():
    context.configure(url=db_url, target_metadata=None,
                       literal_binds=True, dialect_opts={"paramstyle":"named"})
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
