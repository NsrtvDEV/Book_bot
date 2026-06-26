from aiogram import Router

from app.routers.start import router as start_router
from app.routers.menu import router as menu_router
from app.routers.search import router as search_router
from app.routers.files import router as files_router
from app.routers.upload import router as upload_router

router = Router()
router.include_router(start_router)
router.include_router(search_router)   # поиск раньше menu чтобы перехватить кнопку
router.include_router(menu_router)
router.include_router(files_router)
router.include_router(upload_router)