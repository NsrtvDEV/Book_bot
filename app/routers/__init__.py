from aiogram import Router

from app.routers.start import router as start_router
from app.routers.search import router as search_router
from app.routers.upload import router as upload_router

router = Router()
router.include_router(start_router)
router.include_router(search_router)
router.include_router(upload_router)