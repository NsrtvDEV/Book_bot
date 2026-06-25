import logging
from typing import Any, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import User, LanguageEnum

logger = logging.getLogger(__name__)


class DatabaseMiddleware(BaseMiddleware):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def __call__(
        self, handler, event: TelegramObject, data: Dict[str, Any]
    ) -> Any:
        async with self.session_factory() as session:
            data["session"] = session
            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise


class UserMiddleware(BaseMiddleware):
    async def __call__(
        self, handler, event: TelegramObject, data: Dict[str, Any]
    ) -> Any:
        from sqlalchemy import select

        session: AsyncSession = data["session"]
        tg_user = data.get("event_from_user")
        if tg_user is None:
            return await handler(event, data)

        result = await session.execute(
            select(User).where(User.telegram_id == tg_user.id)
        )
        user = result.scalar_one_or_none()

        if user is None:
            user = User(
                telegram_id=tg_user.id,
                username=tg_user.username,
                full_name=tg_user.full_name,
                language=LanguageEnum.RU,
            )
            session.add(user)
            await session.flush()
            logger.info(f"New user: {tg_user.id}")

        data["user"] = user
        return await handler(event, data)


class LanguageMiddleware(BaseMiddleware):
    async def __call__(
        self, handler, event: TelegramObject, data: Dict[str, Any]
    ) -> Any:
        user: User | None = data.get("user")
        data["lang"] = user.language.value if user else LanguageEnum.RU.value
        return await handler(event, data)


class BanCheckMiddleware(BaseMiddleware):
    async def __call__(
        self, handler, event: TelegramObject, data: Dict[str, Any]
    ) -> Any:
        user: User | None = data.get("user")
        if user and user.is_banned:
            logger.warning(f"Banned user: {user.telegram_id}")
            return
        return await handler(event, data)


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, rate_limit: float = 1.0) -> None:
        self.rate_limit = rate_limit
        self._cache: Dict[int, float] = {}

    async def __call__(
        self, handler, event: TelegramObject, data: Dict[str, Any]
    ) -> Any:
        import time

        tg_user = data.get("event_from_user")
        if tg_user is None:
            return await handler(event, data)

        now = time.monotonic()
        if now - self._cache.get(tg_user.id, 0) < self.rate_limit:
            return
        self._cache[tg_user.id] = now
        return await handler(event, data)


class LoggingMiddleware(BaseMiddleware):
    async def __call__(
        self, handler, event: TelegramObject, data: Dict[str, Any]
    ) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user:
            logger.info(
                f"[{type(event).__name__}] user={tg_user.id} @{tg_user.username}"
            )
        return await handler(event, data)


class MaintenanceMiddleware(BaseMiddleware):
    def __init__(
        self, enabled: bool = False, admin_ids: list[int] | None = None
    ) -> None:
        self.enabled = enabled
        self.admin_ids = admin_ids or []

    async def __call__(
        self, handler, event: TelegramObject, data: Dict[str, Any]
    ) -> Any:
        if not self.enabled:
            return await handler(event, data)

        tg_user = data.get("event_from_user")
        if tg_user and tg_user.id in self.admin_ids:
            return await handler(event, data)

        if isinstance(event, Message):
            await event.answer("🔧 Бот на техническом обслуживании. Скоро вернёмся!")
        elif isinstance(event, CallbackQuery):
            await event.answer("🔧 Тех. работы, попробуйте позже.", show_alert=True)
        return
