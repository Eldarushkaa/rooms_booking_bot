from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ── Onboarding ─────────────────────────────────────────────────────────────

def kb_start_choice() -> InlineKeyboardMarkup:
    """First screen: create a new company or join an existing one."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏢 Создать компанию", callback_data="create_company")],
        [InlineKeyboardButton(text="🔑 Ввести пароль компании", callback_data="join_by_passcode")],
    ])


# ── Main Menu ──────────────────────────────────────────────────────────────

def kb_main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="📅 Мои бронирования", callback_data="my_bookings")],
        [InlineKeyboardButton(text="🏠 Список комнат", callback_data="room_list")],
        [InlineKeyboardButton(text="🔍 Найти свободную комнату", callback_data="find_free_room")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton(text="👑 Управление компанией", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_back_to_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Главное меню", callback_data="main_menu")],
    ])


# ── Admin Panel ────────────────────────────────────────────────────────────

def kb_admin_panel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Участники", callback_data="admin_members")],
        [InlineKeyboardButton(text="🔐 Изменить пароль", callback_data="admin_change_passcode")],
        [InlineKeyboardButton(text="🔗 Создать ссылку-приглашение", callback_data="admin_create_invite")],
        [InlineKeyboardButton(text="🚪 Управление комнатами", callback_data="admin_rooms")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")],
    ])


def kb_member_actions(user_id: int, is_admin: bool) -> InlineKeyboardMarkup:
    promote_text = "⬇️ Снять с роли администратора" if is_admin else "⬆️ Назначить администратором"
    promote_cb = f"admin_demote:{user_id}" if is_admin else f"admin_promote:{user_id}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=promote_text, callback_data=promote_cb)],
        [InlineKeyboardButton(text="❌ Удалить из компании", callback_data=f"admin_remove:{user_id}")],
        [InlineKeyboardButton(text="◀️ Назад к участникам", callback_data="admin_members")],
    ])


def kb_admin_rooms(rooms: list) -> InlineKeyboardMarkup:
    """List of rooms with edit buttons + create button."""
    rows = []
    for room in rooms:
        status = "✅" if room["is_active"] else "❌"
        rows.append([
            InlineKeyboardButton(
                text=f"{status} {room['name']}",
                callback_data=f"admin_room:{room['id']}",
            )
        ])
    rows.append([InlineKeyboardButton(text="➕ Создать комнату", callback_data="admin_create_room")])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_admin_room_detail(room_id: int, is_active: bool) -> InlineKeyboardMarkup:
    toggle_text = "🔴 Деактивировать" if is_active else "🟢 Активировать"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить название", callback_data=f"admin_room_edit_name:{room_id}")],
        [InlineKeyboardButton(text="📝 Изменить описание", callback_data=f"admin_room_edit_desc:{room_id}")],
        [InlineKeyboardButton(text="👥 Изменить вместимость", callback_data=f"admin_room_edit_cap:{room_id}")],
        [InlineKeyboardButton(text=toggle_text, callback_data=f"admin_room_toggle:{room_id}")],
        [InlineKeyboardButton(text="🗑 Удалить комнату", callback_data=f"admin_room_delete:{room_id}")],
        [InlineKeyboardButton(text="◀️ Назад к комнатам", callback_data="admin_rooms")],
    ])


def kb_invite_created(token: str, bot_username: str) -> InlineKeyboardMarkup:
    """Shown after invite link is generated — just a back button."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Панель управления", callback_data="admin_panel")],
    ])


# ── Rooms ──────────────────────────────────────────────────────────────────

def kb_room_list(rooms: list) -> InlineKeyboardMarkup:
    rows = []
    for room in rooms:
        cap = f" (до {room['capacity']} чел.)" if room["capacity"] else ""
        rows.append([
            InlineKeyboardButton(
                text=f"🚪 {room['name']}{cap}",
                callback_data=f"room_view:{room['id']}",
            )
        ])
    rows.append([InlineKeyboardButton(text="◀️ Главное меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_room_view(room_id: int) -> InlineKeyboardMarkup:
    """Room detail: schedule is shown inline, no separate button needed."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Забронировать", callback_data=f"book_room:{room_id}")],
        [
            InlineKeyboardButton(text="◀️ Пред. неделя", callback_data=f"room_schedule:{room_id}:-1"),
            InlineKeyboardButton(text="След. неделя ▶️", callback_data=f"room_schedule:{room_id}:1"),
        ],
        [InlineKeyboardButton(text="◀️ Список комнат", callback_data="room_list")],
    ])


def kb_schedule_nav(room_id: int, week_offset: int) -> InlineKeyboardMarkup:
    """Navigation arrows for the weekly schedule view."""
    return InlineKeyboardMarkup(inline_keyboard=[
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
        [InlineKeyboardButton(text="◀️ Назад к комнате", callback_data=f"room_view:{room_id}")],
    ])


def kb_date_picker() -> InlineKeyboardMarkup:
    """Quick date shortcuts + back to title."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📅 Сегодня", callback_data="date_today"),
            InlineKeyboardButton(text="📅 Завтра", callback_data="date_tomorrow"),
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="booking_back:title")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_booking")],
    ])


def kb_start_time_picker(slots: list[str]) -> InlineKeyboardMarkup:
    """Quick start-time slot buttons (up to 4) + back to date + cancel."""
    rows = []
    if slots:
        rows.append([
            InlineKeyboardButton(text=s, callback_data=f"start_time:{s}")
            for s in slots
        ])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="booking_back:date")])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_booking")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_duration_picker(available_minutes: list[int] | None = None) -> InlineKeyboardMarkup:
    """Quick duration buttons (only conflict-free ones) + back to start time + cancel."""
    _labels = {30: "30 мин", 60: "1 ч", 90: "1 ч 30 мин", 120: "2 ч"}
    if available_minutes is None:
        available_minutes = [30, 60, 90, 120]
    btns = [
        InlineKeyboardButton(text=_labels[m], callback_data=f"duration:{m}")
        for m in (30, 60, 90, 120)
        if m in available_minutes
    ]
    rows = []
    # Render in pairs
    for i in range(0, len(btns), 2):
        rows.append(btns[i:i + 2])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="booking_back:start_time")])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_booking")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_booking_back_to_title() -> InlineKeyboardMarkup:
    """Shown during title entry — back goes to room view."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="booking_back:room")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_booking")],
    ])


# ── Booking ────────────────────────────────────────────────────────────────

def kb_recurrence_type() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Разовое", callback_data="rec_type:none")],
        [InlineKeyboardButton(text="🔁 Каждый день", callback_data="rec_type:daily")],
        [InlineKeyboardButton(text="📆 По дням недели", callback_data="rec_type:weekly")],
        [InlineKeyboardButton(text="🗓 По дням месяца", callback_data="rec_type:monthly")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="booking_back:duration")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_booking")],
    ])


def kb_weekdays(selected: list[int]) -> InlineKeyboardMarkup:
    """Weekday picker. selected = list of selected weekday numbers (0=Mon..6=Sun)."""
    day_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    buttons = []
    for i, name in enumerate(day_names):
        mark = "✅" if i in selected else ""
        buttons.append(
            InlineKeyboardButton(
                text=f"{mark}{name}",
                callback_data=f"weekday_toggle:{i}",
            )
        )
    return InlineKeyboardMarkup(inline_keyboard=[
        buttons[:4],
        buttons[4:],
        [InlineKeyboardButton(text="✔️ Подтвердить", callback_data="weekday_confirm")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="booking_back:recurrence")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_booking")],
    ])


def kb_until_input() -> InlineKeyboardMarkup:
    """Keyboard shown while entering recurrence until date."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 1 год", callback_data="until_1year")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="booking_back:recurrence")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_booking")],
    ])


def kb_monthly_days_input() -> InlineKeyboardMarkup:
    """Keyboard shown while entering monthly days."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="booking_back:recurrence")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_booking")],
    ])


def kb_booking_confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data="booking_confirm")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="booking_back:recurrence")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_booking")],
    ])


def kb_cancel_booking(booking_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Отменить бронь", callback_data=f"cancel_booking_id:{booking_id}")],
    ])


def kb_my_bookings_nav() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Главное меню", callback_data="main_menu")],
    ])


# ── Find Free Room ─────────────────────────────────────────────────────────

def kb_find_start_time_picker(slots: list[str]) -> InlineKeyboardMarkup:
    """Quick start-time buttons for the find-room flow (no room-specific conflict filter)."""
    rows = []
    if slots:
        rows.append([
            InlineKeyboardButton(text=s, callback_data=f"find_start_time:{s}")
            for s in slots
        ])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="find_back:date")])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_find_duration_picker() -> InlineKeyboardMarkup:
    """Duration buttons for the find-room flow."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="30 мин", callback_data="find_duration:30"),
            InlineKeyboardButton(text="1 ч", callback_data="find_duration:60"),
        ],
        [
            InlineKeyboardButton(text="1 ч 30 мин", callback_data="find_duration:90"),
            InlineKeyboardButton(text="2 ч", callback_data="find_duration:120"),
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="find_back:start_time")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")],
    ])


def kb_free_rooms(rooms: list) -> InlineKeyboardMarkup:
    rows = []
    for room in rooms:
        cap = f" (до {room['capacity']} чел.)" if room["capacity"] else ""
        rows.append([
            InlineKeyboardButton(
                text=f"✅ {room['name']}{cap}",
                callback_data=f"book_free_room:{room['id']}",
            )
        ])
    rows.append([InlineKeyboardButton(text="◀️ Главное меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ── Settings ───────────────────────────────────────────────────────────────

def kb_settings() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏢 Мои компании", callback_data="settings_companies")],
        [InlineKeyboardButton(text="🔄 Сменить активную компанию", callback_data="settings_switch")],
        [InlineKeyboardButton(text="🚪 Покинуть текущую компанию", callback_data="settings_leave")],
        [InlineKeyboardButton(text="🔑 Вступить в другую компанию", callback_data="settings_join")],
        [InlineKeyboardButton(text="➕ Создать новую компанию", callback_data="create_company")],
        [InlineKeyboardButton(text="◀️ Главное меню", callback_data="main_menu")],
    ])


def kb_company_list(memberships: list, active_company_id: int | None) -> InlineKeyboardMarkup:
    """List of companies the user belongs to, for switching."""
    rows = []
    for m in memberships:
        mark = "✅ " if m["company_id"] == active_company_id else ""
        rows.append([
            InlineKeyboardButton(
                text=f"{mark}{m['company_name']}",
                callback_data=f"switch_company:{m['company_id']}",
            )
        ])
    rows.append([InlineKeyboardButton(text="◀️ Настройки", callback_data="settings")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_confirm_leave() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, покинуть", callback_data="settings_leave_confirm")],
        [InlineKeyboardButton(text="❌ Нет, остаться", callback_data="settings")],
    ])


def kb_last_admin_leave(company_id: int) -> InlineKeyboardMarkup:
    """Options for the last admin who tries to leave."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👑 Назначить другого администратора", callback_data="admin_members")],
        [InlineKeyboardButton(text="🗑 Удалить компанию", callback_data=f"settings_delete_company:{company_id}")],
        [InlineKeyboardButton(text="↩️ Остаться", callback_data="settings")],
    ])


def kb_confirm_delete_company() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚠️ Да, удалить навсегда", callback_data="settings_delete_company_confirm")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="settings")],
    ])


def kb_back_to_settings() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад к настройкам", callback_data="settings")],
    ])


# ── Generic ────────────────────────────────────────────────────────────────

def kb_cancel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")],
    ])
