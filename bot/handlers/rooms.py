import logging
from datetime import date, timedelta
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from bot.keyboards.keyboards import (
    kb_room_list, kb_room_view, kb_main_menu, kb_back_to_menu,
)
from db.queries.rooms import get_rooms, get_room
from db.queries.bookings import get_room_schedule

logger = logging.getLogger(__name__)
router = Router()

WEEKDAY_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def _build_schedule_text(room_name: str, week_start: date, week_end: date, schedule: list) -> str:
    """Renders the weekly schedule as an HTML string."""
    lines = [f"📅 <b>Расписание: {room_name}</b>"]
    lines.append(f"Неделя: {week_start.strftime('%d.%m')} – {week_end.strftime('%d.%m.%Y')}\n")

    by_day: dict[date, list] = {}
    for slot in schedule:
        d = slot["start_dt"].date()
        by_day.setdefault(d, []).append(slot)

    current = week_start
    while current <= week_end:
        day_name = WEEKDAY_RU[current.weekday()]
        day_str = current.strftime("%d.%m")
        header = f"<b>{day_name} {day_str}</b>"
        slots = by_day.get(current, [])
        if slots:
            lines.append(header)
            for s in slots:
                uname = f"@{s['username']}" if s["username"] else s["full_name"]
                start_str = s["start_dt"].strftime("%H:%M")
                end_str = s["end_dt"].strftime("%H:%M")
                rec = " 🔁" if s["recurrence_type"] else ""
                lines.append(f"  🔴 {start_str}–{end_str} | {s['title']} | {uname}{rec}")
        else:
            lines.append(f"{header} — свободно")
        current += timedelta(days=1)

    return "\n".join(lines)


# ── Room list ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "room_list")
async def cb_room_list(cb: CallbackQuery, active_company) -> None:
    if not active_company:
        await cb.answer("⛔ Сначала вступите в компанию.", show_alert=True)
        return
    await cb.answer()
    rooms = await get_rooms(active_company["company_id"])
    if not rooms:
        await cb.message.edit_text(
            "🚪 В этой компании пока нет комнат.\nОбратитесь к администратору.",
            reply_markup=kb_back_to_menu(),
        )
        return
    await cb.message.edit_text(
        "🏠 <b>Список комнат</b>\n\nВыберите комнату:",
        reply_markup=kb_room_list(rooms),
        parse_mode="HTML",
    )


# ── Room detail — shows info + current week schedule inline ────────────────

@router.callback_query(F.data.startswith("room_view:"))
async def cb_room_view(cb: CallbackQuery, active_company) -> None:
    if not active_company:
        await cb.answer()
        return
    room_id = int(cb.data.split(":")[1])
    room = await get_room(room_id)
    if not room or not room["is_active"]:
        await cb.answer("❌ Комната недоступна.", show_alert=True)
        return
    await cb.answer()

    today = date.today()
    week_start = today - timedelta(days=today.weekday())  # Monday
    week_end = week_start + timedelta(days=6)
    schedule = await get_room_schedule(room_id, week_start, week_end)

    cap = f"\n👥 Вместимость: {room['capacity']} чел." if room["capacity"] else ""
    desc = f"\n📝 {room['description']}" if room["description"] else ""
    header = f"🚪 <b>{room['name']}</b>{desc}{cap}\n\n"

    schedule_text = _build_schedule_text(room["name"], week_start, week_end, schedule)
    # Remove repeated room name from schedule text (first line)
    schedule_lines = schedule_text.split("\n", 1)
    schedule_body = schedule_lines[1] if len(schedule_lines) > 1 else ""

    await cb.message.edit_text(
        header + schedule_body,
        reply_markup=kb_room_view(room_id),
        parse_mode="HTML",
    )


# ── Room schedule navigation (prev/next week) ──────────────────────────────

@router.callback_query(F.data.startswith("room_schedule:"))
async def cb_room_schedule(cb: CallbackQuery, active_company) -> None:
    if not active_company:
        await cb.answer()
        return

    parts = cb.data.split(":")
    room_id = int(parts[1])
    week_offset = int(parts[2]) if len(parts) > 2 else 0

    room = await get_room(room_id)
    if not room:
        await cb.answer("Комната не найдена.", show_alert=True)
        return
    await cb.answer()

    today = date.today()
    week_start = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
    week_end = week_start + timedelta(days=6)
    schedule = await get_room_schedule(room_id, week_start, week_end)

    cap = f"\n👥 Вместимость: {room['capacity']} чел." if room["capacity"] else ""
    desc = f"\n📝 {room['description']}" if room["description"] else ""
    header = f"🚪 <b>{room['name']}</b>{desc}{cap}\n\n"

    schedule_text = _build_schedule_text(room["name"], week_start, week_end, schedule)
    schedule_lines = schedule_text.split("\n", 1)
    schedule_body = schedule_lines[1] if len(schedule_lines) > 1 else ""

    # Use a nav keyboard with the correct week offset
    nav_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="◀️ Пред. неделя",
                callback_data=f"room_schedule:{room_id}:{week_offset - 1}",
            ),
            InlineKeyboardButton(
                text="След. неделя ▶️",
                callback_data=f"room_schedule:{room_id}:{week_offset + 1}",
            ),
        ],
        [InlineKeyboardButton(text="➕ Забронировать", callback_data=f"book_room:{room_id}")],
        [InlineKeyboardButton(text="◀️ Список комнат", callback_data="room_list")],
    ])

    await cb.message.edit_text(
        header + schedule_body,
        reply_markup=nav_kb,
        parse_mode="HTML",
    )
