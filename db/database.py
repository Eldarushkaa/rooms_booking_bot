import aiosqlite
import os
import pathlib

_DB_PATH = pathlib.Path(__file__).parent.parent / "booking_bot.db"
_SQL_PATH = pathlib.Path(__file__).parent / "models.sql"

_db: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _db


async def init_db() -> None:
    global _db
    _db = await aiosqlite.connect(_DB_PATH)
    _db.row_factory = aiosqlite.Row

    # Performance and correctness settings
    await _db.execute("PRAGMA journal_mode=WAL")
    await _db.execute("PRAGMA foreign_keys=ON")
    await _db.execute("PRAGMA synchronous=NORMAL")

    # Create tables from schema
    schema = _SQL_PATH.read_text()
    await _db.executescript(schema)
    await _db.commit()


async def close_db() -> None:
    global _db
    if _db is not None:
        await _db.close()
        _db = None
