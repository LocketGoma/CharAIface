from pathlib import Path
from shared.schema.chat import ChatRequest
from desktop.chat.chat_session import ChatSession
from desktop.client.backend_http_client import BackendHttpClient
from desktop.workers.local_model_prepare_worker import LocalModelPrepareWorker
from PySide6.QtCore import QEvent, QThread, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desktop.characters.character_pack import CharacterPack
from desktop.characters.character_registry import CharacterRegistry
from desktop.core.character_state import CharacterStateController
from desktop.localization.localization_manager import LocalizationManager
from desktop.settings.app_settings import AppSettings
from desktop.settings.settings_repository import SettingsRepository
from desktop.theme.qss_builder import build_qss
from desktop.theme.theme_manager import ThemeManager
from desktop.theme.theme_model import ThemeDefinition
from desktop.ui.bottom_user_area import BottomUserArea
from desktop.ui.chat_view import ChatView
from desktop.ui.settings_dialog import SettingsDialog


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
        self.initial_notice_added = False
        self.chat_session = ChatSession()
        self.backend_client = BackendHttpClient()

        self.setMinimumSize(self.MIN_WINDOW_WIDTH, self.MIN_WINDOW_HEIGHT)
        self.resize(self.settings.window_width, self.settings.window_height)

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        header = self._create_header()
        content_area = self._create_content_area()

        root_layout.addWidget(header)
        root_layout.addWidget(content_area, stretch=1)

        self.setCentralWidget(root)

        self.apply_theme_from_settings()
        self.retranslate_ui()
        QTimer.singleShot(0, self._restore_window_geometry)
        QTimer.singleShot(100, self._check_backend_health)
        QTimer.singleShot(500, self._check_local_ai_model)

    def _create_content_area(self) -> QWidget:
        self.content_area = QWidget()
        self.content_area.setObjectName("ContentArea")

        self.chat_view = ChatView()
        self.chat_view.setParent(self.content_area)

        self.bottom_area = BottomUserArea(localization=self.localization)
        self.bottom_area.setParent(self.content_area)
        self.bottom_area.set_user_name(self.settings.user_name)

        self._load_character_registry()
        self._apply_selected_or_default_character_pack()
        self._update_chat_view_display_names()

        self.bottom_area.send_requested.connect(self.on_send_requested)
        self.bottom_area.text_changed.connect(self.character_state.on_user_text_changed)
        self.character_state.state_changed.connect(self.bottom_area.set_state)

        self.chat_view.verticalScrollBar().valueChanged.connect(
            self._update_avatar_occlusion_later
        )

        self.chat_view.show()
        self.bottom_area.show()

        self.bottom_area.installEventFilter(self)
        self.bottom_area.character_area.installEventFilter(self)
        self.bottom_area.character_info_box.installEventFilter(self)
        self.bottom_area.user_label.installEventFilter(self)
        self.bottom_area.user_name_label.installEventFilter(self)

        self.bottom_area.raise_()

        QTimer.singleShot(0, self._update_content_geometry)

        return self.content_area

    def _create_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("HeaderBar")
        header.setFixedHeight(56)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 8, 16, 8)

        self.title_label = QLabel()
        self.title_label.setObjectName("HeaderTitle")

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

        self.character_registry = CharacterRegistry(
            builtin_characters_dir=builtin_characters_dir,
            user_characters_dir=user_characters_dir,
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

        dialog = SettingsDialog(
            settings=self.settings.model_copy(deep=True),
            localization=self.localization,
            theme_manager=self.theme_manager,
            character_registry=self.character_registry,
            parent=self,
        )

        if not dialog.exec():
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
        self.bottom_area.retranslate_ui()
        self.bottom_area.set_user_name(self.settings.user_name)
        self._update_chat_view_display_names()

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
        message = self.chat_session.add_user_message(content)
        self.chat_view.add_chat_message(message)

    def _add_assistant_message(self, content: str) -> None:
        message = self.chat_session.add_assistant_message(content)
        self.chat_view.add_chat_message(message)

    def on_send_requested(self, text: str) -> None:
        normalized_text = text.strip().lower()

        if normalized_text.startswith("/"):
            if self._handle_command(normalized_text):
                return

        self.bottom_area.raise_()
        self.character_state.on_message_sent()
        self._add_user_message(text)
        self._update_avatar_occlusion_later()

        QTimer.singleShot(300, self._show_fake_assistant_typing)
        QTimer.singleShot(700, self._request_backend_chat_response)

    def _handle_command(self, command: str) -> bool:
        if command == "/clear":
            self._clear_chat_display_only()
            return True

        if command == "/help":
            self._add_assistant_message(self._command_help_text())
            return True

        if command == "/status":
            self._add_assistant_message(self._command_status_text())
            return True

        if command == "/health":
            self._add_assistant_message(self._command_health_text())
            return True

        return False

    def _command_help_text(self) -> str:
        return (
            "Available commands:\n"
            "- /help: Show this command list.\n"
            "- /clear: Clear displayed chat messages only. The internal session remains.\n"
            "- /status: Show current desktop/session settings.\n"
            "- /health: Show backend health payload."
        )

    def _command_status_text(self) -> str:
        return (
            "Status:\n"
            f"- user_name: {self.settings.user_name}\n"
            f"- character_id: {self.settings.selected_character_id}\n"
            f"- character_name: {self._character_display_name()}\n"
            f"- developer_mode: {self.settings.developer_mode}\n"
            f"- local_model: {self.settings.local_model}\n"
            f"- cloud_ai_enabled: {self.settings.cloud_ai_enabled}\n"
            f"- cloud_ai_provider: {self.settings.cloud_ai_provider}\n"
            f"- cloud_model: {self.settings.cloud_model}"
        )

    def _command_health_text(self) -> str:
        result = self.backend_client.health()
        if result is None:
            return "Backend health: unavailable"

        status = result.get("status", "unknown")
        errors = result.get("errors", [])
        local_ai = result.get("local_ai", {})
        cloud_ai = result.get("cloud_ai", {})

        lines = [
            f"Backend health: {status}",
            f"- local_ai: {local_ai.get('state', 'unknown')}",
            f"- cloud_ai: {cloud_ai.get('state', 'unknown')}",
        ]

        if errors:
            lines.append("- errors:")
            for error in errors:
                code = error.get("code", "unknown")
                message = error.get("message", "")
                lines.append(f"  - {code}: {message}")

        return "\n".join(lines)

    def _clear_chat_display_only(self) -> None:
        self.chat_view.clear_messages()
        self.bottom_area.raise_()
        self._update_avatar_occlusion_later()

    def _show_fake_assistant_typing(self) -> None:
        self.character_state.on_assistant_typing()

    def _request_backend_chat_response(self) -> None:
        request = ChatRequest(
            messages=self.chat_session.messages,
            character_id=self.settings.selected_character_id,
            user_name=self.settings.user_name,
            developer_mode=self.settings.developer_mode,
        )

        response = self.backend_client.chat(request)

        if response is None:
            self._add_backend_fallback_response()
            return

        self.chat_session.append_message(response.message)
        self.chat_view.add_chat_message(response.message)

        self.character_state.on_assistant_done()
        self._update_avatar_occlusion_later()

    def _add_backend_fallback_response(self) -> None:
        self._add_assistant_message(self.localization.t("chat.backend_fallback"))

        self.character_state.on_assistant_done()
        self._update_avatar_occlusion_later()

    def _update_content_geometry(self) -> None:
        if not hasattr(self, "content_area"):
            return

        area_width = self.content_area.width()
        area_height = self.content_area.height()

        # 하단 입력 UI가 차지하는 실제 높이.
        # composer 110 + margins + 여유분.
        input_area_height = 150

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

        self.bottom_area.setGeometry(
            0,
            max(0, area_height - overlay_height),
            area_width,
            overlay_height,
        )

        # 메시지 영역은 입력창 좌우 폭과 맞춘다.
        character_reserved_width = 238
        send_reserved_width = 86

        self.chat_view.set_side_reserved_widths(
            left_width=character_reserved_width,
            right_width=send_reserved_width,
        )

        # ChatView 자체가 이미 입력창 위까지만 있으므로 bottom viewport margin은 필요 없다.
        self.chat_view.set_bottom_reserved_height(0)

        self.chat_view.raise_()
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

    def _start_local_model_prepare_worker(
        self,
        model_name: str,
        auto_pull: bool,
        auto_install_runtime: bool,
    ) -> None:
        if self.local_model_prepare_thread is not None:
            QMessageBox.information(
                self,
                self.localization.t("app.title"),
                self.localization.t("local_ai.model.prepare.already_running"),
            )
            return
        
        self.character_state.on_assistant_typing()

        self.local_model_prepare_thread = QThread(self)
        self.local_model_prepare_worker = LocalModelPrepareWorker(
            backend_client=self.backend_client,
            model=model_name,
            auto_pull=auto_pull,
            auto_install_runtime=auto_install_runtime,
            auto_start_server=self.settings.auto_start_local_ai_server,
            timeout_seconds=float(self.settings.model_download_timeout_seconds),
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

    def _local_ai_error_message(self, error_code: str) -> str:
        key = f"local_ai.error.{error_code}"
        text = self.localization.t(key)

        if text == f"{{{key}}}":
            return error_code

        return text

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.Wheel:
            if self._should_forward_wheel_to_chat_view(watched):
                self._scroll_chat_view_by_wheel(event)
                return True

        return super().eventFilter(watched, event)

    def _should_forward_wheel_to_chat_view(self, watched) -> bool:
        if not hasattr(self, "bottom_area"):
            return False

        if watched is self.bottom_area.composer:
            return False

        if watched is self.bottom_area.send_button:
            return False

        return True

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
        self.settings.window_width = self.width()
        self.settings.window_height = self.height()
        self.settings_repository.save(self.settings)

        super().closeEvent(event)