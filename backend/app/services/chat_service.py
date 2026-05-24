from typing import Literal

from backend.app.services.health_service import HealthService
from shared.schema.chat import ChatMessage, ChatRequest, ChatResponse


ChatRoute = Literal["local_mock", "cloud_mock", "command"]


class ChatService:
    def __init__(self) -> None:
        self.health_service = HealthService()

    def create_response(self, request: ChatRequest) -> ChatResponse:
        latest_user_message = self._find_latest_user_message(request)

        if latest_user_message is None:
            return self._create_assistant_response(
                content="사용자 메시지가 없습니다.",
                route="local_mock",
                model="none",
                paid_model_used=False,
                metadata={
                    "source": "chat_service",
                    "reason": "no_user_message",
                },
            )

        command_response = self._try_handle_command(
            command_text=latest_user_message.content,
            request=request,
        )

        if command_response is not None:
            return command_response

        route = self._select_route(request)

        if route == "cloud_mock":
            return self._create_cloud_mock_response(
                latest_user_message=latest_user_message,
                request=request,
            )

        return self._create_local_mock_response(
            latest_user_message=latest_user_message,
            request=request,
        )

    def _find_latest_user_message(
        self,
        request: ChatRequest,
    ) -> ChatMessage | None:
        for message in reversed(request.messages):
            if message.role == "user":
                return message

        return None

    def _try_handle_command(
        self,
        command_text: str,
        request: ChatRequest,
    ) -> ChatResponse | None:
        normalized_command = command_text.strip().lower()

        if normalized_command == "/status":
            return self._create_status_response(request)

        if normalized_command == "/health":
            return self._create_health_response()

        if normalized_command == "/help":
            return self._create_help_response()

        return None

    def _select_route(self, request: ChatRequest) -> ChatRoute:
        if request.developer_mode:
            return "cloud_mock"

        return "local_mock"

    def _create_local_mock_response(
        self,
        latest_user_message: ChatMessage,
        request: ChatRequest,
    ) -> ChatResponse:
        user_name = request.user_name or "사용자"
        character_id = request.character_id or "unknown"

        content = (
            f"Local Mock: {latest_user_message.content}\n\n"
            f"- user_name: {user_name}\n"
            f"- character_id: {character_id}\n"
            f"- developer_mode: {request.developer_mode}\n"
            f"- route: local_mock\n"
            f"- model: local_mock_model"
        )

        return self._create_assistant_response(
            content=content,
            route="local_mock",
            model="local_mock_model",
            paid_model_used=False,
            metadata={
                "source": "chat_service",
            },
        )

    def _create_cloud_mock_response(
        self,
        latest_user_message: ChatMessage,
        request: ChatRequest,
    ) -> ChatResponse:
        user_name = request.user_name or "사용자"
        character_id = request.character_id or "unknown"

        content = (
            f"Cloud Mock: {latest_user_message.content}\n\n"
            f"- user_name: {user_name}\n"
            f"- character_id: {character_id}\n"
            f"- developer_mode: {request.developer_mode}\n"
            f"- route: cloud_mock\n"
            f"- model: cloud_mock_model\n"
            f"- paid_model_used: True"
        )

        return self._create_assistant_response(
            content=content,
            route="cloud_mock",
            model="cloud_mock_model",
            paid_model_used=True,
            metadata={
                "source": "chat_service",
            },
        )

    def _create_status_response(self, request: ChatRequest) -> ChatResponse:
        user_name = request.user_name or "사용자"
        character_id = request.character_id or "unknown"
        route = self._select_route(request)

        if route == "cloud_mock":
            model = "cloud_mock_model"
            paid_model_used = True
        else:
            model = "local_mock_model"
            paid_model_used = False

        content = (
            "Status\n\n"
            f"- user_name: {user_name}\n"
            f"- character_id: {character_id}\n"
            f"- developer_mode: {request.developer_mode}\n"
            f"- message_count: {len(request.messages)}\n"
            f"- selected_route: {route}\n"
            f"- selected_model: {model}\n"
            f"- paid_model_used: {paid_model_used}"
        )

        return self._create_assistant_response(
            content=content,
            route="command",
            model="system_command",
            paid_model_used=False,
            metadata={
                "source": "chat_service",
                "command": "status",
                "selected_route": route,
                "selected_model": model,
                "selected_paid_model_used": paid_model_used,
            },
        )

    def _create_help_response(self) -> ChatResponse:
        content = (
            "Help\n\n"
            "Available commands:\n"
            "- /help: Show this command list.\n"
            "- /clear: Clear only the visible chat messages. The current ChatSession data is kept.\n"
            "- /status: Show current user, character, route, model, and session state.\n"
            "- /health: Show backend, local AI, cloud AI, and overall AI health.\n"
        )

        return self._create_assistant_response(
            content=content,
            route="command",
            model="system_command",
            paid_model_used=False,
            metadata={
                "source": "chat_service",
                "command": "help",
            },
        )

    def _create_health_response(self) -> ChatResponse:
        health = self.health_service.build_payload()
        status = health.get("status", "error")
        errors = health.get("errors", [])

        content = (
            f"Health: {status}\n\n"
            f"- backend_api: {health.get('backend_api')}\n"
            f"- chat_api: {health.get('chat_api')}\n"
            f"- chat_service: {health.get('chat_service')}\n"
            f"- local_ai_available: {health.get('checks', {}).get('local_ai_available')}\n"
            f"- cloud_ai_available: {health.get('checks', {}).get('cloud_ai_available')}\n"
            f"- ai_available: {health.get('checks', {}).get('ai_available')}\n"
            f"- errors: {errors}\n"
            f"- server_time_utc: {health.get('server_time_utc')}"
        )

        return self._create_assistant_response(
            content=content,
            route="command",
            model="system_command",
            paid_model_used=False,
            metadata={
                "source": "chat_service",
                "command": "health",
                "health": health,
            },
        )

    def _create_assistant_response(
        self,
        content: str,
        route: ChatRoute,
        model: str,
        paid_model_used: bool,
        metadata: dict | None = None,
    ) -> ChatResponse:
        response_metadata = {
            "route": route,
            "model": model,
            "paid_model_used": paid_model_used,
        }

        if metadata:
            response_metadata.update(metadata)

        return ChatResponse(
            message=ChatMessage(
                role="assistant",
                content=content,
                metadata=response_metadata,
            )
        )