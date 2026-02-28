from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Update

from db.queries.users import get_or_create_user
from db.queries.companies import get_active_membership


class UserMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Update, dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: dict[str, Any],
    ) -> Any:
        # Extract Telegram user from message or callback_query
        tg_user = None
        if event.message:
            tg_user = event.message.from_user
        elif event.callback_query:
            tg_user = event.callback_query.from_user

        if tg_user:
            full_name = (
                f"{tg_user.first_name} {tg_user.last_name}".strip()
                if tg_user.last_name
                else tg_user.first_name
            )
            db_user = await get_or_create_user(
                user_id=tg_user.id,
                username=tg_user.username,
                full_name=full_name,
            )
            active_company = await get_active_membership(tg_user.id)
            data["db_user"] = db_user
            data["active_company"] = active_company

        return await handler(event, data)
