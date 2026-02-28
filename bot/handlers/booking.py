import logging
from datetime import datetime, date, timedelta
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.keyboards.keyboards import (
    kb_recurrence_type, kb_weekdays, kb_booking_confirm,
    kb_cancel, kb_my_bookings_nav, kb_free_rooms, kb_back_to_menu,
    kb_main_menu, kb_date_picker, kb_start_time_picker, kb_duration_picker,
    kb_until_input, kb_monthly_days_input, kb_booking_back_to_title, kb_room_view,
)
from db.queries.rooms import get_rooms, get_room
from db.queries.bookings import (
    save_booking, cancel_booking, get_user_bookings,
    check_conflicts, find_free_rooms,
)

logger = logging.getLogger(__name__)
router = Router()

DT_FMT = "%Y-%m-%d %H:%M"
DATE_FMT_INPUT = "%d.%m.%Y"
TIME_FMT_INPUT = "%H:%M"


class BookingStates(StatesGroup):
    entering_title = State()
    entering_date = State()
    entering_start_time = State()
    entering_duration = State()
    choosing_recurrence = State()
    choosing_weekdays = State()
    entering_monthly_days = State()
    entering_recurrence_until = State()
    confirming = State()
    # Find free room flow
    find_entering_date = State()
    find_entering_time = State()


def _format_booking_summary(data: dict) -> str:
    title = data["title"]
    start_dt = data["start_dt"]
    end_dt = data["end_dt"]
    room_name = data.get("room_name", "?")
    rec_type = data.get("recurrence_type")
    rec_days = data.get("recurrence_days")
    rec_until = data.get("recurrence_until")

    start = datetime.strptime(start_dt, DT_FMT)
    end = datetime.strptime(end_dt, DT_FMT)

    lines = [
        f"📋 <b>Подтверждение бронирования</b>\n",
        f"🚪 Комната: <b>{room_name}</b>",
        f"📌 Название: <b>{title}</b>",
        f"📅 Дата: {start.strftime('%d.%m.%Y')}",
        f"⏰ Время: {start.strftime('%H:%M')}–{end.strftime('%H:%M')}",
    ]

    if rec_type == "daily":
        lines.append(f"🔁 Повтор: каждый день до {rec_until}")
    elif rec_type == "weekly":
        day_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        nums = [int(d) for d in rec_days.split(",") if d]
        days_str = ", ".join(day_names[n] for n in sorted(nums))
        lines.append(f"🔁 Повтор: по {days_str} до {rec_until}")
    elif rec_type == "monthly":
        lines.append(f"🔁 Повтор: по числам {rec_days} каждого месяца до {rec_until}")

    return "\n".join(lines)


def _parse_date_input(text: str) -> date | None:
    """Parses DD.MM.YYYY or YYYY-MM-DD."""
    for fmt in (DATE_FMT_INPUT, "%Y-%m-%d"):
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _parse_time(text: str):
    """Parses 'HH:MM'. Returns time object or None."""
    try:
        return datetime.strptime(text.strip(), "%H:%M").time()
    except ValueError:
        return None


def _parse_time_range(text: str) -> tuple[str, str] | None:
    """Parses 'HH:MM-HH:MM' or 'HH:MM – HH:MM'. Used for find-free-room flow."""
    text = text.replace(" ", "").replace("–", "-")
    parts = text.split("-")
    if len(parts) != 2:
        return None
    try:
        start = datetime.strptime(parts[0], "%H:%M").time()
        end = datetime.strptime(parts[1], "%H:%M").time()
        if end <= start:
            return None
        return parts[0], parts[1]
    except ValueError:
        return None


async def _next_half_hour_slots(booking_date: date, room_id: int, n: int = 4) -> list[str]:
    """Return up to n upcoming free half-hour slots (HH:MM) for the given room.
    Today: start after now. Future date: start at 11:00."""
    now = datetime.now()
    today = now.date()
    date_str = booking_date.isoformat()

    # Determine starting hour/minute
    if booking_date == today:
        # Round now up to next half-hour
        start_h, start_m = now.hour, now.minute
    else:
        start_h, start_m = 11, 0

    free_slots: list[str] = []
    for h in range(start_h, 24):
        for m in (0, 30):
            if h == start_h and m < start_m:
                continue
            slot_start = f"{date_str} {h:02d}:{m:02d}"
            end_m = m + 30
            end_h = h + end_m // 60
            end_m = end_m % 60
            if end_h >= 24:
                break
            slot_end = f"{date_str} {end_h:02d}:{end_m:02d}"
            conflicts = await check_conflicts(
                room_id=room_id,
                start_dt=slot_start,
                end_dt=slot_end,
                recurrence_type=None,
                recurrence_days=None,
                recurrence_until=None,
            )
            if not conflicts:
                free_slots.append(f"{h:02d}:{m:02d}")
            if len(free_slots) >= n:
                return free_slots
    return free_slots


# ── My Bookings ────────────────────────────────────────────────────────────

@router.callback_query(F.data == "my_bookings")
async def cb_my_bookings(cb: CallbackQuery, active_company) -> None:
    if not active_company:
        await cb.answer("⛔ Выберите активную компанию.", show_alert=True)
        return
    await cb.answer()
    bookings = await get_user_bookings(cb.from_user.id, active_company["company_id"])
    if not bookings:
        await cb.message.edit_text(
            "📅 У вас нет активных бронирований.",
            reply_markup=kb_my_bookings_nav(),
        )
        return

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    lines = ["📅 <b>Ваши бронирования:</b>\n"]
    rows = []
    for b in bookings:
        start = datetime.strptime(b["start_dt"], DT_FMT)
        end = datetime.strptime(b["end_dt"], DT_FMT)
        rec = " 🔁" if b["recurrence_type"] else ""
        lines.append(
            f"• {b['room_name']} | {b['title']}\n"
            f"  {start.strftime('%d.%m.%Y %H:%M')}–{end.strftime('%H:%M')}{rec}"
        )
        rows.append([InlineKeyboardButton(
            text=f"❌ Отменить: {b['title'][:20]}",
            callback_data=f"cancel_booking_id:{b['id']}",
        )])
    rows.append([InlineKeyboardButton(text="◀️ Главное меню", callback_data="main_menu")])

    await cb.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("cancel_booking_id:"))
async def cb_cancel_booking(cb: CallbackQuery, active_company) -> None:
    booking_id = int(cb.data.split(":")[1])
    await cancel_booking(booking_id)
    await cb.answer("✅ Бронирование отменено.", show_alert=True)
    # Refresh the list
    await cb_my_bookings(cb, active_company)


# ── Start booking flow ─────────────────────────────────────────────────────

async def _start_booking_for_room(cb: CallbackQuery, state: FSMContext, room_id: int) -> None:
    room = await get_room(room_id)
    if not room or not room["is_active"]:
        await cb.answer("❌ Комната недоступна.", show_alert=True)
        return
    await state.update_data(room_id=room_id, room_name=room["name"])
    await cb.message.edit_text(
        f"➕ <b>Бронирование: {room['name']}</b>\n\n"
        "📌 Введите название брони (например: «Совещание»):",
        reply_markup=kb_booking_back_to_title(),
        parse_mode="HTML",
    )
    await state.set_state(BookingStates.entering_title)


# ── Back navigation handler ────────────────────────────────────────────────

@router.callback_query(F.data.startswith("booking_back:"))
async def cb_booking_back(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    step = cb.data.split(":")[1]
    data = await state.get_data()

    if step == "room":
        # Go back to room view, clear booking state
        room_id = data.get("room_id")
        room_name = data.get("room_name", "Комната")
        await state.clear()
        if room_id:
            room = await get_room(room_id)
            cap = f" · {room['capacity']} чел." if room and room["capacity"] else ""
            desc = f"\n{room['description']}" if room and room["description"] else ""
            await cb.message.edit_text(
                f"🚪 <b>{room_name}</b>{cap}{desc}",
                reply_markup=kb_room_view(room_id),
                parse_mode="HTML",
            )
        else:
            await cb.message.edit_text("Выберите действие:", reply_markup=kb_back_to_menu())
        return

    elif step == "title":
        # Go back to title entry
        room_name = data.get("room_name", "комнату")
        await cb.message.edit_text(
            f"➕ <b>Бронирование: {room_name}</b>\n\n"
            "📌 Введите название брони (например: «Совещание»):",
            reply_markup=kb_booking_back_to_title(),
            parse_mode="HTML",
        )
        await state.set_state(BookingStates.entering_title)

    elif step == "date":
        # Go back to date entry
        today_str = date.today().strftime(DATE_FMT_INPUT)
        await cb.message.edit_text(
            f"📅 Введите дату брони в формате ДД.ММ.ГГГГ\n"
            f"Например: {today_str}\n\nИли выберите быстро:",
            reply_markup=kb_date_picker(),
        )
        await state.set_state(BookingStates.entering_date)

    elif step == "start_time":
        # Go back to start time entry
        booking_date = data.get("booking_date", "")
        room_id = data.get("room_id")
        d = datetime.strptime(booking_date, "%Y-%m-%d").date() if booking_date else date.today()
        slots = await _next_half_hour_slots(d, room_id) if room_id else []
        date_display = d.strftime("%d.%m.%Y")
        hint = "\n\nИли введите время вручную в формате ЧЧ:ММ:" if slots else "\nВведите время начала в формате ЧЧ:ММ:"
        await cb.message.edit_text(
            f"⏰ Дата: <b>{date_display}</b>\n\nВыберите время начала:{hint}",
            reply_markup=kb_start_time_picker(slots),
            parse_mode="HTML",
        )
        await state.set_state(BookingStates.entering_start_time)

    elif step == "duration":
        # Go back to duration entry — re-compute available durations
        booking_date = data.get("booking_date", "")
        start_time_str = data.get("start_time", "")
        room_id = data.get("room_id")
        date_display = ""
        available_minutes: list[int] = []
        if booking_date and start_time_str:
            d = datetime.strptime(booking_date, "%Y-%m-%d").date()
            date_display = d.strftime("%d.%m.%Y")
            for minutes in (30, 60, 90, 120):
                start_dt = datetime.strptime(f"{booking_date} {start_time_str}", DT_FMT)
                end_dt = start_dt + timedelta(minutes=minutes)
                if room_id:
                    conflicts = await check_conflicts(
                        room_id=room_id,
                        start_dt=start_dt.strftime(DT_FMT),
                        end_dt=end_dt.strftime(DT_FMT),
                        recurrence_type=None,
                        recurrence_days=None,
                        recurrence_until=None,
                    )
                    if not conflicts:
                        available_minutes.append(minutes)
                else:
                    available_minutes.append(minutes)
        else:
            available_minutes = [30, 60, 90, 120]
        await cb.message.edit_text(
            f"⏰ Начало: <b>{date_display} {start_time_str}</b>\n\n"
            "Выберите продолжительность или введите время окончания (ЧЧ:ММ):",
            reply_markup=kb_duration_picker(available_minutes),
            parse_mode="HTML",
        )
        await state.set_state(BookingStates.entering_duration)

    elif step == "recurrence":
        # Go back to recurrence type picker
        await cb.message.edit_text(
            "🔁 Это разовое бронирование или повторяющееся?",
            reply_markup=kb_recurrence_type(),
        )
        await state.set_state(BookingStates.choosing_recurrence)


@router.callback_query(F.data.startswith("book_room:"))
async def cb_book_room(cb: CallbackQuery, state: FSMContext, active_company) -> None:
    if not active_company:
        await cb.answer("⛔ Выберите активную компанию.", show_alert=True)
        return
    await cb.answer()
    room_id = int(cb.data.split(":")[1])
    await _start_booking_for_room(cb, state, room_id)


@router.callback_query(F.data.startswith("book_free_room:"))
async def cb_book_free_room(cb: CallbackQuery, state: FSMContext, active_company) -> None:
    if not active_company:
        await cb.answer("⛔ Выберите активную компанию.", show_alert=True)
        return
    await cb.answer()
    room_id = int(cb.data.split(":")[1])
    # Restore pre-entered date/time to skip those steps
    data = await state.get_data()
    await _start_booking_for_room(cb, state, room_id)
    # Preserve the time data from find flow
    if "find_start_dt" in data and "find_end_dt" in data:
        await state.update_data(
            prefilled_start_dt=data["find_start_dt"],
            prefilled_end_dt=data["find_end_dt"],
        )


# ── Title ──────────────────────────────────────────────────────────────────

@router.message(BookingStates.entering_title, F.text, ~F.text.startswith("/"))
async def msg_title(message: Message, state: FSMContext) -> None:
    title = message.text.strip()
    if len(title) < 1 or len(title) > 128:
        await message.answer("❗ Название должно быть от 1 до 128 символов. Попробуйте ещё раз:")
        return
    await state.update_data(title=title)
    # Check if date is prefilled (from find free room flow)
    data = await state.get_data()
    if "prefilled_start_dt" in data:
        await state.update_data(
            start_dt=data["prefilled_start_dt"],
            end_dt=data["prefilled_end_dt"],
        )
        await message.answer(
            "🔁 Это разовое бронирование или повторяющееся?",
            reply_markup=kb_recurrence_type(),
        )
        await state.set_state(BookingStates.choosing_recurrence)
    else:
        today_str = date.today().strftime(DATE_FMT_INPUT)
        await message.answer(
            f"📅 Введите дату брони в формате ДД.ММ.ГГГГ\n"
            f"Например: {today_str}\n\n"
            "Или выберите быстро:",
            reply_markup=kb_date_picker(),
        )
        await state.set_state(BookingStates.entering_date)


# ── Date ───────────────────────────────────────────────────────────────────

async def _set_booking_date(target, state: FSMContext, d: date) -> None:
    """Common helper: stores the date and asks for start time."""
    await state.update_data(booking_date=d.isoformat())
    data = await state.get_data()
    room_id = data.get("room_id")
    date_display = d.strftime("%d.%m.%Y")
    slots = await _next_half_hour_slots(d, room_id) if room_id else []
    hint = "\n\nИли введите время вручную в формате ЧЧ:ММ:" if slots else "\nВведите время начала в формате ЧЧ:ММ:"
    text = f"⏰ Дата: <b>{date_display}</b>\n\nВыберите время начала:{hint}"
    kb = kb_start_time_picker(slots)
    if hasattr(target, "message"):
        await target.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await target.answer(text, reply_markup=kb, parse_mode="HTML")
    await state.set_state(BookingStates.entering_start_time)


@router.callback_query(BookingStates.entering_date, F.data == "date_today")
async def cb_date_today(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await _set_booking_date(cb, state, date.today())


@router.callback_query(BookingStates.entering_date, F.data == "date_tomorrow")
async def cb_date_tomorrow(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await _set_booking_date(cb, state, date.today() + timedelta(days=1))


@router.message(BookingStates.entering_date, F.text, ~F.text.startswith("/"))
async def msg_date(message: Message, state: FSMContext) -> None:
    d = _parse_date_input(message.text)
    if d is None:
        await message.answer("❗ Неверный формат даты. Введите дату в формате ДД.ММ.ГГГГ:")
        return
    if d < date.today():
        await message.answer("❗ Нельзя бронировать прошедшую дату. Введите сегодняшнюю или будущую:")
        return
    await _set_booking_date(message, state, d)


# ── Start time ─────────────────────────────────────────────────────────────

async def _proceed_to_duration(target, state: FSMContext, start_time_str: str) -> None:
    """Store start time and ask for duration. Only show conflict-free durations."""
    await state.update_data(start_time=start_time_str)
    data = await state.get_data()
    room_id = data.get("room_id")
    booking_date = data["booking_date"]
    date_display = datetime.strptime(booking_date, "%Y-%m-%d").strftime("%d.%m.%Y")

    # Check which preset durations are free
    available_minutes: list[int] = []
    for minutes in (30, 60, 90, 120):
        start_dt = datetime.strptime(f"{booking_date} {start_time_str}", DT_FMT)
        end_dt = start_dt + timedelta(minutes=minutes)
        if room_id:
            conflicts = await check_conflicts(
                room_id=room_id,
                start_dt=start_dt.strftime(DT_FMT),
                end_dt=end_dt.strftime(DT_FMT),
                recurrence_type=None,
                recurrence_days=None,
                recurrence_until=None,
            )
            if not conflicts:
                available_minutes.append(minutes)
        else:
            available_minutes.append(minutes)

    text = (
        f"⏰ Начало: <b>{date_display} {start_time_str}</b>\n\n"
        "Выберите продолжительность или введите время окончания (ЧЧ:ММ):"
    )
    kb = kb_duration_picker(available_minutes)
    if hasattr(target, "message"):
        await target.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await target.answer(text, reply_markup=kb, parse_mode="HTML")
    await state.set_state(BookingStates.entering_duration)


@router.callback_query(BookingStates.entering_start_time, F.data.startswith("start_time:"))
async def cb_start_time_slot(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    start_time_str = cb.data.split(":", 1)[1]
    await _proceed_to_duration(cb, state, start_time_str)


@router.message(BookingStates.entering_start_time, F.text, ~F.text.startswith("/"))
async def msg_start_time(message: Message, state: FSMContext) -> None:
    t = _parse_time(message.text)
    if t is None:
        await message.answer("❗ Неверный формат. Введите время в формате ЧЧ:ММ:")
        return
    await _proceed_to_duration(message, state, t.strftime("%H:%M"))


# ── Duration ───────────────────────────────────────────────────────────────

async def _apply_duration(target, state: FSMContext, end_time_str: str) -> None:
    """Validate end > start, conflict-check, then move to recurrence."""
    data = await state.get_data()
    booking_date = data["booking_date"]
    start_time_str = data["start_time"]
    start_dt = f"{booking_date} {start_time_str}"
    end_dt = f"{booking_date} {end_time_str}"

    # Sanity check
    s = datetime.strptime(start_dt, DT_FMT)
    e = datetime.strptime(end_dt, DT_FMT)
    if e <= s:
        err = "❗ Время окончания должно быть позже начала. Введите другое время или нажмите ◀️ Назад:"
        # Re-compute available durations for the correct keyboard
        avail = []
        room_id = data.get("room_id")
        for mins in (30, 60, 90, 120):
            candidate_end = s + timedelta(minutes=mins)
            if room_id:
                cfls = await check_conflicts(
                    room_id=room_id,
                    start_dt=start_dt,
                    end_dt=candidate_end.strftime(DT_FMT),
                    recurrence_type=None, recurrence_days=None, recurrence_until=None,
                )
                if not cfls:
                    avail.append(mins)
            else:
                avail.append(mins)
        kb = kb_duration_picker(avail)
        if hasattr(target, "message"):
            await target.message.answer(err, reply_markup=kb)
        else:
            await target.answer(err, reply_markup=kb)
        return

    # Early conflict check
    early_conflicts = await check_conflicts(
        room_id=data["room_id"],
        start_dt=start_dt,
        end_dt=end_dt,
        recurrence_type=None,
        recurrence_days=None,
        recurrence_until=None,
    )
    if early_conflicts:
        conflict_lines = []
        for c in early_conflicts[:3]:
            conflict_lines.append(
                f"  🔴 {c['start_dt'].strftime('%H:%M')}–{c['end_dt'].strftime('%H:%M')} | {c['title']}"
            )
        more = f"\n  ...и ещё {len(early_conflicts) - 3}" if len(early_conflicts) > 3 else ""
        # Show only actually-free preset durations in the keyboard
        avail = []
        room_id = data.get("room_id")
        for mins in (30, 60, 90, 120):
            candidate_end = s + timedelta(minutes=mins)
            if room_id:
                cfls = await check_conflicts(
                    room_id=room_id,
                    start_dt=start_dt,
                    end_dt=candidate_end.strftime(DT_FMT),
                    recurrence_type=None, recurrence_days=None, recurrence_until=None,
                )
                if not cfls:
                    avail.append(mins)
            else:
                avail.append(mins)
        err_text = (
            "❌ <b>Это время уже занято:</b>\n"
            + "\n".join(conflict_lines) + more
            + "\n\nВыберите другую продолжительность или введите другое время окончания:"
        )
        if hasattr(target, "message"):
            await target.message.answer(err_text, reply_markup=kb_duration_picker(avail), parse_mode="HTML")
        else:
            await target.answer(err_text, reply_markup=kb_duration_picker(avail), parse_mode="HTML")
        return

    await state.update_data(start_dt=start_dt, end_dt=end_dt)
    text = "🔁 Это разовое бронирование или повторяющееся?"
    if hasattr(target, "message"):
        await target.message.answer(text, reply_markup=kb_recurrence_type())
    else:
        await target.answer(text, reply_markup=kb_recurrence_type())
    await state.set_state(BookingStates.choosing_recurrence)


@router.callback_query(BookingStates.entering_duration, F.data.startswith("duration:"))
async def cb_duration_slot(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    minutes = int(cb.data.split(":")[1])
    data = await state.get_data()
    booking_date = data["booking_date"]
    start_time_str = data["start_time"]
    start_dt = datetime.strptime(f"{booking_date} {start_time_str}", DT_FMT)
    end_dt = start_dt + timedelta(minutes=minutes)
    end_time_str = end_dt.strftime("%H:%M")
    await _apply_duration(cb, state, end_time_str)


@router.message(BookingStates.entering_duration, F.text, ~F.text.startswith("/"))
async def msg_duration_manual(message: Message, state: FSMContext) -> None:
    t = _parse_time(message.text)
    if t is None:
        await message.answer("❗ Неверный формат. Введите время окончания в формате ЧЧ:ММ:")
        return
    await _apply_duration(message, state, t.strftime("%H:%M"))


# ── Recurrence ─────────────────────────────────────────────────────────────

@router.callback_query(BookingStates.choosing_recurrence, F.data == "rec_type:none")
async def cb_rec_none(cb: CallbackQuery, state: FSMContext, active_company) -> None:
    await cb.answer()
    await state.update_data(recurrence_type=None, recurrence_days=None, recurrence_until=None)
    await _check_and_confirm(cb, state, active_company)


@router.callback_query(BookingStates.choosing_recurrence, F.data == "rec_type:daily")
async def cb_rec_daily(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await state.update_data(recurrence_type="daily", recurrence_days=None)
    await cb.message.edit_text(
        "📅 Введите дату окончания повтора в формате ДД.ММ.ГГГГ:",
        reply_markup=kb_until_input(),
    )
    await state.set_state(BookingStates.entering_recurrence_until)


@router.callback_query(BookingStates.choosing_recurrence, F.data == "rec_type:weekly")
async def cb_rec_weekly(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await state.update_data(recurrence_type="weekly", selected_weekdays=[])
    await cb.message.edit_text(
        "📆 Выберите дни недели для повтора:",
        reply_markup=kb_weekdays([]),
    )
    await state.set_state(BookingStates.choosing_weekdays)


@router.callback_query(BookingStates.choosing_recurrence, F.data == "rec_type:monthly")
async def cb_rec_monthly(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await state.update_data(recurrence_type="monthly")
    await cb.message.edit_text(
        "🗓 Введите числа месяца через запятую (например: 1,15,28):",
        reply_markup=kb_monthly_days_input(),
    )
    await state.set_state(BookingStates.entering_monthly_days)


# ── Weekday picker ─────────────────────────────────────────────────────────

@router.callback_query(BookingStates.choosing_weekdays, F.data.startswith("weekday_toggle:"))
async def cb_weekday_toggle(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    day = int(cb.data.split(":")[1])
    data = await state.get_data()
    selected = data.get("selected_weekdays", [])
    if day in selected:
        selected.remove(day)
    else:
        selected.append(day)
    await state.update_data(selected_weekdays=selected)
    await cb.message.edit_reply_markup(reply_markup=kb_weekdays(selected))


@router.callback_query(BookingStates.choosing_weekdays, F.data == "weekday_confirm")
async def cb_weekday_confirm(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    data = await state.get_data()
    selected = data.get("selected_weekdays", [])
    if not selected:
        await cb.answer("❗ Выберите хотя бы один день недели.", show_alert=True)
        return
    rec_days = ",".join(str(d) for d in sorted(selected))
    await state.update_data(recurrence_days=rec_days)
    await cb.message.edit_text(
        "📅 Введите дату окончания повтора в формате ДД.ММ.ГГГГ:",
        reply_markup=kb_until_input(),
    )
    await state.set_state(BookingStates.entering_recurrence_until)


# ── Monthly days ───────────────────────────────────────────────────────────

@router.message(BookingStates.entering_monthly_days, F.text, ~F.text.startswith("/"))
async def msg_monthly_days(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    parts = [p.strip() for p in text.split(",")]
    try:
        days = [int(p) for p in parts if p]
        if not days or any(d < 1 or d > 31 for d in days):
            raise ValueError
    except ValueError:
        await message.answer(
            "❗ Введите числа от 1 до 31 через запятую. Пример: 1,15,28",
            reply_markup=kb_monthly_days_input(),
        )
        return
    rec_days = ",".join(str(d) for d in sorted(set(days)))
    await state.update_data(recurrence_days=rec_days)
    await message.answer(
        "📅 Введите дату окончания повтора в формате ДД.ММ.ГГГГ:",
        reply_markup=kb_until_input(),
    )
    await state.set_state(BookingStates.entering_recurrence_until)


# ── Recurrence until ───────────────────────────────────────────────────────

@router.callback_query(BookingStates.entering_recurrence_until, F.data == "until_1year")
async def cb_until_1year(cb: CallbackQuery, state: FSMContext, active_company) -> None:
    await cb.answer()
    data = await state.get_data()
    booking_date = data.get("booking_date", data.get("start_dt", "")[:10])
    start_date = datetime.strptime(booking_date, "%Y-%m-%d").date() if booking_date else date.today()
    until_date = start_date.replace(year=start_date.year + 1)
    await state.update_data(recurrence_until=until_date.isoformat())
    await _check_and_confirm(cb, state, active_company)


@router.message(BookingStates.entering_recurrence_until, F.text, ~F.text.startswith("/"))
async def msg_rec_until(message: Message, state: FSMContext, active_company) -> None:
    d = _parse_date_input(message.text)
    if d is None:
        await message.answer("❗ Неверный формат. Введите ДД.ММ.ГГГГ:")
        return
    data = await state.get_data()
    booking_date = data.get("booking_date", data.get("start_dt", "")[:10])
    start_date = datetime.strptime(booking_date, "%Y-%m-%d").date() if booking_date else date.today()
    if d <= start_date:
        await message.answer("❗ Дата окончания должна быть позже даты начала. Попробуйте ещё раз:")
        return
    await state.update_data(recurrence_until=d.isoformat())
    await _check_and_confirm_msg(message, state, active_company)


# ── Conflict check & confirmation ──────────────────────────────────────────

async def _check_and_confirm(cb: CallbackQuery, state: FSMContext, active_company) -> None:
    data = await state.get_data()
    conflicts = await check_conflicts(
        room_id=data["room_id"],
        start_dt=data["start_dt"],
        end_dt=data["end_dt"],
        recurrence_type=data.get("recurrence_type"),
        recurrence_days=data.get("recurrence_days"),
        recurrence_until=data.get("recurrence_until"),
    )
    if conflicts:
        conflict_lines = []
        for c in conflicts[:3]:
            conflict_lines.append(
                f"  🔴 {c['start_dt'].strftime('%d.%m %H:%M')}–{c['end_dt'].strftime('%H:%M')} | {c['title']}"
            )
        more = f"\n  ...и ещё {len(conflicts) - 3}" if len(conflicts) > 3 else ""
        await cb.message.edit_text(
            "❌ <b>Обнаружен конфликт с существующими бронями:</b>\n"
            + "\n".join(conflict_lines) + more
            + "\n\nВернитесь и выберите другое время.",
            reply_markup=kb_back_to_menu(),
            parse_mode="HTML",
        )
        await state.clear()
        return

    await state.set_state(BookingStates.confirming)
    await cb.message.edit_text(
        _format_booking_summary(data),
        reply_markup=kb_booking_confirm(),
        parse_mode="HTML",
    )


async def _check_and_confirm_msg(message: Message, state: FSMContext, active_company) -> None:
    data = await state.get_data()
    conflicts = await check_conflicts(
        room_id=data["room_id"],
        start_dt=data["start_dt"],
        end_dt=data["end_dt"],
        recurrence_type=data.get("recurrence_type"),
        recurrence_days=data.get("recurrence_days"),
        recurrence_until=data.get("recurrence_until"),
    )
    if conflicts:
        conflict_lines = []
        for c in conflicts[:3]:
            conflict_lines.append(
                f"  🔴 {c['start_dt'].strftime('%d.%m %H:%M')}–{c['end_dt'].strftime('%H:%M')} | {c['title']}"
            )
        more = f"\n  ...и ещё {len(conflicts) - 3}" if len(conflicts) > 3 else ""
        await message.answer(
            "❌ <b>Обнаружен конфликт с существующими бронями:</b>\n"
            + "\n".join(conflict_lines) + more
            + "\n\nВернитесь и выберите другое время.",
            reply_markup=kb_back_to_menu(),
            parse_mode="HTML",
        )
        await state.clear()
        return

    await state.set_state(BookingStates.confirming)
    await message.answer(
        _format_booking_summary(data),
        reply_markup=kb_booking_confirm(),
        parse_mode="HTML",
    )


# ── Final confirm ──────────────────────────────────────────────────────────

@router.callback_query(BookingStates.confirming, F.data == "booking_confirm")
async def cb_booking_confirm(cb: CallbackQuery, state: FSMContext, active_company) -> None:
    await cb.answer()
    if not active_company:
        await state.clear()
        return
    data = await state.get_data()
    booking_id = await save_booking(
        room_id=data["room_id"],
        user_id=cb.from_user.id,
        company_id=active_company["company_id"],
        title=data["title"],
        start_dt=data["start_dt"],
        end_dt=data["end_dt"],
        recurrence_type=data.get("recurrence_type"),
        recurrence_days=data.get("recurrence_days"),
        recurrence_until=data.get("recurrence_until"),
    )
    await state.clear()
    start = datetime.strptime(data["start_dt"], DT_FMT)
    end = datetime.strptime(data["end_dt"], DT_FMT)
    await cb.message.edit_text(
        f"✅ <b>Бронирование создано!</b>\n\n"
        f"🚪 {data['room_name']}\n"
        f"📌 {data['title']}\n"
        f"📅 {start.strftime('%d.%m.%Y')} {start.strftime('%H:%M')}–{end.strftime('%H:%M')}",
        reply_markup=kb_main_menu(is_admin=bool(active_company["is_admin"])),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "cancel_booking")
async def cb_cancel_booking_flow(cb: CallbackQuery, state: FSMContext, active_company) -> None:
    await cb.answer()
    await state.clear()
    is_admin = bool(active_company["is_admin"]) if active_company else False
    await cb.message.edit_text(
        "Бронирование отменено.",
        reply_markup=kb_main_menu(is_admin=is_admin),
    )


# ── Find Free Room ─────────────────────────────────────────────────────────

@router.callback_query(F.data == "find_free_room")
async def cb_find_free_room(cb: CallbackQuery, state: FSMContext, active_company) -> None:
    if not active_company:
        await cb.answer("⛔ Выберите активную компанию.", show_alert=True)
        return
    await cb.answer()
    await cb.message.edit_text(
        "🔍 <b>Поиск свободной комнаты</b>\n\n"
        "📅 Введите дату в формате ДД.ММ.ГГГГ:",
        reply_markup=kb_cancel(),
        parse_mode="HTML",
    )
    await state.set_state(BookingStates.find_entering_date)


@router.message(BookingStates.find_entering_date, F.text, ~F.text.startswith("/"))
async def msg_find_date(message: Message, state: FSMContext) -> None:
    d = _parse_date_input(message.text)
    if d is None:
        await message.answer("❗ Неверный формат даты. Введите ДД.ММ.ГГГГ:")
        return
    if d < date.today():
        await message.answer("❗ Нельзя искать в прошлом. Введите сегодняшнюю или будущую дату:")
        return
    await state.update_data(find_date=d.isoformat())
    await message.answer(
        "⏰ Введите желаемое время начала и конца в формате ЧЧ:ММ-ЧЧ:ММ\n"
        "Например: 10:00-11:30",
        reply_markup=kb_cancel(),
    )
    await state.set_state(BookingStates.find_entering_time)


@router.message(BookingStates.find_entering_time, F.text, ~F.text.startswith("/"))
async def msg_find_time(message: Message, state: FSMContext, active_company) -> None:
    parsed = _parse_time_range(message.text)
    if parsed is None:
        await message.answer(
            "❗ Неверный формат. Введите ЧЧ:ММ-ЧЧ:ММ (конец должен быть позже начала):"
        )
        return
    start_time, end_time = parsed
    data = await state.get_data()
    find_date = data["find_date"]
    start_dt = f"{find_date} {start_time}"
    end_dt = f"{find_date} {end_time}"

    await state.update_data(find_start_dt=start_dt, find_end_dt=end_dt)

    free_rooms = await find_free_rooms(
        company_id=active_company["company_id"],
        start_dt=start_dt,
        end_dt=end_dt,
    )

    start = datetime.strptime(start_dt, DT_FMT)
    end = datetime.strptime(end_dt, DT_FMT)
    time_str = f"{start.strftime('%d.%m.%Y')} {start.strftime('%H:%M')}–{end.strftime('%H:%M')}"

    if not free_rooms:
        await message.answer(
            f"😔 На <b>{time_str}</b> все комнаты заняты.\n\nПопробуйте другое время.",
            reply_markup=kb_back_to_menu(),
            parse_mode="HTML",
        )
        await state.clear()
        return

    await message.answer(
        f"✅ Свободные комнаты на <b>{time_str}</b>:\n\nВыберите комнату для бронирования:",
        reply_markup=kb_free_rooms(free_rooms),
        parse_mode="HTML",
    )
