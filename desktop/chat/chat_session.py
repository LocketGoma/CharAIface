from shared.schema.chat import ChatMessage, ChatRole


class ChatSession:
    def __init__(self) -> None:
        self._messages: list[ChatMessage] = []

    @property
    def messages(self) -> list[ChatMessage]:
        return self._messages.copy()

    def add_message(
        self,
        role: ChatRole,
        content: str,
        metadata: dict | None = None,
    ) -> ChatMessage:
        message = ChatMessage(
            role=role,
            content=content,
            metadata=metadata or {},
        )

        self._messages.append(message)
        return message

    def add_user_message(self, content: str) -> ChatMessage:
        return self.add_message(role="user", content=content)

    def add_assistant_message(self, content: str) -> ChatMessage:
        return self.add_message(role="assistant", content=content)

    def clear(self) -> None:
        self._messages.clear()