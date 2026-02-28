import secrets
import aiosqlite
from db.database import get_db


# ── Company ────────────────────────────────────────────────────────────────

async def create_company(name: str, passcode: str, created_by: int) -> int:
    """Creates a company and returns its new id."""
    db = await get_db()
    async with db.execute(
        "INSERT INTO companies (name, passcode, created_by) VALUES (?, ?, ?)",
        (name, passcode, created_by),
    ) as cur:
        company_id = cur.lastrowid
    await db.commit()
    return company_id


async def get_company(company_id: int) -> aiosqlite.Row | None:
    db = await get_db()
    async with db.execute("SELECT * FROM companies WHERE id = ?", (company_id,)) as cur:
        return await cur.fetchone()


async def update_company_passcode(company_id: int, new_passcode: str) -> None:
    db = await get_db()
    await db.execute(
        "UPDATE companies SET passcode = ? WHERE id = ?",
        (new_passcode, company_id),
    )
    await db.commit()


async def find_companies_by_passcode(passcode: str) -> list[aiosqlite.Row]:
    """Returns all companies that match the given passcode."""
    db = await get_db()
    async with db.execute(
        "SELECT * FROM companies WHERE passcode = ?", (passcode,)
    ) as cur:
        return await cur.fetchall()


# ── Membership ─────────────────────────────────────────────────────────────

async def get_membership(user_id: int, company_id: int) -> aiosqlite.Row | None:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM memberships WHERE user_id = ? AND company_id = ?",
        (user_id, company_id),
    ) as cur:
        return await cur.fetchone()


async def get_active_membership(user_id: int) -> aiosqlite.Row | None:
    """Returns the membership row for the user's currently active company."""
    db = await get_db()
    async with db.execute(
        """
        SELECT m.*, c.name AS company_name, c.passcode
        FROM memberships m
        JOIN companies c ON c.id = m.company_id
        WHERE m.user_id = ? AND m.is_active_company = 1
        """,
        (user_id,),
    ) as cur:
        return await cur.fetchone()


async def get_all_memberships(user_id: int) -> list[aiosqlite.Row]:
    """Returns all companies a user belongs to."""
    db = await get_db()
    async with db.execute(
        """
        SELECT m.*, c.name AS company_name
        FROM memberships m
        JOIN companies c ON c.id = m.company_id
        WHERE m.user_id = ?
        ORDER BY m.joined_at
        """,
        (user_id,),
    ) as cur:
        return await cur.fetchall()


async def add_member(user_id: int, company_id: int, is_admin: bool = False) -> None:
    """Adds a user to a company. Silently ignores if already a member.
    Sets this company as active only if user has no other active company."""
    db = await get_db()
    # Check if user already has an active company
    async with db.execute(
        "SELECT 1 FROM memberships WHERE user_id = ? AND is_active_company = 1",
        (user_id,),
    ) as cur:
        has_active = await cur.fetchone() is not None

    is_active = 0 if has_active else 1

    await db.execute(
        """
        INSERT INTO memberships (user_id, company_id, is_admin, is_active_company)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id, company_id) DO NOTHING
        """,
        (user_id, company_id, int(is_admin), is_active),
    )
    await db.commit()


async def set_active_company(user_id: int, company_id: int) -> None:
    """Switches the user's active company."""
    db = await get_db()
    await db.execute(
        "UPDATE memberships SET is_active_company = 0 WHERE user_id = ?",
        (user_id,),
    )
    await db.execute(
        "UPDATE memberships SET is_active_company = 1 WHERE user_id = ? AND company_id = ?",
        (user_id, company_id),
    )
    await db.commit()


async def remove_member(user_id: int, company_id: int) -> None:
    """Removes a user from a company. If that was their active company, picks another."""
    db = await get_db()
    # Check if this was the active company
    async with db.execute(
        "SELECT is_active_company FROM memberships WHERE user_id = ? AND company_id = ?",
        (user_id, company_id),
    ) as cur:
        row = await cur.fetchone()
    was_active = row and row["is_active_company"] == 1

    await db.execute(
        "DELETE FROM memberships WHERE user_id = ? AND company_id = ?",
        (user_id, company_id),
    )
    await db.commit()

    if was_active:
        # Pick another membership to make active
        async with db.execute(
            "SELECT id, company_id FROM memberships WHERE user_id = ? LIMIT 1",
            (user_id,),
        ) as cur:
            other = await cur.fetchone()
        if other:
            await db.execute(
                "UPDATE memberships SET is_active_company = 1 WHERE id = ?",
                (other["id"],),
            )
            await db.commit()


async def count_admins(company_id: int) -> int:
    """Returns the number of admins in a company."""
    db = await get_db()
    async with db.execute(
        "SELECT COUNT(*) FROM memberships WHERE company_id = ? AND is_admin = 1",
        (company_id,),
    ) as cur:
        row = await cur.fetchone()
    return row[0] if row else 0


async def delete_company(company_id: int) -> None:
    """Deletes a company and all its memberships, rooms, bookings, and invite tokens."""
    db = await get_db()
    await db.execute("DELETE FROM invite_tokens WHERE company_id = ?", (company_id,))
    await db.execute("UPDATE bookings SET is_cancelled = 1 WHERE company_id = ?", (company_id,))
    await db.execute("UPDATE rooms SET is_active = 0 WHERE company_id = ?", (company_id,))
    await db.execute("DELETE FROM memberships WHERE company_id = ?", (company_id,))
    await db.execute("DELETE FROM companies WHERE id = ?", (company_id,))
    await db.commit()


async def set_admin(user_id: int, company_id: int, is_admin: bool) -> None:
    db = await get_db()
    await db.execute(
        "UPDATE memberships SET is_admin = ? WHERE user_id = ? AND company_id = ?",
        (int(is_admin), user_id, company_id),
    )
    await db.commit()


async def get_company_members(company_id: int) -> list[aiosqlite.Row]:
    db = await get_db()
    async with db.execute(
        """
        SELECT m.*, u.username, u.full_name
        FROM memberships m
        JOIN users u ON u.user_id = m.user_id
        WHERE m.company_id = ?
        ORDER BY m.is_admin DESC, u.full_name
        """,
        (company_id,),
    ) as cur:
        return await cur.fetchall()


# ── Invite Tokens ──────────────────────────────────────────────────────────

async def create_invite_token(
    company_id: int,
    created_by: int,
    uses_left: int | None = None,
    expires_at: str | None = None,
) -> str:
    """Creates a new invite token and returns the token string."""
    token = secrets.token_urlsafe(16)
    db = await get_db()
    await db.execute(
        """
        INSERT INTO invite_tokens (company_id, token, created_by, uses_left, expires_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (company_id, token, created_by, uses_left, expires_at),
    )
    await db.commit()
    return token


async def get_invite_token(token: str) -> aiosqlite.Row | None:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM invite_tokens WHERE token = ?", (token,)
    ) as cur:
        return await cur.fetchone()


async def consume_invite_token(token: str) -> None:
    """Decrements uses_left by 1. If uses_left reaches 0, deletes the token."""
    db = await get_db()
    async with db.execute(
        "SELECT uses_left FROM invite_tokens WHERE token = ?", (token,)
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return
    if row["uses_left"] is not None:
        new_uses = row["uses_left"] - 1
        if new_uses <= 0:
            await db.execute("DELETE FROM invite_tokens WHERE token = ?", (token,))
        else:
            await db.execute(
                "UPDATE invite_tokens SET uses_left = ? WHERE token = ?",
                (new_uses, token),
            )
        await db.commit()


async def get_company_tokens(company_id: int) -> list[aiosqlite.Row]:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM invite_tokens WHERE company_id = ? ORDER BY created_at DESC",
        (company_id,),
    ) as cur:
        return await cur.fetchall()


async def delete_invite_token(token_id: int) -> None:
    db = await get_db()
    await db.execute("DELETE FROM invite_tokens WHERE id = ?", (token_id,))
    await db.commit()
