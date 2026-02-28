import aiosqlite
from db.database import get_db


async def get_or_create_user(user_id: int, username: str | None, full_name: str) -> aiosqlite.Row:
    db = await get_db()
    await db.execute(
        """
        INSERT INTO users (user_id, username, full_name)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            username  = excluded.username,
            full_name = excluded.full_name
        """,
        (user_id, username, full_name),
    )
    await db.commit()
    async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cur:
        return await cur.fetchone()


async def get_user(user_id: int) -> aiosqlite.Row | None:
    db = await get_db()
    async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cur:
        return await cur.fetchone()
