import asyncio
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from dotenv import load_dotenv

from app.database import SessionLocal, engine
from app.models import Base
from app.middleware import (
    BanCheckMiddleware,
    DatabaseMiddleware,
    LanguageMiddleware,
    LoggingMiddleware,
    MaintenanceMiddleware,
    ThrottlingMiddleware,
    UserMiddleware,
)
from app.routers import router

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]


async def on_startup(bot: Bot) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✅ Database ready")
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("🤖 Bot started")


async def on_shutdown(bot: Bot) -> None:
    await engine.dispose()
    logger.info("Bot stopped")


async def main() -> None:
    bot = Bot(
        token=os.getenv("BOT_TOKEN"),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher()

    dp.update.middleware(LoggingMiddleware())
    dp.update.middleware(ThrottlingMiddleware(rate_limit=1.0))
    dp.update.middleware(DatabaseMiddleware(SessionLocal))
    dp.update.middleware(UserMiddleware())
    dp.update.middleware(BanCheckMiddleware())
    dp.update.middleware(LanguageMiddleware())
    dp.update.middleware(MaintenanceMiddleware(enabled=False, admin_ids=ADMIN_IDS))

    dp.include_router(router)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())


from app.admin.settings import admin

app = FastAPI(title="Book bot for search books", description="bookbot-search necessary")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


admin.mount_to(app=app)
