import logging
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.keyboards.keyboards import (
    kb_settings, kb_company_list, kb_confirm_leave,
    kb_main_menu, kb_start_choice, kb_cancel,
    kb_last_admin_leave, kb_confirm_delete_company, kb_back_to_settings,
)
from db.queries.companies import (
    get_all_memberships, set_active_company, remove_member,
    find_companies_by_passcode, add_member, get_membership,
    get_active_membership, count_admins, delete_company,
)

logger = logging.getLogger(__name__)
router = Router()


class SettingsStates(StatesGroup):
    entering_join_passcode = State()


# ── Settings menu ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "settings")
async def cb_settings(cb: CallbackQuery, state: FSMContext, active_company) -> None:
    await cb.answer()
    await state.clear()
    company_name = active_company["company_name"] if active_company else "не выбрана"
    await cb.message.edit_text(
        f"⚙️ <b>Настройки</b>\n\nАктивная компания: <b>{company_name}</b>",
        reply_markup=kb_settings(),
        parse_mode="HTML",
    )


# ── List companies ─────────────────────────────────────────────────────────
# "Мои компании" — shows a read-only list with a back button

@router.callback_query(F.data == "settings_companies")
async def cb_list_companies(cb: CallbackQuery, active_company) -> None:
    await cb.answer()
    memberships = await get_all_memberships(cb.from_user.id)
    if not memberships:
        await cb.message.edit_text(
            "Вы не состоите ни в одной компании.",
            reply_markup=kb_settings(),
        )
        return
    active_id = active_company["company_id"] if active_company else None
    lines = []
    for m in memberships:
        mark = "✅ " if m["company_id"] == active_id else "   "
        role = "👑" if m["is_admin"] else "👤"
        lines.append(f"{mark}{role} {m['company_name']}")
    # Use back-to-settings keyboard so the screen actually changes visually
    await cb.message.edit_text(
        "🏢 <b>Ваши компании:</b>\n\n" + "\n".join(lines),
        reply_markup=kb_back_to_settings(),
        parse_mode="HTML",
    )


# ── Switch active company ──────────────────────────────────────────────────

@router.callback_query(F.data == "settings_switch")
async def cb_switch_company(cb: CallbackQuery, active_company) -> None:
    memberships = await get_all_memberships(cb.from_user.id)
    if len(memberships) <= 1:
        # Only one company → show alert, don't change the screen
        await cb.answer("У вас только одна компания.", show_alert=True)
        return
    await cb.answer()
    active_id = active_company["company_id"] if active_company else None
    await cb.message.edit_text(
        "🔄 Выберите компанию для активации:",
        reply_markup=kb_company_list(memberships, active_id),
    )


@router.callback_query(F.data.startswith("switch_company:"))
async def cb_do_switch(cb: CallbackQuery) -> None:
    await cb.answer()
    company_id = int(cb.data.split(":")[1])
    await set_active_company(cb.from_user.id, company_id)
    active_company = await get_active_membership(cb.from_user.id)
    if not active_company:
        await cb.message.edit_text("Не удалось переключиться.", reply_markup=kb_settings())
        return
    await cb.message.edit_text(
        f"✅ Активная компания: <b>{active_company['company_name']}</b>",
        reply_markup=kb_main_menu(is_admin=bool(active_company["is_admin"])),
        parse_mode="HTML",
    )


# ── Leave company ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "settings_leave")
async def cb_leave_company(cb: CallbackQuery, active_company) -> None:
    if not active_company:
        await cb.answer("Вы не состоите ни в одной компании.", show_alert=True)
        return
    await cb.answer()

    company_id = active_company["company_id"]
    is_admin = bool(active_company["is_admin"])

    # Guard: last admin can't just leave
    if is_admin:
        admin_count = await count_admins(company_id)
        if admin_count <= 1:
            # They are the sole admin — offer alternatives
            await cb.message.edit_text(
                f"⚠️ Вы — единственный администратор компании <b>{active_company['company_name']}</b>.\n\n"
                "Прежде чем покинуть компанию, вы должны:\n"
                "• назначить другого участника администратором, или\n"
                "• удалить компанию полностью.",
                reply_markup=kb_last_admin_leave(company_id),
                parse_mode="HTML",
            )
            return

    await cb.message.edit_text(
        f"⚠️ Вы уверены, что хотите покинуть компанию <b>{active_company['company_name']}</b>?\n\n"
        "Ваши бронирования останутся в системе.",
        reply_markup=kb_confirm_leave(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "settings_leave_confirm")
async def cb_leave_confirm(cb: CallbackQuery, active_company) -> None:
    await cb.answer()
    if not active_company:
        return
    company_name = active_company["company_name"]
    await remove_member(cb.from_user.id, active_company["company_id"])
    new_active = await get_active_membership(cb.from_user.id)
    if new_active:
        await cb.message.edit_text(
            f"✅ Вы покинули компанию <b>{company_name}</b>.\n"
            f"Активная компания: <b>{new_active['company_name']}</b>",
            reply_markup=kb_main_menu(is_admin=bool(new_active["is_admin"])),
            parse_mode="HTML",
        )
    else:
        await cb.message.edit_text(
            f"✅ Вы покинули компанию <b>{company_name}</b>.\n\n"
            "Вы больше не состоите ни в одной компании.",
            reply_markup=kb_start_choice(),
            parse_mode="HTML",
        )


# ── Delete company (last-admin flow) ──────────────────────────────────────

@router.callback_query(F.data.startswith("settings_delete_company:"))
async def cb_delete_company_prompt(cb: CallbackQuery, active_company) -> None:
    await cb.answer()
    company_id = int(cb.data.split(":")[1])
    company_name = active_company["company_name"] if active_company else "компанию"
    await cb.message.edit_text(
        f"🗑 <b>Удалить компанию «{company_name}»?</b>\n\n"
        "Это действие необратимо. Все комнаты и бронирования будут деактивированы, "
        "все участники будут удалены.",
        reply_markup=kb_confirm_delete_company(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "settings_delete_company_confirm")
async def cb_delete_company_confirm(cb: CallbackQuery, active_company) -> None:
    await cb.answer()
    if not active_company:
        return
    # Re-check: must still be the last admin
    admin_count = await count_admins(active_company["company_id"])
    if admin_count > 1:
        await cb.message.edit_text(
            "❌ Вы больше не единственный администратор. Удаление недоступно.",
            reply_markup=kb_settings(),
        )
        return
    company_name = active_company["company_name"]
    await delete_company(active_company["company_id"])
    new_active = await get_active_membership(cb.from_user.id)
    if new_active:
        await cb.message.edit_text(
            f"✅ Компания <b>{company_name}</b> удалена.\n"
            f"Активная компания: <b>{new_active['company_name']}</b>",
            reply_markup=kb_main_menu(is_admin=bool(new_active["is_admin"])),
            parse_mode="HTML",
        )
    else:
        await cb.message.edit_text(
            f"✅ Компания <b>{company_name}</b> удалена.\n\n"
            "Вы больше не состоите ни в одной компании.",
            reply_markup=kb_start_choice(),
            parse_mode="HTML",
        )


# ── Join another company ───────────────────────────────────────────────────

@router.callback_query(F.data == "settings_join")
async def cb_settings_join(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await cb.message.edit_text(
        "🔑 Введите пароль компании, в которую хотите вступить:",
        reply_markup=kb_cancel(),
    )
    await state.set_state(SettingsStates.entering_join_passcode)


@router.message(SettingsStates.entering_join_passcode, F.text, ~F.text.startswith("/"))
async def msg_join_passcode(message: Message, state: FSMContext, db_user) -> None:
    passcode = message.text.strip()
    companies = await find_companies_by_passcode(passcode)
    user_id = db_user["user_id"]

    if not companies:
        await message.answer("❌ Компания с таким паролем не найдена. Попробуйте ещё раз:")
        return

    await state.clear()

    if len(companies) == 1:
        company = companies[0]
        existing = await get_membership(user_id, company["id"])
        if existing:
            await message.answer(
                f"ℹ️ Вы уже состоите в компании <b>{company['name']}</b>.",
                parse_mode="HTML",
                reply_markup=kb_settings(),
            )
            return
        await add_member(user_id, company["id"])
        active_company = await get_active_membership(user_id)
        await message.answer(
            f"✅ Вы вступили в компанию <b>{company['name']}</b>.",
            reply_markup=kb_main_menu(is_admin=bool(active_company["is_admin"])),
            parse_mode="HTML",
        )
    else:
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        rows = [
            [InlineKeyboardButton(text=c["name"], callback_data=f"join_company:{c['id']}")]
            for c in companies
        ]
        rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="settings")])
        kb = InlineKeyboardMarkup(inline_keyboard=rows)
        await message.answer(
            "🏢 Несколько компаний используют этот пароль. Выберите одну:",
            reply_markup=kb,
        )
