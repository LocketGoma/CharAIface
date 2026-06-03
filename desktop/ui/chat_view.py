from html import escape
from pathlib import Path
import re

from PySide6.QtCore import QPoint, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont, QGuiApplication

try:
    import shiboken6
except ImportError:  # pragma: no cover - PySide6 normally provides this.
    shiboken6 = None
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
TYPEWRITER_INTERVAL_MS = 25
TYPEWRITER_MAX_INTERVAL_MS = 100
TYPEWRITER_MAX_TICKS = 160


class SelectableMessageLabel(QLabel):
    def __init__(self, raw_text: str = "") -> None:
        super().__init__()
        self.raw_text = raw_text
        self.local_export_path = ""
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
            | Qt.TextInteractionFlag.LinksAccessibleByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByKeyboard
        )
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)


class ChatView(QScrollArea):
    regenerate_requested = Signal(object)
    cancel_response_requested = Signal()
    assistant_message_display_finished = Signal(str)

    def __init__(self) -> None:
        super().__init__()

        self.user_display_name = "User"
        self.assistant_display_name = "Assistant"
        self._message_widgets: list[QWidget] = []
        self._markdown_enabled = True
        self._bottom_reserved_height = 0
        self._left_reserved_width = 0
        self._right_reserved_width = 0
        self._message_font_family = ""
        self._message_font_size = 10
        self._typewriter_interval_ms = TYPEWRITER_INTERVAL_MS
        self._typewriter_timers: dict[str, QTimer] = {}
        self._copy_action_text = ""
        self._regenerate_action_text = ""
        self._cancel_response_action_text = ""

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

    def set_message_font(self, family: str = "", size: int = 10) -> None:
        self._message_font_family = str(family or "").strip()
        try:
            self._message_font_size = int(size)
        except (TypeError, ValueError):
            self._message_font_size = 10
        self._message_font_size = max(1, min(200, self._message_font_size))

        for label in self.findChildren(SelectableMessageLabel):
            self._apply_message_font(label)

    def _apply_message_font(self, label: SelectableMessageLabel) -> None:
        font = QFont(label.font())
        if self._message_font_family:
            font.setFamily(self._message_font_family)
        font.setPointSize(max(1, int(self._message_font_size)))
        label.setFont(font)

    def _message_html_style(self) -> str:
        size = max(1, min(200, int(self._message_font_size)))
        styles = [f"font-size:{size}pt"]
        if self._message_font_family:
            styles.append(f"font-family:'{escape(self._message_font_family, quote=True)}'")
        return "; ".join(styles)

    def set_markdown_enabled(self, enabled: bool) -> None:
        self._markdown_enabled = bool(enabled)

    def set_typewriter_interval_ms(self, interval_ms: int) -> None:
        try:
            interval = int(interval_ms)
        except (TypeError, ValueError):
            interval = TYPEWRITER_INTERVAL_MS
        if interval <= 0:
            self._typewriter_interval_ms = 0
            return

        interval = max(10, min(TYPEWRITER_MAX_INTERVAL_MS, interval))
        self._typewriter_interval_ms = round(interval / 10) * 10

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

    def add_chat_message(self, message: ChatMessage, *, animate: bool = False) -> QWidget:
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
        label.local_export_path = str((message.metadata or {}).get("local_export_path") or "")
        self._apply_message_font(label)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.RichText)
        # Only file links generated by local export notices are opened.
        label.setOpenExternalLinks(False)
        label.linkActivated.connect(self._open_message_link)
        label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        label.setMaximumWidth(self._message_max_width())
        if (message.metadata or {}).get("pending"):
            label.setMinimumWidth(180)
        should_animate = (
            animate
            and message.role == "assistant"
            and bool(message.content)
            and self._typewriter_interval_ms > 0
        )
        if should_animate:
            label.setText(
                self._build_message_html(
                    message,
                    content_override="",
                    render_markdown=False,
                    plain_text_only=True,
                )
            )
        else:
            label.setText(self._build_message_html(message))

        actions = self._create_message_actions(message, message_index, row)

        if message.role == "user":
            label.setObjectName("UserMessageBubble")
            bubble_layout.addWidget(label)
            bubble_layout.addWidget(actions, alignment=Qt.AlignmentFlag.AlignRight)
            row_layout.addStretch()
            row_layout.addWidget(bubble_stack)
        else:
            label.setObjectName("AssistantMessageBubble")
            bubble_layout.addWidget(label)
            bubble_layout.addWidget(actions, alignment=Qt.AlignmentFlag.AlignLeft)
            row_layout.addWidget(bubble_stack)
            row_layout.addStretch()

        self.layout.addWidget(row)
        self._message_widgets.append(row)
        self._scroll_to_bottom_later()
        if should_animate:
            self._start_typewriter_animation(message, label, row)
        return row

    def _create_message_actions(self, message: ChatMessage, message_index: int, row: QWidget | None = None) -> QWidget:
        actions = QWidget()
        actions.setObjectName("ChatMessageActions")

        layout = QHBoxLayout(actions)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(4)

        if message.role == "assistant" and (message.metadata or {}).get("pending"):
            cancel_button = QPushButton(self._cancel_response_action_text)
            cancel_button.setObjectName("ChatMessagePendingCancelButton")
            cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
            cancel_button.clicked.connect(self.cancel_response_requested.emit)
            layout.addWidget(cancel_button)
            layout.addStretch()
            return actions

        copy_button = QPushButton(self._copy_action_text)
        copy_button.setObjectName("ChatMessageActionButton")
        copy_button.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_button.clicked.connect(
            lambda _checked=False, button=copy_button, text=message.content: self._copy_text(text, button)
        )
        layout.addWidget(copy_button)

        if message.role == "assistant":
            regenerate_button = QPushButton(self._regenerate_action_text)
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

    def set_action_texts(
        self,
        *,
        copy_text: str,
        regenerate_text: str,
        cancel_response_text: str,
    ) -> None:
        self._copy_action_text = copy_text
        self._regenerate_action_text = regenerate_text
        self._cancel_response_action_text = cancel_response_text

    def handle_global_mouse_press(self, global_pos: QPoint) -> bool:
        """Handle clickable chat content hidden under the bottom overlay.

        The bottom character/composer overlay visually overlaps the lower chat
        area. When chat controls are behind that overlay, Qt delivers the mouse
        press to the overlay instead of the chat content. This method uses
        global coordinates as a fallback and lets ChatView decide what is
        clickable inside itself.
        It should only be called from overlay mouse handling, never for normal
        ChatView events, so it cannot double-fire a normal click.
        """
        return self._handle_global_link_mouse_press(global_pos) or self._handle_global_action_mouse_press(global_pos)

    def _handle_global_action_mouse_press(self, global_pos: QPoint) -> bool:
        if global_pos is None:
            return False

        action_button_names = {
            "ChatMessageActionButton",
            "ChatMessagePendingCancelButton",
        }
        buttons = [
            button
            for button in self.findChildren(QPushButton)
            if button.objectName() in action_button_names
        ]
        for button in buttons:
            if not self._is_alive_widget(button) or not button.isVisible() or not button.isEnabled():
                continue

            top_left = button.mapToGlobal(button.rect().topLeft())
            button_rect = button.rect().translated(top_left)
            if button_rect.contains(global_pos):
                button.click()
                return True

        return False

    def _handle_global_link_mouse_press(self, global_pos: QPoint) -> bool:
        if global_pos is None:
            return False

        labels = [
            label
            for label in self.findChildren(SelectableMessageLabel)
            if self._is_alive_widget(label) and label.isVisible() and label.isEnabled()
        ]
        for label in labels:
            local_pos = label.mapFromGlobal(global_pos)
            if not label.rect().contains(local_pos):
                continue

            export_path = str(getattr(label, "local_export_path", "") or "").strip()
            if not export_path:
                continue

            try:
                href = Path(export_path).resolve().as_uri()
            except ValueError:
                continue

            self._open_message_link(href)
            return True

        return False

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

    def _flash_action_button(self, button: QPushButton | None) -> None:
        if not self._is_alive_widget(button):
            return

        button.setProperty("actionFlash", True)
        self._repolish_widget(button)
        QTimer.singleShot(1600, lambda btn=button: self._clear_action_button_flash(btn))

    def _clear_action_button_flash(self, button: QPushButton | None) -> None:
        if not self._is_alive_widget(button):
            return

        button.setProperty("actionFlash", False)
        self._repolish_widget(button)

    def _repolish_widget(self, widget: QWidget | None) -> None:
        if not self._is_alive_widget(widget):
            return

        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)
        widget.update()

    def _is_alive_widget(self, widget: QWidget | None) -> bool:
        if widget is None:
            return False
        if shiboken6 is not None and not shiboken6.isValid(widget):
            return False
        return True

    def clear_messages(self) -> None:
        self._stop_all_typewriter_animations()
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

    def _build_message_html(
        self,
        message: ChatMessage,
        *,
        content_override: str | None = None,
        render_markdown: bool | None = None,
        plain_text_only: bool = False,
    ) -> str:
        display_role = escape(self._display_role(message))
        raw_content = message.content if content_override is None else content_override
        should_render_markdown = (
            self._should_render_markdown(message)
            if render_markdown is None
            else render_markdown
        )
        content = (
            escape(raw_content).replace("\n", "<br>")
            if plain_text_only
            else self._content_to_html(raw_content, should_render_markdown)
        )
        content += self._local_export_link_html(message)

        style = self._message_html_style()
        return f'<div style="{style}"><b>{display_role}</b><br>{content}</div>'

    def _local_export_link_html(self, message: ChatMessage) -> str:
        metadata = message.metadata or {}
        export_path = str(metadata.get("local_export_path") or "").strip()
        if not export_path:
            return ""

        try:
            href = Path(export_path).resolve().as_uri()
        except ValueError:
            return ""

        link_text = str(metadata.get("local_export_link_text") or "Open file")
        return (
            "<br>"
            f"<a href=\"{escape(href, quote=True)}\">"
            f"{escape(link_text)}"
            "</a>"
        )

    def _open_message_link(self, url: str) -> None:
        if not str(url).startswith("file://"):
            return

        QDesktopServices.openUrl(QUrl(url))

    def _start_typewriter_animation(
        self,
        message: ChatMessage,
        label: SelectableMessageLabel,
        row: QWidget,
    ) -> None:
        content = message.content or ""
        message_id = message.id
        total_length = len(content)
        if total_length <= 0:
            self.assistant_message_display_finished.emit(message_id)
            return

        interval_ms = max(1, self._typewriter_interval_ms)
        chunk_size = max(1, (total_length + TYPEWRITER_MAX_TICKS - 1) // TYPEWRITER_MAX_TICKS)
        state = {"index": 0}

        timer = QTimer(self)
        timer.setInterval(interval_ms)
        self._typewriter_timers[message_id] = timer

        def advance() -> None:
            if not self._is_alive_widget(row) or not self._is_alive_widget(label):
                self._stop_typewriter_animation(message_id)
                return

            state["index"] = min(total_length, state["index"] + chunk_size)
            partial = content[: state["index"]]
            label.raw_text = partial
            label.setText(
                self._build_message_html(
                    message,
                    content_override=partial,
                    render_markdown=False,
                    plain_text_only=True,
                )
            )
            self._scroll_to_bottom()

            if state["index"] >= total_length:
                self._stop_typewriter_animation(message_id)
                label.raw_text = content
                label.setText(self._build_message_html(message))
                self._scroll_to_bottom_later()
                self.assistant_message_display_finished.emit(message_id)

        timer.timeout.connect(advance)
        timer.start()

    def _stop_typewriter_animation(self, message_id: str) -> None:
        timer = self._typewriter_timers.pop(message_id, None)
        if timer is None:
            return

        timer.stop()
        timer.deleteLater()

    def _stop_all_typewriter_animations(self) -> None:
        for message_id in list(self._typewriter_timers):
            self._stop_typewriter_animation(message_id)

    def add_pending_assistant_message(self, text: str) -> QWidget:
        message = ChatMessage(
            role="assistant",
            content=text,
            metadata={
                "render_markdown": False,
                "pending": True,
            },
        )
        before_count = len(self._message_widgets)
        self.add_chat_message(message)
        if len(self._message_widgets) > before_count:
            return self._message_widgets[-1]
        return self.container

    def _should_render_markdown(self, message: ChatMessage) -> bool:
        metadata = message.metadata or {}

        if message.role == "user":
            return False

        if metadata.get("render_markdown") is False:
            return False

        if not self._markdown_enabled:
            return False

        if metadata.get("render_markdown"):
            return True

        # Default conversation output is markdown-enabled. Local slash-command
        # responses explicitly set render_markdown=False before reaching here.
        return True

    def remove_message_widget(self, widget: QWidget | None) -> None:
        if widget is None:
            return
        if not self._is_alive_widget(widget):
            try:
                self._message_widgets.remove(widget)
            except ValueError:
                pass
            return
        try:
            self.layout.removeWidget(widget)
            if widget in self._message_widgets:
                self._message_widgets.remove(widget)
            widget.deleteLater()
            self._scroll_to_bottom_later()
        except RuntimeError:
            try:
                self._message_widgets.remove(widget)
            except ValueError:
                pass

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
