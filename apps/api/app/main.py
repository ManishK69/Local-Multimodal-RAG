from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.health import router as health_router
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
    return app


app = create_app()
