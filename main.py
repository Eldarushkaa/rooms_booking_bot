import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

from db.database import init_db, close_db
from bot.middlewares.user_middleware import UserMiddleware
from bot.handlers import onboarding, company_admin, rooms, booking, settings

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def main() -> None:
    token = os.getenv("BOT_TOKEN")
    if not token or token == "your_token_here":
        raise ValueError("BOT_TOKEN is not set. Please add your token to the .env file.")

    await init_db()
    logger.info("Database initialized.")

    bot = Bot(token=token)
    # TODO: Replace MemoryStorage with RedisStorage for production.
    #       With MemoryStorage, all FSM state is lost on bot restart and users
    #       mid-session will silently lose their progress.
    dp = Dispatcher(storage=MemoryStorage())

    # Middleware — auto-creates user and injects db_user + active_company
    dp.update.middleware(UserMiddleware())

    # Routers (order matters: onboarding first to catch /start and cancel_action)
    dp.include_router(onboarding.router)
    dp.include_router(company_admin.router)
    dp.include_router(rooms.router)
    dp.include_router(booking.router)
    dp.include_router(settings.router)

    # Gracefully close DB connection on shutdown
    dp.shutdown.register(close_db)

    logger.info("Booking bot is running...")
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    asyncio.run(main())
