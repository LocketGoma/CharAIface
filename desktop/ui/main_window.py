from datetime import datetime, timedelta
import sys
from pathlib import Path
from uuid import uuid4
from shared.schema.chat import ChatMessage, ChatRequest
from shared.file_intake import (
    render_attached_file_handling_hint,
    render_inline_data_handling_hint,
)
from shared.file_types import file_dialog_filter
from shared.runtime_paths import (
    app_data_path,
    character_data_root,
    ensure_app_data_dirs,
    resource_path,
    runtime_root,
)
from desktop.chat.chat_session import ChatSession
from desktop.chat.session_store import ChatSessionStore
from desktop.client.backend_http_client import BackendHttpClient
from desktop.workers.local_model_prepare_worker import LocalModelPrepareWorker
from desktop.workers.chat_response_worker import ChatResponseWorker
from PySide6.QtCore import QEvent, QPoint, Qt, QThread, QTimer
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QInputDialog,
    QFileDialog,
    QMessageBox,
    QPushButton,
    QMenu,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from desktop.characters.character_pack import CharacterPack
from desktop.characters.character_registry import CharacterRegistry
from desktop.core.chat_exporter import (
    ChatExportError,
    default_chat_export_filename,
    export_chat_session,
    export_text_content,
    extract_csv_like_content,
)
from desktop.core.character_state import CharacterStateController
from desktop.core.export_filename_parser import parse_manual_export_filename
from desktop.core.file_reader import (
    FileReadError,
    FileReadResult,
    build_file_context_message,
    build_inline_csv_context_message,
    read_file_for_chat,
)
from desktop.core.manual_export_parser import (
    is_manual_message_export_request,
    manual_export_suffix,
    should_extract_csv_like_content,
)
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
from desktop.ui.setup_wizard_dialog import SetupWizardDialog
from desktop.ui.session_sidebar import SessionSidebar


CHAT_RESPONSE_STATE_RULES = {
    "panic": ("paid_model_unavailable", "panic"),
    "error": ("error",),
}

CHAT_RESPONSE_STATE_HANDLERS = {
    "panic": "on_panic",
    "error": "on_error",
    "assistant_done": "on_assistant_done",
}

CHAT_RESPONSE_GENERATING_SECONDS = 20
CHAT_RESPONSE_LONG_WAIT_SECONDS = 60
APP_NOTICE_METADATA_KEY = "app_notice_key"
INITIAL_NOTICE_KEYS = (
    "chat.initial_notice.model_required",
    "chat.initial_notice.new_session",
)


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
        self._character_resources_missing = False
        self.local_model_prepare_thread: QThread | None = None
        self.local_model_prepare_worker: LocalModelPrepareWorker | None = None
        self.chat_response_thread: QThread | None = None
        self.chat_response_worker: ChatResponseWorker | None = None
        self.active_chat_response_session_id: str | None = None
        self.active_chat_response_request_id: str | None = None
        self.chat_response_threads: dict[str, QThread] = {}
        self.chat_response_workers: dict[str, ChatResponseWorker] = {}
        self.chat_response_request_sessions: dict[str, str] = {}
        self.cancelled_chat_response_request_ids: set[str] = set()
        self._chat_response_display_metadata: dict[str, tuple[str, dict]] = {}
        self._chat_response_started_at: datetime | None = None
        self._chat_response_elapsed_timer = QTimer(self)
        self._chat_response_elapsed_timer.setInterval(1000)
        self._chat_response_elapsed_timer.timeout.connect(
            self._update_chat_response_elapsed_status
        )
        self.pending_response_session_id: str | None = None
        self.pending_response_widget = None
        self.initial_notice_added = False
        ensure_app_data_dirs()
        self.session_store = ChatSessionStore(
            app_data_path("chat_sessions")
        )
        self.chat_session = ChatSession()
        self.pending_file_attachment: FileReadResult | None = None
        self.current_session_id: str | None = None
        self.current_session_title: str = ""
        self.backend_client = BackendHttpClient()
        self._restore_last_chat_session()

        # Timer for periodic local model update checks. It is initialised in
        # _schedule_local_model_update_timer when settings indicate that
        # update checks are enabled. The timer is restarted whenever the
        # settings change via the settings dialog.
        self._local_model_update_timer: QTimer | None = None
        self._active_settings_dialog: SettingsDialog | None = None
        self._setup_wizard_active = False
        self._startup_local_ai_check_done = False
        self._tray_icon: QSystemTrayIcon | None = None
        self._tray_menu: QMenu | None = None
        self._force_quit_requested = False

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
        self._setup_tray_icon()
        self.retranslate_ui()
        QTimer.singleShot(0, self._restore_window_geometry)
        QTimer.singleShot(100, self._check_backend_health)
        QTimer.singleShot(300, self._show_setup_wizard_if_needed)
        QTimer.singleShot(1200, self._check_local_ai_model)

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
        self.chat_view.set_message_font(self.settings.chat_font_family, self.settings.chat_font_size)
        self.chat_view.set_typewriter_interval_ms(self.settings.typewriter_interval_ms)
        self.chat_view.set_developer_mode(self.settings.developer_mode)
        self.chat_view.setParent(self.content_area)

        self.session_sidebar = SessionSidebar(
            localization=self.localization,
            parent=self.content_area,
        )
        self.session_sidebar.new_session_requested.connect(
            self._on_sidebar_new_session_requested
        )
        self.session_sidebar.refresh_requested.connect(
            self._refresh_session_sidebar
        )
        self.session_sidebar.session_selected.connect(
            self._on_sidebar_session_selected
        )
        self.session_sidebar.session_export_requested.connect(
            self._on_export_chat_requested
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
        self._character_click_text = self.localization.t("chat.character_click_text")
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
        self.bottom_area.cancel_requested.connect(
            self._on_chat_response_cancel_requested
        )
        self.bottom_area.file_attach_requested.connect(
            self._on_file_attach_requested
        )
        self.bottom_area.file_attachment_cancel_requested.connect(
            self._clear_pending_file_attachment
        )
        self.bottom_area.text_changed.connect(self.character_state.on_user_text_changed)
        self.character_state.state_changed.connect(self.bottom_area.set_state)
        self.chat_view.regenerate_requested.connect(self._on_regenerate_requested)
        self.chat_view.cancel_response_requested.connect(
            self._on_chat_response_cancel_requested
        )
        self.chat_view.assistant_message_display_finished.connect(
            self._finish_chat_response_display
        )

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
        project_root = runtime_root()

        builtin_characters_dir = project_root / "resources" / "builtin"
        user_characters_dir = character_data_root()

        additional_user_characters_dirs = [
            project_root / "resources" / "characters",
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
        self._character_resources_missing = False
        self.settings.selected_character_id = character_pack.id

        self.bottom_area.set_character_name(self._character_pack_display_name(character_pack))
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
            f"{self._character_pack_display_name(character_pack)} ({character_pack.id}) [{source}]"
        )

    def _show_missing_default_character_warning(self) -> None:
        message = self.localization.t("character.default_missing")
        was_missing = self._character_resources_missing
        if not was_missing:
            print(f"[CharacterRegistry] {message}")

        self.current_character_pack = None
        self._character_resources_missing = True
        if hasattr(self, "bottom_area"):
            self.bottom_area.set_character_name(message)
            self.bottom_area.set_avatar_images({})
            self.bottom_area.set_state_text(message)
        self._update_chat_view_display_names()


    def _local_model_name_from_payload(self, model_payload: dict) -> str:
        return str(
            model_payload.get("model")
            or model_payload.get("name")
            or ""
        ).strip()

    def _local_model_names_from_list_result(self, result: dict | None) -> list[str]:
        if not result or not result.get("success"):
            return []

        model_names: list[str] = []
        seen: set[str] = set()

        for model in result.get("models") or []:
            if not isinstance(model, dict):
                continue

            model_name = self._local_model_name_from_payload(model)
            if not model_name:
                continue

            key = self._normalize_ollama_model_name(model_name)
            if key in seen:
                continue

            model_names.append(model_name)
            seen.add(key)

        return model_names

    def _fetch_installed_local_model_names(self, auto_start_server: bool) -> list[str]:
        try:
            result = self.backend_client.list_ollama_models(
                auto_start_server=auto_start_server,
                timeout_seconds=15.0,
            )
            return self._local_model_names_from_list_result(result)
        except Exception as exc:
            print(f"[Settings] Failed to list installed models: {exc}")
            return []

    def _refresh_active_settings_local_models(
        self,
        model_names: list[str],
        preferred_model: str | None = None,
    ) -> None:
        dialog = self._active_settings_dialog
        if dialog is None:
            return

        try:
            dialog.refresh_installed_local_models(model_names, preferred_model=preferred_model)
        except RuntimeError:
            self._active_settings_dialog = None

    def open_settings_dialog(self) -> None:
        if self.character_registry is None:
            print("[Settings] CharacterRegistry is not initialized.")
            return

        dialog = SettingsDialog(
            settings=self.settings.model_copy(deep=True),
            localization=self.localization,
            theme_manager=self.theme_manager,
            character_registry=self.character_registry,
            installed_models=[],
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

        self._active_settings_dialog = dialog
        try:
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
        finally:
            if self._active_settings_dialog is dialog:
                self._active_settings_dialog = None

    def _show_setup_wizard_if_needed(self) -> None:
        if self.settings.setup_wizard_completed:
            return
        self.open_setup_wizard(required=True)

    def open_setup_wizard(self, *, required: bool = False) -> None:
        if self._setup_wizard_active:
            return

        dialog = SetupWizardDialog(
            settings=self.settings.model_copy(deep=True),
            localization=self.localization,
            parent=self,
        )

        self._setup_wizard_active = True
        try:
            accepted = bool(dialog.exec())
            new_settings = dialog.settings

            if accepted:
                dialog.apply_to_settings()
                new_settings = dialog.settings
            elif required:
                new_settings.setup_wizard_completed = True

            if accepted or required:
                self._apply_settings(new_settings)
                QTimer.singleShot(100, self._check_local_ai_model)
        finally:
            self._setup_wizard_active = False

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
            self.chat_view.set_message_font(self.settings.chat_font_family, self.settings.chat_font_size)
            self.chat_view.set_typewriter_interval_ms(self.settings.typewriter_interval_ms)
            self.chat_view.set_developer_mode(self.settings.developer_mode)

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
        self._render_current_chat_session()

        self.settings_repository.save(self.settings)
        self._setup_tray_icon()
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
                        character_name=self._character_pack_display_name(character_pack),
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
        self.chat_view.set_action_texts(
            copy_text=self.localization.t("chat.action.copy"),
            regenerate_text=self.localization.t("chat.action.regenerate"),
            cancel_response_text=self.localization.t("chat.action.stop_thinking"),
            paid_model_label=self.localization.t("chat.paid_model_label"),
        )
        self._character_click_text = self.localization.t("chat.character_click_text")
        if hasattr(self, "session_sidebar"):
            self.session_sidebar.retranslate_ui()
            self._refresh_session_sidebar()
        self.bottom_area.retranslate_ui()
        if self._character_resources_missing:
            self._show_missing_default_character_warning()
        self.bottom_area.set_user_name(self.settings.user_name)
        if self.current_character_pack is not None:
            self.bottom_area.set_character_name(
                self._character_pack_display_name(self.current_character_pack)
            )
        self._update_chat_response_elapsed_status()
        self._update_chat_view_display_names()
        if self._tray_icon is not None:
            self._setup_tray_icon()

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

    def _on_file_attach_requested(self) -> None:
        selected_path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            self.localization.t("chat.file.attach.title"),
            str(Path.home() / "Documents"),
            file_dialog_filter(),
        )
        if not selected_path:
            return

        try:
            attachment = read_file_for_chat(selected_path)
        except FileReadError as error:
            QMessageBox.warning(
                self,
                self.localization.t("chat.file.attach.title"),
                self.localization.t(
                    "chat.file.attach.failed",
                    error=self._file_read_error_message(error),
                ),
            )
            return

        self.pending_file_attachment = attachment
        self.bottom_area.set_attached_file_name(
            self.localization.t(
                "chat.file.attached",
                name=attachment.name,
            ),
            detail=attachment.display_detail,
        )
        self._update_content_geometry()

    def _clear_pending_file_attachment(self) -> None:
        self.pending_file_attachment = None
        if hasattr(self, "bottom_area"):
            self.bottom_area.set_attached_file_name(None)
            self._update_content_geometry()

    def _file_read_error_message(self, error: FileReadError) -> str:
        code = getattr(error, "code", "read_failed")
        detail = str(getattr(error, "detail", "") or str(error))
        key = f"chat.file.error.{code}"
        localized = self.localization.t(key, detail=detail)
        if localized != f"{{{key}}}":
            return localized
        return str(error)

    def _on_export_chat_requested(self, session_id: str | None = None) -> None:
        payload = None
        if session_id:
            payload = self.session_store.load_session(session_id)
            if payload is None:
                QMessageBox.warning(
                    self,
                    self.localization.t("chat.export.title"),
                    self.localization.t("chat.export.session_missing"),
                )
                return

        messages = (
            list(payload.get("messages") or [])
            if payload is not None
            else self.chat_session.messages
        )
        if not messages:
            QMessageBox.information(
                self,
                self.localization.t("chat.export.title"),
                self.localization.t("chat.export.empty"),
            )
            return

        export_title = (
            str(payload.get("title") or "").strip()
            if payload is not None
            else self.current_session_title
        ) or self.localization.t("chat.export.default_title")
        default_name = default_chat_export_filename(export_title)
        default_path = str(Path.home() / "Documents" / f"{default_name}.md")
        selected_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            self.localization.t("chat.export.title"),
            default_path,
            "Markdown (*.md);;Text (*.txt);;CSV (*.csv);;PDF (*.pdf)",
        )

        if not selected_path:
            return

        export_path = self._export_path_with_suffix(selected_path, selected_filter)

        try:
            export_chat_session(
                export_path,
                messages,
                title=export_title,
                role_labels={
                    "system": self.localization.t("chat.export.role.system"),
                    "user": self.settings.user_name
                    or self.localization.t("chat.export.role.user"),
                    "assistant": self._character_display_name(),
                    "tool": self.localization.t("chat.export.role.tool"),
                },
            )
        except ChatExportError as error:
            QMessageBox.warning(
                self,
                self.localization.t("chat.export.title"),
                self.localization.t("chat.export.failed", error=str(error)),
            )
            return
        except Exception as error:
            QMessageBox.warning(
                self,
                self.localization.t("chat.export.title"),
                self.localization.t("chat.export.failed", error=str(error)),
            )
            return

        QMessageBox.information(
            self,
            self.localization.t("chat.export.title"),
            self.localization.t("chat.export.completed", path=str(export_path)),
        )

    def _export_path_with_suffix(self, selected_path: str, selected_filter: str) -> Path:
        export_path = Path(selected_path)
        if export_path.suffix.lower() in {".txt", ".md", ".csv", ".pdf"}:
            return export_path

        if "*.txt" in selected_filter:
            return export_path.with_suffix(".txt")
        if "*.csv" in selected_filter:
            return export_path.with_suffix(".csv")
        if "*.pdf" in selected_filter:
            return export_path.with_suffix(".pdf")
        return export_path.with_suffix(".md")

    def _application_display_name(self) -> str:
        app_name = self.localization.t("app.title")

        if app_name == "{app.title}":
            return "CharAIface"

        return app_name

    def _character_display_name(self) -> str:
        if self.current_character_pack is not None:
            return self._character_pack_display_name(self.current_character_pack)

        return "Assistant"

    def _character_pack_display_name(self, pack: CharacterPack) -> str:
        return pack.display_name(self.settings.language)

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
            ),
            metadata={APP_NOTICE_METADATA_KEY: key},
        )
        self.initial_notice_added = True

    def _localized_app_notice_message(self, message: ChatMessage) -> ChatMessage:
        key = self._app_notice_key_for_message(message)
        if key is None:
            return message

        metadata = dict(message.metadata or {})
        metadata[APP_NOTICE_METADATA_KEY] = key
        return message.model_copy(
            update={
                "content": self._localized_initial_notice_text(key),
                "metadata": metadata,
            }
        )

    def _app_notice_key_for_message(self, message: ChatMessage) -> str | None:
        if message.role != "assistant":
            return None

        metadata_key = str((message.metadata or {}).get(APP_NOTICE_METADATA_KEY) or "").strip()
        if metadata_key in INITIAL_NOTICE_KEYS:
            return metadata_key

        return self._legacy_initial_notice_key(message.content)

    def _legacy_initial_notice_key(self, content: str) -> str | None:
        normalized_content = str(content or "").strip()
        if not normalized_content:
            return None

        for key in INITIAL_NOTICE_KEYS:
            for language in self.localization.available_languages:
                if normalized_content == self._localized_initial_notice_text(key, language=language):
                    return key

        return None

    def _localized_initial_notice_text(self, key: str, *, language: str | None = None) -> str:
        kwargs = {
            "app_name": self._application_display_name(),
            "character_name": self._character_display_name(),
        }
        if language:
            return self.localization.t_for_language(language, key, **kwargs)
        return self.localization.t(key, **kwargs)

    def _add_user_message(self, content: str) -> None:
        message = self.chat_session.add_user_message(
            content,
            metadata={"render_markdown": False},
        )
        self.chat_view.add_chat_message(message)
        self._save_current_chat_session()

    def _add_assistant_message(
        self,
        content: str,
        *,
        render_markdown: bool | None = None,
        metadata: dict | None = None,
    ) -> None:
        if render_markdown is None:
            render_markdown = bool(self.settings.conversation_markdown_enabled)
        message_metadata = dict(metadata or {})
        message_metadata["render_markdown"] = bool(render_markdown)
        message = self.chat_session.add_assistant_message(content, metadata=message_metadata)
        self.chat_view.add_chat_message(message)
        self._save_current_chat_session()

    def _finish_local_command(self) -> None:
        # Local slash commands do not enter the normal ChatResponseWorker finish path.
        # Always restore the character state unless a command explicitly left it in
        # panic/error state. This prevents /status, /health, /systemstatus, etc.
        # from being stuck in user_typing after the composer was cleared.
        if self.character_state.current_state not in {"panic", "error"}:
            self.character_state.on_assistant_done()
        self.bottom_area.raise_()
        self._update_avatar_occlusion_later()

    def _has_active_chat_response_request(self) -> bool:
        request_id = self.active_chat_response_request_id
        return bool(
            request_id
            and request_id in self.chat_response_threads
            and request_id not in self.cancelled_chat_response_request_ids
        )

    def _mark_input_blocked_by_active_response(self) -> None:
        self.character_state.on_embarrassed()
        print("[Chat] Chat response request is already running.")

    def _on_regenerate_requested(self, message_ref) -> None:
        if self._has_active_chat_response_request():
            self._mark_input_blocked_by_active_response()
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
        if not text.strip() and self.pending_file_attachment is not None:
            text = self.localization.t("chat.file.default_prompt")

        visible_text = self._message_text_with_file_attachment_prefix(text)

        command_text = visible_text.strip()
        normalized_text = command_text.lower()

        if normalized_text.startswith("/"):
            if self._handle_command(command_text):
                return

        if (
            self.pending_file_attachment is None
            and self._is_manual_message_export_request(command_text)
        ):
            self.bottom_area.raise_()
            self.character_state.on_message_sent()
            self._add_user_message(visible_text)
            self._update_avatar_occlusion_later()
            self._handle_manual_message_export_request(command_text)
            return

        if self._has_active_chat_response_request():
            self._mark_input_blocked_by_active_response()
            return

        self.bottom_area.raise_()
        self.character_state.on_message_sent()
        self._add_user_message(visible_text)
        self._update_avatar_occlusion_later()

        self._start_chat_response_worker()

    def _message_text_with_file_attachment_prefix(self, text: str) -> str:
        attachment = self.pending_file_attachment
        if attachment is None:
            return text

        prefix = self.localization.t("chat.file.message_prefix", name=attachment.name)
        stripped_text = text.strip()
        if not stripped_text:
            return prefix
        return f"{prefix}\n{stripped_text}"

    def _handle_manual_message_export_request(self, text: str) -> bool:
        if not self._is_manual_message_export_request(text):
            return False

        target_message = self._latest_exportable_assistant_message()
        if target_message is None:
            self._add_assistant_message(
                self.localization.t("chat.export.message.empty"),
                render_markdown=False,
                metadata={"local_export_notice": True},
            )
            self._finish_local_command()
            return True

        suffix = self._manual_export_suffix(text)
        export_title = self.localization.t("chat.export.message.default_title")
        export_filename = self._manual_export_filename(text, suffix)
        if export_filename is not None:
            suffix = export_filename.suffix
            export_title = export_filename.stem
        export_path = self._message_export_path(export_title, suffix, export_filename)
        export_content = self._manual_export_content(text, target_message.content, suffix)

        try:
            export_text_content(
                export_path,
                export_content,
                title=export_title,
            )
        except ChatExportError as error:
            self._add_assistant_message(
                self.localization.t("chat.export.failed", error=str(error)),
                render_markdown=False,
                metadata={"local_export_notice": True},
            )
            self._finish_local_command()
            return True
        except Exception as error:
            self._add_assistant_message(
                self.localization.t("chat.export.failed", error=str(error)),
                render_markdown=False,
                metadata={"local_export_notice": True},
            )
            self._finish_local_command()
            return True

        self._add_assistant_message(
            self.localization.t(
                "chat.export.message.completed",
                format=suffix.lstrip(".").upper(),
                path=str(export_path),
            ),
            render_markdown=False,
            metadata={
                "local_export_notice": True,
                "local_export_path": str(export_path),
                "local_export_link_text": self.localization.t("chat.export.open_file"),
            },
        )
        self._finish_local_command()
        return True

    def _manual_export_content(self, request_text: str, content: str, suffix: str) -> str:
        if suffix != ".csv":
            return content

        if not should_extract_csv_like_content(
            request_text,
            language=self._manual_export_language(),
        ):
            return content

        csv_content = extract_csv_like_content(content)
        return csv_content or content

    def _is_manual_message_export_request(self, text: str) -> bool:
        language = self._manual_export_language()
        suffix = self._manual_export_suffix(text)
        return is_manual_message_export_request(
            text,
            language=language,
            has_filename=self._manual_export_filename(text, suffix) is not None,
        )

    def _manual_export_suffix(self, text: str) -> str:
        return manual_export_suffix(text, language=self._manual_export_language())

    def _manual_export_filename(self, text: str, fallback_suffix: str) -> Path | None:
        return parse_manual_export_filename(
            text,
            language=self._manual_export_language(),
            fallback_suffix=fallback_suffix,
        )

    def _manual_export_language(self) -> str:
        return getattr(self.settings, "language", "en")

    def _latest_exportable_assistant_message(self) -> ChatMessage | None:
        for message in reversed(self.chat_session.messages):
            if message.role != "assistant":
                continue
            metadata = message.metadata or {}
            if metadata.get("pending"):
                continue
            if metadata.get("local_export_notice"):
                continue
            if not message.content.strip():
                continue
            return message
        return None

    def _message_export_path(
        self,
        title: str,
        suffix: str,
        filename: Path | None = None,
    ) -> Path:
        export_dir = app_data_path("exports")
        if filename is not None:
            return export_dir / filename.name

        default_filename = default_chat_export_filename(title)
        return export_dir / f"{default_filename}{suffix}"

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
            "- /systemstatus: Show desktop/backend CPU and memory usage.\n"
            "- /cloudaistatus: Show cloud AI availability and unavailable reason.\n"
            "- /search <query>: Search the web and answer using the search results."
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
            f"- web_search_enabled: {bool(getattr(self.settings, 'web_search_enabled', False))}",
            f"- web_search_auto_enabled: {bool(getattr(self.settings, 'web_search_auto_enabled', False))}",
            f"- web_search_provider: {getattr(self.settings, 'web_search_provider', 'none')}",
            f"- web_search_auth_mode: {getattr(self.settings, 'web_search_auth_mode', 'secure_store')}",
            f"- web_search_api_key_env: {getattr(self.settings, 'web_search_api_key_env', '')}",
            f"- web_search_max_results: {getattr(self.settings, 'web_search_max_results', 5)}",
            f"- web_search_timeout_seconds: {getattr(self.settings, 'web_search_timeout_seconds', 20)}",
            f"- user_country: {getattr(self.settings, 'user_country_code', '')} / {getattr(self.settings, 'user_country_location', '')}",
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
        backend_status = self.backend_client.system_status() if self.settings.developer_mode else None

        lines = [
            "System Status:",
            "",
            "System",
            *self._format_system_overview_lines(desktop_system),
            "",
            "Desktop process",
            *self._format_process_status_lines(desktop_status),
        ]

        if not self.settings.developer_mode:
            lines.extend([
                "",
                "Backend process",
                "- hidden: developer mode is disabled",
            ])
        elif backend_status is None:
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
            self.chat_view.add_chat_message(self._localized_app_notice_message(message))
        if self.current_session_id == self.active_chat_response_session_id:
            self._show_pending_assistant_response(self.current_session_id)
            self._update_chat_response_elapsed_status()
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
        if self.current_session_id == self.active_chat_response_session_id:
            self.character_state.on_message_sent()
            self._update_chat_response_elapsed_status()
        else:
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
            self.localization.t("session.rename.title"),
            text=current_title,
        )
        if not accepted:
            return

        normalized_title = " ".join(new_title.strip().split())
        if len(normalized_title.encode("utf-8")) < 2:
            QMessageBox.warning(
                self,
                self.localization.t("app.title"),
                self.localization.t("session.rename.too_short"),
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
        self.current_session_title = self.localization.t("session.default_title")
        self.initial_notice_added = True
        self.chat_view.clear_messages()

        if show_message:
            self._add_assistant_message("New local chat session created.", render_markdown=False)
        else:
            self._add_assistant_message(
                self.localization.t("session.new.created"),
                render_markdown=False,
            )

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

    def _start_chat_response_elapsed_status(
        self,
        session_id: str,
        request_id: str,
    ) -> None:
        self._chat_response_started_at = datetime.now()
        self.active_chat_response_session_id = session_id
        self.active_chat_response_request_id = request_id
        self._chat_response_elapsed_timer.start()
        self._update_chat_response_elapsed_status()

    def _stop_chat_response_elapsed_status(
        self,
        session_id: str | None = None,
        request_id: str | None = None,
    ) -> None:
        if (
            request_id is not None
            and request_id != self.active_chat_response_request_id
        ):
            return
        if session_id is not None and session_id != self.active_chat_response_session_id:
            return

        self._chat_response_elapsed_timer.stop()
        self._chat_response_started_at = None

    def _update_chat_response_elapsed_status(self) -> None:
        if (
            self._chat_response_started_at is None
            or self.active_chat_response_session_id is None
            or self.current_session_id != self.active_chat_response_session_id
        ):
            return

        elapsed_seconds = max(
            0,
            int((datetime.now() - self._chat_response_started_at).total_seconds()),
        )
        if elapsed_seconds >= CHAT_RESPONSE_LONG_WAIT_SECONDS:
            key = "chat.response_wait.long"
        elif elapsed_seconds >= CHAT_RESPONSE_GENERATING_SECONDS:
            key = "chat.response_wait.generating"
        else:
            key = "chat.response_wait.thinking"

        self.bottom_area.set_state_text(
            self.localization.t(key, seconds=elapsed_seconds)
        )

    def _show_pending_assistant_response(self, session_id: str | None) -> None:
        if not session_id or session_id != self.current_session_id:
            return
        if self.pending_response_widget is not None:
            self.chat_view.remove_message_widget(self.pending_response_widget)
        self.pending_response_session_id = session_id
        self.pending_response_widget = self.chat_view.add_pending_assistant_message(
            self._pending_response_text()
        )
        self._update_chat_response_elapsed_status()
        self._update_avatar_occlusion_later()

    def _clear_pending_assistant_response(self, session_id: str | None = None) -> None:
        if session_id is not None and self.pending_response_session_id not in {None, session_id}:
            return
        if self.pending_response_widget is not None:
            self.chat_view.remove_message_widget(self.pending_response_widget)
        self.pending_response_widget = None
        if session_id is None or self.pending_response_session_id == session_id:
            self.pending_response_session_id = None

    def _start_chat_response_worker(self) -> None:
        if self._has_active_chat_response_request():
            self._mark_input_blocked_by_active_response()
            return

        if self.current_session_id is None:
            self._save_current_chat_session(force=True)

        request_session_id = self.current_session_id
        if not request_session_id:
            print("[Chat] Cannot start chat response without a session id.")
            self._add_backend_fallback_response()
            return

        request = ChatRequest(
            messages=self._chat_request_messages_for_model(),
            character_id=self.settings.selected_character_id,
            user_name=self.settings.user_name,
            developer_mode=self.settings.developer_mode,
            language=self.settings.language,
            settings_snapshot=self.settings.model_dump(mode="json"),
        )

        request_id = uuid4().hex
        chat_response_thread = QThread(self)
        chat_response_worker = ChatResponseWorker(
            backend_client=self.backend_client,
            request=request,
            session_id=request_session_id,
            request_id=request_id,
        )
        chat_response_worker.moveToThread(chat_response_thread)

        self.chat_response_threads[request_id] = chat_response_thread
        self.chat_response_workers[request_id] = chat_response_worker
        self.chat_response_request_sessions[request_id] = request_session_id
        self.chat_response_thread = chat_response_thread
        self.chat_response_worker = chat_response_worker

        chat_response_thread.started.connect(chat_response_worker.run)
        chat_response_worker.finished.connect(self._on_chat_response_finished)
        chat_response_worker.failed.connect(self._on_chat_response_failed)
        chat_response_worker.finished.connect(self._quit_chat_response_thread)
        chat_response_worker.failed.connect(self._quit_chat_response_thread)
        chat_response_thread.finished.connect(
            lambda request_id=request_id: self._cleanup_chat_response_worker(request_id)
        )

        self._start_chat_response_elapsed_status(request_session_id, request_id)
        self._show_pending_assistant_response(request_session_id)
        self.bottom_area.set_response_pending(True)
        self._clear_pending_file_attachment()
        chat_response_thread.start()

    def _chat_request_messages_for_model(self) -> list[ChatMessage]:
        if self.pending_file_attachment is not None:
            return self._chat_request_messages_with_pending_file()
        return self._chat_request_messages_with_inline_data_context()

    def _chat_request_messages_with_pending_file(self) -> list[ChatMessage]:
        messages = self.chat_session.messages
        attachment = self.pending_file_attachment
        if attachment is None:
            return messages

        if messages and messages[-1].role == "user":
            latest_user_message = messages[-1]
            request_message = latest_user_message.model_copy(
                update={
                    "content": self._user_message_content_with_file_context(
                        latest_user_message.content,
                        attachment,
                    ),
                    "metadata": {
                        **(latest_user_message.metadata or {}),
                        "transient_file_context": True,
                        "transient_original_user_content": latest_user_message.content,
                        "file_name": attachment.name,
                        "file_path": str(attachment.path),
                        "file_type": attachment.suffix,
                    },
                }
            )
            return [*messages[:-1], request_message]

        default_prompt = self.localization.t("chat.file.default_prompt")
        return [
            *messages,
            ChatMessage(
                role="user",
                content=self._user_message_content_with_file_context(
                    default_prompt,
                    attachment,
                ),
                metadata={
                    "transient_file_context": True,
                    "transient_original_user_content": default_prompt,
                    "file_name": attachment.name,
                    "file_path": str(attachment.path),
                    "file_type": attachment.suffix,
                },
            ),
        ]

    def _chat_request_messages_with_inline_data_context(self) -> list[ChatMessage]:
        messages = self.chat_session.messages
        if not messages or messages[-1].role != "user":
            return messages

        latest_user_message = messages[-1]
        inline_context = build_inline_csv_context_message(latest_user_message.content)
        if not inline_context:
            return messages

        request_message = latest_user_message.model_copy(
            update={
                "content": self._user_message_content_with_inline_data_context(
                    latest_user_message.content,
                    inline_context,
                ),
                "metadata": {
                    **(latest_user_message.metadata or {}),
                    "transient_inline_data_context": True,
                    "transient_original_user_content": latest_user_message.content,
                    "inline_data_type": "csv",
                },
            }
        )
        return [*messages[:-1], request_message]

    def _user_message_content_with_file_context(
        self,
        user_content: str,
        attachment: FileReadResult,
    ) -> str:
        clean_user_content = user_content.strip()
        return (
            "[User Request]\n"
            f"{clean_user_content}\n\n"
            "[Attached File Handling Hint]\n"
            f"{render_attached_file_handling_hint()}\n\n"
            "[Attached File]\n"
            f"{build_file_context_message(attachment, clean_user_content)}"
        ).strip()

    def _user_message_content_with_inline_data_context(
        self,
        user_content: str,
        inline_context: str,
    ) -> str:
        clean_user_content = user_content.strip()
        return (
            "[User Request]\n"
            f"{clean_user_content}\n\n"
            "[Inline Data Handling Hint]\n"
            f"{render_inline_data_handling_hint()}\n\n"
            "[Machine-readable Inline Data]\n"
            f"{inline_context}"
        ).strip()

    def _on_chat_response_cancel_requested(self) -> None:
        request_id = self.active_chat_response_request_id
        session_id = self.active_chat_response_session_id
        if not request_id or request_id not in self.chat_response_threads:
            self.character_state.on_embarrassed()
            self.bottom_area.set_response_pending(False)
            return

        self.cancelled_chat_response_request_ids.add(request_id)
        self._stop_chat_response_elapsed_status(session_id, request_id)
        self._clear_pending_assistant_response(session_id)
        self.active_chat_response_request_id = None
        self.active_chat_response_session_id = None
        self.bottom_area.set_response_pending(False)
        if session_id == self.current_session_id:
            self._add_assistant_message(
                self.localization.t("chat.response_cancelled"),
                render_markdown=False,
            )
        self.character_state.on_assistant_done()
        self._update_avatar_occlusion_later()

    def _is_stale_chat_response_request(
        self,
        session_id: str,
        request_id: str,
    ) -> bool:
        if request_id in self.cancelled_chat_response_request_ids:
            return True
        if request_id != self.active_chat_response_request_id:
            return True
        return session_id != self.active_chat_response_session_id

    def _on_chat_response_finished(self, session_id: str, request_id: str, response) -> None:
        if self._is_stale_chat_response_request(session_id, request_id):
            print(f"[Chat] Ignored stale chat response request: {request_id}")
            return

        self._stop_chat_response_elapsed_status(session_id, request_id)
        self._clear_pending_assistant_response(session_id)
        self.bottom_area.set_response_pending(False)
        metadata = getattr(response.message, "metadata", {}) or {}
        response_state = self._chat_response_state_from_metadata(metadata)
        animate_response = (
            response_state == "assistant_done"
            and session_id == self.current_session_id
            and self.settings.typewriter_interval_ms > 0
        )
        if animate_response:
            self.character_state.on_assistant_typing()

        message_added = self._append_message_to_session(
            session_id,
            response.message,
            animate_current=animate_response,
        )
        if not message_added:
            print(f"[Chat] Response target session was not found: {session_id}")

        if animate_response and message_added:
            self._chat_response_display_metadata[response.message.id] = (
                session_id,
                dict(metadata),
            )
        elif session_id == self.current_session_id:
            self._apply_chat_response_state(metadata)

        self._update_avatar_occlusion_later()

    def _chat_response_state_from_metadata(self, metadata: dict) -> str:
        for state, keys in CHAT_RESPONSE_STATE_RULES.items():
            if any(metadata.get(key) for key in keys):
                return state
        return "assistant_done"

    def _apply_chat_response_state(self, metadata: dict) -> None:
        state = self._chat_response_state_from_metadata(metadata)
        handler_name = CHAT_RESPONSE_STATE_HANDLERS.get(
            state,
            CHAT_RESPONSE_STATE_HANDLERS["assistant_done"],
        )
        getattr(self.character_state, handler_name)()

    def _finish_chat_response_display(self, message_id: str) -> None:
        display_context = self._chat_response_display_metadata.pop(message_id, None)
        if display_context is None:
            return

        session_id, metadata = display_context
        if session_id != self.current_session_id:
            return

        self._apply_chat_response_state(metadata)

    def _on_chat_response_failed(self, session_id: str, request_id: str, failure) -> None:
        if self._is_stale_chat_response_request(session_id, request_id):
            print(f"[Chat] Ignored stale chat response failure: {request_id}")
            return

        self._stop_chat_response_elapsed_status(session_id, request_id)
        self._clear_pending_assistant_response(session_id)
        self.bottom_area.set_response_pending(False)
        failure_payload = self._normalize_chat_failure_payload(failure)
        print(
            "[Chat] Backend chat response failed for session "
            f"{session_id}: {failure_payload.get('error_code')}: {failure_payload.get('error_detail')}"
        )
        self._add_backend_fallback_response(session_id=session_id, failure=failure_payload)

    def _quit_chat_response_thread(self, session_id: str, request_id: str, *args) -> None:  # noqa: ANN002
        thread = self.chat_response_threads.get(request_id)
        if thread is not None:
            thread.quit()

    def _cleanup_chat_response_worker(self, request_id: str) -> None:
        worker = self.chat_response_workers.pop(request_id, None)
        if worker is not None:
            worker.deleteLater()

        thread = self.chat_response_threads.pop(request_id, None)
        if thread is not None:
            thread.deleteLater()

        self.chat_response_request_sessions.pop(request_id, None)
        self.cancelled_chat_response_request_ids.discard(request_id)

        if request_id == self.active_chat_response_request_id:
            self.active_chat_response_request_id = None
            self.active_chat_response_session_id = None
            self.bottom_area.set_response_pending(False)

        if worker is self.chat_response_worker:
            self.chat_response_worker = None
        if thread is self.chat_response_thread:
            self.chat_response_thread = None

    def _append_message_to_session(
        self,
        session_id: str,
        message,
        *,
        animate_current: bool = False,
    ) -> bool:
        if not session_id:
            return False

        if session_id == self.current_session_id:
            self.chat_session.append_message(message)
            self.chat_view.add_chat_message(message, animate=animate_current)
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

    def _normalize_chat_failure_payload(self, failure) -> dict:
        if isinstance(failure, dict):
            return dict(failure)
        return {
            "error_code": "unknown_error",
            "error_detail": str(failure or ""),
        }

    def _chat_failure_message(self, failure: dict) -> str:
        error_code = str(failure.get("error_code") or "unknown_error")
        message_key = {
            "backend_communication_timeout": "chat.failure.backend_communication_timeout",
            "backend_unreachable": "chat.failure.backend_unreachable",
            "backend_http_error": "chat.failure.backend_http_error",
            "backend_invalid_response": "chat.failure.backend_invalid_response",
            "backend_network_error": "chat.failure.backend_unreachable",
            "backend_chat_request_failed": "chat.failure.backend_unreachable",
        }.get(error_code, "chat.failure.unknown")

        content = self.localization.t(message_key)
        if not self.settings.developer_mode:
            return content

        detail_lines = [
            "",
            self.localization.t("chat.failure.developer_details"),
            f"- error_code: {error_code}",
        ]
        for key in (
            "elapsed_seconds",
            "timeout_seconds",
            "backend_url",
            "exception_type",
            "http_status",
            "error_detail",
        ):
            value = failure.get(key)
            if value not in (None, ""):
                detail_lines.append(f"- {key}: {value}")
        return content + "\n" + "\n".join(detail_lines)

    def _add_backend_fallback_response(
        self,
        session_id: str | None = None,
        failure: dict | None = None,
    ) -> None:
        target_session_id = session_id or self.current_session_id
        failure_payload = failure or {
            "error_code": "backend_chat_request_failed",
            "error_detail": "Backend chat request failed.",
        }
        fallback_message = ChatMessage(
            role="assistant",
            content=self._chat_failure_message(failure_payload),
            metadata={
                "render_markdown": bool(self.settings.conversation_markdown_enabled),
                "source": "backend_fallback",
                "error": True,
                "panic": True,
                **failure_payload,
            },
        )

        if target_session_id and self._append_message_to_session(target_session_id, fallback_message):
            pass
        else:
            self.chat_session.append_message(fallback_message)
            self.chat_view.add_chat_message(fallback_message)
            self._save_current_chat_session()

        self.character_state.on_panic()
        self._update_avatar_occlusion_later()

    def _update_content_geometry(self) -> None:
        if not hasattr(self, "content_area"):
            return

        area_width = self.content_area.width()
        area_height = self.content_area.height()

        composer_preferred_height = self._composer_preferred_height(area_height)
        self.bottom_area.sync_composer_height_to_left_name_area(
            preferred_height=composer_preferred_height
        )

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
        scroll_bar_width = self.chat_view.verticalScrollBar().sizeHint().width()
        bottom_overlay_width = max(1, area_width - scroll_bar_width)
        self.bottom_area.setGeometry(
            0,
            bottom_overlay_top,
            bottom_overlay_width,
            overlay_height,
        )
        self.bottom_area.sync_composer_height_to_left_name_area(
            preferred_height=composer_preferred_height
        )

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

    def _composer_preferred_height(self, area_height: int) -> int:
        return min(220, max(110, int(area_height * 0.16)))

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
            print(f"[Backend] health ready with warnings: {result}")
            return

        print(f"[Backend] health ok: {result}")

    def _check_local_ai_model(self) -> None:
        if not self.settings.setup_wizard_completed:
            print("[LocalAI] Setup wizard is not completed; skipping startup model check.")
            return
        if self._startup_local_ai_check_done:
            return
        self._startup_local_ai_check_done = True

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
        force_pull: bool,
    ) -> None:
        self._start_local_model_prepare_worker(
            model_name=model_name,
            auto_pull=auto_pull,
            auto_install_runtime=auto_install_runtime,
            auto_start_server=auto_start_server,
            timeout_seconds=timeout_seconds,
            force_pull=force_pull,
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

        self._refresh_active_settings_local_models(
            self._fetch_installed_local_model_names(auto_start_server=auto_start_server)
        )


    def _on_settings_local_model_list_requested(
        self,
        auto_start_server: bool,
    ) -> None:
        result = self.backend_client.list_ollama_models(
            auto_start_server=auto_start_server,
            timeout_seconds=15.0,
        )

        if result is None:
            QMessageBox.warning(
                self,
                self.localization.t("app.title"),
                self.localization.t(
                    "local_ai.model.list.failed",
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
                    "local_ai.model.list.failed",
                    error=self._local_ai_error_message(error_code),
                ),
            )
            return

        models = result.get("models") or []
        installed_model_names = self._local_model_names_from_list_result(result)
        self._refresh_active_settings_local_models(installed_model_names)

        if not models:
            message = self.localization.t("local_ai.model.list.empty")
        else:
            lines = []
            for model in models:
                if not isinstance(model, dict):
                    continue
                name = self._local_model_name_from_payload(model) or "unknown"
                size = self._format_bytes(model.get("size"))
                modified_at = str(model.get("modified_at") or "unknown")
                lines.append(f"- {name} / {size} / {modified_at}")

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
        force_pull: bool = False,
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
            force_pull=force_pull,
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

        self._refresh_active_settings_local_models(
            self._fetch_installed_local_model_names(
                auto_start_server=self.settings.auto_start_local_ai_server
            ),
            preferred_model=model_name,
        )

        self.character_state.on_assistant_done()

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
        if self._is_local_model_update_check_due():
            QTimer.singleShot(0, self._on_local_model_update_timer)

    def _is_local_model_update_check_due(self) -> bool:
        if not getattr(self.settings, "local_model_update_check_enabled", False):
            return False

        model_name = str(getattr(self.settings, "local_model", "") or "").strip()
        if not model_name:
            return False

        try:
            interval_days = int(getattr(self.settings, "local_model_update_check_interval_days", 7))
        except Exception:
            interval_days = 7
        interval_days = max(1, min(60, interval_days))

        raw_last_checked = str(
            getattr(self.settings, "local_model_update_last_checked_at", "")
            or ""
        ).strip()
        if not raw_last_checked:
            return True

        try:
            last_checked = datetime.fromisoformat(raw_last_checked)
        except ValueError:
            return True

        return datetime.now() - last_checked >= timedelta(days=interval_days)

    def _record_local_model_update_checked_at(self) -> None:
        self.settings.local_model_update_last_checked_at = datetime.now().isoformat()
        self.settings_repository.save(self.settings)

    def _on_local_model_update_timer(self) -> None:
        """
        Invoked periodically by the update timer to check whether the configured
        interval has elapsed before asking the user to re-pull the selected
        local model.
        """
        if self.local_model_prepare_thread is not None:
            return

        if not self._is_local_model_update_check_due():
            return

        model_name = str(getattr(self.settings, "local_model", "") or "").strip()
        if not model_name:
            return

        prompt = self.localization.t("local_ai.model.update.prompt")
        if not prompt or prompt.startswith("{"):
            prompt = "The local AI model update check interval has elapsed. Would you like to check and update the selected model now?"

        result = QMessageBox.question(
            self,
            self.localization.t("app.title"),
            prompt,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        self._record_local_model_update_checked_at()

        if result == QMessageBox.StandardButton.Yes:
            self._start_local_model_prepare_worker(
                model_name=model_name,
                auto_pull=True,
                auto_install_runtime=False,
                force_pull=True,
            )

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
            if widget in {
                self.bottom_area.composer,
                self.bottom_area.send_button,
                self.bottom_area.attach_button,
            }:
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

        if self._route_bottom_overlay_press_to_underlay(global_pos):
            return True

        return False

    def _route_bottom_overlay_press_to_underlay(self, global_pos: QPoint) -> bool:
        # Keep the overlay fallback generic: MainWindow only decides the visual
        # priority of underlay surfaces, while each widget decides what is
        # clickable inside itself.
        underlay_widgets = (
            getattr(self, "session_sidebar", None),
            getattr(self, "chat_view", None),
        )
        for widget in underlay_widgets:
            handler = getattr(widget, "handle_global_mouse_press", None)
            if handler is not None and handler(global_pos):
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
    def _is_macos(self) -> bool:
        return sys.platform == "darwin"

    def _hide_session_window_from_tray(self) -> None:
        if self._is_macos():
            # On macOS, keep the window represented by the Dock instead of
            # fully hiding it like a Windows tray app.  This matches normal
            # Dock behavior: the app remains alive and the session window can
            # be restored from the Dock/app menu or the menu-bar icon.
            self.showMinimized()
            return

        self.hide()

    def _setup_tray_icon(self) -> None:
        if not bool(getattr(self.settings, "enable_tray_icon", True)):
            if self._tray_icon is not None:
                self._tray_icon.hide()
            self._tray_icon = None
            self._tray_menu = None
            return

        if not QSystemTrayIcon.isSystemTrayAvailable():
            self._tray_icon = None
            self._tray_menu = None
            return

        if self._tray_icon is None:
            icon = self.windowIcon()
            if icon.isNull():
                icon = QApplication.style().standardIcon(
                    QApplication.style().StandardPixmap.SP_ComputerIcon
                )

            self._tray_icon = QSystemTrayIcon(icon, self)
            self._tray_icon.activated.connect(self._on_tray_icon_activated)

        menu = QMenu(self)

        show_action = QAction(self.localization.t("tray.open_session_window"), self)
        show_action.triggered.connect(self.show_session_window)
        menu.addAction(show_action)

        hide_action = QAction(self.localization.t("tray.hide"), self)
        hide_action.triggered.connect(self._hide_session_window_from_tray)
        menu.addAction(hide_action)

        menu.addSeparator()

        quit_action = QAction(self.localization.t("tray.quit"), self)
        quit_action.triggered.connect(self._quit_from_tray)
        menu.addAction(quit_action)

        self._tray_menu = menu
        self._tray_icon.setContextMenu(menu)
        self._tray_icon.setToolTip(self.localization.t("app.title"))
        self._tray_icon.show()

    def _on_tray_icon_activated(self, reason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_session_window()

    def show_session_window(self) -> None:
        """Show and focus the existing session window.

        This is used by the tray/menu bar action and by the single-instance
        activation channel.  It intentionally revives the current frontend
        instead of starting another frontend process.
        """
        self._restore_session_window_focus()
        # Some macOS window managers ignore the first activation request when it
        # originates from a menu bar/tray action. Retry shortly on the Qt event
        # loop instead of starting another frontend process.
        QTimer.singleShot(60, self._restore_session_window_focus)
        QTimer.singleShot(180, self._restore_session_window_focus)

    def _restore_session_window_focus(self) -> None:
        app = QApplication.instance()

        if app is not None:
            app.setActiveWindow(self)

        self.setVisible(True)
        self.show()
        self.setWindowState(
            (
                self.windowState()
                & ~Qt.WindowState.WindowMinimized
                & ~Qt.WindowState.WindowFullScreen
            )
            | Qt.WindowState.WindowActive
        )
        self.showNormal()
        self.raise_()
        self.activateWindow()

        if app is not None:
            app.alert(self, 0)


    def _quit_from_tray(self) -> None:
        self._request_application_quit()

    def prepare_application_quit(self) -> None:
        self._force_quit_requested = True
        self._save_current_chat_session()
        if self._tray_icon is not None:
            self._tray_icon.hide()

    def _request_application_quit(self) -> None:
        self.prepare_application_quit()

        app = QApplication.instance()
        if app is not None:
            QTimer.singleShot(0, app.quit)
        else:
            self.close()

    def _should_minimize_to_tray_on_close(self) -> bool:
        if self._force_quit_requested:
            return False

        if not bool(getattr(self.settings, "enable_tray_icon", True)):
            return False

        if str(getattr(self.settings, "close_button_behavior", "exit")) != "minimize_to_tray":
            return False

        return self._tray_icon is not None and self._tray_icon.isVisible()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_content_geometry()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._save_current_chat_session()
        self.settings.window_width = self.width()
        self.settings.window_height = self.height()
        self.settings_repository.save(self.settings)

        if self._should_minimize_to_tray_on_close():
            event.ignore()
            self._hide_session_window_from_tray()
            if self._tray_icon is not None:
                self._tray_icon.showMessage(
                    self.localization.t("app.title"),
                    self.localization.t("tray.minimized_message"),
                    QSystemTrayIcon.MessageIcon.Information,
                    1800,
                )
            return

        event.accept()
        self._request_application_quit()
