from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from mis.core.config import settings

connect_args = {}
if "postgresql" in (settings.DATABASE_URL or ""):
    schema_name = getattr(settings, "MIS_DB_SCHEMA", "mis") or "mis"
    connect_args["server_settings"] = {"search_path": f"{schema_name},public"}

engine = create_async_engine(settings.DATABASE_URL, echo=False, connect_args=connect_args)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
