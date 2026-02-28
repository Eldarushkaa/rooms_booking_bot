import logging
from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from bot.keyboards.keyboards import kb_start_choice, kb_main_menu, kb_cancel
from db.queries.companies import (
    create_company, find_companies_by_passcode,
    add_member, get_invite_token, consume_invite_token,
    get_membership, get_active_membership,
)

logger = logging.getLogger(__name__)
router = Router()


class OnboardingStates(StatesGroup):
    choosing_action = State()
    entering_passcode = State()
    entering_company_name = State()
    entering_company_passcode_create = State()


def _welcome_text(company_name: str, is_admin: bool) -> str:
    role = "администратор" if is_admin else "участник"
    return (
        f"✅ Вы вошли в компанию <b>{company_name}</b> как {role}.\n\n"
        "Выберите действие:"
    )


async def _show_main_menu(target, active_company):
    is_admin = bool(active_company["is_admin"]) if active_company else False
    company_name = active_company["company_name"] if active_company else "—"
    text = (
        f"🏢 <b>{company_name}</b>\n\n"
        "Выберите действие:"
    )
    kb = kb_main_menu(is_admin=is_admin)
    if hasattr(target, "message"):
        await target.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await target.answer(text, reply_markup=kb, parse_mode="HTML")


# ── /start handler ─────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, db_user, active_company) -> None:
    await state.clear()

    # Check for deep-link invite token
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        token_str = args[1]
        token_row = await get_invite_token(token_str)
        if token_row:
            # Validate expiry
            from datetime import datetime
            if token_row["expires_at"]:
                expires = datetime.fromisoformat(token_row["expires_at"])
                if datetime.now() > expires:
                    await message.answer(
                        "❌ Эта ссылка-приглашение истекла. Попросите администратора создать новую."
                    )
                    return

            company_id = token_row["company_id"]
            existing = await get_membership(message.from_user.id, company_id)
            if existing:
                await message.answer(
                    "ℹ️ Вы уже состоите в этой компании.",
                    parse_mode="HTML",
                )
            else:
                await add_member(message.from_user.id, company_id)
                await consume_invite_token(token_str)

            # Refresh active company
            active_company = await get_active_membership(message.from_user.id)
            text = _welcome_text(active_company["company_name"], bool(active_company["is_admin"]))
            await message.answer(
                text,
                reply_markup=kb_main_menu(is_admin=bool(active_company["is_admin"])),
                parse_mode="HTML",
            )
            return

    # Normal flow
    if active_company:
        text = (
            f"👋 С возвращением, <b>{db_user['full_name']}</b>!\n"
            f"Активная компания: <b>{active_company['company_name']}</b>\n\n"
            "Выберите действие:"
        )
        await message.answer(
            text,
            reply_markup=kb_main_menu(is_admin=bool(active_company["is_admin"])),
            parse_mode="HTML",
        )
    else:
        await message.answer(
            f"👋 Привет, <b>{db_user['full_name']}</b>!\n\n"
            "Вы ещё не состоите ни в одной компании. Создайте свою или вступите в существующую:",
            reply_markup=kb_start_choice(),
            parse_mode="HTML",
        )
        await state.set_state(OnboardingStates.choosing_action)


# ── Create company ─────────────────────────────────────────────────────────

@router.callback_query(F.data == "create_company")
async def cb_create_company(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await cb.message.edit_text(
        "🏢 Введите название вашей компании:",
        reply_markup=kb_cancel(),
    )
    await state.set_state(OnboardingStates.entering_company_name)


@router.message(OnboardingStates.entering_company_name, F.text, ~F.text.startswith("/"))
async def msg_company_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if len(name) < 2 or len(name) > 64:
        await message.answer("❗ Название должно быть от 2 до 64 символов. Попробуйте ещё раз:")
        return
    await state.update_data(company_name=name)
    await message.answer(
        f"🔐 Придумайте пароль для компании <b>{name}</b>.\n"
        "Участники будут использовать его для вступления:",
        reply_markup=kb_cancel(),
        parse_mode="HTML",
    )
    await state.set_state(OnboardingStates.entering_company_passcode_create)


@router.message(OnboardingStates.entering_company_passcode_create, F.text, ~F.text.startswith("/"))
async def msg_company_passcode(message: Message, state: FSMContext, db_user) -> None:
    passcode = message.text.strip()
    if len(passcode) < 3 or len(passcode) > 32:
        await message.answer("❗ Пароль должен быть от 3 до 32 символов. Попробуйте ещё раз:")
        return

    data = await state.get_data()
    company_name = data["company_name"]
    user_id = db_user["user_id"]

    company_id = await create_company(name=company_name, passcode=passcode, created_by=user_id)
    await add_member(user_id, company_id, is_admin=True)
    await state.clear()

    active_company = await get_active_membership(user_id)
    await message.answer(
        f"✅ Компания <b>{company_name}</b> создана!\n"
        f"Пароль: <code>{passcode}</code>\n\n"
        "Вы — администратор. Выберите действие:",
        reply_markup=kb_main_menu(is_admin=True),
        parse_mode="HTML",
    )


# ── Join by passcode ───────────────────────────────────────────────────────

@router.callback_query(F.data == "join_by_passcode")
async def cb_join_by_passcode(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await cb.message.edit_text(
        "🔑 Введите пароль компании:",
        reply_markup=kb_cancel(),
    )
    await state.set_state(OnboardingStates.entering_passcode)


@router.message(OnboardingStates.entering_passcode, F.text, ~F.text.startswith("/"))
async def msg_passcode(message: Message, state: FSMContext, db_user) -> None:
    passcode = message.text.strip()
    companies = await find_companies_by_passcode(passcode)

    if not companies:
        await message.answer(
            "❌ Компания с таким паролем не найдена. Попробуйте ещё раз или введите /start для отмены:"
        )
        return

    user_id = db_user["user_id"]

    if len(companies) == 1:
        company = companies[0]
        existing = await get_membership(user_id, company["id"])
        if existing:
            await message.answer(
                f"ℹ️ Вы уже состоите в компании <b>{company['name']}</b>.",
                parse_mode="HTML",
            )
            await state.clear()
            active_company = await get_active_membership(user_id)
            await message.answer(
                "Выберите действие:",
                reply_markup=kb_main_menu(is_admin=bool(active_company["is_admin"])),
            )
            return

        await add_member(user_id, company["id"])
        await state.clear()
        active_company = await get_active_membership(user_id)
        await message.answer(
            _welcome_text(company["name"], bool(active_company["is_admin"])),
            reply_markup=kb_main_menu(is_admin=bool(active_company["is_admin"])),
            parse_mode="HTML",
        )
    else:
        # Multiple companies share the same passcode — let user pick
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        rows = [
            [InlineKeyboardButton(
                text=c["name"],
                callback_data=f"join_company:{c['id']}",
            )]
            for c in companies
        ]
        rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")])
        kb = InlineKeyboardMarkup(inline_keyboard=rows)
        await state.update_data(passcode=passcode)
        await message.answer(
            "🏢 Несколько компаний используют этот пароль. Выберите одну:",
            reply_markup=kb,
        )


@router.callback_query(F.data.startswith("join_company:"))
async def cb_join_company(cb: CallbackQuery, state: FSMContext, db_user) -> None:
    await cb.answer()
    company_id = int(cb.data.split(":")[1])
    user_id = db_user["user_id"]
    existing = await get_membership(user_id, company_id)
    if existing:
        await cb.message.edit_text("ℹ️ Вы уже состоите в этой компании.")
    else:
        await add_member(user_id, company_id)
        active_company = await get_active_membership(user_id)
        await cb.message.edit_text(
            _welcome_text(active_company["company_name"], bool(active_company["is_admin"])),
            reply_markup=kb_main_menu(is_admin=bool(active_company["is_admin"])),
            parse_mode="HTML",
        )
    await state.clear()


# ── Cancel action ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "cancel_action")
async def cb_cancel_action(cb: CallbackQuery, state: FSMContext, active_company) -> None:
    await cb.answer()
    await state.clear()
    if active_company:
        await cb.message.edit_text(
            "Выберите действие:",
            reply_markup=kb_main_menu(is_admin=bool(active_company["is_admin"])),
        )
    else:
        await cb.message.edit_text(
            "Выберите действие:",
            reply_markup=kb_start_choice(),
        )


# ── Main menu callback ─────────────────────────────────────────────────────

@router.callback_query(F.data == "main_menu")
async def cb_main_menu(cb: CallbackQuery, state: FSMContext, active_company) -> None:
    await cb.answer()
    await state.clear()
    if not active_company:
        await cb.message.edit_text(
            "Вы не состоите ни в одной компании:",
            reply_markup=kb_start_choice(),
        )
        return
    company_name = active_company["company_name"]
    is_admin = bool(active_company["is_admin"])
    await cb.message.edit_text(
        f"🏢 <b>{company_name}</b>\n\nВыберите действие:",
        reply_markup=kb_main_menu(is_admin=is_admin),
        parse_mode="HTML",
    )
