from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api import router
from backend.app.config import get_settings
from backend.app.exception_handlers import register_exception_handlers

settings = get_settings()

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)
app.include_router(router)
