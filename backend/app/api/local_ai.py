from fastapi import APIRouter
from pydantic import BaseModel

from backend.app.services.local_ai.ollama_manager import OllamaManager


router = APIRouter(prefix="/local-ai", tags=["local-ai"])

ollama_manager = OllamaManager()


class EnsureLocalModelRequest(BaseModel):
    model: str
    auto_pull: bool = True
    auto_install_ollama: bool = False


@router.get("/ollama/status")
def get_ollama_status() -> dict:
    return {
        "provider": "ollama",
        "status": ollama_manager.status_payload(),
    }


@router.post("/ollama/install")
def install_ollama() -> dict:
    result = ollama_manager.install_ollama_with_winget()

    return {
        "provider": "ollama",
        "install_method": "winget",
        "success": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


@router.post("/ollama/ensure-model")
def ensure_ollama_model(request: EnsureLocalModelRequest) -> dict:
    status = ollama_manager.check()

    if not status.installed and request.auto_install_ollama:
        install_result = ollama_manager.install_ollama_with_winget()

        if install_result.returncode != 0:
            return {
                "provider": "ollama",
                "model": request.model,
                "success": False,
                "installed": False,
                "pulled": False,
                "error": install_result.stderr or install_result.stdout,
                "install_attempted": True,
            }

    result = ollama_manager.ensure_model(
        model_name=request.model,
        auto_pull=request.auto_pull,
    )

    return {
        "provider": "ollama",
        "model": result.model,
        "success": result.installed,
        "installed": result.installed,
        "pulled": result.pulled,
        "error": result.error,
        "install_attempted": not status.installed and request.auto_install_ollama,
    }