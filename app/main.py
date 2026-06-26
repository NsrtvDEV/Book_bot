from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.admin.settings import admin

app = FastAPI(
    title="Book Bot Admin",
    description="Admin panel for KitobchiBot",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

admin.mount_to(app=app)
