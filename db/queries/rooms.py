import aiosqlite
from db.database import get_db


async def get_rooms(company_id: int, include_inactive: bool = False) -> list[aiosqlite.Row]:
    db = await get_db()
    if include_inactive:
        async with db.execute(
            "SELECT * FROM rooms WHERE company_id = ? ORDER BY name",
            (company_id,),
        ) as cur:
            return await cur.fetchall()
    else:
        async with db.execute(
            "SELECT * FROM rooms WHERE company_id = ? AND is_active = 1 ORDER BY name",
            (company_id,),
        ) as cur:
            return await cur.fetchall()


async def get_room(room_id: int) -> aiosqlite.Row | None:
    db = await get_db()
    async with db.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)) as cur:
        return await cur.fetchone()


async def create_room(
    company_id: int,
    name: str,
    description: str | None = None,
    capacity: int | None = None,
) -> int:
    db = await get_db()
    async with db.execute(
        "INSERT INTO rooms (company_id, name, description, capacity) VALUES (?, ?, ?, ?)",
        (company_id, name, description, capacity),
    ) as cur:
        room_id = cur.lastrowid
    await db.commit()
    return room_id


_UNSET = object()  # Sentinel meaning "do not update this field"


async def update_room(
    room_id: int,
    name: str | None = _UNSET,
    description: str | None = _UNSET,
    capacity: int | None = _UNSET,
) -> None:
    """Update room fields. Pass None to explicitly clear a nullable field.
    Omit a parameter (or use the default sentinel) to leave it unchanged."""
    db = await get_db()
    if name is not _UNSET:
        await db.execute("UPDATE rooms SET name = ? WHERE id = ?", (name, room_id))
    if description is not _UNSET:
        await db.execute("UPDATE rooms SET description = ? WHERE id = ?", (description, room_id))
    if capacity is not _UNSET:
        await db.execute("UPDATE rooms SET capacity = ? WHERE id = ?", (capacity, room_id))
    await db.commit()


async def toggle_room_active(room_id: int) -> bool:
    """Toggles is_active and returns the new value."""
    db = await get_db()
    async with db.execute("SELECT is_active FROM rooms WHERE id = ?", (room_id,)) as cur:
        row = await cur.fetchone()
    if row is None:
        return False
    new_val = 0 if row["is_active"] else 1
    await db.execute("UPDATE rooms SET is_active = ? WHERE id = ?", (new_val, room_id))
    await db.commit()
    return bool(new_val)


async def delete_room(room_id: int) -> None:
    """Permanently deletes a room and cancels all its bookings."""
    db = await get_db()
    await db.execute("UPDATE bookings SET is_cancelled = 1 WHERE room_id = ?", (room_id,))
    await db.execute("DELETE FROM rooms WHERE id = ?", (room_id,))
    await db.commit()
