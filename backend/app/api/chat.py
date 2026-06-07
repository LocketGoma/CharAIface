from datetime import datetime
import logging
from time import perf_counter
from typing import Any

from fastapi import APIRouter

from backend.app.services.chat_service import ChatService
from shared.schema.chat import ChatRequest, ChatResponse


router = APIRouter(prefix="/chat", tags=["chat"])

chat_service = ChatService()
logger = logging.getLogger("uvicorn.info")


@router.post("", response_model=ChatResponse)
def create_chat_response(request: ChatRequest) -> ChatResponse:
    started_at = perf_counter()
    response = chat_service.create_response(request)
    _log_developer_chat_response(request, response, perf_counter() - started_at)
    return response


def _log_developer_chat_response(
    request: ChatRequest,
    response: ChatResponse,
    elapsed_seconds: float,
) -> None:
    if not _developer_mode_enabled(request):
        return

    metadata = getattr(response.message, "metadata", {}) or {}
    route = str(metadata.get("route") or "unknown")
    source = str(metadata.get("source") or route)
    provider = str(metadata.get("provider") or metadata.get("cloud_ai_provider") or "-")
    model = str(metadata.get("model") or "unknown")
    answered_at = datetime.now().astimezone().strftime("%H:%M:%S")
    fallback = "cloud->local" if metadata.get("cloud_ai_fallback_to_local") else "-"
    web_search = _web_search_summary(metadata)
    logger.info(
        "[Chat] response "
        f"at={answered_at} elapsed={elapsed_seconds:.2f}s "
        f"source={source} route={route} provider={provider} model={model} "
        f"paid={bool(metadata.get('paid_model_used'))} fallback={fallback} "
        f"{web_search}"
    )


def _developer_mode_enabled(request: ChatRequest) -> bool:
    if bool(getattr(request, "developer_mode", False)):
        return True
    snapshot = getattr(request, "settings_snapshot", {}) or {}
    return isinstance(snapshot, dict) and bool(snapshot.get("developer_mode"))


def _web_search_summary(metadata: dict[str, Any]) -> str:
    if not metadata.get("web_search_used"):
        return "web_search=off"

    provider = str(metadata.get("web_search_provider") or "-")
    count = metadata.get("web_search_result_count")
    query = str(metadata.get("web_search_query") or "").strip()
    query_part = f' query="{query[:80]}"' if query else ""
    return f"web_search={provider} results={count}{query_part}"
