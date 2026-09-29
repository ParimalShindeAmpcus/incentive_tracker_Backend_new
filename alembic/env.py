from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from mis.core.config import settings
from mis.models.base import Base
import mis.models  # noqa: F401 - register all models with Base.metadata


config = context.config
config.set_main_option("sqlalchemy.url", settings.sync_database_url.replace("%", "%%"))

if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    schema = getattr(settings, "MIS_DB_SCHEMA", "mis") or "mis"
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        version_table_schema=schema,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    schema = getattr(settings, "MIS_DB_SCHEMA", "mis") or "mis"
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={"options": f"-c search_path={schema},public"},
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            version_table_schema=schema,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
