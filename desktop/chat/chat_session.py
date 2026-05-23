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

    def append_message(self, message: ChatMessage) -> ChatMessage:
        self._messages.append(message)
        return message

    def add_user_message(
        self,
        content: str,
        metadata: dict | None = None,
    ) -> ChatMessage:
        return self.add_message(
            role="user",
            content=content,
            metadata=metadata,
        )

    def add_assistant_message(
        self,
        content: str,
        metadata: dict | None = None,
    ) -> ChatMessage:
        return self.add_message(
            role="assistant",
            content=content,
            metadata=metadata,
        )

    def add_system_message(
        self,
        content: str,
        metadata: dict | None = None,
    ) -> ChatMessage:
        return self.add_message(
            role="system",
            content=content,
            metadata=metadata,
        )

    def add_tool_message(
        self,
        content: str,
        metadata: dict | None = None,
    ) -> ChatMessage:
        return self.add_message(
            role="tool",
            content=content,
            metadata=metadata,
        )

    def latest_user_message(self) -> ChatMessage | None:
        for message in reversed(self._messages):
            if message.role == "user":
                return message

        return None

    def last_message(self) -> ChatMessage | None:
        if not self._messages:
            return None

        return self._messages[-1]

    def replace_messages(self, messages: list[ChatMessage]) -> None:
        self._messages = messages.copy()

    def clear(self) -> None:
        self._messages.clear()