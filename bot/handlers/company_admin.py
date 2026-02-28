import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.keyboards.keyboards import (
    kb_admin_panel, kb_main_menu, kb_member_actions,
    kb_admin_rooms, kb_admin_room_detail, kb_cancel,
)
from db.queries.companies import (
    get_company_members, set_admin, remove_member,
    update_company_passcode, create_invite_token, get_company,
)
from db.queries.rooms import get_rooms, get_room, create_room, update_room, toggle_room_active, delete_room

logger = logging.getLogger(__name__)
router = Router()


def _require_admin(active_company) -> bool:
    return active_company and bool(active_company["is_admin"])


# ── Admin Panel ────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_panel")
async def cb_admin_panel(cb: CallbackQuery, active_company) -> None:
    if not _require_admin(active_company):
        await cb.answer("⛔ У вас нет прав администратора.", show_alert=True)
        return
    await cb.answer()
    company_name = active_company["company_name"]
    await cb.message.edit_text(
        f"👑 <b>Управление компанией «{company_name}»</b>\n\nВыберите действие:",
        reply_markup=kb_admin_panel(),
        parse_mode="HTML",
    )


# ── Members ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_members")
async def cb_admin_members(cb: CallbackQuery, active_company) -> None:
    if not _require_admin(active_company):
        await cb.answer("⛔ Недостаточно прав.", show_alert=True)
        return
    await cb.answer()
    company_id = active_company["company_id"]
    members = await get_company_members(company_id)

    lines = []
    for m in members:
        role = "👑 Админ" if m["is_admin"] else "👤 Участник"
        uname = f"@{m['username']}" if m["username"] else m["full_name"]
        lines.append(f"{role} — {uname}")

    text = (
        f"👥 <b>Участники компании</b> ({len(members)}):\n\n"
        + "\n".join(lines)
        + "\n\nВыберите участника для управления:"
    )

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    rows = []
    for m in members:
        uname = f"@{m['username']}" if m["username"] else m["full_name"]
        mark = "👑 " if m["is_admin"] else ""
        rows.append([
            InlineKeyboardButton(
                text=f"{mark}{uname}",
                callback_data=f"admin_member_detail:{m['user_id']}",
            )
        ])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_panel")])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)

    await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("admin_member_detail:"))
async def cb_member_detail(cb: CallbackQuery, active_company) -> None:
    await cb.answer()
    if not _require_admin(active_company):
        return
    target_user_id = int(cb.data.split(":")[1])
    company_id = active_company["company_id"]
    members = await get_company_members(company_id)
    target = next((m for m in members if m["user_id"] == target_user_id), None)
    if not target:
        await cb.answer("Участник не найден.", show_alert=True)
        return
    uname = f"@{target['username']}" if target["username"] else target["full_name"]
    role = "👑 Администратор" if target["is_admin"] else "👤 Участник"
    await cb.message.edit_text(
        f"<b>{uname}</b>\nРоль: {role}",
        reply_markup=kb_member_actions(target_user_id, bool(target["is_admin"])),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin_promote:"))
async def cb_promote(cb: CallbackQuery, active_company) -> None:
    if not _require_admin(active_company):
        await cb.answer("⛔ Недостаточно прав.", show_alert=True)
        return
    target_user_id = int(cb.data.split(":")[1])
    await set_admin(target_user_id, active_company["company_id"], True)
    await cb.answer("✅ Участник назначен администратором.", show_alert=True)
    # Refresh member list
    await cb_admin_members(cb, active_company)


@router.callback_query(F.data.startswith("admin_demote:"))
async def cb_demote(cb: CallbackQuery, active_company) -> None:
    if not _require_admin(active_company):
        await cb.answer("⛔ Недостаточно прав.", show_alert=True)
        return
    target_user_id = int(cb.data.split(":")[1])
    await set_admin(target_user_id, active_company["company_id"], False)
    await cb.answer("✅ Права администратора сняты.", show_alert=True)
    await cb_admin_members(cb, active_company)


@router.callback_query(F.data.startswith("admin_remove:"))
async def cb_remove_member(cb: CallbackQuery, active_company) -> None:
    if not _require_admin(active_company):
        await cb.answer("⛔ Недостаточно прав.", show_alert=True)
        return
    target_user_id = int(cb.data.split(":")[1])
    if target_user_id == cb.from_user.id:
        await cb.answer("❗ Нельзя удалить самого себя. Используйте «Покинуть компанию» в настройках.", show_alert=True)
        return
    await remove_member(target_user_id, active_company["company_id"])
    await cb.answer("✅ Участник удалён из компании.", show_alert=True)
    await cb_admin_members(cb, active_company)


# ── Passcode ───────────────────────────────────────────────────────────────

class AdminStates(StatesGroup):
    entering_new_passcode = State()
    entering_room_name = State()
    entering_room_desc = State()
    entering_room_cap = State()
    editing_room_name = State()
    editing_room_desc = State()
    editing_room_cap = State()


@router.callback_query(F.data == "admin_change_passcode")
async def cb_change_passcode(cb: CallbackQuery, state: FSMContext, active_company) -> None:
    await cb.answer()
    if not _require_admin(active_company):
        return
    await cb.message.edit_text(
        "🔐 Введите новый пароль для компании (3–32 символа):",
        reply_markup=kb_cancel(),
    )
    await state.set_state(AdminStates.entering_new_passcode)


@router.message(AdminStates.entering_new_passcode, F.text, ~F.text.startswith("/"))
async def msg_new_passcode(message: Message, state: FSMContext, active_company) -> None:
    if not _require_admin(active_company):
        await state.clear()
        return
    passcode = message.text.strip()
    if len(passcode) < 3 or len(passcode) > 32:
        await message.answer("❗ Пароль должен быть от 3 до 32 символов. Попробуйте ещё раз:")
        return
    await update_company_passcode(active_company["company_id"], passcode)
    await state.clear()
    await message.answer(
        f"✅ Пароль компании изменён на: <code>{passcode}</code>",
        reply_markup=kb_admin_panel(),
        parse_mode="HTML",
    )


# ── Invite Link ────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_create_invite")
async def cb_create_invite(cb: CallbackQuery, active_company) -> None:
    await cb.answer()
    if not _require_admin(active_company):
        return
    token = await create_invite_token(
        company_id=active_company["company_id"],
        created_by=cb.from_user.id,
        uses_left=None,
        expires_at=None,
    )
    bot_info = await cb.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={token}"
    await cb.message.edit_text(
        f"🔗 <b>Ссылка-приглашение создана:</b>\n\n"
        f"<code>{link}</code>\n\n"
        "Поделитесь ею — человек автоматически вступит в компанию при переходе.\n"
        "Ссылка действует без ограничений.",
        reply_markup=kb_admin_panel(),
        parse_mode="HTML",
    )


# ── Rooms CRUD ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_rooms")
async def cb_admin_rooms(cb: CallbackQuery, active_company) -> None:
    await cb.answer()
    if not _require_admin(active_company):
        return
    rooms = await get_rooms(active_company["company_id"], include_inactive=True)
    await cb.message.edit_text(
        "🚪 <b>Комнаты компании</b>\n\nВыберите комнату для редактирования или создайте новую:",
        reply_markup=kb_admin_rooms(rooms),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin_room:"))
async def cb_admin_room_detail(cb: CallbackQuery, active_company) -> None:
    await cb.answer()
    if not _require_admin(active_company):
        return
    room_id = int(cb.data.split(":")[1])
    room = await get_room(room_id)
    if not room:
        await cb.answer("Комната не найдена.", show_alert=True)
        return
    cap = f"Вместимость: {room['capacity']} чел.\n" if room["capacity"] else ""
    desc = f"Описание: {room['description']}\n" if room["description"] else ""
    status = "🟢 Активна" if room["is_active"] else "🔴 Неактивна"
    await cb.message.edit_text(
        f"🚪 <b>{room['name']}</b>\n{desc}{cap}Статус: {status}",
        reply_markup=kb_admin_room_detail(room_id, bool(room["is_active"])),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin_create_room")
async def cb_create_room_start(cb: CallbackQuery, state: FSMContext, active_company) -> None:
    await cb.answer()
    if not _require_admin(active_company):
        return
    await cb.message.edit_text(
        "🚪 Введите название новой комнаты:",
        reply_markup=kb_cancel(),
    )
    await state.set_state(AdminStates.entering_room_name)


@router.message(AdminStates.entering_room_name, F.text, ~F.text.startswith("/"))
async def msg_room_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if len(name) < 1 or len(name) > 64:
        await message.answer("❗ Название должно быть от 1 до 64 символов. Попробуйте ещё раз:")
        return
    await state.update_data(room_name=name)
    await message.answer(
        "📝 Введите описание комнаты (или отправьте «-» чтобы пропустить):",
        reply_markup=kb_cancel(),
    )
    await state.set_state(AdminStates.entering_room_desc)


@router.message(AdminStates.entering_room_desc, F.text, ~F.text.startswith("/"))
async def msg_room_desc(message: Message, state: FSMContext) -> None:
    desc = message.text.strip()
    await state.update_data(room_desc=None if desc == "-" else desc)
    await message.answer(
        "👥 Введите вместимость комнаты (число) или «-» чтобы пропустить:",
        reply_markup=kb_cancel(),
    )
    await state.set_state(AdminStates.entering_room_cap)


@router.message(AdminStates.entering_room_cap, F.text, ~F.text.startswith("/"))
async def msg_room_cap(message: Message, state: FSMContext, active_company) -> None:
    text = message.text.strip()
    capacity = None
    if text != "-":
        if not text.isdigit() or int(text) <= 0:
            await message.answer("❗ Введите целое положительное число или «-» для пропуска:")
            return
        capacity = int(text)

    data = await state.get_data()
    room_name = data["room_name"]
    room_desc = data.get("room_desc")
    company_id = active_company["company_id"]

    room_id = await create_room(
        company_id=company_id,
        name=room_name,
        description=room_desc,
        capacity=capacity,
    )
    await state.clear()
    rooms = await get_rooms(company_id, include_inactive=True)
    await message.answer(
        f"✅ Комната <b>{room_name}</b> создана!",
        reply_markup=kb_admin_rooms(rooms),
        parse_mode="HTML",
    )


# ── Room edit handlers ─────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin_room_edit_name:"))
async def cb_edit_room_name(cb: CallbackQuery, state: FSMContext, active_company) -> None:
    await cb.answer()
    if not _require_admin(active_company):
        return
    room_id = int(cb.data.split(":")[1])
    await state.update_data(editing_room_id=room_id)
    await cb.message.edit_text("✏️ Введите новое название комнаты:", reply_markup=kb_cancel())
    await state.set_state(AdminStates.editing_room_name)


@router.message(AdminStates.editing_room_name, F.text, ~F.text.startswith("/"))
async def msg_edit_room_name(message: Message, state: FSMContext, active_company) -> None:
    name = message.text.strip()
    if len(name) < 1 or len(name) > 64:
        await message.answer("❗ Название должно быть от 1 до 64 символов:")
        return
    data = await state.get_data()
    room_id = data["editing_room_id"]
    await update_room(room_id, name=name)
    await state.clear()
    room = await get_room(room_id)
    await message.answer(
        f"✅ Название обновлено.",
        reply_markup=kb_admin_room_detail(room_id, bool(room["is_active"])),
    )


@router.callback_query(F.data.startswith("admin_room_edit_desc:"))
async def cb_edit_room_desc(cb: CallbackQuery, state: FSMContext, active_company) -> None:
    await cb.answer()
    if not _require_admin(active_company):
        return
    room_id = int(cb.data.split(":")[1])
    await state.update_data(editing_room_id=room_id)
    await cb.message.edit_text("📝 Введите новое описание (или «-» чтобы убрать):", reply_markup=kb_cancel())
    await state.set_state(AdminStates.editing_room_desc)


@router.message(AdminStates.editing_room_desc, F.text, ~F.text.startswith("/"))
async def msg_edit_room_desc(message: Message, state: FSMContext) -> None:
    desc = message.text.strip()
    data = await state.get_data()
    room_id = data["editing_room_id"]
    await update_room(room_id, description=None if desc == "-" else desc)
    await state.clear()
    room = await get_room(room_id)
    await message.answer(
        "✅ Описание обновлено.",
        reply_markup=kb_admin_room_detail(room_id, bool(room["is_active"])),
    )


@router.callback_query(F.data.startswith("admin_room_edit_cap:"))
async def cb_edit_room_cap(cb: CallbackQuery, state: FSMContext, active_company) -> None:
    await cb.answer()
    if not _require_admin(active_company):
        return
    room_id = int(cb.data.split(":")[1])
    await state.update_data(editing_room_id=room_id)
    await cb.message.edit_text("👥 Введите новую вместимость (число или «-» чтобы убрать):", reply_markup=kb_cancel())
    await state.set_state(AdminStates.editing_room_cap)


@router.message(AdminStates.editing_room_cap, F.text, ~F.text.startswith("/"))
async def msg_edit_room_cap(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    capacity = None
    if text != "-":
        if not text.isdigit() or int(text) <= 0:
            await message.answer("❗ Введите целое положительное число или «-»:")
            return
        capacity = int(text)
    data = await state.get_data()
    room_id = data["editing_room_id"]
    await update_room(room_id, capacity=capacity)
    await state.clear()
    room = await get_room(room_id)
    await message.answer(
        "✅ Вместимость обновлена.",
        reply_markup=kb_admin_room_detail(room_id, bool(room["is_active"])),
    )


@router.callback_query(F.data.startswith("admin_room_toggle:"))
async def cb_toggle_room(cb: CallbackQuery, active_company) -> None:
    if not _require_admin(active_company):
        await cb.answer("⛔ Недостаточно прав.", show_alert=True)
        return
    room_id = int(cb.data.split(":")[1])
    new_active = await toggle_room_active(room_id)
    status = "активирована" if new_active else "деактивирована"
    await cb.answer(f"✅ Комната {status}.", show_alert=True)
    room = await get_room(room_id)
    cap = f"Вместимость: {room['capacity']} чел.\n" if room["capacity"] else ""
    desc = f"Описание: {room['description']}\n" if room["description"] else ""
    status_text = "🟢 Активна" if room["is_active"] else "🔴 Неактивна"
    await cb.message.edit_text(
        f"🚪 <b>{room['name']}</b>\n{desc}{cap}Статус: {status_text}",
        reply_markup=kb_admin_room_detail(room_id, bool(room["is_active"])),
        parse_mode="HTML",
    )


# ── Delete room ────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin_room_delete:"))
async def cb_delete_room_prompt(cb: CallbackQuery, active_company) -> None:
    if not _require_admin(active_company):
        await cb.answer("⛔ Недостаточно прав.", show_alert=True)
        return
    await cb.answer()
    room_id = int(cb.data.split(":")[1])
    room = await get_room(room_id)
    if not room:
        await cb.answer("Комната не найдена.", show_alert=True)
        return
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚠️ Да, удалить комнату", callback_data=f"admin_room_delete_confirm:{room_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"admin_room:{room_id}")],
    ])
    await cb.message.edit_text(
        f"🗑 <b>Удалить комнату «{room['name']}»?</b>\n\n"
        "Все бронирования в этой комнате будут отменены. Это действие необратимо.",
        reply_markup=kb,
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin_room_delete_confirm:"))
async def cb_delete_room_confirm(cb: CallbackQuery, active_company) -> None:
    if not _require_admin(active_company):
        await cb.answer("⛔ Недостаточно прав.", show_alert=True)
        return
    room_id = int(cb.data.split(":")[1])
    room = await get_room(room_id)
    room_name = room["name"] if room else "комнату"
    await delete_room(room_id)
    await cb.answer(f"✅ Комната «{room_name}» удалена.", show_alert=True)
    rooms = await get_rooms(active_company["company_id"], include_inactive=True)
    await cb.message.edit_text(
        "🚪 <b>Комнаты компании</b>",
        reply_markup=kb_admin_rooms(rooms),
        parse_mode="HTML",
    )
