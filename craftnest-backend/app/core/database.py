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

# Set the selector event loop policy on Windows for psycopg async compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings

# Create the asynchronous SQLAlchemy engine
engine = create_async_engine(
    settings.DATABASE_URL,
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
