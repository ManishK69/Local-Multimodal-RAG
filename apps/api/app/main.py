from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.chat import router as chat_router
from app.api.routes.documents import router as documents_router
from app.api.routes.folders import router as folders_router
from app.api.routes.health import router as health_router
from app.api.routes.settings import router as settings_router
from app.core.errors import register_error_handlers

CORS_ORIGINS = (
    "http://127.0.0.1:3000",
    "http://localhost:3000",
)


def create_app() -> FastAPI:
    app = FastAPI(title="Local Multimodal RAG")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(CORS_ORIGINS),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    app.include_router(health_router)
    app.include_router(settings_router)
    app.include_router(documents_router)
    app.include_router(folders_router)
    app.include_router(chat_router)
    return app


app = create_app()
