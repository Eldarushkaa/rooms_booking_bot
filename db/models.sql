-- ============================================================
-- Booking Bot Database Schema
-- ============================================================

CREATE TABLE IF NOT EXISTS users (
    user_id    INTEGER PRIMARY KEY,
    username   TEXT,
    full_name  TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS companies (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL,
    passcode   TEXT    NOT NULL,
    created_by INTEGER NOT NULL REFERENCES users(user_id),
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- One row per user×company. is_active_company=1 for at most one row per user.
CREATE TABLE IF NOT EXISTS memberships (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id           INTEGER NOT NULL REFERENCES users(user_id),
    company_id        INTEGER NOT NULL REFERENCES companies(id),
    is_admin          INTEGER NOT NULL DEFAULT 0,
    is_active_company INTEGER NOT NULL DEFAULT 0,
    joined_at         TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, company_id)
);

-- Invite tokens for joining without a passcode
CREATE TABLE IF NOT EXISTS invite_tokens (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    token      TEXT    NOT NULL UNIQUE,
    created_by INTEGER NOT NULL REFERENCES users(user_id),
    uses_left  INTEGER,            -- NULL = unlimited
    expires_at TEXT,               -- NULL = never expires
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS rooms (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id  INTEGER NOT NULL REFERENCES companies(id),
    name        TEXT    NOT NULL,
    description TEXT,
    capacity    INTEGER,
    is_active   INTEGER NOT NULL DEFAULT 1
);

-- Bookings. Recurrence is stored as metadata; occurrences are expanded in-memory.
-- recurrence_type: NULL | 'daily' | 'weekly' | 'monthly'
-- recurrence_days: comma-separated integers
--   weekly:  day-of-week numbers 0=Mon..6=Sun  e.g. "0,2,4"
--   monthly: day-of-month numbers 1..31         e.g. "1,15"
-- recurrence_until: ISO date string "YYYY-MM-DD" (inclusive)
CREATE TABLE IF NOT EXISTS bookings (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id          INTEGER NOT NULL REFERENCES rooms(id),
    user_id          INTEGER NOT NULL REFERENCES users(user_id),
    company_id       INTEGER NOT NULL REFERENCES companies(id),
    title            TEXT    NOT NULL,
    start_dt         TEXT    NOT NULL,  -- "YYYY-MM-DD HH:MM"
    end_dt           TEXT    NOT NULL,  -- "YYYY-MM-DD HH:MM"
    recurrence_type  TEXT,
    recurrence_days  TEXT,
    recurrence_until TEXT,
    is_cancelled     INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
);
