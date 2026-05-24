import json

import httpx
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.app.services.local_ai.ollama_manager import OllamaManager


router = APIRouter(prefix="/local-ai", tags=["local-ai"])

ollama_manager = OllamaManager()


class PrepareLocalModelRequest(BaseModel):
    model: str
    auto_pull: bool = True
    auto_install_runtime: bool = False
    auto_start_server: bool = True


class DeleteLocalModelRequest(BaseModel):
    model: str
    auto_start_server: bool = True


class ListLocalModelsRequest(BaseModel):
    auto_start_server: bool = True


@router.get("/ollama/status")
def get_ollama_status() -> dict:
    return {
        "provider": "ollama",
        "status": ollama_manager.status_payload(),
    }


@router.post("/ollama/install-runtime")
def install_ollama_runtime() -> dict:
    result = ollama_manager.install_runtime_with_winget()

    return {
        "provider": "ollama",
        "runtime": "ollama",
        **result,
    }


@router.post("/ollama/prepare-model-stream")
def prepare_ollama_model_stream(request: PrepareLocalModelRequest):
    def event_stream():
        for payload in ollama_manager.prepare_model_stream(
            model_name=request.model,
            auto_pull=request.auto_pull,
            auto_start_server=request.auto_start_server,
            auto_install_runtime=request.auto_install_runtime,
        ):
            yield json.dumps(payload, ensure_ascii=False) + "\n"

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
    )




@router.post("/ollama/list-models")
def list_ollama_models(request: ListLocalModelsRequest) -> dict:
    result = ollama_manager.list_models_payload(
        auto_start_server=request.auto_start_server,
    )

    return {
        "provider": "ollama",
        **result,
    }


@router.post("/ollama/delete-model")
def delete_ollama_model(request: DeleteLocalModelRequest) -> dict:
    result = ollama_manager.delete_model(
        model_name=request.model,
        auto_start_server=request.auto_start_server,
    )

    return {
        "provider": "ollama",
        **result,
    }


@router.post("/ollama/prepare-model")
def prepare_ollama_model(request: PrepareLocalModelRequest) -> dict:
    runtime = ollama_manager.runtime_status()
    install_result = None

    if not runtime.installed and request.auto_install_runtime:
        install_result = ollama_manager.install_runtime_with_winget()
        runtime = ollama_manager.runtime_status()

        if not install_result.get("success"):
            return {
                "provider": "ollama",
                "success": False,
                "runtime": runtime.to_dict(),
                "model": {
                    "model": request.model,
                    "installed": False,
                    "pulled": False,
                    "state": "unknown",
                    "error_code": install_result.get("error_code")
                    or "ollama_install_failed",
                },
                "install_result": install_result,
            }

    model_status = ollama_manager.prepare_model(
        model_name=request.model,
        auto_pull=request.auto_pull,
        auto_start_server=request.auto_start_server,
    )

    return {
        "provider": "ollama",
        "success": model_status.installed,
        "runtime": ollama_manager.runtime_status().to_dict(),
        "model": model_status.to_dict(),
        "install_result": install_result,
    }