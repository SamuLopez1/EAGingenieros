from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import Settings
from app.db import (
    comparison_models,  # noqa: F401 - register migration metadata
    document_models,  # noqa: F401 - register migration metadata
    extraction_models,  # noqa: F401 - register migration metadata
    filter_models,  # noqa: F401 - register migration metadata
    margin_models,  # noqa: F401 - register migration metadata
    profile_models,  # noqa: F401 - register migration metadata
    shortlist_models,  # noqa: F401 - register migration metadata
    staffing_models,  # noqa: F401 - register migration metadata
)
from app.db.models import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# El metadata se importa del modelo. La URL no se lee de alembic.ini, que si
# se versiona, sino de la configuracion por entorno de la aplicacion.
target_metadata = Base.metadata


def get_url() -> str:
    """URL de conexion desde EAG_DATABASE_URL. Nunca se registra en claro."""

    from app.db.session import normalise_database_url

    return normalise_database_url(Settings().require_database_url())

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
