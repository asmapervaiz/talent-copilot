"""Database connection and session management with tenant awareness."""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from .config import get_settings

Base = declarative_base()
engine = create_async_engine(
    get_settings().database_url,
    echo=False,
    future=True,
)
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Create all tables. Run once at startup or via migration."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
