from html import escape
import re

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
try:
    from shiboken6 import isValid as shiboken_is_valid
except Exception:  # pragma: no cover - defensive fallback for unusual PySide builds.
    shiboken_is_valid = None

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from shared.schema.chat import ChatMessage, ChatRole


PAID_MODEL_LABEL = " (유료 모델 사용) "


class SelectableMessageLabel(QLabel):
    def __init__(self, raw_text: str = "") -> None:
        super().__init__()
        self.raw_text = raw_text
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)


class ChatView(QScrollArea):
    regenerate_requested = Signal(object)

    def __init__(self) -> None:
        super().__init__()

        self.user_display_name = "User"
        self.assistant_display_name = "Assistant"
        self._message_widgets: list[QWidget] = []
        self._markdown_enabled = True
        self._bottom_reserved_height = 0
        self._left_reserved_width = 0
        self._right_reserved_width = 0

        self.setWidgetResizable(True)

        self.container = QWidget()
        self.container.setObjectName("ChatContainer")

        self.layout = QVBoxLayout(self.container)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.layout.setContentsMargins(24, 24, 24, 24)
        self.layout.setSpacing(12)

        self.top_spacer = QSpacerItem(
            0,
            0,
            QSizePolicy.Policy.Minimum,
            QSizePolicy.Policy.Expanding,
        )
        self.layout.addItem(self.top_spacer)

        self.setWidget(self.container)
        self.verticalScrollBar().setSingleStep(36)
        self.verticalScrollBar().setPageStep(180)

    def set_user_display_name(self, name: str) -> None:
        stripped_name = name.strip()
        self.user_display_name = stripped_name or "User"

    def set_assistant_display_name(self, name: str) -> None:
        stripped_name = name.strip()
        self.assistant_display_name = stripped_name or "Assistant"

    def set_display_names(
        self,
        user_name: str,
        assistant_name: str,
    ) -> None:
        self.set_user_display_name(user_name)
        self.set_assistant_display_name(assistant_name)

    def set_bottom_reserved_height(self, height: int) -> None:
        self._bottom_reserved_height = max(0, height)
        self.setViewportMargins(0, 0, 0, self._bottom_reserved_height)

    def set_side_reserved_widths(
        self,
        left_width: int,
        right_width: int,
    ) -> None:
        self._left_reserved_width = max(0, left_width)
        self._right_reserved_width = max(0, right_width)

        self.layout.setContentsMargins(
            24 + self._left_reserved_width,
            24,
            24 + self._right_reserved_width,
            24,
        )

        self._update_message_max_widths()

    def message_widgets(self) -> list[QWidget]:
        return self._message_widgets.copy()

    def set_markdown_enabled(self, enabled: bool) -> None:
        self._markdown_enabled = bool(enabled)

    def add_message(self, role: str, text: str) -> None:
        message = ChatMessage(
            role=self._normalize_role(role),
            content=text,
        )
        self.add_chat_message(message)

    def _message_max_width(self) -> int:
        available_width = (
            self.viewport().width()
            - self._left_reserved_width
            - self._right_reserved_width
            - 72
        )

        return max(260, int(available_width * 0.72))

    def _update_message_max_widths(self) -> None:
        max_width = self._message_max_width()

        for row in self._message_widgets:
            labels = row.findChildren(QLabel)
            for label in labels:
                if label.objectName() in {"UserMessageBubble", "AssistantMessageBubble"}:
                    label.setMaximumWidth(max_width)

    def add_chat_message(self, message: ChatMessage, *, show_actions: bool = True) -> QWidget:
        message_index = len(self._message_widgets)

        row = QWidget()
        row.setObjectName("ChatMessageRow")

        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(0)

        bubble_stack = QWidget()
        bubble_stack.setObjectName("ChatBubbleStack")
        bubble_layout = QVBoxLayout(bubble_stack)
        bubble_layout.setContentsMargins(0, 0, 0, 0)
        bubble_layout.setSpacing(4)

        label = SelectableMessageLabel(raw_text=message.content)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setText(self._build_message_html(message))
        # Links are rendered as text only unless a future explicit safe-open policy is added.
        label.setOpenExternalLinks(False)
        label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        label.setMaximumWidth(self._message_max_width())

        actions = self._create_message_actions(message, message_index, row) if show_actions else None

        if message.role == "user":
            label.setObjectName("UserMessageBubble")
            bubble_layout.addWidget(label)
            if actions is not None:
                bubble_layout.addWidget(actions, alignment=Qt.AlignmentFlag.AlignRight)
            row_layout.addStretch()
            row_layout.addWidget(bubble_stack)
        else:
            label.setObjectName("AssistantMessageBubble")
            bubble_layout.addWidget(label)
            if actions is not None:
                bubble_layout.addWidget(actions, alignment=Qt.AlignmentFlag.AlignLeft)
            row_layout.addWidget(bubble_stack)
            row_layout.addStretch()

        self.layout.addWidget(row)
        self._message_widgets.append(row)
        self._scroll_to_bottom_later()
        return row

    def add_pending_assistant_message(self, text: str) -> QWidget:
        message = ChatMessage(
            role="assistant",
            content=text,
            metadata={"render_markdown": False, "pending": True},
        )
        row = self.add_chat_message(message, show_actions=False)
        row.setProperty("pendingResponse", True)
        return row

    def remove_message_widget(self, widget: QWidget | None) -> None:
        if not self._is_alive_widget(widget):
            return
        try:
            if widget in self._message_widgets:
                self._message_widgets.remove(widget)
            self.layout.removeWidget(widget)
            widget.deleteLater()
            self._scroll_to_bottom_later()
        except RuntimeError:
            return

    def _create_message_actions(self, message: ChatMessage, message_index: int, row: QWidget | None = None) -> QWidget:
        actions = QWidget()
        actions.setObjectName("ChatMessageActions")

        layout = QHBoxLayout(actions)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(4)

        copy_button = QPushButton("복사")
        copy_button.setObjectName("ChatMessageActionButton")
        copy_button.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_button.clicked.connect(
            lambda _checked=False, button=copy_button, text=message.content: self._copy_text(text, button)
        )
        layout.addWidget(copy_button)

        if message.role == "assistant":
            regenerate_button = QPushButton("새로고침")
            regenerate_button.setObjectName("ChatMessageActionButton")
            regenerate_button.setCursor(Qt.CursorShape.PointingHandCursor)
            regenerate_button.clicked.connect(
                lambda _checked=False, button=regenerate_button, msg_id=message.id, fallback_index=message_index: self._request_regenerate(
                    msg_id,
                    fallback_index,
                    button,
                )
            )
            layout.addWidget(regenerate_button)

        layout.addStretch()
        return actions

    def _copy_text(self, text: str, button: QPushButton | None = None) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
        self._flash_action_button(button)

    def _request_regenerate(
        self,
        message_id: str,
        fallback_index: int,
        button: QPushButton | None = None,
    ) -> None:
        # TODO: Replace text action buttons with ChatGPT-like icon buttons later.
        self._flash_action_button(button)
        self.regenerate_requested.emit(message_id or fallback_index)

    def _is_alive_widget(self, widget: QWidget | None) -> bool:
        if widget is None:
            return False
        if shiboken_is_valid is not None:
            try:
                return bool(shiboken_is_valid(widget))
            except RuntimeError:
                return False
        try:
            widget.objectName()
            return True
        except RuntimeError:
            return False

    def _flash_action_button(self, button: QPushButton | None) -> None:
        if not self._is_alive_widget(button):
            return

        try:
            button.setProperty("actionFlash", True)
            self._repolish_widget(button)
        except RuntimeError:
            return

        QTimer.singleShot(1600, lambda btn=button: self._clear_action_button_flash(btn))

    def _clear_action_button_flash(self, button: QPushButton | None) -> None:
        if not self._is_alive_widget(button):
            return

        try:
            button.setProperty("actionFlash", False)
            self._repolish_widget(button)
        except RuntimeError:
            return

    def _repolish_widget(self, widget: QWidget | None) -> None:
        if not self._is_alive_widget(widget):
            return
        try:
            style = widget.style()
            style.unpolish(widget)
            style.polish(widget)
            widget.update()
        except RuntimeError:
            return

    def clear_messages(self) -> None:
        for widget in self._message_widgets:
            self.layout.removeWidget(widget)
            widget.deleteLater()

        self._message_widgets.clear()
        self._scroll_to_bottom_later()

    def _scroll_to_bottom_later(self) -> None:
        QTimer.singleShot(0, self._scroll_to_bottom)
        QTimer.singleShot(30, self._scroll_to_bottom)
        QTimer.singleShot(80, self._scroll_to_bottom)

    def _scroll_to_bottom(self) -> None:
        self.container.adjustSize()
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def _build_message_html(self, message: ChatMessage) -> str:
        display_role = escape(self._display_role(message))
        content = self._content_to_html(message.content, self._should_render_markdown(message))

        return f"<b>{display_role}</b><br>{content}"

    def _should_render_markdown(self, message: ChatMessage) -> bool:
        metadata = message.metadata or {}

        if metadata.get("render_markdown") is False:
            return False

        if not self._markdown_enabled:
            return False

        if metadata.get("render_markdown") is True:
            return True

        # Default conversation output is markdown-enabled. Local slash-command
        # responses explicitly set render_markdown=False before reaching here.
        return True

    def _content_to_html(self, content: str, render_markdown: bool) -> str:
        if not content:
            return ""

        if render_markdown:
            blocks = self._split_fenced_code_blocks(content)
            rendered_parts: list[str] = []
            for block_type, block_text in blocks:
                if block_type == "code":
                    rendered_parts.append(self._render_code_block(block_text))
                else:
                    rendered_parts.append(self._render_markdown_text_block(block_text))
            return "".join(rendered_parts)

        return self._render_plain_text_with_code_blocks(content)

    def _contains_fenced_code_block(self, content: str) -> bool:
        return bool(re.search(r"```", content or ""))

    def _render_plain_text_with_code_blocks(self, content: str) -> str:
        blocks = self._split_fenced_code_blocks(content)
        rendered_parts: list[str] = []
        for block_type, block_text in blocks:
            if block_type == "code":
                rendered_parts.append(self._render_code_block(block_text))
            else:
                rendered_parts.append(escape(block_text).replace("\n", "<br>"))
        return "".join(rendered_parts)

    def _split_fenced_code_blocks(self, content: str) -> list[tuple[str, str]]:
        parts: list[tuple[str, str]] = []
        pattern = re.compile(r"```(?:[^\n`]*)\n?(.*?)```", re.DOTALL)
        last_index = 0
        for match in pattern.finditer(content):
            if match.start() > last_index:
                parts.append(("text", content[last_index:match.start()]))
            parts.append(("code", match.group(1)))
            last_index = match.end()

        if last_index < len(content):
            parts.append(("text", content[last_index:]))

        if not parts:
            parts.append(("text", content))

        return parts

    def _render_code_block(self, code: str) -> str:
        escaped_code = escape(code.strip("\n"))
        if not escaped_code:
            return ""
        return (
            "<pre style=\"white-space: pre-wrap; margin: 8px 0; padding: 8px; "
            "border-radius: 6px; background-color: rgba(127,127,127,0.16);\">"
            f"<code>{escaped_code}</code></pre>"
        )

    def _render_markdown_text_block(self, text: str) -> str:
        lines = text.splitlines()
        html_lines: list[str] = []
        in_list = False

        for raw_line in lines:
            stripped = raw_line.strip()
            if not stripped:
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                html_lines.append("<br>")
                continue

            list_match = re.match(r"^[-*+]\s+(.+)$", stripped)
            if list_match:
                if not in_list:
                    html_lines.append("<ul style=\"margin-top: 4px; margin-bottom: 4px;\">")
                    in_list = True
                html_lines.append(f"<li>{self._render_inline_markdown(list_match.group(1))}</li>")
                continue

            if in_list:
                html_lines.append("</ul>")
                in_list = False

            html_lines.append(self._render_inline_markdown(stripped) + "<br>")

        if in_list:
            html_lines.append("</ul>")

        return "".join(html_lines)

    def _render_inline_markdown(self, text: str) -> str:
        escaped_text = escape(text)

        code_spans: list[str] = []

        def stash_code(match: re.Match) -> str:
            code_spans.append(
                "<code style=\"background-color: rgba(127,127,127,0.16); "
                "border-radius: 4px; padding: 1px 4px;\">"
                f"{match.group(1)}</code>"
            )
            return f"@@CODE_SPAN_{len(code_spans) - 1}@@"

        escaped_text = re.sub(r"`([^`]+)`", stash_code, escaped_text)
        escaped_text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", escaped_text)
        escaped_text = re.sub(r"__([^_]+)__", r"<b>\1</b>", escaped_text)
        escaped_text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", escaped_text)
        escaped_text = re.sub(r"(?<!_)_([^_]+)_(?!_)", r"<i>\1</i>", escaped_text)
        # Do not create clickable links in the first pass; show label and URL clearly.
        escaped_text = re.sub(r"\[([^\]]+)\]\(([^\)]+)\)", r"<u>\1</u> (\2)", escaped_text)

        for index, html in enumerate(code_spans):
            escaped_text = escaped_text.replace(f"@@CODE_SPAN_{index}@@", html)

        return escaped_text

    def _normalize_role(self, role: str) -> ChatRole:
        lowered = role.lower()

        if lowered in {"system", "user", "assistant", "tool"}:
            return lowered  # type: ignore[return-value]

        return "assistant"

    def _display_role(self, message: ChatMessage) -> str:
        role = message.role

        if role == "user":
            return self.user_display_name

        if role == "assistant":
            display_name = self.assistant_display_name

            if self._is_paid_model_message(message):
                display_name += PAID_MODEL_LABEL

            return display_name

        if role == "system":
            return "System"

        if role == "tool":
            return "Tool"

        return role

    def _is_paid_model_message(self, message: ChatMessage) -> bool:
        value = message.metadata.get("paid_model_used", False)
        return bool(value)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_message_max_widths()
