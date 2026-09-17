"""Creación de motor y sesiones de base de datos.

La URL se toma de configuración y nunca se registra: puede contener
credenciales. Sin URL configurada, la aplicación funciona en modo memoria,
lo que permite desarrollar y probar sin una base de datos disponible.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def normalise_database_url(database_url: str) -> str:
    """Adapta la URL al driver psycopg 3.

    Los proveedores entregan habitualmente `postgres://` o `postgresql://`,
    que SQLAlchemy no resuelve por sí solo hacia psycopg 3.
    """

    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


def create_engine_from_url(database_url: str, *, echo: bool = False) -> Engine:
    """Crea un motor con la URL ya normalizada."""

    return create_engine(
        normalise_database_url(database_url),
        echo=echo,
        pool_pre_ping=True,
        future=True,
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Sesión con confirmación o reversión automática."""

    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
