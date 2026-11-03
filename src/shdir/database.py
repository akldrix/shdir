from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy import NullPool
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

BASE_DIR: Path = Path(__file__).resolve().parent

DB_NAME: str = "shmsg.db"
DB_URL: str = f"sqlite+aiosqlite:///{BASE_DIR / DB_NAME}"

engine: AsyncEngine = create_async_engine(DB_URL, poolclass=NullPool)

async_session: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session


class Base(DeclarativeBase):
    pass
