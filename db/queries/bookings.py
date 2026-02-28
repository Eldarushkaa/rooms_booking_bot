import aiosqlite
from datetime import datetime, date, timedelta
from db.database import get_db

DT_FMT = "%Y-%m-%d %H:%M"
DATE_FMT = "%Y-%m-%d"


# ── Helpers ────────────────────────────────────────────────────────────────

def _parse_dt(s: str) -> datetime:
    return datetime.strptime(s, DT_FMT)


def _parse_date(s: str) -> date:
    return datetime.strptime(s, DATE_FMT).date()


def _expand_occurrences(
    booking: aiosqlite.Row,
    window_start: date,
    window_end: date,
) -> list[tuple[datetime, datetime]]:
    """
    Returns a list of (start_dt, end_dt) datetime pairs for the booking
    that fall within [window_start, window_end].
    For non-recurring bookings, returns the single slot if it's in the window.
    """
    start = _parse_dt(booking["start_dt"])
    end = _parse_dt(booking["end_dt"])
    duration = end - start
    rec_type = booking["recurrence_type"]

    if rec_type is None:
        if window_start <= start.date() <= window_end:
            return [(start, end)]
        return []

    until_str = booking["recurrence_until"]
    until = _parse_date(until_str) if until_str else window_end

    days_raw = booking["recurrence_days"] or ""
    day_nums = [int(d) for d in days_raw.split(",") if d.strip().isdigit()]

    results = []
    cursor = start.date()

    while cursor <= min(until, window_end):
        if cursor >= window_start:
            include = False
            if rec_type == "daily":
                include = True
            elif rec_type == "weekly":
                # day_nums are weekday numbers 0=Mon..6=Sun
                include = cursor.weekday() in day_nums
            elif rec_type == "monthly":
                include = cursor.day in day_nums

            if include:
                occ_start = datetime.combine(cursor, start.time())
                occ_end = occ_start + duration
                results.append((occ_start, occ_end))

        cursor += timedelta(days=1)

    return results


# ── Bookings ───────────────────────────────────────────────────────────────

async def save_booking(
    room_id: int,
    user_id: int,
    company_id: int,
    title: str,
    start_dt: str,
    end_dt: str,
    recurrence_type: str | None = None,
    recurrence_days: str | None = None,
    recurrence_until: str | None = None,
) -> int:
    db = await get_db()
    async with db.execute(
        """
        INSERT INTO bookings
            (room_id, user_id, company_id, title, start_dt, end_dt,
             recurrence_type, recurrence_days, recurrence_until)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            room_id, user_id, company_id, title, start_dt, end_dt,
            recurrence_type, recurrence_days, recurrence_until,
        ),
    ) as cur:
        booking_id = cur.lastrowid
    await db.commit()
    return booking_id


async def cancel_booking(booking_id: int) -> None:
    db = await get_db()
    await db.execute(
        "UPDATE bookings SET is_cancelled = 1 WHERE id = ?", (booking_id,)
    )
    await db.commit()


async def get_booking(booking_id: int) -> aiosqlite.Row | None:
    db = await get_db()
    async with db.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)) as cur:
        return await cur.fetchone()


async def get_user_bookings(user_id: int, company_id: int) -> list[aiosqlite.Row]:
    """Returns all non-cancelled bookings by this user in this company, newest first."""
    db = await get_db()
    async with db.execute(
        """
        SELECT b.*, r.name AS room_name
        FROM bookings b
        JOIN rooms r ON r.id = b.room_id
        WHERE b.user_id = ? AND b.company_id = ? AND b.is_cancelled = 0
        ORDER BY b.start_dt DESC
        """,
        (user_id, company_id),
    ) as cur:
        return await cur.fetchall()


async def get_room_bookings_raw(room_id: int) -> list[aiosqlite.Row]:
    """Returns all non-cancelled bookings for a room (including recurring definitions)."""
    db = await get_db()
    async with db.execute(
        """
        SELECT b.*, u.username, u.full_name
        FROM bookings b
        JOIN users u ON u.user_id = b.user_id
        WHERE b.room_id = ? AND b.is_cancelled = 0
        ORDER BY b.start_dt
        """,
        (room_id,),
    ) as cur:
        return await cur.fetchall()


async def get_room_schedule(
    room_id: int,
    window_start: date,
    window_end: date,
) -> list[dict]:
    """
    Returns expanded booking occurrences for a room within a date window.
    Each dict has: booking_id, title, start_dt, end_dt, username, full_name
    Sorted by start_dt.
    """
    raw = await get_room_bookings_raw(room_id)
    result = []
    for b in raw:
        for occ_start, occ_end in _expand_occurrences(b, window_start, window_end):
            result.append({
                "booking_id": b["id"],
                "title": b["title"],
                "start_dt": occ_start,
                "end_dt": occ_end,
                "username": b["username"],
                "full_name": b["full_name"],
                "recurrence_type": b["recurrence_type"],
            })
    result.sort(key=lambda x: x["start_dt"])
    return result


async def check_conflicts(
    room_id: int,
    start_dt: str,
    end_dt: str,
    recurrence_type: str | None,
    recurrence_days: str | None,
    recurrence_until: str | None,
    exclude_booking_id: int | None = None,
) -> list[dict]:
    """
    Checks whether a proposed booking (possibly recurring) conflicts with existing ones.
    Returns a list of conflicting occurrence dicts (may be empty = no conflict).
    """
    new_start = _parse_dt(start_dt)

    proposed = {
        "start_dt": start_dt,
        "end_dt": end_dt,
        "recurrence_type": recurrence_type,
        "recurrence_days": recurrence_days,
        "recurrence_until": recurrence_until,
    }

    # Determine window for conflict check
    if recurrence_until:
        win_end = _parse_date(recurrence_until)
    else:
        win_end = new_start.date() + timedelta(days=366)  # max 1 year lookahead

    win_start = new_start.date()

    # Expand proposed occurrences
    # Use a minimal aiosqlite.Row-like object
    proposed_row = _make_fake_row(proposed)
    proposed_occurrences = _expand_occurrences(proposed_row, win_start, win_end)

    if not proposed_occurrences:
        return []

    # Get existing bookings for the room
    db = await get_db()
    async with db.execute(
        """
        SELECT b.*, u.username, u.full_name
        FROM bookings b
        JOIN users u ON u.user_id = b.user_id
        WHERE b.room_id = ? AND b.is_cancelled = 0
        """,
        (room_id,),
    ) as cur:
        existing = await cur.fetchall()

    conflicts = []
    for ex in existing:
        if exclude_booking_id and ex["id"] == exclude_booking_id:
            continue
        ex_occurrences = _expand_occurrences(ex, win_start, win_end)
        for p_start, p_end in proposed_occurrences:
            for e_start, e_end in ex_occurrences:
                # Overlap: p_start < e_end AND p_end > e_start
                if p_start < e_end and p_end > e_start:
                    conflicts.append({
                        "booking_id": ex["id"],
                        "title": ex["title"],
                        "start_dt": e_start,
                        "end_dt": e_end,
                        "username": ex["username"],
                        "full_name": ex["full_name"],
                    })
    return conflicts


def _make_fake_row(data: dict):
    """Creates a dict-like object that supports item access for _expand_occurrences."""
    class FakeRow:
        def __init__(self, d):
            self._d = d
        def __getitem__(self, key):
            return self._d.get(key)
    return FakeRow(data)


async def find_free_rooms(
    company_id: int,
    start_dt: str,
    end_dt: str,
) -> list[aiosqlite.Row]:
    """
    Returns rooms in the company that are free during [start_dt, end_dt).
    Only checks the specific time slot (non-recurring check for the given window).
    """
    db = await get_db()
    async with db.execute(
        "SELECT * FROM rooms WHERE company_id = ? AND is_active = 1 ORDER BY name",
        (company_id,),
    ) as cur:
        all_rooms = await cur.fetchall()

    free_rooms = []
    for room in all_rooms:
        conflicts = await check_conflicts(
            room_id=room["id"],
            start_dt=start_dt,
            end_dt=end_dt,
            recurrence_type=None,
            recurrence_days=None,
            recurrence_until=None,
        )
        if not conflicts:
            free_rooms.append(room)
    return free_rooms
