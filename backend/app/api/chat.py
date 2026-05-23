from fastapi import APIRouter

from backend.app.services.chat_service import ChatService
from shared.schema.chat import ChatRequest, ChatResponse


router = APIRouter(prefix="/chat", tags=["chat"])

chat_service = ChatService()


@router.post("", response_model=ChatResponse)
def create_chat_response(request: ChatRequest) -> ChatResponse:
    return chat_service.create_response(request)