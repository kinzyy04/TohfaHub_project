"""
Database configuration and session management for the CraftNest application.

This module sets up:
1. **Async Engine**: The connection factory using the async `psycopg` driver (`postgresql+psycopg://`).
   - `pool_pre_ping=True` is enabled to automatically test connections and handle stale pools.
   - `echo` is dynamically toggled to `True` during local "development" to log SQL statements, and `False` in other environments.
2. **SessionLocal**: An `async_sessionmaker` that instantiates `AsyncSession` contexts for handling asynchronous database transactions.
3. **Base**: The standard SQLAlchemy 2.0 `DeclarativeBase` subclass from which all system ORM models inherit.
4. **get_db()**: An asynchronous dependency function for FastAPI endpoints. It yields an active `AsyncSession` and automatically handles standard transaction logic:
   - Commits the transaction if the endpoint executes successfully.
   - Rolls back the transaction if any exception or error occurs during processing.
   - Disposes/closes the session cleanly upon exit using the `async with` context manager.
"""

import sys
import asyncio
import uuid

# Set the selector event loop policy on Windows for psycopg async compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings

import socket

db_url = settings.DATABASE_URL
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)
elif db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

if db_url.startswith("postgresql"):
    if "localhost" in db_url or "127.0.0.1" in db_url:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            s.connect(("127.0.0.1", 5432))
            s.close()
        except OSError:
            # Fallback to local SQLite database when Postgres is not running
            db_url = "sqlite+aiosqlite:///./craftnest.db"

# Create the asynchronous SQLAlchemy engine
engine = create_async_engine(
    db_url,
    echo=settings.ENV == "development",
    pool_pre_ping=True,
)

# Create the session maker for AsyncSession
SessionLocal = async_sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

# Base class for models in SQLAlchemy 2.0
class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency generator for database sessions.
    
    Yields an AsyncSession, commits on successful completion of the request,
    and rolls back if any exception occurs.
    """
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# Platform-independent type decorators to support both PostgreSQL and SQLite
from sqlalchemy.types import TypeDecorator, CHAR
from sqlalchemy import String, JSON
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, INET as PG_INET, JSONB as PG_JSONB

class GUID(TypeDecorator):
    """Platform-independent GUID type.
    Uses PostgreSQL's UUID type, or CHAR(36) in SQLite.
    """
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        else:
            return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        elif dialect.name == 'postgresql':
            return value
        else:
            if isinstance(value, uuid.UUID):
                return str(value)
            return value

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        else:
            if not isinstance(value, uuid.UUID):
                try:
                    return uuid.UUID(value)
                except ValueError:
                    return value
            return value

class INET(TypeDecorator):
    """Platform-independent INET type.
    Uses PostgreSQL's INET type, or String in SQLite.
    """
    impl = String
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(PG_INET)
        else:
            return dialect.type_descriptor(String)

class JSONB(TypeDecorator):
    """Platform-independent JSONB type.
    Uses PostgreSQL's JSONB type, or JSON in SQLite.
    """
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(PG_JSONB)
        else:
            return dialect.type_descriptor(JSON)


from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY, TSVECTOR as PG_TSVECTOR

class DialectArray(TypeDecorator):
    """Platform-independent ARRAY type.
    Uses PostgreSQL's ARRAY type, or JSON in SQLite.
    """
    impl = JSON
    cache_ok = True

    def __init__(self, item_type, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.item_type = item_type

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(PG_ARRAY(self.item_type))
        else:
            return dialect.type_descriptor(JSON)


class TSVECTOR(TypeDecorator):
    """Platform-independent TSVECTOR type.
    Uses PostgreSQL's TSVECTOR type, or String in SQLite.
    """
    impl = String
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(PG_TSVECTOR)
        else:
            return dialect.type_descriptor(String)


