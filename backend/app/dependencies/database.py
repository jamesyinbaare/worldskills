import contextlib
import logging
from collections.abc import AsyncIterator
from http.client import HTTPException
from typing import Annotated, Any
from urllib.parse import parse_qs, urlparse
import os

from alembic_utils.replaceable_entity import registry
from fastapi import Depends
from pydantic_settings import BaseSettings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)
from sqlalchemy.pool import NullPool
from sqlalchemy.types import JSON

try:
    from sqlalchemy.ext.asyncio import async_sessionmaker  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover
    from sqlalchemy.orm import sessionmaker as _sessionmaker

    def async_sessionmaker(*args: Any, **kwargs: Any):  # type: ignore[no-redef]
        return _sessionmaker(*args, class_=AsyncSession, **kwargs)

try:
    from sqlalchemy.orm import DeclarativeBase
except ImportError:  # pragma: no cover
    DeclarativeBase = None
    from sqlalchemy.orm import declarative_base


if DeclarativeBase is not None:
    class Base(DeclarativeBase):
        __abstract__ = True
        type_annotation_map = {
            dict[str, Any]: JSON,
        }
else:
    Base = declarative_base()
    Base.__abstract__ = True
    Base.type_annotation_map = {
        dict[str, Any]: JSON,
    }


class DBSettings(BaseSettings):
    database_use: bool = True
    database_url: str | None = None
    echo_sql: bool = False
    pool_size: int = 10
    max_overflow: int = 10
    pool_timeout: int = 30
    pool_recycle: int = 1800  # 30 minutes
    mock_database: bool = False
    use_null_pool: bool = False
    database_extensions: list[str] = []


db_settings = DBSettings()  # type: ignore

# Heavily inspired by https://praciano.com.br/fastapi-and-async-sqlalchemy-20-with-pytest-done-right.html



def convert_to_async_url(url: str) -> str:
    """Convert a synchronous PostgreSQL URL to use asyncpg driver for async SQLAlchemy.

    Converts:
    - postgresql:// -> postgresql+asyncpg://
    - postgresql+psycopg2:// -> postgresql+asyncpg://
    - postgresql+asyncpg:// -> postgresql+asyncpg:// (no change)

    Args:
        url: The database URL string

    Returns:
        The URL string with asyncpg driver specified
    """
    # If already using asyncpg, return as-is
    if "postgresql+asyncpg://" in url:
        return url

    # Replace postgresql:// with postgresql+asyncpg://
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)

    # Replace postgresql+psycopg2:// with postgresql+asyncpg://
    if url.startswith("postgresql+psycopg2://"):
        return url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)

    # Return as-is if no conversion needed (e.g., already async or different driver)
    return url


def asyncpg_connect_args(database_url: str) -> dict[str, Any]:
    """Connect args for asyncpg.

    Cloud SQL Auth Proxy exposes plaintext Postgres to clients (it terminates TLS
    to Cloud SQL itself). asyncpg defaults to ssl='prefer', which can reset the
    connection against the proxy. Local Compose Postgres also uses plaintext.

    Disable SSL unless DATABASE_SSL / URL ssl|sslmode explicitly enables it.
    Host ``cloud-sql-proxy`` always forces ssl=False.
    """
    normalized = (
        database_url.replace("postgresql+asyncpg://", "postgresql://", 1).replace(
            "postgresql+psycopg2://", "postgresql://", 1
        )
    )
    parsed = urlparse(normalized)
    query = {k.lower(): (v[-1] if v else "").lower() for k, v in parse_qs(parsed.query).items()}
    ssl_q = query.get("ssl") or query.get("sslmode") or ""
    env_ssl = os.environ.get("DATABASE_SSL", "").strip().lower()
    host = (parsed.hostname or "").lower()

    explicit_disable = ssl_q in {"disable", "disabled", "false", "0"} or env_ssl in {
        "0",
        "false",
        "disable",
        "disabled",
    }
    explicit_enable = ssl_q in {
        "1",
        "true",
        "require",
        "verify-ca",
        "verify-full",
        "prefer",
        "allow",
    } or env_ssl in {"1", "true", "require", "verify-ca", "verify-full"}

    if host == "cloud-sql-proxy" or explicit_disable or not explicit_enable:
        return {"ssl": False}
    return {}


class DatabaseSessionManager:
    _engine: AsyncEngine | None
    _sessionmaker: Any | None

    def __init__(self, host: str, engine_kwargs: dict[str, Any] | None = None):
        self._host = host
        self._engine_kwargs = engine_kwargs or {}
        self._engine = None
        self._sessionmaker = None

    async def configure(self) -> None:
        if self._engine is not None:
            return  # Already configured

        self._engine = create_async_engine(self._host, **self._engine_kwargs)
        self._sessionmaker: Any = async_sessionmaker(
            autocommit=False, bind=self._engine, expire_on_commit=False
        )

    async def close(self) -> None:
        if self._engine is None:
            return
        await self._engine.dispose()

        self._engine = None
        self._sessionmaker = None

    @contextlib.asynccontextmanager
    async def connect(self) -> AsyncIterator[AsyncConnection]:
        if self._engine is None:
            raise Exception("DatabaseSessionManager is not initialized")

        async with self._engine.begin() as connection:
            try:
                yield connection
            except Exception:
                await connection.rollback()
                raise

    @contextlib.asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        if self._sessionmaker is None:
            raise Exception("DatabaseSessionManager is not initialized")

        session = self._sessionmaker()
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


class TestingDatabaseSessionManager(DatabaseSessionManager):
    async def configure(self) -> None:
        from pytest_postgresql.janitor import DatabaseJanitor

        result = urlparse(db_settings.database_url)
        self.__janitor = DatabaseJanitor(
            user=result.username,
            host=result.hostname,
            port=result.port,  # type: ignore
            dbname=result.path.strip("/"),
            version=14,
            password=result.password,
        )  # type: ignore

        try:
            self.__janitor.drop()
        except Exception:
            pass
        self.__janitor.init()

        await super().configure()

        if db_settings.database_extensions:
            async with self.connect() as conn:
                for ext in db_settings.database_extensions:
                    await conn.execute(text(f"CREATE EXTENSION IF NOT EXISTS {ext};"))
                await conn.commit()

        async with self.connect() as conn:
            tables_only = [table for table in Base.metadata.sorted_tables if not table.info.get("is_view")]
            await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables_only))
        async with self.session() as session:
            for entity in registry.entities():
                for action in entity.to_sql_statement_create_or_replace():
                    await session.execute(action)
                await session.commit()

    async def close(self) -> None:
        async with self.session() as session:
            for entity in registry.entities():
                await session.execute(entity.to_sql_statement_drop())
                await session.commit()

        async with self.connect() as conn:
            tables_only = [table for table in reversed(Base.metadata.sorted_tables) if not table.info.get("is_view")]
            await conn.run_sync(lambda sync_conn: Base.metadata.drop_all(sync_conn, tables=tables_only))
        await super().close()
        self.__janitor.drop()


if db_settings.mock_database:
    if db_settings.database_url is None:
        raise Exception("Database URL is not set")
    _async_url = convert_to_async_url(db_settings.database_url)
    _connect_args = asyncpg_connect_args(_async_url)
    if db_settings.use_null_pool:
        sessionmanager: DatabaseSessionManager = TestingDatabaseSessionManager(
            _async_url,
            {
                "echo": db_settings.echo_sql,
                "poolclass": NullPool,
                "connect_args": _connect_args,
            },
        )
    else:
        sessionmanager = TestingDatabaseSessionManager(
            _async_url,
            {
                "echo": db_settings.echo_sql,
                "pool_size": db_settings.pool_size,
                "max_overflow": db_settings.max_overflow,
                "pool_timeout": db_settings.pool_timeout,
                "pool_recycle": db_settings.pool_recycle,
                "connect_args": _connect_args,
            },
        )
elif db_settings.database_use:
    if db_settings.database_url is None:
        raise Exception("Database URL is not set")
    _async_url = convert_to_async_url(db_settings.database_url)
    sessionmanager = DatabaseSessionManager(
        _async_url,
        {
            "echo": db_settings.echo_sql,
            "pool_size": db_settings.pool_size,
            "max_overflow": db_settings.max_overflow,
            "pool_timeout": db_settings.pool_timeout,
            "pool_recycle": db_settings.pool_recycle,
            "connect_args": asyncpg_connect_args(_async_url),
        },
    )
else:
    logging.getLogger().warning("Database is not configured")
    sessionmanager = None


async def get_db_session() -> AsyncIterator[AsyncSession]:
    if sessionmanager is None:
        raise HTTPException(512, "Database is not configured")

    async with sessionmanager.session() as session:
        yield session


async def get_db() -> AsyncIterator[DatabaseSessionManager]:
    if sessionmanager is None:
        raise HTTPException(512, "Database is not configured")

    yield sessionmanager


def get_sessionmanager() -> DatabaseSessionManager:
    if sessionmanager is None:
        raise Exception("Database is not configured")

    return sessionmanager


DBSessionDep = Annotated[AsyncSession, Depends(get_db_session)]


@contextlib.asynccontextmanager
async def initialize_db(manager: DatabaseSessionManager) -> AsyncIterator[DatabaseSessionManager]:
    await manager.configure()
    yield manager
    await manager.close()
