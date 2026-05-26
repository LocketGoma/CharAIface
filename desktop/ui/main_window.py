from pathlib import Path
from shared.schema.chat import ChatMessage, ChatRequest
from desktop.chat.chat_session import ChatSession
from desktop.chat.session_store import ChatSessionStore
from desktop.client.backend_http_client import BackendHttpClient
from desktop.workers.local_model_prepare_worker import LocalModelPrepareWorker
from desktop.workers.chat_response_worker import ChatResponseWorker
from PySide6.QtCore import QEvent, QPoint, Qt, QThread, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QInputDialog,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desktop.characters.character_pack import CharacterPack
from desktop.characters.character_registry import CharacterRegistry
from desktop.core.character_state import CharacterStateController
from desktop.core.system_status import get_process_status, get_system_overview
from desktop.localization.localization_manager import LocalizationManager
from desktop.settings.app_settings import AppSettings
from desktop.settings.settings_repository import SettingsRepository
from desktop.theme.qss_builder import build_qss
from desktop.theme.theme_manager import ThemeManager
from desktop.theme.theme_model import ThemeDefinition
from desktop.ui.bottom_user_area import BottomUserArea
from desktop.ui.chat_view import ChatView
from desktop.ui.settings_dialog import SettingsDialog
from desktop.ui.session_sidebar import SessionSidebar


class MainWindow(QMainWindow):
    MIN_WINDOW_WIDTH = 600
    MIN_WINDOW_HEIGHT = 450

    def __init__(
        self,
        localization: LocalizationManager,
        theme: ThemeDefinition,
        theme_manager: ThemeManager,
        settings: AppSettings,
        settings_repository: SettingsRepository,
    ) -> None:
        super().__init__()

        self.localization = localization
        self.theme = theme
        self.theme_manager = theme_manager
        self.settings = settings
        self.settings_repository = settings_repository

        self.character_state = CharacterStateController(done_to_idle_ms=3000)
        self.character_registry: CharacterRegistry | None = None
        self.current_character_pack: CharacterPack | None = None
        self.local_model_prepare_thread: QThread | None = None
        self.local_model_prepare_worker: LocalModelPrepareWorker | None = None
        self.chat_response_thread: QThread | None = None
        self.chat_response_worker: ChatResponseWorker | None = None
        self.active_chat_response_session_id: str | None = None
        self.pending_response_session_id: str | None = None
        self.pending_response_widget = None
        self.initial_notice_added = False
        project_root = Path(__file__).resolve().parents[2]
        self.session_store = ChatSessionStore(
            project_root / "resources" / "data" / "chat_sessions"
        )
        self.chat_session = ChatSession()
        self.current_session_id: str | None = None
        self.current_session_title: str = ""
        self.backend_client = BackendHttpClient()
        self._restore_last_chat_session()

        # Cache of installed local AI model names. This list is populated on
        # demand via _refresh_installed_models(). It ensures the settings
        # dialog and other parts of the UI always display the most recent
        # selection of available models without repeatedly querying the
        # backend. The cache is refreshed whenever models are installed or
        # removed.
        self._installed_models_cache: list[str] = []

        # Timer for periodic local model update checks. It is initialised in
        # _schedule_local_model_update_timer when settings indicate that
        # update checks are enabled. The timer is restarted whenever the
        # settings change via the settings dialog.
        self._local_model_update_timer: QTimer | None = None

        self.setMinimumSize(self.MIN_WINDOW_WIDTH, self.MIN_WINDOW_HEIGHT)
        self.resize(self.settings.window_width, self.settings.window_height)

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        header = self._create_header()
        body = self._create_body_area()

        root_layout.addWidget(header)
        root_layout.addWidget(body, stretch=1)

        self.setCentralWidget(root)

        self.apply_theme_from_settings()
        self.retranslate_ui()
        QTimer.singleShot(0, self._restore_window_geometry)
        QTimer.singleShot(100, self._check_backend_health)
        QTimer.singleShot(500, self._check_local_ai_model)

        # Schedule periodic model update checks based on the loaded settings.
        QTimer.singleShot(1000, self._schedule_local_model_update_timer)

    def _create_body_area(self) -> QWidget:
        self.body_area = QWidget()
        self.body_area.setObjectName("BodyArea")

        layout = QHBoxLayout(self.body_area)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        content_area = self._create_content_area()
        layout.addWidget(content_area, stretch=1)

        QTimer.singleShot(0, self._refresh_session_sidebar)
        return self.body_area

    def _create_content_area(self) -> QWidget:
        self.content_area = QWidget()
        self.content_area.setObjectName("ContentArea")

        self.chat_view = ChatView()
        self.chat_view.set_markdown_enabled(self.settings.conversation_markdown_enabled)
        self.chat_view.setParent(self.content_area)

        self.session_sidebar = SessionSidebar(parent=self.content_area)
        self.session_sidebar.new_session_requested.connect(
            self._on_sidebar_new_session_requested
        )
        self.session_sidebar.refresh_requested.connect(
            self._refresh_session_sidebar
        )
        self.session_sidebar.session_selected.connect(
            self._on_sidebar_session_selected
        )
        self.session_sidebar.session_rename_requested.connect(
            self._on_sidebar_session_rename_requested
        )
        self.session_sidebar.session_delete_requested.connect(
            self._on_sidebar_session_delete_requested
        )
        self.session_sidebar.collapsed_changed.connect(
            lambda _collapsed: self._update_content_geometry()
        )

        self.bottom_area = BottomUserArea(localization=self.localization)
        self.bottom_area.setParent(self.content_area)
        self.bottom_area.set_user_name(self.settings.user_name)

        # The character overlay is visual-first. Normal mouse input over the
        # character is ignored/pass-through. Holding Alt (Option on macOS) turns
        # the character layer into an interactive mouse target.
        self._character_click_text = "(캐릭터를 쓰다듬는다)"
        self._character_mouse_events_enabled = False
        app = QApplication.instance()
        if app is not None:
            # App-level filtering is used only to track modifier key state.
            # Mouse presses are handled only for widgets that actually belong to
            # the character area, avoiding recursive re-dispatch loops.
            app.installEventFilter(self)

        self._load_character_registry()
        self._apply_selected_or_default_character_pack()
        self._update_chat_view_display_names()

        self.bottom_area.send_requested.connect(self.on_send_requested)
        self.bottom_area.text_changed.connect(self.character_state.on_user_text_changed)
        self.character_state.state_changed.connect(self.bottom_area.set_state)
        self.chat_view.regenerate_requested.connect(self._on_regenerate_requested)

        self.chat_view.verticalScrollBar().valueChanged.connect(
            self._update_avatar_occlusion_later
        )

        self.chat_view.show()
        self.session_sidebar.show()
        self.bottom_area.show()

        self.bottom_area.installEventFilter(self)
        self.bottom_area.character_area.installEventFilter(self)
        self.bottom_area.character_info_box.installEventFilter(self)
        self.bottom_area.user_label.installEventFilter(self)
        self.bottom_area.user_name_label.installEventFilter(self)
        self.bottom_area.avatar_widget.installEventFilter(self)

        self._set_character_mouse_events_enabled(False)

        self.session_sidebar.raise_()
        self.bottom_area.raise_()

        QTimer.singleShot(0, self._update_content_geometry)
        if self.chat_session.messages:
            QTimer.singleShot(0, self._render_current_chat_session)

        return self.content_area

    def _create_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("HeaderBar")
        header.setFixedHeight(56)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 8, 16, 8)

        self.title_label = QLabel()
        self.title_label.setObjectName("HeaderTitle")
        self.title_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.title_label.installEventFilter(self)

        self.settings_button = QPushButton()
        self.settings_button.setObjectName("HeaderButton")
        self.settings_button.clicked.connect(self.open_settings_dialog)

        layout.addWidget(self.title_label)
        layout.addStretch()
        layout.addWidget(self.settings_button)

        return header

    def _load_character_registry(self) -> None:
        project_root = Path(__file__).resolve().parents[2]

        builtin_characters_dir = (
            project_root
            / "resources"
            / "builtin"
            / "characters"
        )

        user_characters_dir = (
            project_root
            / "resources"
            / "characters"
        )

        additional_user_characters_dirs = [
            project_root / "resources" / "character",
            project_root / "resource" / "characters",
            project_root / "resource" / "character",
        ]

        self.character_registry = CharacterRegistry(
            builtin_characters_dir=builtin_characters_dir,
            user_characters_dir=user_characters_dir,
            additional_user_characters_dirs=additional_user_characters_dirs,
        )
        self.character_registry.load()

        print(
            "[CharacterRegistry] Loaded "
            f"{len(self.character_registry.packs)} character pack(s)."
        )

        for warning in self.character_registry.warnings:
            print(f"[CharacterRegistry] Warning: {warning}")

        for invalid in self.character_registry.invalid_packs:
            source = invalid.get("source", "unknown")
            path = invalid.get("path", "")

            print(f"[CharacterRegistry] Invalid [{source}]: {path}")

            for message in invalid.get("messages", []):
                print(f"  - {message}")

    def _apply_selected_or_default_character_pack(self) -> None:
        if self.character_registry is None:
            print("[CharacterRegistry] Registry is not initialized.")
            self._show_missing_default_character_warning()
            return

        character_pack = self.character_registry.get_pack(
            self.settings.selected_character_id
        )

        if character_pack is None:
            character_pack = self.character_registry.get_default_pack()

        if character_pack is None:
            print("[CharacterRegistry] No valid character pack found.")
            self._show_missing_default_character_warning()
            return

        self._apply_character_pack(character_pack)

    def _apply_character_pack(self, character_pack: CharacterPack) -> None:
        self.current_character_pack = character_pack
        self.settings.selected_character_id = character_pack.id

        self.bottom_area.set_character_name(character_pack.name)
        self.bottom_area.set_avatar_images(character_pack.avatar_images_as_str())
        self._update_chat_view_display_names()

        if self.character_registry is not None:
            source = (
                "builtin"
                if self.character_registry.is_builtin(character_pack.id)
                else "user"
            )
        else:
            source = "unknown"

        print(
            "[CharacterRegistry] Applied character: "
            f"{character_pack.name} ({character_pack.id}) [{source}]"
        )

    def _show_missing_default_character_warning(self) -> None:
        QMessageBox.critical(
            self,
            self.localization.t("app.title"),
            self.localization.t("character.default_missing"),
        )

        app = QApplication.instance()

        if app is not None:
            QTimer.singleShot(0, app.quit)
        else:
            QTimer.singleShot(0, self.close)

    def open_settings_dialog(self) -> None:
        if self.character_registry is None:
            print("[Settings] CharacterRegistry is not initialized.")
            return

        # Refresh the installed model cache so that the settings dialog can
        # populate its model selection combo box with the latest models. We
        # pass auto_start_server=True to start the Ollama server if needed.
        installed_models = self._refresh_installed_models(auto_start_server=True)

        dialog = SettingsDialog(
            settings=self.settings.model_copy(deep=True),
            localization=self.localization,
            theme_manager=self.theme_manager,
            character_registry=self.character_registry,
            installed_models=installed_models,
            parent=self,
        )
        dialog.local_model_prepare_requested.connect(
            self._on_settings_local_model_prepare_requested
        )
        dialog.local_model_delete_requested.connect(
            self._on_settings_local_model_delete_requested
        )
        dialog.local_model_list_requested.connect(
            self._on_settings_local_model_list_requested
        )
        previous_avatar_occluded_opacity = self.settings.avatar_occluded_opacity
        dialog.avatar_opacity_preview_changed.connect(
            self._preview_avatar_occluded_opacity
        )

        if not dialog.exec():
            self.settings.avatar_occluded_opacity = previous_avatar_occluded_opacity
            self._update_avatar_occlusion_later()
            return

        character_registry_reloaded = bool(
            getattr(dialog, "character_registry_reloaded", False)
        )

        dialog.apply_to_settings()
        new_settings = dialog.settings

        self._apply_settings(
            new_settings,
            force_character_reload=character_registry_reloaded,
        )

    def _apply_settings(
        self,
        new_settings: AppSettings,
        force_character_reload: bool = False,
    ) -> None:
        old_language = self.settings.language
        old_theme_id = self.settings.theme_id
        old_character_id = self.settings.selected_character_id

        self.settings = new_settings
        if hasattr(self, "chat_view"):
            self.chat_view.set_markdown_enabled(self.settings.conversation_markdown_enabled)
            self._render_current_chat_session()

        if self.settings.language != old_language:
            try:
                self.localization.set_language(self.settings.language)
            except ValueError:
                print(
                    f'[Settings] Unsupported language "{self.settings.language}". '
                    f'Keeping "{old_language}".'
                )
                self.settings.language = old_language

        if (
            self.settings.theme_id != old_theme_id
            or self.settings.selected_character_id != old_character_id
            or force_character_reload
        ):
            self.apply_theme_from_settings()

        if self.character_registry is not None and (
            self.settings.selected_character_id != old_character_id
            or force_character_reload
        ):
            character_pack = self.character_registry.get_pack(
                self.settings.selected_character_id
            )

            if character_pack is None:
                character_pack = self.character_registry.get_default_pack()

            if character_pack is not None:
                self._apply_character_pack(character_pack)
            else:
                print(
                    "[Settings] Unknown character id and no fallback character found: "
                    f"{self.settings.selected_character_id}"
                )
                self.settings.selected_character_id = old_character_id

        #유저 이름 변경시 적용
        self.bottom_area.set_user_name(self.settings.user_name)
        self._update_chat_view_display_names()
        self.retranslate_ui()

        self.settings_repository.save(self.settings)
        self._update_avatar_occlusion_later()

        # Reschedule periodic model update checks whenever the settings are applied. This
        # ensures that changes to the update check enabled flag or interval take
        # effect without requiring an application restart.
        self._schedule_local_model_update_timer()

    def _preview_avatar_occluded_opacity(self, opacity: float) -> None:
        self.settings.avatar_occluded_opacity = min(1.0, max(0.1, float(opacity)))
        self._update_avatar_occlusion_later()

    def apply_theme(self, theme: ThemeDefinition) -> None:
        self.theme = theme
        self.setStyleSheet(build_qss(theme))

    def apply_theme_from_settings(self) -> None:
        if self.settings.theme_id == "character":
            character_pack = self.current_character_pack

            if character_pack is not None and character_pack.theme is not None:
                try:
                    character_theme = self.theme_manager.create_character_theme(
                        base_theme_id=character_pack.theme.base_theme,
                        palette_override=character_pack.theme.palette_override,
                        character_name=character_pack.name,
                    )
                    self.apply_theme(character_theme)
                    return

                except ValueError as error:
                    print(f"[Theme] Failed to apply character theme: {error}")

            try:
                self.apply_theme(self.theme_manager.get_theme("light"))
            except ValueError:
                self.apply_theme(self.theme)

            return

        try:
            theme = self.theme_manager.get_theme(self.settings.theme_id)
            self.apply_theme(theme)

        except ValueError:
            print(
                f'[Theme] Unknown theme "{self.settings.theme_id}". '
                "Falling back to light."
            )
            self.settings.theme_id = "light"
            self.apply_theme(self.theme_manager.get_theme("light"))

    def retranslate_ui(self) -> None:
        self.setWindowTitle(self.localization.t("app.title"))
        self.title_label.setText(self.localization.t("app.title"))
        self.settings_button.setText(self.localization.t("settings.title"))
        if hasattr(self, "session_sidebar"):
            self.session_sidebar.retranslate_ui()
        self.bottom_area.retranslate_ui()
        self.bottom_area.set_user_name(self.settings.user_name)
        self._update_chat_view_display_names()

    def _show_about_dialog(self) -> None:
        QMessageBox.information(
            self,
            self.localization.t("about.title"),
            self.localization.t(
                "about.message",
                app_name=self._application_display_name(),
                character_name=self._character_display_name(),
            ),
        )

    def _update_chat_view_display_names(self) -> None:
        if not hasattr(self, "chat_view"):
            return

        user_name = self.settings.user_name
        assistant_name = self._character_display_name()

        self.chat_view.set_display_names(
            user_name=user_name,
            assistant_name=assistant_name,
        )

    def _application_display_name(self) -> str:
        app_name = self.localization.t("app.title")

        if app_name == "{app.title}":
            return "CharAIface"

        return app_name

    def _character_display_name(self) -> str:
        if self.current_character_pack is not None:
            return self.current_character_pack.name

        return "Assistant"

    def _add_initial_session_notice(self, local_model_installed: bool) -> None:
        if self.initial_notice_added:
            return

        if self.chat_session.messages:
            self.initial_notice_added = True
            return

        key = (
            "chat.initial_notice.new_session"
            if local_model_installed
            else "chat.initial_notice.model_required"
        )

        self._add_assistant_message(
            self.localization.t(
                key,
                app_name=self._application_display_name(),
                character_name=self._character_display_name(),
            )
        )
        self.initial_notice_added = True

    def _add_user_message(self, content: str) -> None:
        render_markdown = self._should_use_markdown_for_request(content)
        message = self.chat_session.add_user_message(
            content,
            metadata={"render_markdown": render_markdown},
        )
        self.chat_view.add_chat_message(message)
        self._save_current_chat_session()

    def _add_assistant_message(
        self,
        content: str,
        *,
        render_markdown: bool | None = None,
    ) -> None:
        if render_markdown is None:
            render_markdown = bool(self.settings.conversation_markdown_enabled)
        metadata = {"render_markdown": bool(render_markdown)}
        message = self.chat_session.add_assistant_message(content, metadata=metadata)
        self.chat_view.add_chat_message(message)
        self._save_current_chat_session()

    def _should_use_markdown_for_request(self, text: str) -> bool:
        if not self.settings.conversation_markdown_enabled:
            return False

        stripped = (text or "").strip()
        if stripped.startswith("/"):
            return False

        return True

    def _finish_local_command(self) -> None:
        # Local slash commands do not enter the normal ChatResponseWorker finish path.
        # Always restore the character state unless a command explicitly left it in
        # panic/error state. This prevents /status, /health, /systemstatus, etc.
        # from being stuck in user_typing after the composer was cleared.
        if self.character_state.current_state not in {"panic", "error"}:
            self.character_state.on_assistant_done()
        self.bottom_area.raise_()
        self._update_avatar_occlusion_later()

    def _on_regenerate_requested(self, message_ref) -> None:
        if self.chat_response_thread is not None:
            print("[Chat] Cannot regenerate while a response request is already running.")
            return

        messages = self.chat_session.messages
        if not messages:
            print("[Chat] Regenerate request ignored because the session is empty.")
            return

        assistant_index = -1

        # Newer ChatView builds emit the stable ChatMessage.id. Older builds may
        # still emit a row index, so keep both paths for compatibility.
        if isinstance(message_ref, str):
            for index, message in enumerate(messages):
                if getattr(message, "id", "") == message_ref:
                    assistant_index = index
                    break

            if assistant_index < 0 and message_ref.isdigit():
                assistant_index = int(message_ref)
        elif isinstance(message_ref, int):
            assistant_index = message_ref

        if assistant_index < 0 or assistant_index >= len(messages):
            print(f"[Chat] Regenerate request index out of range: {message_ref}")
            return

        # Regenerate is primarily shown on assistant messages. If an older UI build
        # sends a nearby index, walk backward to the assistant message that should be
        # replaced instead of crashing or doing nothing.
        while assistant_index >= 0 and messages[assistant_index].role != "assistant":
            assistant_index -= 1

        if assistant_index < 0:
            print(f"[Chat] Regenerate request has no assistant message: {message_ref}")
            return

        user_index = assistant_index - 1
        while user_index >= 0 and messages[user_index].role != "user":
            user_index -= 1

        if user_index < 0:
            print(f"[Chat] Regenerate request has no preceding user message: {message_ref}")
            return

        # Keep conversation history through the source user message, then remove the
        # target assistant reply and any later messages. The next worker call will
        # generate a fresh assistant response for that user turn.
        retained_messages = messages[: user_index + 1]
        self.chat_session.replace_messages(retained_messages)
        self._render_current_chat_session()
        self._save_current_chat_session(force=True)

        self.bottom_area.raise_()
        self.character_state.on_message_sent()
        self._update_avatar_occlusion_later()
        self._start_chat_response_worker()

    def on_send_requested(self, text: str) -> None:
        command_text = text.strip()
        normalized_text = command_text.lower()

        if normalized_text.startswith("/"):
            if self._handle_command(command_text):
                return

        if self.chat_response_thread is not None:
            print("[Chat] Chat response request is already running.")
            return

        self.bottom_area.raise_()
        self.character_state.on_message_sent()
        self._add_user_message(text)
        self._update_avatar_occlusion_later()

        self._start_chat_response_worker()

    def _handle_command(self, command: str) -> bool:
        command_text = command.strip()
        normalized = command_text.lower()

        handled = False
        try:
            if normalized == "/clear":
                self._clear_chat_display_only()
                handled = True

            elif normalized == "/newsession":
                self._create_new_chat_session()
                handled = True

            elif normalized == "/savesession":
                self._save_current_chat_session(force=True)
                self._add_assistant_message(self._command_session_saved_text(), render_markdown=False)
                handled = True

            elif normalized == "/sessions":
                self._add_assistant_message(self._command_sessions_text(), render_markdown=False)
                handled = True

            elif normalized.startswith("/loadsession"):
                selector = command_text[len("/loadsession"):].strip()
                self._load_chat_session_by_selector(selector)
                handled = True

            elif normalized.startswith("/deletesession"):
                selector = command_text[len("/deletesession"):].strip()
                self._delete_chat_session_by_selector(selector)
                handled = True

            elif normalized == "/help":
                self._add_assistant_message(self._command_help_text(), render_markdown=False)
                handled = True

            elif normalized == "/status":
                self._add_assistant_message(self._command_status_text(), render_markdown=False)
                handled = True

            elif normalized == "/health":
                self._add_assistant_message(self._command_health_text(), render_markdown=False)
                handled = True

            elif normalized == "/systemstatus":
                self._add_assistant_message(self._command_system_status_text(), render_markdown=False)
                handled = True

        finally:
            if handled:
                self._finish_local_command()

        return handled

    def _command_help_text(self) -> str:
        return (
            "Available commands:\n"
            "- /help: Show this command list.\n"
            "- /clear: Clear displayed chat messages only. The internal session remains.\n"
            "- /newsession: Create a new local chat session.\n"
            "- /savesession: Save the current local chat session.\n"
            "- /sessions: Show saved local chat sessions.\n"
            "- /loadsession <number|id>: Load a saved local chat session.\n"
            "- /deletesession <number|id>: Delete a saved local chat session.\n"
            "- /status: Show current desktop/session settings and a brief memory summary.\n"
            "- /health: Show backend health payload.\n"
            "- /systemstatus: Show desktop/backend CPU and memory usage."
        )

    def _command_status_text(self) -> str:
        desktop_status = get_process_status(sample_seconds=0.0)
        desktop_memory = self._format_mb(desktop_status.get("memory_rss_mb"))
        health = self.backend_client.health() or {}
        backend_process = (self.backend_client.system_status() or {}).get("process", {})
        backend_memory = self._format_mb(backend_process.get("memory_rss_mb"))
        local_ai = health.get("local_ai") if isinstance(health.get("local_ai"), dict) else {}
        cloud_ai = health.get("cloud_ai") if isinstance(health.get("cloud_ai"), dict) else {}
        cloud_available = bool(cloud_ai.get("available"))

        return "\n".join([
            "Status:",
            "",
            "App",
            f"- language: {self.settings.language}",
            f"- theme: {self.settings.theme_id}",
            f"- character: {self._character_display_name()} ({self.settings.selected_character_id})",
            f"- developer_mode: {self.settings.developer_mode}",
            "",
            "AI",
            f"- route_policy: {getattr(self.settings, 'ai_route_policy', 'auto')}",
            f"- local_model: {self.settings.local_model}",
            f"- local_ai: {local_ai.get('state', 'unknown')}",
            f"- cloud_provider: {self.settings.cloud_ai_provider}",
            f"- cloud_model: {self.settings.cloud_model or 'not selected'}",
            f"- cloud_available: {cloud_available}",
            "",
            "Session",
            f"- current_session: {self.current_session_title or self.current_session_id or 'unsaved'}",
            f"- session_id: {self.current_session_id or 'unsaved'}",
            f"- message_count: {len(self.chat_session.messages)}",
            "",
            "System",
            f"- desktop_memory: {desktop_memory}",
            f"- backend_memory: {backend_memory}",
        ])


    def _command_system_status_text(self) -> str:
        desktop_status = get_process_status(sample_seconds=0.2)
        desktop_system = get_system_overview(sample_seconds=0.0)
        backend_status = self.backend_client.system_status()

        lines = [
            "System Status:",
            "",
            "System",
            *self._format_system_overview_lines(desktop_system),
            "",
            "Desktop process",
            *self._format_process_status_lines(desktop_status),
        ]

        if backend_status is None:
            lines.extend([
                "",
                "Backend process",
                "- status: unavailable",
            ])
        else:
            backend_process = backend_status.get("process", {})
            lines.extend([
                "",
                "Backend process",
                *self._format_process_status_lines(backend_process),
            ])

            backend_system = backend_status.get("system")
            if isinstance(backend_system, dict) and not desktop_system.get("ram_total_bytes"):
                lines.extend([
                    "",
                    "Backend system snapshot",
                    *self._format_system_overview_lines(backend_system),
                ])

        total_memory = self._sum_numeric_values(
            desktop_status.get("memory_rss_mb"),
            (backend_status or {}).get("process", {}).get("memory_rss_mb"),
        )
        if total_memory is not None:
            lines.extend([
                "",
                f"Total app memory: {self._format_mb(total_memory)}",
            ])

        return "\n".join(lines)

    def _format_system_overview_lines(self, status: dict) -> list[str]:
        disk = status.get("disk") if isinstance(status.get("disk"), dict) else {}
        return [
            f"- platform: {status.get('platform', 'unknown')}",
            f"- cpu_usage: {self._format_percent(status.get('cpu_percent'))}",
            f"- cpu_count: {status.get('cpu_count', 'unknown')}",
            f"- ram_total: {self._format_bytes(status.get('ram_total_bytes'))}",
            f"- ram_used: {self._format_bytes(status.get('ram_used_bytes'))}",
            f"- ram_available: {self._format_bytes(status.get('ram_available_bytes'))}",
            f"- ram_usage: {self._format_percent(status.get('ram_percent'))}",
            f"- disk_path: {disk.get('path', 'unknown')}",
            f"- disk_total: {self._format_bytes(disk.get('total_bytes'))}",
            f"- disk_used: {self._format_bytes(disk.get('used_bytes'))}",
            f"- disk_free: {self._format_bytes(disk.get('free_bytes'))}",
            f"- disk_usage: {self._format_percent(disk.get('percent'))}",
        ]

    def _format_process_status_lines(self, status: dict) -> list[str]:
        return [
            f"- pid: {status.get('pid', 'unknown')}",
            f"- process: {status.get('process_name', 'unknown')}",
            f"- memory_rss: {self._format_mb(status.get('memory_rss_mb'))}",
            f"- memory_peak_rss: {self._format_mb(status.get('memory_peak_rss_mb'))}",
            f"- cpu_usage: {self._format_percent(status.get('cpu_percent'))}",
            f"- cpu_sample_seconds: {status.get('cpu_sample_seconds', 'unknown')}",
            f"- threads: {status.get('thread_count', 'unknown')}",
            f"- uptime_seconds: {status.get('uptime_seconds', 'unknown')}",
        ]

    def _format_mb(self, value) -> str:
        if value is None:
            return "unknown"
        try:
            return f"{float(value):.1f} MB"
        except (TypeError, ValueError):
            return str(value)

    def _format_bytes(self, value) -> str:
        if value is None:
            return "unknown"
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value)

        units = ["B", "KB", "MB", "GB", "TB"]
        unit_index = 0
        while number >= 1024.0 and unit_index < len(units) - 1:
            number /= 1024.0
            unit_index += 1

        if unit_index == 0:
            return f"{number:.0f} {units[unit_index]}"

        return f"{number:.1f} {units[unit_index]}"

    def _format_percent(self, value) -> str:
        if value is None:
            return "unknown"
        try:
            return f"{float(value):.1f}%"
        except (TypeError, ValueError):
            return str(value)

    def _sum_numeric_values(self, *values):
        total = 0.0
        found = False
        for value in values:
            try:
                if value is None:
                    continue
                total += float(value)
                found = True
            except (TypeError, ValueError):
                continue
        return round(total, 1) if found else None

    def _command_health_text(self) -> str:
        result = self.backend_client.health()
        if result is None:
            return "Health:\n- backend_process_alive: false\n- overall_ai_ready: false"

        status = result.get("status", "unknown")
        checks = result.get("checks") if isinstance(result.get("checks"), dict) else {}
        errors = result.get("errors", [])
        local_ai = result.get("local_ai") if isinstance(result.get("local_ai"), dict) else {}
        cloud_ai = result.get("cloud_ai") if isinstance(result.get("cloud_ai"), dict) else {}

        local_available = bool(local_ai.get("available") or checks.get("local_ai_available"))
        cloud_configured = bool(cloud_ai.get("configured"))
        cloud_available = bool(cloud_ai.get("available") or checks.get("cloud_ai_available"))
        selected_model_available = local_available or cloud_available
        overall_ai_ready = bool(checks.get("ai_available") or selected_model_available)

        lines = [
            "Health:",
            f"- backend_process_alive: true",
            f"- backend_status: {status}",
            f"- local_ai_available: {local_available} ({local_ai.get('state', 'unknown')})",
            f"- cloud_ai_configured: {cloud_configured}",
            f"- cloud_ai_available: {cloud_available} ({cloud_ai.get('state', 'unknown')})",
            f"- selected_model_available: {selected_model_available}",
            f"- overall_ai_ready: {overall_ai_ready}",
        ]

        if errors:
            lines.append("- errors:")
            for error in errors:
                if isinstance(error, dict):
                    code = error.get("code", "unknown")
                    message = error.get("message", "")
                    lines.append(f"  - {code}: {message}")
                else:
                    lines.append(f"  - {error}")

        return "\n".join(lines)

    def _clear_chat_display_only(self) -> None:
        self.chat_view.clear_messages()
        self.bottom_area.raise_()
        self._update_avatar_occlusion_later()

    def _restore_last_chat_session(self) -> None:
        payload = self.session_store.load_last_session()
        if payload is None:
            return

        messages = payload.get("messages") or []
        self.chat_session.replace_messages(messages)
        self.current_session_id = str(payload.get("session_id") or "") or None
        self.current_session_title = str(payload.get("title") or "")
        self.initial_notice_added = bool(messages)
        print(
            "[Session] Restored last session: "
            f"{self.current_session_title or self.current_session_id}"
        )

    def _render_current_chat_session(self) -> None:
        self.pending_response_widget = None
        if self.current_session_id != self.active_chat_response_session_id:
            self.pending_response_session_id = None
        self.chat_view.clear_messages()
        for message in self.chat_session.messages:
            self.chat_view.add_chat_message(message)
        self.bottom_area.raise_()
        self._update_avatar_occlusion_later()

    def _save_current_chat_session(
        self,
        force: bool = False,
        *,
        make_current: bool = True,
        touch_updated_at: bool = True,
    ) -> None:
        messages = self.chat_session.messages
        if not messages and not force:
            return

        self.current_session_id = self.session_store.save_session(
            self.current_session_id,
            messages,
            title=self.current_session_title or None,
            character_id=self.settings.selected_character_id,
            character_name=self._character_display_name(),
            user_name=self.settings.user_name,
            route_policy=getattr(self.settings, "ai_route_policy", "auto"),
            make_current=make_current,
            touch_updated_at=touch_updated_at,
        )

        if not self.current_session_title:
            sessions = self.session_store.list_sessions()
            for session in sessions:
                if session.get("session_id") == self.current_session_id:
                    self.current_session_title = str(session.get("title") or "")
                    break

        self._refresh_session_sidebar()

    def _refresh_session_sidebar(self) -> None:
        if not hasattr(self, "session_sidebar"):
            return
        self.session_sidebar.set_sessions(
            self.session_store.list_sessions(),
            self.current_session_id,
        )

    def _on_sidebar_new_session_requested(self) -> None:
        self._create_new_chat_session(show_message=bool(self.settings.developer_mode))
        self.character_state.on_assistant_done()

    def _on_sidebar_session_selected(self, session_id: str) -> None:
        self._load_chat_session_by_selector(
            session_id,
            show_message=bool(self.settings.developer_mode),
        )
        self.character_state.on_assistant_done()

    def _on_sidebar_session_rename_requested(self, session_id: str) -> None:
        sessions = self.session_store.list_sessions()
        current_title = "Untitled Session"
        for session in sessions:
            if session.get("session_id") == session_id:
                current_title = str(session.get("title") or current_title)
                break

        new_title, accepted = QInputDialog.getText(
            self,
            self.localization.t("app.title"),
            "세션 명칭 변경",
            text=current_title,
        )
        if not accepted:
            return

        normalized_title = " ".join(new_title.strip().split())
        if len(normalized_title.encode("utf-8")) < 2:
            QMessageBox.warning(
                self,
                self.localization.t("app.title"),
                "세션 명칭은 공백을 제외하고 최소 2바이트 이상이어야 합니다.",
            )
            return

        if self.session_store.rename_session(session_id, normalized_title):
            if session_id == self.current_session_id:
                self.current_session_title = normalized_title
            self._refresh_session_sidebar()
            if self.settings.developer_mode:
                self._add_assistant_message(
                    "Renamed local chat session.\n"
                    f"- title: {normalized_title}\n"
                    f"- session_id: {session_id}",
                    render_markdown=False,
                )
        elif self.settings.developer_mode:
            self._add_assistant_message(f"Rename failed. Session not found: {session_id}", render_markdown=False)

        self.character_state.on_assistant_done()

    def _on_sidebar_session_delete_requested(self, session_id: str) -> None:
        sessions = self.session_store.list_sessions()
        title = "Untitled Session"
        for session in sessions:
            if session.get("session_id") == session_id:
                title = str(session.get("title") or title)
                break

        result = QMessageBox.question(
            self,
            self.localization.t("app.title"),
            f'Delete local chat session?\n\n{title}\n{session_id}',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return

        self._delete_chat_session_by_selector(
            session_id,
            show_message=bool(self.settings.developer_mode),
        )
        self.character_state.on_assistant_done()

    def _create_new_chat_session(self, *, show_message: bool = True) -> None:
        self._save_current_chat_session(touch_updated_at=False)
        self.chat_session.clear()
        self.current_session_id = None
        self.current_session_title = "New Chat Session"
        self.initial_notice_added = True
        self.chat_view.clear_messages()

        if show_message:
            self._add_assistant_message("New local chat session created.", render_markdown=False)
        else:
            self._add_assistant_message("새 세션입니다.", render_markdown=False)

        # Ensure a newly created session is saved and rendered in the sidebar immediately.
        self._save_current_chat_session(force=True)
        self._refresh_session_sidebar()
        self.bottom_area.raise_()
        self._update_avatar_occlusion_later()

    def _command_session_saved_text(self) -> str:
        return (
            "Local chat session saved.\n"
            f"- session_id: {self.current_session_id or 'unsaved'}\n"
            f"- title: {self.current_session_title or 'Untitled Session'}"
        )

    def _command_sessions_text(self) -> str:
        sessions = self.session_store.list_sessions()
        if not sessions:
            return "No saved local chat sessions."

        lines = ["Saved local chat sessions:"]
        for index, session in enumerate(sessions, start=1):
            session_id = str(session.get("session_id") or "")
            title = str(session.get("title") or "Untitled Session")
            updated_at = str(session.get("updated_at") or "unknown")
            message_count = session.get("message_count", 0)
            current_marker = " *current*" if session_id == self.current_session_id else ""
            lines.append(
                f"{index}. {title}{current_marker}\n"
                f"   id: {session_id}\n"
                f"   updated: {updated_at} / messages: {message_count}"
            )
        return "\n".join(lines)

    def _load_chat_session_by_selector(self, selector: str, *, show_message: bool = True) -> None:
        session_id = self.session_store.resolve_session_selector(selector)
        if not session_id:
            self._add_assistant_message(
                "Load failed. Use /sessions first, then /loadsession <number|id>.",
                render_markdown=False,
            )
            return

        payload = self.session_store.load_session(session_id)
        if payload is None:
            self._add_assistant_message(f"Load failed. Session not found: {selector}", render_markdown=False)
            return

        self._save_current_chat_session(touch_updated_at=False)
        self.chat_session.replace_messages(payload.get("messages") or [])
        self.current_session_id = str(payload.get("session_id") or session_id)
        self.current_session_title = str(payload.get("title") or "")
        self.session_store.mark_current(self.current_session_id)
        self.initial_notice_added = bool(self.chat_session.messages)
        self._render_current_chat_session()
        if show_message:
            self._add_assistant_message(
                "Loaded local chat session.\n"
                f"- title: {self.current_session_title or 'Untitled Session'}\n"
                f"- session_id: {self.current_session_id}",
                render_markdown=False,
            )
        self._refresh_session_sidebar()

    def _delete_chat_session_by_selector(self, selector: str, show_message: bool = True) -> None:
        session_id = self.session_store.resolve_session_selector(selector)
        if not session_id:
            self._add_assistant_message(
                "Delete failed. Use /sessions first, then /deletesession <number|id>.",
                render_markdown=False,
            )
            return

        deleted = self.session_store.delete_session(session_id)
        if session_id == self.current_session_id:
            self.chat_session.clear()
            self.current_session_id = None
            self.current_session_title = ""
            self.initial_notice_added = False
            self.chat_view.clear_messages()

        if show_message:
            if deleted:
                self._add_assistant_message(f"Deleted local chat session: {session_id}", render_markdown=False)
            else:
                self._add_assistant_message(f"Session index cleaned, but file was missing: {session_id}", render_markdown=False)

        self._refresh_session_sidebar()

    def _pending_response_text(self) -> str:
        return self.localization.t("chat.pending_response")

    def _show_pending_assistant_response(self, session_id: str | None) -> None:
        if not session_id or session_id != self.current_session_id:
            return
        if self.pending_response_widget is not None:
            self.chat_view.remove_message_widget(self.pending_response_widget)
        self.pending_response_session_id = session_id
        self.pending_response_widget = self.chat_view.add_pending_assistant_message(
            self._pending_response_text()
        )
        self._update_avatar_occlusion_later()

    def _clear_pending_assistant_response(self, session_id: str | None = None) -> None:
        if session_id is not None and self.pending_response_session_id not in {None, session_id}:
            return
        if self.pending_response_widget is not None:
            self.chat_view.remove_message_widget(self.pending_response_widget)
        self.pending_response_widget = None
        if session_id is None or self.pending_response_session_id == session_id:
            self.pending_response_session_id = None

    def _show_fake_assistant_typing(self) -> None:
        if self.chat_response_thread is not None:
            self.character_state.on_assistant_typing()

    def _start_chat_response_worker(self) -> None:
        if self.chat_response_thread is not None:
            print("[Chat] Chat response request is already running.")
            return

        if self.current_session_id is None:
            self._save_current_chat_session(force=True)

        request_session_id = self.current_session_id
        if not request_session_id:
            print("[Chat] Cannot start chat response without a session id.")
            self._add_backend_fallback_response()
            return

        request = ChatRequest(
            messages=self.chat_session.messages,
            character_id=self.settings.selected_character_id,
            user_name=self.settings.user_name,
            developer_mode=self.settings.developer_mode,
            language=self.settings.language,
        )

        self.active_chat_response_session_id = request_session_id
        self.chat_response_thread = QThread(self)
        self.chat_response_worker = ChatResponseWorker(
            backend_client=self.backend_client,
            request=request,
            session_id=request_session_id,
        )
        self.chat_response_worker.moveToThread(self.chat_response_thread)

        self.chat_response_thread.started.connect(self.chat_response_worker.run)
        self.chat_response_worker.finished.connect(self._on_chat_response_finished)
        self.chat_response_worker.failed.connect(self._on_chat_response_failed)
        self.chat_response_worker.finished.connect(self._quit_chat_response_thread)
        self.chat_response_worker.failed.connect(self._quit_chat_response_thread)
        self.chat_response_thread.finished.connect(self._cleanup_chat_response_worker)

        self._show_pending_assistant_response(request_session_id)
        QTimer.singleShot(300, self._show_fake_assistant_typing)
        self.chat_response_thread.start()

    def _on_chat_response_finished(self, session_id: str, response) -> None:
        self._clear_pending_assistant_response(session_id)
        message_added = self._append_message_to_session(session_id, response.message)
        if not message_added:
            print(f"[Chat] Response target session was not found: {session_id}")

        metadata = getattr(response.message, "metadata", {}) or {}
        if metadata.get("paid_model_unavailable"):
            self.character_state.on_panic()
        elif metadata.get("error"):
            self.character_state.on_error()
        else:
            self.character_state.on_assistant_done()

        self._update_avatar_occlusion_later()

    def _on_chat_response_failed(self, session_id: str, error: str) -> None:
        self._clear_pending_assistant_response(session_id)
        print(f"[Chat] Backend chat response failed for session {session_id}: {error}")
        self._add_backend_fallback_response(session_id=session_id)

    def _quit_chat_response_thread(self, *args) -> None:  # noqa: ANN002
        if self.chat_response_thread is not None:
            self.chat_response_thread.quit()

    def _cleanup_chat_response_worker(self) -> None:
        if self.chat_response_worker is not None:
            self.chat_response_worker.deleteLater()
            self.chat_response_worker = None

        if self.chat_response_thread is not None:
            self.chat_response_thread.deleteLater()
            self.chat_response_thread = None

        self.active_chat_response_session_id = None

    def _append_message_to_session(self, session_id: str, message) -> bool:
        if not session_id:
            return False

        if session_id == self.current_session_id:
            self.chat_session.append_message(message)
            self.chat_view.add_chat_message(message)
            self._save_current_chat_session()
            return True

        payload = self.session_store.load_session(session_id)
        if payload is None:
            return False

        messages = list(payload.get("messages") or [])
        messages.append(message)
        self.session_store.save_session(
            session_id,
            messages,
            title=str(payload.get("title") or "") or None,
            character_id=str(payload.get("character_id") or self.settings.selected_character_id),
            character_name=str(payload.get("character_name") or self._character_display_name()),
            user_name=str(payload.get("user_name") or self.settings.user_name),
            route_policy=str(payload.get("route_policy") or getattr(self.settings, "ai_route_policy", "auto")),
            make_current=False,
        )
        self._refresh_session_sidebar()
        return True

    def _add_backend_fallback_response(self, session_id: str | None = None) -> None:
        target_session_id = session_id or self.current_session_id
        fallback_message = ChatMessage(
            role="assistant",
            content=self.localization.t("chat.backend_fallback"),
        )

        if target_session_id and self._append_message_to_session(target_session_id, fallback_message):
            pass
        else:
            self.chat_session.append_message(fallback_message)
            self.chat_view.add_chat_message(fallback_message)
            self._save_current_chat_session()

        self.character_state.on_error()
        QTimer.singleShot(3000, self.character_state.on_assistant_done)
        self._update_avatar_occlusion_later()

    def _update_content_geometry(self) -> None:
        if not hasattr(self, "content_area"):
            return

        area_width = self.content_area.width()
        area_height = self.content_area.height()

        self.bottom_area.sync_composer_height_to_left_name_area()

        # 하단 입력 UI가 차지하는 실제 높이.
        # composer height is synchronized with the left character/name label stack.
        input_area_height = max(132, self.bottom_area.recommended_input_area_height())

        # 캐릭터가 포함된 overlay 전체 높이.
        # 캐릭터가 잘리지 않도록 충분히 크게 잡는다.
        overlay_height = min(area_height, 430)

        # ChatView는 입력창 위에서 끝난다.
        chat_view_height = max(0, area_height - input_area_height)

        self.chat_view.setGeometry(
            0,
            0,
            area_width,
            chat_view_height,
        )

        bottom_overlay_top = max(0, area_height - overlay_height)
        self.bottom_area.setGeometry(
            0,
            bottom_overlay_top,
            area_width,
            overlay_height,
        )
        self.bottom_area.sync_composer_height_to_left_name_area()

        # 메시지 영역은 입력창 좌우 폭과 맞춘다.
        character_reserved_width = 238
        send_reserved_width = 86

        self.chat_view.set_side_reserved_widths(
            left_width=character_reserved_width,
            right_width=send_reserved_width,
        )

        # 세션 패널은 좌측 캐릭터 컬럼 전체 높이를 사용하되, 좌우 폭은
        # 캐릭터/사용자 이름 박스와 맞춘다. 배경과 테두리는 QSS에서 투명 처리한다.
        if hasattr(self, "session_sidebar"):
            character_area = self.bottom_area.character_area
            character_top_left = self.content_area.mapFromGlobal(
                character_area.mapToGlobal(character_area.rect().topLeft())
            )
            session_x = character_top_left.x()
            session_y = 0
            session_width = character_area.width()
            available_session_height = max(1, area_height)
            session_height = self.session_sidebar.preferred_height(
                available_session_height
            )
            self.session_sidebar.setGeometry(
                session_x,
                session_y,
                session_width,
                session_height,
            )

        # ChatView 자체가 이미 입력창 위까지만 있으므로 bottom viewport margin은 필요 없다.
        self.chat_view.set_bottom_reserved_height(0)

        self.chat_view.raise_()
        if hasattr(self, "session_sidebar"):
            self.session_sidebar.raise_()
        # The character/composer overlay stays visually above the session panel.
        # Mouse events over the character are handled in eventFilter so the
        # character does not block the session list by default.
        self.bottom_area.raise_()
        self._update_avatar_occlusion_later()

    def _update_avatar_occlusion_later(self) -> None:
        QTimer.singleShot(0, self._update_avatar_occlusion)

    def _update_avatar_occlusion(self) -> None:
        if not hasattr(self, "bottom_area") or not hasattr(self, "chat_view"):
            return

        if not self.settings.expand_chat_over_character_area:
            self.bottom_area.set_character_occluded(False, 1.0)
            return

        character_rect = self.bottom_area.character_global_rect()
        is_occluded = False

        for message_widget in self.chat_view.message_widgets():
            if not message_widget.isVisible():
                continue

            message_top_left = message_widget.mapToGlobal(
                message_widget.rect().topLeft()
            )
            message_rect = message_widget.rect().translated(message_top_left)

            if character_rect.intersects(message_rect):
                is_occluded = True
                break

        if not is_occluded and hasattr(self, "session_sidebar"):
            for session_item_rect in self.session_sidebar.session_item_global_rects():
                if character_rect.intersects(session_item_rect):
                    is_occluded = True
                    break

        self.bottom_area.set_character_occluded(
            is_occluded=is_occluded,
            occluded_opacity=self.settings.avatar_occluded_opacity,
        )

    def _restore_window_geometry(self) -> None:
        width = max(self.MIN_WINDOW_WIDTH, self.settings.window_width)
        height = max(self.MIN_WINDOW_HEIGHT, self.settings.window_height)

        self.resize(width, height)

    def _check_backend_health(self) -> None:
        result = self.backend_client.health()

        if result is None:
            print("[Backend] unavailable")
            return

        status = result.get("status", "unknown")
        if status != "ok":
            print(f"[Backend] health error: {result}")
            return

        print(f"[Backend] health ok: {result}")

    def _check_local_ai_model(self) -> None:
        model_name = self.settings.local_model

        if not model_name:
            print("[LocalAI] local_model is empty.")
            self._add_initial_session_notice(local_model_installed=False)
            return

        status = self.backend_client.ollama_status()

        if status is None:
            print("[LocalAI] Failed to check Ollama status.")
            self._add_initial_session_notice(local_model_installed=False)
            return

        ollama_status = status.get("status", {})
        runtime = ollama_status.get("runtime", {})
        installed = bool(runtime.get("installed"))
        server_available = bool(runtime.get("server_available"))
        local_model_installed = self._is_local_model_installed(
            ollama_status,
            model_name,
        )

        print(f"[LocalAI] Ollama status: {ollama_status}")
        self._add_initial_session_notice(local_model_installed=local_model_installed)

        # 이미 로컬 모델이 확인되었으면 다운로드/준비 확인창을 띄우지 않는다.
        if local_model_installed:
            print(f'[LocalAI] Local model "{model_name}" is already available.')
            return

        if self.settings.model_install_policy == "never":
            print("[LocalAI] model_install_policy is never.")
            return

        if not installed:
            self._handle_missing_local_ai_runtime(model_name)
            return

        if not server_available:
            print("[LocalAI] Ollama is installed but server is not available.")

        # 여기까지 온 경우만:
        # - settings.local_model 값은 있음
        # - Ollama status 조회는 됨
        # - 모델 목록에서 해당 모델을 찾지 못함
        # 따라서 이때만 모델 준비/다운로드 확인창을 띄운다.
        self._handle_local_model_prepare(model_name)
        
    def _is_local_model_installed(self, ollama_status: dict, model_name: str) -> bool:
        models = ollama_status.get("models", [])

        if not isinstance(models, list):
            return False

        normalized_target = self._normalize_ollama_model_name(model_name)

        for model in models:
            if not isinstance(model, str):
                continue

            if self._normalize_ollama_model_name(model) == normalized_target:
                return True

        return False

    def _normalize_ollama_model_name(self, model_name: str) -> str:
        normalized = model_name.strip().lower()

        if not normalized:
            return normalized

        if ":" not in normalized:
            return f"{normalized}:latest"

        return normalized

    def _handle_missing_local_ai_runtime(self, model_name: str) -> None:
        if self.settings.runtime_install_policy == "never":
            QMessageBox.warning(
                self,
                self.localization.t("app.title"),
                self.localization.t("local_ai.runtime.missing"),
            )
            return

        result = QMessageBox.question(
            self,
            self.localization.t("app.title"),
            self.localization.t("local_ai.ollama.install.confirm"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if result != QMessageBox.StandardButton.Yes:
            print("[LocalAI] User skipped Ollama installation.")
            return

        self._start_local_model_prepare_worker(
            model_name=model_name,
            auto_pull=self.settings.model_install_policy != "never",
            auto_install_runtime=True,
        )

    def _handle_local_model_prepare(self, model_name: str) -> None:
        if self.settings.model_install_policy == "never":
            return

        if self.settings.model_install_policy == "ask":
            result = QMessageBox.question(
                self,
                self.localization.t("app.title"),
                self.localization.t(
                    "local_ai.model.ensure.confirm",
                    model=model_name,
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )

            if result != QMessageBox.StandardButton.Yes:
                print("[LocalAI] User skipped model prepare.")
                return

        self._start_local_model_prepare_worker(
            model_name=model_name,
            auto_pull=True,
            auto_install_runtime=False,
        )


    def _on_settings_local_model_prepare_requested(
        self,
        model_name: str,
        auto_pull: bool,
        auto_install_runtime: bool,
        auto_start_server: bool,
        timeout_seconds: float,
    ) -> None:
        self._start_local_model_prepare_worker(
            model_name=model_name,
            auto_pull=auto_pull,
            auto_install_runtime=auto_install_runtime,
            auto_start_server=auto_start_server,
            timeout_seconds=timeout_seconds,
        )


    def _on_settings_local_model_delete_requested(
        self,
        model_name: str,
        auto_start_server: bool,
    ) -> None:
        result = self.backend_client.delete_ollama_model(
            model=model_name,
            auto_start_server=auto_start_server,
            timeout_seconds=30.0,
        )

        if result is None:
            QMessageBox.warning(
                self,
                self.localization.t("app.title"),
                self.localization.t(
                    "local_ai.model.delete.failed",
                    error=self._local_ai_error_message("request_failed"),
                ),
            )
            return

        if not result.get("success"):
            error_code = str(result.get("error_code") or "unknown")
            QMessageBox.warning(
                self,
                self.localization.t("app.title"),
                self.localization.t(
                    "local_ai.model.delete.failed",
                    error=self._local_ai_error_message(error_code),
                ),
            )
            return

        if result.get("deleted"):
            QMessageBox.information(
                self,
                self.localization.t("app.title"),
                self.localization.t(
                    "local_ai.model.delete.completed",
                    model=result.get("model") or model_name,
                ),
            )
        else:
            QMessageBox.information(
                self,
                self.localization.t("app.title"),
                self.localization.t(
                    "local_ai.model.delete.not_installed",
                    model=result.get("model") or model_name,
                ),
            )


    def _on_settings_local_model_list_requested(
        self,
        auto_start_server: bool,
    ) -> None:
        # Refresh the installed model cache so that the list reflects the
        # latest installed models. This avoids stale data when models are
        # downloaded or removed. If refreshing fails, we proceed with the
        # existing cache. We still call list_ollama_models to obtain
        # additional metadata such as size and modified date when available.
        try:
            refreshed_names = self._refresh_installed_models(
                auto_start_server=auto_start_server
            )
        except Exception:
            refreshed_names = self._installed_models_cache

        result = self.backend_client.list_ollama_models(
            auto_start_server=auto_start_server,
            timeout_seconds=15.0,
        )

        if result is None or not result.get("success"):
            # If the backend call fails, fall back to showing the cached
            # model names without sizes or dates.
            if not refreshed_names:
                message = self.localization.t("local_ai.model.list.empty")
            else:
                lines = [f"- {name}" for name in refreshed_names]
                message = self.localization.t(
                    "local_ai.model.list.result",
                    count=len(lines),
                    models="\n".join(lines),
                )
            QMessageBox.information(
                self,
                self.localization.t("app.title"),
                message,
            )
            return

        models = result.get("models") or []
        if not models:
            message = self.localization.t("local_ai.model.list.empty")
        else:
            lines: list[str] = []
            for model in models:
                if not isinstance(model, dict):
                    continue
                name = str(model.get("name") or model.get("model") or "unknown")
                size_val = model.get("size")
                size_str = self._format_bytes(size_val) if size_val else ""
                modified_at = str(model.get("modified_at") or "")
                if size_str and modified_at:
                    lines.append(f"- {name} / {size_str} / {modified_at}")
                else:
                    lines.append(f"- {name}")

            message = self.localization.t(
                "local_ai.model.list.result",
                count=len(lines),
                models="\n".join(lines),
            )

        QMessageBox.information(
            self,
            self.localization.t("app.title"),
            message,
        )


    def _start_local_model_prepare_worker(
        self,
        model_name: str,
        auto_pull: bool,
        auto_install_runtime: bool,
        auto_start_server: bool | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        if self.local_model_prepare_thread is not None:
            QMessageBox.information(
                self,
                self.localization.t("app.title"),
                self.localization.t("local_ai.model.prepare.already_running"),
            )
            return
        
        self.character_state.on_assistant_typing()
        self.bottom_area.set_state_text(
            self.localization.t(
                "local_ai.model.download.progress",
                progress=0,
            )
        )

        if auto_start_server is None:
            auto_start_server = self.settings.auto_start_local_ai_server

        if timeout_seconds is None:
            timeout_seconds = float(self.settings.model_download_timeout_seconds)

        self.local_model_prepare_thread = QThread(self)
        self.local_model_prepare_worker = LocalModelPrepareWorker(
            backend_client=self.backend_client,
            model=model_name,
            auto_pull=auto_pull,
            auto_install_runtime=auto_install_runtime,
            auto_start_server=auto_start_server,
            timeout_seconds=timeout_seconds,
        )

        self.local_model_prepare_worker.moveToThread(
            self.local_model_prepare_thread
        )

        self.local_model_prepare_thread.started.connect(
            self.local_model_prepare_worker.run
        )
        self.local_model_prepare_worker.finished.connect(
            self._on_local_model_prepare_finished
        )
        self.local_model_prepare_worker.failed.connect(
            self._on_local_model_prepare_failed
        )
        self.local_model_prepare_worker.progress.connect(
            self._on_local_model_prepare_progress
        )

        self.local_model_prepare_worker.finished.connect(
            self.local_model_prepare_thread.quit
        )
        self.local_model_prepare_worker.failed.connect(
            self.local_model_prepare_thread.quit
        )
        self.local_model_prepare_thread.finished.connect(
            self._cleanup_local_model_prepare_worker
        )

        self.local_model_prepare_thread.start()


    def _on_local_model_prepare_progress(self, payload: dict) -> None:
        progress = payload.get("progress")

        if isinstance(progress, (int, float)):
            progress_value = int(max(0, min(100, round(progress))))
            self.bottom_area.set_state_text(
                self.localization.t(
                    "local_ai.model.download.progress",
                    progress=progress_value,
                )
            )
            return

        status = str(payload.get("status") or "").strip()
        if status:
            self.bottom_area.set_state_text(
                self.localization.t(
                    "local_ai.model.download.progress.status",
                    status=status,
                )
            )
        else:
            self.bottom_area.set_state_text(
                self.localization.t(
                    "local_ai.model.download.progress",
                    progress=0,
                )
            )

    def _on_local_model_prepare_finished(self, result: dict) -> None:
        print(f"[LocalAI] Prepare model result: {result}")

        if not result.get("success"):
            model_payload = result.get("model", {})
            error_code = (
                model_payload.get("error_code")
                or result.get("error_code")
                or "unknown"
            )

            QMessageBox.warning(
                self,
                self.localization.t("app.title"),
                self.localization.t(
                    "local_ai.model.prepare.failed",
                    error=self._local_ai_error_message(str(error_code)),
                ),
            )
            self.character_state.on_assistant_done()
            return

        model_payload = result.get("model", {})
        model_name = model_payload.get("model") or self.settings.local_model

        if model_payload.get("pulled"):
            QMessageBox.information(
                self,
                self.localization.t("app.title"),
                self.localization.t(
                    "local_ai.model.download.completed",
                    model=model_name,
                ),
            )
        else:
            print(f'[LocalAI] Model "{model_name}" is already available.')

        self.character_state.on_assistant_done()

        # If the prepare succeeded, refresh the list of installed models so
        # that any newly installed model appears in the settings dialog and
        # other parts of the UI. Do not auto-start the server here, as it
        # should already be running. If the refresh fails, we ignore the
        # error and keep the existing cache.
        if result.get("success"):
            try:
                self._refresh_installed_models(auto_start_server=False)
            except Exception:
                pass

    def _on_local_model_prepare_failed(self, error_code: str) -> None:
        QMessageBox.warning(
            self,
            self.localization.t("app.title"),
            self.localization.t(
                "local_ai.model.prepare.failed",
                error=self._local_ai_error_message(error_code),
            ),
        )

        self.character_state.on_assistant_done()

    def _cleanup_local_model_prepare_worker(self) -> None:
        if self.local_model_prepare_worker is not None:
            self.local_model_prepare_worker.deleteLater()
            self.local_model_prepare_worker = None

        if self.local_model_prepare_thread is not None:
            self.local_model_prepare_thread.deleteLater()
            self.local_model_prepare_thread = None

    def _refresh_installed_models(self, auto_start_server: bool = True) -> list[str]:
        """
        Refresh the list of installed local AI models by querying the backend.
        Updates the internal cache and returns the list of model identifiers.

        The Ollama API may return both a base name (e.g. `exaone2.5`) and a
        full identifier including version or quantisation suffix (e.g.
        `exaone2.5:7b`). To ensure that all variants can be selected, both
        forms are added to the list. Duplicate strings are removed while
        preserving order. If the query fails, the previous cache is returned.

        Args:
            auto_start_server: Whether to start the local AI server to
                enumerate models. If False, enumeration will fail if the
                server is not already running.

        Returns:
            A list of installed model names.
        """
        names: list[str] = []
        try:
            result = self.backend_client.list_ollama_models(
                auto_start_server=auto_start_server,
                timeout_seconds=15.0,
            )
            if result and result.get("success"):
                for model in result.get("models") or []:
                    if not isinstance(model, dict):
                        continue
                    full_identifier = str(model.get("model") or "").strip()
                    base_name = str(model.get("name") or "").strip()
                    # Include both full identifier and base name to expose
                    # version-specific models and the base model name.
                    if full_identifier:
                        names.append(full_identifier)
                    if base_name and base_name != full_identifier:
                        names.append(base_name)
        except Exception as exc:
            # On failure, do not clear the cache; return it as is.
            print(f"[LocalAI] Failed to refresh installed models: {exc}")
            return self._installed_models_cache
        # Deduplicate while preserving order
        seen: set[str] = set()
        refreshed: list[str] = []
        for n in names:
            if n and n not in seen:
                refreshed.append(n)
                seen.add(n)
        # Always ensure the currently configured local model is in the list
        current = getattr(self.settings, "local_model", "").strip()
        if current and current not in refreshed:
            refreshed.insert(0, current)
        self._installed_models_cache = refreshed
        return refreshed

    def _schedule_local_model_update_timer(self) -> None:
        """
        Set up or cancel the timer that periodically checks for updates to the
        installed local AI model. The timer interval is derived from the
        settings and clamped between 1 and 60 days. If update checks are
        disabled, any existing timer is stopped and removed. When enabled,
        the timer will immediately trigger a check and then repeat at the
        configured interval. This function should be called whenever the
        settings change.
        """
        # Stop and clean up any existing timer
        if hasattr(self, "_local_model_update_timer") and self._local_model_update_timer:
            try:
                self._local_model_update_timer.stop()
                self._local_model_update_timer.timeout.disconnect()
                self._local_model_update_timer.deleteLater()
            except Exception:
                pass
            self._local_model_update_timer = None

        # Determine whether update checks are enabled and obtain the interval
        if not getattr(self.settings, "local_model_update_check_enabled", False):
            return

        interval_days = getattr(self.settings, "local_model_update_check_interval_days", 7)
        try:
            interval_days = int(interval_days)
        except Exception:
            interval_days = 7
        interval_days = max(1, min(60, interval_days))
        interval_ms = int(interval_days * 24 * 60 * 60 * 1000)

        # Create a repeating timer; connect to the update handler
        timer = QTimer(self)
        timer.setInterval(interval_ms)
        timer.setSingleShot(False)
        timer.timeout.connect(self._on_local_model_update_timer)
        self._local_model_update_timer = timer
        timer.start()

        # Determine whether an immediate check is required based on when
        # the last update check was performed. If the last checked timestamp
        # is missing or the interval has elapsed since then, schedule an
        # immediate check; otherwise, rely on the timer to fire after the
        # appropriate delay. Any parsing errors result in an immediate
        # check to avoid missing potential updates.
        try:
            from datetime import datetime
            last_checked_str = getattr(self.settings, "local_model_update_last_checked_at", "")
            immediate = False
            if not last_checked_str:
                immediate = True
            else:
                last_checked = datetime.fromisoformat(last_checked_str)
                now = datetime.now()
                elapsed_days = (now - last_checked).total_seconds() / (24 * 60 * 60)
                if elapsed_days >= interval_days:
                    immediate = True
            if immediate:
                QTimer.singleShot(0, self._on_local_model_update_timer)
        except Exception:
            QTimer.singleShot(0, self._on_local_model_update_timer)

    def _on_local_model_update_timer(self) -> None:
        """
        Invoked periodically by the update timer to check whether a newer version
        of the currently installed local model may be available. The user is
        prompted to confirm the update. If confirmed, the model prepare
        workflow is initiated with auto_pull enabled. After the check, the
        last_checked timestamp is updated and saved.
        """
        # Do not start an update while a model prepare worker is already running
        if self.local_model_prepare_thread is not None:
            return

        # Only proceed if a local model is configured
        model_name = getattr(self.settings, "local_model", "").strip()
        if not model_name:
            return

        # Ask the user whether to update. If the translation key is missing,
        # fall back to a sensible default string.
        prompt = self.localization.t("local_ai.model.update.prompt")
        if not prompt or prompt.startswith("{"):
            prompt = "A new version of the local AI model may be available. Would you like to update?"
        result = QMessageBox.question(
            self,
            self.localization.t("app.title"),
            prompt,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if result == QMessageBox.StandardButton.Yes:
            # Trigger a model prepare with auto_pull enabled. Avoid auto
            # installation of the runtime to reduce unexpected changes.
            self._start_local_model_prepare_worker(
                model_name=model_name,
                auto_pull=True,
                auto_install_runtime=False,
            )

        # Update the last checked timestamp and persist the settings. The
        # digest is not updated here because the current implementation does
        # not retrieve remote digests. When full update detection is
        # implemented, this value should be updated accordingly.
        try:
            from datetime import datetime
            now_str = datetime.now().isoformat()
            self.settings.local_model_update_last_checked_at = now_str
            self.settings_repository.save(self.settings)
        except Exception:
            pass

    def _local_ai_error_message(self, error_code: str) -> str:
        key = f"local_ai.error.{error_code}"
        text = self.localization.t(key)

        if text == f"{{{key}}}":
            return error_code

        return text

    def eventFilter(self, watched, event) -> bool:
        event_type = event.type()

        if event_type in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            self._update_character_mouse_event_mode_from_keyboard(event)
            return False

        if event_type == QEvent.Type.WindowDeactivate:
            self._set_character_mouse_events_enabled(False)
            return False

        if event_type == QEvent.Type.MouseButtonPress:
            if watched is getattr(self, "title_label", None) and event.button() == Qt.MouseButton.LeftButton:
                self._show_about_dialog()
                return True

            if self._is_bottom_overlay_mouse_event_target(watched):
                if self._handle_bottom_overlay_mouse_press(watched, event):
                    return True

            if self._is_character_mouse_event_target(watched):
                if self._handle_character_mouse_press(event):
                    return True

        if event_type == QEvent.Type.Wheel:
            if self._should_forward_wheel_to_chat_view(watched):
                self._scroll_chat_view_by_wheel(event)
                return True

        return super().eventFilter(watched, event)

    def _update_character_mouse_event_mode_from_keyboard(self, event) -> None:  # noqa: ANN001
        # Qt maps macOS Option to AltModifier. Command/Meta is intentionally not
        # accepted. The character layer becomes a mouse target only while Alt /
        # Option is actively held.
        try:
            is_alt_event = event.key() == Qt.Key.Key_Alt
        except AttributeError:
            is_alt_event = False

        alt_pressed = bool(QApplication.keyboardModifiers() & Qt.KeyboardModifier.AltModifier)

        if event.type() == QEvent.Type.KeyPress and is_alt_event:
            alt_pressed = True
        elif event.type() == QEvent.Type.KeyRelease and is_alt_event:
            alt_pressed = False

        self._set_character_mouse_events_enabled(alt_pressed)

    def _set_character_mouse_events_enabled(self, enabled: bool) -> None:
        if not hasattr(self, "bottom_area"):
            return

        enabled = bool(enabled)
        if getattr(self, "_character_mouse_events_enabled", None) == enabled:
            return

        self._character_mouse_events_enabled = enabled
        self.bottom_area.character_area.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            not enabled,
        )

    def _is_character_mouse_event_target(self, watched) -> bool:  # noqa: ANN001
        if not hasattr(self, "bottom_area"):
            return False

        widget = watched if isinstance(watched, QWidget) else None
        while widget is not None:
            if widget is self.bottom_area.character_area:
                return True
            widget = widget.parentWidget()

        return False

    def _is_bottom_overlay_mouse_event_target(self, watched) -> bool:  # noqa: ANN001
        if not hasattr(self, "bottom_area"):
            return False

        widget = watched if isinstance(watched, QWidget) else None
        while widget is not None:
            if widget is self.bottom_area:
                return True
            widget = widget.parentWidget()

        return False

    def _is_overlay_control_widget(self, watched) -> bool:  # noqa: ANN001
        if not hasattr(self, "bottom_area"):
            return False

        widget = watched if isinstance(watched, QWidget) else None
        while widget is not None:
            if widget is self.bottom_area.composer or widget is self.bottom_area.send_button:
                return True
            if widget is self.bottom_area:
                return False
            widget = widget.parentWidget()

        return False

    def _handle_bottom_overlay_mouse_press(self, watched, event) -> bool:  # noqa: ANN001
        if event.button() != Qt.MouseButton.LeftButton:
            return False

        # Composer and send button are real controls and must keep their own
        # mouse handling. Only the visual overlay area is pass-through/routed.
        if self._is_overlay_control_widget(watched):
            return False

        # Alt/Option deliberately activates the character click target. In that
        # mode the character may consume the event instead of passing it through.
        if (
            self._is_character_mouse_event_target(watched)
            and getattr(self, "_character_mouse_events_enabled", False)
        ):
            return self._handle_character_mouse_press(event)

        global_pos = self._event_global_pos(event)

        # Session list gets priority because it is visually placed over the
        # character column. This keeps row selection working when the avatar
        # overlaps it.
        if hasattr(self, "session_sidebar") and self.session_sidebar.handle_global_mouse_press(global_pos):
            return True

        # Copy/regenerate buttons may be visually under the transparent bottom
        # overlay. Route by global coordinates only from overlay handling so a
        # normal button click cannot be fired twice.
        if hasattr(self, "chat_view") and self.chat_view.handle_global_action_mouse_press(global_pos):
            return True

        return False

    def _handle_character_mouse_press(self, event) -> bool:  # noqa: ANN001
        if not getattr(self, "_character_mouse_events_enabled", False):
            return False

        if event.button() != Qt.MouseButton.LeftButton:
            return False

        # Test hook for later character interaction handling. Holding Alt/Option
        # enables the character layer to consume mouse input; the click then
        # behaves as if the user sent this action message.
        self.on_send_requested(self._character_click_text)
        return True

    def _event_global_pos(self, event) -> QPoint:  # noqa: ANN001
        try:
            return event.globalPosition().toPoint()
        except AttributeError:
            return event.globalPos()

    def _should_forward_wheel_to_chat_view(self, watched) -> bool:
        if not hasattr(self, "bottom_area"):
            return False

        if watched is self.bottom_area.composer:
            return False

        if watched is self.bottom_area.send_button:
            return False

        widget = watched if isinstance(watched, QWidget) else None
        if widget is None:
            return False

        current = widget
        while current is not None:
            if current is self.bottom_area:
                return True
            current = current.parentWidget()

        return False

    def _scroll_chat_view_by_wheel(self, event) -> None:
        if not hasattr(self, "chat_view"):
            return

        scroll_bar = self.chat_view.verticalScrollBar()
        delta_y = event.angleDelta().y()

        if delta_y == 0:
            return

        # Qt wheel delta는 보통 120 단위.
        # 값이 너무 작으면 답답하고, 너무 크면 튀니까 3배 정도로 보정.
        step = scroll_bar.singleStep() * 3

        if delta_y > 0:
            scroll_bar.setValue(scroll_bar.value() - step)
        else:
            scroll_bar.setValue(scroll_bar.value() + step)
    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_content_geometry()

    def closeEvent(self, event) -> None:
        self._save_current_chat_session()
        self.settings.window_width = self.width()
        self.settings.window_height = self.height()
        self.settings_repository.save(self.settings)

        super().closeEvent(event)