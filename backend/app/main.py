from fastapi import FastAPI

from backend.app.api.chat import router as chat_router
from backend.app.api.cloud_ai import router as cloud_ai_router
from backend.app.api.health import router as health_router
from backend.app.api.local_ai import router as local_ai_router
from backend.app.api.system_status import router as system_status_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="CharAIface Backend",
        version="0.1.0",
    )

    app.include_router(health_router)
    app.include_router(chat_router)
    app.include_router(cloud_ai_router)
    app.include_router(local_ai_router)
    app.include_router(system_status_router)

    return app


app = create_app()