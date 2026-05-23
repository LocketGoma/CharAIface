from datetime import datetime, timezone

from fastapi import APIRouter

from backend.app.services.local_ai.ollama_manager import OllamaManager


router = APIRouter(tags=["health"])

ollama_manager = OllamaManager()


@router.get("/health")
def health() -> dict:
    ollama_status = ollama_manager.check()

    return {
        "status": "ok",
        "app": "CharAIface Backend",
        "version": "0.1.0",
        "backend_api": "available",
        "chat_api": "available",
        "chat_service": "available",
        "local_ai": {
            "provider": "ollama",
            "installed": ollama_status.installed,
            "server_available": ollama_status.server_available,
            "version": ollama_status.version,
            "cli_path": ollama_status.cli_path,
        },
        "server_time_utc": datetime.now(timezone.utc).isoformat(),
    }