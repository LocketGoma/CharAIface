from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFontDatabase, QIntValidator

import httpx
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from backend.app.services.cloud_auth_manager import (
    CloudAuthManager,
    CloudCredentialConfig,
)
from desktop.characters.character_registry import CharacterRegistry
from desktop.core.frontend_helper import (
    KNOWN_CLOUD_PROVIDER_IDS,
    WEB_SEARCH_PROVIDER_DEFAULTS,
    cloud_ai_provider_defaults,
    default_cloud_api_key_env,
    default_cloud_credential_id,
    default_web_search_api_key_env,
    default_web_search_credential_id,
    web_search_provider_defaults,
)
from desktop.localization.localization_manager import LocalizationManager
from desktop.settings.app_settings import AppSettings
from desktop.theme.theme_manager import ThemeManager
from desktop.theme.theme_model import ThemePalette


class SettingsDialog(QDialog):
    local_model_prepare_requested = Signal(str, bool, bool, bool, float, bool)
    local_model_delete_requested = Signal(str, bool)
    local_model_list_requested = Signal(bool)
    avatar_opacity_preview_changed = Signal(float)

    def __init__(
        self,
        settings: AppSettings,
        localization: LocalizationManager,
        theme_manager: ThemeManager,
        character_registry: CharacterRegistry,
        installed_models: list[str] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)

        self.settings = settings
        self.localization = localization
        self.theme_manager = theme_manager
        self.character_registry = character_registry
        # A list of installed local AI model names. When provided, this allows the
        # model combo box and download dialog to present available models for
        # selection. If not provided or empty, only the current model is available.
        self.installed_models: list[str] = self._unique_model_names(installed_models or [])
        self.character_registry_reloaded = False
        self._updating_cloud_model_combo = False

        self.setWindowTitle(self.localization.t("settings.title"))
        self.setMinimumSize(620, 520)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        self.tabs = QTabWidget()

        self.general_tab = self._create_general_tab()
        self.character_tab = self._create_character_tab()
        self.theme_tab = self._create_theme_tab()
        self.model_tab = self._create_model_tab()
        self.cloud_ai_tab = self._create_cloud_ai_tab()
        self.web_search_tab = self._create_web_search_tab()
        self.advanced_tab = self._create_advanced_tab()

        self.tabs.addTab(self.general_tab, self.localization.t("settings.tab.general"))
        self.tabs.addTab(self.character_tab, self.localization.t("settings.tab.character"))
        self.tabs.addTab(self.theme_tab, self.localization.t("settings.tab.theme"))
        self.tabs.addTab(self.model_tab, self.localization.t("settings.tab.model"))
        self.tabs.addTab(self.cloud_ai_tab, self.localization.t("settings.tab.cloud_ai"))
        self.tabs.addTab(self.web_search_tab, self.localization.t("settings.tab.web_search"))
        self.tabs.addTab(self.advanced_tab, self.localization.t("settings.tab.advanced"))

        root_layout.addWidget(self.tabs)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )

        save_button = self.button_box.button(QDialogButtonBox.StandardButton.Save)
        cancel_button = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)

        if save_button is not None:
            save_button.setObjectName("DialogSaveButton")
            save_button.setText(self.localization.t("settings.button.save"))

        if cancel_button is not None:
            cancel_button.setObjectName("DialogCancelButton")
            cancel_button.setText(self.localization.t("settings.button.cancel"))

        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        root_layout.addWidget(self.button_box)

    def accept(self) -> None:
        # Keep the dialog-owned settings object synchronized before QDialog
        # returns Accepted.  MainWindow applies it again after exec(), but doing
        # it here prevents newly added tabs from appearing to reset when helper
        # buttons or early accepted-state reads inspect dialog.settings.
        self.apply_to_settings()
        super().accept()

    def _create_general_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        description_label = QLabel(self.localization.t("settings.general.description"))
        description_label.setObjectName("SettingsDescriptionLabel")
        layout.addWidget(description_label)

        form_layout = QFormLayout()
        form_layout.setSpacing(10)

        self.user_name_edit = QLineEdit()
        self.user_name_edit.setText(self.settings.user_name)

        self.language_combo = QComboBox()
        self._setup_language_combo()

        self.user_country_combo = QComboBox()
        self._setup_user_country_combo()

        self.preferred_unit_system_combo = QComboBox()
        self._setup_preferred_unit_system_combo()

        self.user_country_location_edit = QLineEdit()
        self.user_country_location_edit.setText(self.settings.user_country_location)
        self.user_country_location_edit.setPlaceholderText(
            self.localization.t("settings.user_country.custom.placeholder")
        )

        self.user_country_detect_button = QPushButton(
            self.localization.t("settings.user_country.detect_ip")
        )
        self.user_country_detect_button.clicked.connect(self._detect_user_country_by_ip)

        user_country_widget = QWidget()
        user_country_layout = QHBoxLayout(user_country_widget)
        user_country_layout.setContentsMargins(0, 0, 0, 0)
        user_country_layout.setSpacing(8)
        user_country_layout.addWidget(self.user_country_combo, 1)
        user_country_layout.addWidget(self.user_country_detect_button)

        self.language_combo.currentIndexChanged.connect(self._update_user_country_ui)
        self.user_country_combo.currentIndexChanged.connect(self._update_user_country_ui)

        form_layout.addRow(self.localization.t("settings.user_name"), self.user_name_edit)
        form_layout.addRow(self.localization.t("settings.language"), self.language_combo)
        form_layout.addRow(self.localization.t("settings.user_country"), user_country_widget)
        form_layout.addRow(self.localization.t("settings.user_country.custom"), self.user_country_location_edit)
        form_layout.addRow(self.localization.t("settings.preferred_unit_system"), self.preferred_unit_system_combo)

        output_label = QLabel(self.localization.t("settings.conversation_output"))
        output_label.setObjectName("SettingsSectionLabel")

        self.conversation_markdown_checkbox = QCheckBox(
            self.localization.t("settings.conversation_markdown_enabled")
        )
        self.conversation_markdown_checkbox.setChecked(self.settings.conversation_markdown_enabled)

        self.enforce_response_language_checkbox = QCheckBox(
            self.localization.t("settings.enforce_response_language")
        )
        self.enforce_response_language_checkbox.setChecked(self.settings.enforce_response_language)

        self.emphasize_character_style_checkbox = QCheckBox(
            self.localization.t("settings.emphasize_character_style")
        )
        self.emphasize_character_style_checkbox.setChecked(self.settings.emphasize_character_style)

        layout.addLayout(form_layout)
        layout.addWidget(output_label)
        layout.addWidget(self.conversation_markdown_checkbox)
        layout.addWidget(self.enforce_response_language_checkbox)
        layout.addWidget(self.emphasize_character_style_checkbox)
        layout.addStretch()

        self._update_user_country_ui()

        return tab

    def _create_character_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        description_label = QLabel(self.localization.t("settings.character.description"))
        description_label.setObjectName("SettingsDescriptionLabel")
        layout.addWidget(description_label)

        form_layout = QFormLayout()
        form_layout.setSpacing(10)

        self.character_combo = QComboBox()
        self._setup_character_combo()

        self.character_reload_button = QPushButton(
            self.localization.t("settings.character.reload_all")
        )
        self.character_reload_button.clicked.connect(self._reload_character_packs)

        self.character_info_label = QLabel()
        self.character_info_label.setWordWrap(True)
        self.character_info_label.setObjectName("CharacterInfoLabel")

        self.character_combo.currentIndexChanged.connect(self._update_character_info_label)
        self.character_combo.currentIndexChanged.connect(self._refresh_theme_palette_view)

        form_layout.addRow(self.localization.t("settings.character.select"), self.character_combo)
        form_layout.addRow("", self.character_reload_button)

        layout.addLayout(form_layout)
        layout.addWidget(self.character_info_label)
        layout.addStretch()

        self._update_character_info_label()

        return tab

    def _create_theme_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        description_label = QLabel(self.localization.t("settings.theme.description"))
        description_label.setObjectName("SettingsDescriptionLabel")
        layout.addWidget(description_label)

        form_layout = QFormLayout()
        form_layout.setSpacing(10)

        self.chat_font_combo = QComboBox()
        self._setup_chat_font_combo()

        self.chat_font_size_combo = QComboBox()
        self._setup_chat_font_size_combo()

        chat_font_widget = QWidget()
        chat_font_layout = QHBoxLayout(chat_font_widget)
        chat_font_layout.setContentsMargins(0, 0, 0, 0)
        chat_font_layout.setSpacing(8)
        chat_font_layout.addWidget(self.chat_font_combo, 1)
        self.chat_font_size_combo.setFixedWidth(92)
        chat_font_layout.addWidget(self.chat_font_size_combo)

        self.theme_combo = QComboBox()
        self._setup_theme_combo()
        self.theme_combo.currentIndexChanged.connect(self._refresh_theme_palette_view)

        self.theme_palette_button = QPushButton(
            self.localization.t("settings.theme.palette.show")
        )
        self.theme_palette_button.clicked.connect(self._toggle_theme_palette_view)

        theme_select_widget = QWidget()
        theme_select_layout = QHBoxLayout(theme_select_widget)
        theme_select_layout.setContentsMargins(0, 0, 0, 0)
        theme_select_layout.setSpacing(8)
        theme_select_layout.addWidget(self.theme_combo, 1)
        theme_select_layout.addWidget(self.theme_palette_button)

        form_layout.addRow(self.localization.t("settings.chat_font.change"), chat_font_widget)
        form_layout.addRow(self.localization.t("settings.theme.select"), theme_select_widget)
        layout.addLayout(form_layout)

        self.theme_palette_view = QTextEdit()
        self.theme_palette_view.setReadOnly(True)
        self.theme_palette_view.setAcceptRichText(True)
        self.theme_palette_view.setMinimumHeight(300)
        self.theme_palette_view.setObjectName("ThemePaletteView")
        self.theme_palette_view.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.theme_palette_view.setVisible(False)
        layout.addWidget(self.theme_palette_view)

        note_label = QLabel(self.localization.t("settings.theme.character.description"))
        note_label.setWordWrap(True)
        note_label.setObjectName("SettingsNoteLabel")
        layout.addWidget(note_label)

        layout.addStretch()

        return tab

    def _setup_chat_font_combo(self) -> None:
        self.chat_font_combo.clear()
        self.chat_font_combo.setEditable(True)
        self.chat_font_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.chat_font_combo.setPlaceholderText(self.localization.t("settings.chat_font.family_label"))
        self.chat_font_combo.lineEdit().setPlaceholderText(self.localization.t("settings.chat_font.family_label"))


        preferred_fonts = [
            "맑은 고딕",
            "Malgun Gothic",
            "Apple SD Gothic Neo",
            "Noto Sans CJK KR",
            "Noto Sans KR",
            "Pretendard",
            "Arial",
            "Segoe UI",
        ]

        families = list(QFontDatabase.families())
        seen: set[str] = set()

        def add_family(family: str) -> None:
            family = str(family or "").strip()
            if not family or family in seen:
                return
            seen.add(family)
            self.chat_font_combo.addItem(family, family)

        for family in preferred_fonts:
            if family in families:
                add_family(family)

        for family in sorted(families, key=lambda value: value.casefold()):
            add_family(family)

        current_family = str(self.settings.chat_font_family or "").strip()
        if not current_family:
            current_family = self._default_chat_font_family()

        if current_family and current_family not in seen:
            self.chat_font_combo.insertItem(0, current_family, current_family)

        matched_index = -1
        for index in range(self.chat_font_combo.count()):
            if self.chat_font_combo.itemData(index) == current_family:
                matched_index = index
                break

        if matched_index >= 0:
            self.chat_font_combo.setCurrentIndex(matched_index)
        else:
            self.chat_font_combo.setCurrentText(current_family)

    def _default_chat_font_family(self) -> str:
        language = str(getattr(self.settings, "language", "ko") or "ko").strip().lower()
        if language.startswith("ko"):
            return "맑은 고딕"
        return "Noto Sans"

    def _setup_chat_font_size_combo(self) -> None:
        self.chat_font_size_combo.clear()
        self.chat_font_size_combo.setEditable(True)
        self.chat_font_size_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.chat_font_size_combo.setPlaceholderText(self.localization.t("settings.chat_font.size_label"))
        self.chat_font_size_combo.lineEdit().setPlaceholderText(self.localization.t("settings.chat_font.size_label"))
        self.chat_font_size_combo.lineEdit().setValidator(QIntValidator(1, 200, self.chat_font_size_combo))
        sizes = [9, 10, 11, 12, 14, 16, 18, 20, 22, 24, 28, 32, 36, 40, 44, 48, 54, 60, 66, 72]
        for size in sizes:
            self.chat_font_size_combo.addItem(str(size), size)

        try:
            current_size = int(self.settings.chat_font_size or 10)
        except (TypeError, ValueError):
            current_size = 10
        current_size = max(1, min(200, current_size))
        if current_size not in sizes:
            self.chat_font_size_combo.addItem(str(current_size), current_size)

        for index in range(self.chat_font_size_combo.count()):
            if int(self.chat_font_size_combo.itemData(index)) == current_size:
                self.chat_font_size_combo.setCurrentIndex(index)
                break

    def _unique_model_names(self, model_names: list[str]) -> list[str]:
        unique_names: list[str] = []
        seen: set[str] = set()

        for model_name in model_names:
            text = str(model_name or "").strip()
            if not text:
                continue

            key = text.casefold()
            if key in seen:
                continue

            unique_names.append(text)
            seen.add(key)

        return unique_names

    def _populate_local_model_combo(self, preferred_model: str | None = None) -> None:
        if not hasattr(self, "local_model_combo"):
            return

        model_text = str(preferred_model or "").strip()
        if not model_text:
            model_text = str(getattr(self.settings, "local_model", "") or "").strip()
        if not model_text:
            model_text = AppSettings().local_model

        was_blocked = self.local_model_combo.blockSignals(True)
        try:
            self.local_model_combo.clear()

            for installed_model in self.installed_models:
                if self.local_model_combo.findText(installed_model) < 0:
                    self.local_model_combo.addItem(installed_model)

            if self.local_model_combo.findText(model_text) < 0:
                self.local_model_combo.addItem(model_text)

            index = self.local_model_combo.findText(model_text)
            if index >= 0:
                self.local_model_combo.setCurrentIndex(index)
            self.local_model_combo.setEditText(model_text)
        finally:
            self.local_model_combo.blockSignals(was_blocked)

    def refresh_installed_local_models(self, model_names: list[str], preferred_model: str | None = None) -> None:
        current_text = preferred_model or self.local_model_combo.currentText().strip()
        self.installed_models = self._unique_model_names(model_names)
        self._populate_local_model_combo(current_text)
        if hasattr(self, "style_model_edit"):
            self.style_model_edit.setText(self.local_model_combo.currentText().strip())

    def _create_model_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        description_label = QLabel(self.localization.t("settings.model.description"))
        description_label.setObjectName("SettingsDescriptionLabel")
        layout.addWidget(description_label)

        form_layout = QFormLayout()
        form_layout.setSpacing(10)

        self.local_ai_provider_combo = QComboBox()
        self.local_ai_provider_combo.addItem(
            self.localization.t("settings.local_ai.provider.ollama"),
            "ollama",
        )
        provider_index = self.local_ai_provider_combo.findData(self.settings.local_ai_provider)
        if provider_index >= 0:
            self.local_ai_provider_combo.setCurrentIndex(provider_index)
        self._finalize_combo_box(self.local_ai_provider_combo)

        self.local_ai_base_url_edit = QLineEdit()
        self.local_ai_base_url_edit.setText(self.settings.local_ai_base_url)

        # Use a combo box for selecting the local model so that the user can both
        # choose from existing models and type in a custom model name. The combo
        # box is set to be editable. The current text is initialised from the
        # saved settings. We call _finalize_combo_box to apply consistent
        # styling.
        self.local_model_combo = QComboBox()
        self.local_model_combo.setEditable(True)
        self._populate_local_model_combo(self.settings.local_model)
        self._finalize_combo_box(self.local_model_combo)

        self.style_model_edit = QLineEdit()
        # Disable manual editing of the style model. It should always match the local model.
        self.style_model_edit.setEnabled(False)
        self.style_model_edit.setText(self.local_model_combo.currentText().strip() or self.settings.local_model)
        # Mirror local model text into the style model field to keep them in sync.
        # Note: the connection to the editable combo box's line edit is set up after both widgets are created.

        self.runtime_install_policy_combo = QComboBox()
        self._setup_policy_combo(
            combo_box=self.runtime_install_policy_combo,
            items=[
                ("settings.runtime_install_policy.never", "never"),
                ("settings.runtime_install_policy.ask", "ask"),
            ],
            current_value=self.settings.runtime_install_policy,
        )

        self.model_install_policy_combo = QComboBox()
        self._setup_policy_combo(
            combo_box=self.model_install_policy_combo,
            items=[
                ("settings.model_install_policy.never", "never"),
                ("settings.model_install_policy.ask", "ask"),
                ("settings.model_install_policy.auto", "auto"),
            ],
            current_value=self.settings.model_install_policy,
        )

        self.auto_start_local_ai_server_checkbox = QCheckBox()
        self.auto_start_local_ai_server_checkbox.setChecked(
            self.settings.auto_start_local_ai_server
        )

        self.warn_large_local_model_checkbox = QCheckBox()
        self.warn_large_local_model_checkbox.setChecked(self.settings.warn_large_local_model)

        self.model_download_timeout_edit = QLineEdit()
        self.model_download_timeout_edit.setText(
            str(self.settings.model_download_timeout_seconds)
        )

        # Local model update configuration
        # Checkbox to enable or disable periodic update checks
        self.local_model_update_check_checkbox = QCheckBox()
        self.local_model_update_check_checkbox.setChecked(
            bool(self.settings.local_model_update_check_enabled)
        )
        # Input for the update check interval (in days). Use a line edit to
        # allow entry of numbers between 1 and 60. The actual value is
        # validated when saving the settings.
        self.local_model_update_interval_edit = QLineEdit()
        self.local_model_update_interval_edit.setText(
            str(self.settings.local_model_update_check_interval_days)
        )
        # Ensure the style model stays synchronized with the local model whenever the user edits or selects a model.
        # Using the currentTextChanged signal avoids issues where lineEdit() might be None on some platforms.
        self.local_model_combo.currentTextChanged.connect(self.style_model_edit.setText)

        self.local_model_download_button = QPushButton(
            self.localization.t("local_ai.model.download.button")
        )
        self.local_model_download_button.clicked.connect(
            self._request_local_model_prepare
        )

        # Button to manually trigger a model update check. This will use the
        # current local model selection and attempt to download the latest
        # version if one exists. The signal emitted is identical to the
        # download behaviour, but separated here for clarity in the UI.
        self.local_model_update_check_button = QPushButton(
            self.localization.t("local_ai.model.update.check.button")
        )
        self.local_model_update_check_button.clicked.connect(
            self._request_local_model_update
        )

        self.local_model_delete_button = QPushButton(
            self.localization.t("local_ai.model.delete.button")
        )
        self.local_model_delete_button.clicked.connect(
            self._request_local_model_delete
        )

        self.local_model_list_button = QPushButton(
            self.localization.t("local_ai.model.list.button")
        )
        self.local_model_list_button.clicked.connect(
            self._request_local_model_list
        )

        local_model_action_widget = QWidget()
        local_model_action_layout = QHBoxLayout(local_model_action_widget)
        local_model_action_layout.setContentsMargins(0, 0, 0, 0)
        local_model_action_layout.setSpacing(8)
        local_model_action_layout.addWidget(self.local_model_download_button)
        local_model_action_layout.addWidget(self.local_model_delete_button)
        local_model_action_layout.addWidget(self.local_model_list_button)
        local_model_action_layout.addWidget(self.local_model_update_check_button)
        local_model_action_layout.addStretch()

        form_layout.addRow(self.localization.t("settings.local_ai.provider"), self.local_ai_provider_combo)
        form_layout.addRow(self.localization.t("settings.local_ai.base_url"), self.local_ai_base_url_edit)
        # Show only a single input for the local model. The style model is derived
        # automatically from the local model and does not need a separate field.
        form_layout.addRow(self.localization.t("settings.model.local_ai"), self.local_model_combo)
        # Do not display the style model row. The style model field exists only
        # for internal synchronisation and is disabled.
        form_layout.addRow(self.localization.t("settings.runtime_install_policy"), self.runtime_install_policy_combo)
        form_layout.addRow(self.localization.t("settings.model_install_policy"), self.model_install_policy_combo)
        form_layout.addRow(self.localization.t("settings.auto_start_local_ai_server"), self.auto_start_local_ai_server_checkbox)
        form_layout.addRow(self.localization.t("settings.warn_large_local_model"), self.warn_large_local_model_checkbox)
        form_layout.addRow(self.localization.t("settings.model_download_timeout_seconds"), self.model_download_timeout_edit)
        # Local model update settings: enable/disable and interval
        form_layout.addRow(
            self.localization.t("settings.local_model_update_check_enabled"),
            self.local_model_update_check_checkbox,
        )
        form_layout.addRow(
            self.localization.t("settings.local_model_update_interval_days"),
            self.local_model_update_interval_edit,
        )
        form_layout.addRow("", local_model_action_widget)

        layout.addLayout(form_layout)

        note_label = QLabel(self.localization.t("settings.model.note"))
        note_label.setWordWrap(True)
        note_label.setObjectName("SettingsNoteLabel")
        layout.addWidget(note_label)

        layout.addStretch()

        return tab


    def _request_local_model_prepare(self) -> None:
        # Open a modal dialog allowing the user to choose or enter a local model
        # to download or update. The dialog presents a combo box populated with
        # known installed models and allows free text entry. The current model
        # selection is used as the default value.
        dlg = QDialog(self)
        # Use translated strings when available; fall back to a sensible default.
        dlg.setWindowTitle(
            self.localization.t("local_ai.model.download.title")
            or "Download Local Model"
        )
        vbox = QVBoxLayout(dlg)
        prompt_label = QLabel(
            self.localization.t("local_ai.model.download.prompt")
            or "Select or enter a model to download or update:"
        )
        prompt_label.setWordWrap(True)
        vbox.addWidget(prompt_label)
        combo = QComboBox(dlg)
        combo.setEditable(True)
        # Populate with installed models
        for name in self.installed_models:
            text = str(name or "").strip()
            if text:
                combo.addItem(text)
        # Use current local model as the default text
        try:
            combo.setEditText(self.local_model_combo.currentText())
        except AttributeError:
            if combo.count() == 0:
                combo.addItem(self.local_model_combo.currentText())
            combo.setCurrentIndex(0)
        vbox.addWidget(combo)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        vbox.addWidget(buttons)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        model_name = combo.currentText().strip()
        if not model_name:
            QMessageBox.warning(
                self,
                self.localization.t("settings.title"),
                self.localization.t("local_ai.model.empty"),
            )
            return
        # Use the existing timeout configuration
        try:
            timeout_seconds = float(self.model_download_timeout_edit.text().strip())
        except ValueError:
            timeout_seconds = float(AppSettings().model_download_timeout_seconds)
        timeout_seconds = max(30.0, timeout_seconds)
        auto_start_server = self.auto_start_local_ai_server_checkbox.isChecked()
        self.local_model_prepare_requested.emit(
            model_name,
            True,
            False,
            auto_start_server,
            timeout_seconds,
            False,
        )

    def _request_local_model_update(self) -> None:
        """
        Slot invoked when the user clicks the model update check button. This
        function retrieves the currently selected local model name and emits
        a request to prepare (download/update) the model. Unlike the normal
        download flow, this does not prompt the user to choose a different
        model; it simply uses the model selected in the main combo box. If
        the model name is empty, a warning is displayed. The timeout and
        auto-start server options mirror those used for the download button.
        """
        model_name = self.local_model_combo.currentText().strip()
        if not model_name:
            QMessageBox.warning(
                self,
                self.localization.t("settings.title"),
                self.localization.t("local_ai.model.empty"),
            )
            return
        try:
            timeout_seconds = float(self.model_download_timeout_edit.text().strip())
        except ValueError:
            timeout_seconds = float(AppSettings().model_download_timeout_seconds)
        timeout_seconds = max(30.0, timeout_seconds)
        auto_start_server = self.auto_start_local_ai_server_checkbox.isChecked()
        # Always use auto_pull=True for update checks so that the latest
        # revision of the model is retrieved if available. Auto-install
        # runtime is disabled to avoid reinstalling Ollama during update.
        self.local_model_prepare_requested.emit(
            model_name,
            True,
            False,
            auto_start_server,
            timeout_seconds,
            True,
        )

    def _request_local_model_delete(self) -> None:
        model_name = self.local_model_combo.currentText().strip()

        if not model_name:
            QMessageBox.warning(
                self,
                self.localization.t("settings.title"),
                self.localization.t("local_ai.model.empty"),
            )
            return

        result = QMessageBox.question(
            self,
            self.localization.t("settings.title"),
            self.localization.t(
                "local_ai.model.delete.confirm",
                model=model_name,
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if result != QMessageBox.StandardButton.Yes:
            return

        auto_start_server = self.auto_start_local_ai_server_checkbox.isChecked()
        self.local_model_delete_requested.emit(model_name, auto_start_server)

    def _request_local_model_list(self) -> None:
        auto_start_server = self.auto_start_local_ai_server_checkbox.isChecked()
        self.local_model_list_requested.emit(auto_start_server)

    def _create_cloud_ai_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        description_label = QLabel(self.localization.t("settings.cloud_ai.description"))
        description_label.setObjectName("SettingsDescriptionLabel")
        description_label.setWordWrap(True)
        layout.addWidget(description_label)

        form_layout = QFormLayout()
        form_layout.setSpacing(10)

        self.cloud_ai_enabled_checkbox = QCheckBox()
        self.cloud_ai_enabled_checkbox.setChecked(self.settings.cloud_ai_enabled)

        self.cloud_ai_provider_combo = QComboBox()
        self._setup_policy_combo(
            combo_box=self.cloud_ai_provider_combo,
            items=[
                ("settings.cloud_ai.provider.none", "none"),
                ("settings.cloud_ai.provider.openai", "openai"),
                ("settings.cloud_ai.provider.anthropic", "anthropic"),
                ("settings.cloud_ai.provider.gemini", "gemini"),
                ("settings.cloud_ai.provider.openrouter", "openrouter"),
                ("settings.cloud_ai.provider.custom", "custom"),
            ],
            current_value=self.settings.cloud_ai_provider,
        )

        self.cloud_ai_base_url_edit = QLineEdit()
        self.cloud_ai_base_url_edit.setText(self.settings.cloud_ai_base_url)
        self.cloud_ai_base_url_edit.setPlaceholderText(
            self.localization.t("settings.cloud_ai.base_url.placeholder")
        )

        self.cloud_ai_auth_mode_combo = QComboBox()
        self._setup_policy_combo(
            combo_box=self.cloud_ai_auth_mode_combo,
            items=[
                ("settings.cloud_ai.auth_mode.secure_store", "secure_store"),
                ("settings.cloud_ai.auth_mode.env_var", "env_var"),
            ],
            current_value=self.settings.cloud_ai_auth_mode,
        )

        self.cloud_ai_credential_id_edit = QLineEdit()
        self.cloud_ai_credential_id_edit.setText(self.settings.cloud_ai_credential_id)

        self.cloud_ai_api_key_edit = QLineEdit()
        self.cloud_ai_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.cloud_ai_api_key_edit.setPlaceholderText(
            self.localization.t("settings.cloud_ai.api_key.placeholder")
        )

        self.cloud_ai_api_key_env_edit = QLineEdit()
        self.cloud_ai_api_key_env_edit.setText(self.settings.cloud_ai_api_key_env)
        self.cloud_ai_api_key_env_edit.setPlaceholderText("OPENAI_API_KEY")

        self.cloud_ai_auth_input_stack = QStackedWidget()
        self.cloud_ai_auth_input_stack.addWidget(self.cloud_ai_api_key_edit)
        self.cloud_ai_auth_input_stack.addWidget(self.cloud_ai_api_key_env_edit)

        self.cloud_ai_api_key_status_label = QLabel()
        self.cloud_ai_api_key_status_label.setWordWrap(True)
        self.cloud_ai_api_key_status_label.setObjectName("SettingsNoteLabel")

        self.cloud_ai_api_key_page_button = QPushButton(
            self.localization.t("settings.cloud_ai.open_api_key_page")
        )
        self.cloud_ai_api_key_page_button.clicked.connect(self._open_cloud_ai_api_key_page)

        self.cloud_ai_save_api_key_button = QPushButton(
            self.localization.t("settings.cloud_ai.api_key.save")
        )
        self.cloud_ai_save_api_key_button.clicked.connect(self._save_cloud_ai_api_key)

        self.cloud_ai_delete_api_key_button = QPushButton(
            self.localization.t("settings.cloud_ai.api_key.delete")
        )
        self.cloud_ai_delete_api_key_button.clicked.connect(self._delete_cloud_ai_api_key)

        self.cloud_ai_test_button = QPushButton(
            self.localization.t("settings.cloud_ai.test_connection")
        )
        self.cloud_ai_test_button.clicked.connect(self._test_cloud_ai_connection)

        button_row = QWidget()
        button_layout = QHBoxLayout(button_row)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(8)
        button_layout.addWidget(self.cloud_ai_api_key_page_button)
        button_layout.addWidget(self.cloud_ai_save_api_key_button)
        button_layout.addWidget(self.cloud_ai_delete_api_key_button)
        button_layout.addWidget(self.cloud_ai_test_button)
        button_layout.addStretch()

        self.cloud_model_selected_label = QLabel(
            self.localization.t("settings.cloud_ai.selected_model.none")
        )
        self.cloud_model_selected_label.setObjectName("SelectedCloudModelLabel")
        self._selected_cloud_model_id = ""

        self.cloud_ai_models_list = QListWidget()
        self.cloud_ai_models_list.setMinimumHeight(132)
        self.cloud_ai_models_list.setAlternatingRowColors(True)
        self.cloud_ai_models_list.itemSelectionChanged.connect(
            self._on_cloud_ai_model_selection_changed
        )

        self.cloud_ai_refresh_models_button = QPushButton(
            self.localization.t("settings.cloud_ai.refresh_models")
        )
        self.cloud_ai_refresh_models_button.clicked.connect(
            self._refresh_cloud_ai_models_from_backend
        )

        self.cloud_ai_provider_combo.currentIndexChanged.connect(self._on_cloud_ai_provider_changed)
        self.cloud_ai_auth_mode_combo.currentIndexChanged.connect(self._update_cloud_ai_auth_mode_ui)

        self.cloud_ai_auth_input_label_widget = QLabel(
            self._cloud_ai_auth_input_label_text()
        )

        form_layout.addRow(self.localization.t("settings.cloud_ai.enabled"), self.cloud_ai_enabled_checkbox)
        form_layout.addRow(self.localization.t("settings.cloud_ai.provider"), self.cloud_ai_provider_combo)
        form_layout.addRow(self.localization.t("settings.cloud_ai.auth_mode"), self.cloud_ai_auth_mode_combo)
        form_layout.addRow(self.cloud_ai_auth_input_label_widget, self.cloud_ai_auth_input_stack)
        form_layout.addRow("", self.cloud_ai_api_key_status_label)
        form_layout.addRow("", button_row)
        self.cloud_ai_base_url_label_widget = QLabel(
            self.localization.t("settings.cloud_ai.base_url")
        )

        form_layout.addRow(self.localization.t("settings.cloud_ai.selected_model"), self.cloud_model_selected_label)
        form_layout.addRow("", self.cloud_ai_refresh_models_button)
        form_layout.addRow(self.localization.t("settings.cloud_ai.model_list"), self.cloud_ai_models_list)
        form_layout.addRow(self.cloud_ai_base_url_label_widget, self.cloud_ai_base_url_edit)

        layout.addLayout(form_layout)

        note_label = QLabel(self.localization.t("settings.cloud_ai.note"))
        note_label.setWordWrap(True)
        note_label.setObjectName("SettingsNoteLabel")
        layout.addWidget(note_label)

        layout.addStretch()

        self._sync_cloud_ai_model_list(preferred_model=self.settings.cloud_model)
        self._update_cloud_ai_auth_mode_ui()
        self._update_cloud_ai_api_key_page_button()
        self._update_cloud_ai_api_key_status()
        self._update_cloud_ai_base_url_visibility()

        return tab


    def _create_web_search_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        description_label = QLabel(self.localization.t("settings.web_search.description"))
        description_label.setObjectName("SettingsDescriptionLabel")
        description_label.setWordWrap(True)
        layout.addWidget(description_label)

        form_layout = QFormLayout()
        form_layout.setSpacing(10)

        self.web_search_enabled_checkbox = QCheckBox()
        self.web_search_enabled_checkbox.setChecked(bool(self.settings.web_search_enabled))

        self.web_search_auto_enabled_checkbox = QCheckBox()
        self.web_search_auto_enabled_checkbox.setChecked(bool(self.settings.web_search_auto_enabled))

        self.web_search_provider_combo = QComboBox()
        self._setup_policy_combo(
            self.web_search_provider_combo,
            [
                ("settings.web_search.provider.none", "none"),
                ("settings.web_search.provider.tavily", "tavily"),
                ("settings.web_search.provider.firecrawl", "firecrawl"),
            ],
            self.settings.web_search_provider,
        )

        self.web_search_auth_mode_combo = QComboBox()
        self._setup_policy_combo(
            self.web_search_auth_mode_combo,
            [
                ("settings.cloud_ai.auth_mode.secure_store", "secure_store"),
                ("settings.cloud_ai.auth_mode.env_var", "env_var"),
            ],
            self.settings.web_search_auth_mode,
        )

        self.web_search_credential_id_edit = QLineEdit()
        self.web_search_credential_id_edit.setText(self.settings.web_search_credential_id)

        self.web_search_api_key_edit = QLineEdit()
        self.web_search_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.web_search_api_key_edit.setPlaceholderText(
            self.localization.t("settings.cloud_ai.api_key.placeholder")
        )

        self.web_search_api_key_env_edit = QLineEdit()
        self.web_search_api_key_env_edit.setText(self.settings.web_search_api_key_env)
        self.web_search_api_key_env_edit.setPlaceholderText("TAVILY_API_KEY")

        self.web_search_auth_input_stack = QStackedWidget()
        self.web_search_auth_input_stack.addWidget(self.web_search_api_key_edit)
        self.web_search_auth_input_stack.addWidget(self.web_search_api_key_env_edit)

        self.web_search_auth_input_label_widget = QLabel(
            self._web_search_auth_input_label_text()
        )

        self.web_search_base_url_edit = QLineEdit()
        self.web_search_base_url_edit.setText(self.settings.web_search_base_url)
        self.web_search_base_url_edit.setPlaceholderText(
            self.localization.t("settings.web_search.base_url.placeholder")
        )

        self.web_search_max_results_edit = QLineEdit()
        self.web_search_max_results_edit.setText(str(self.settings.web_search_max_results))

        self.web_search_timeout_edit = QLineEdit()
        self.web_search_timeout_edit.setText(str(self.settings.web_search_timeout_seconds))

        self.web_search_api_key_status_label = QLabel()
        self.web_search_api_key_status_label.setWordWrap(True)
        self.web_search_api_key_status_label.setObjectName("SettingsNoteLabel")

        self.web_search_api_key_page_button = QPushButton(
            self.localization.t("settings.web_search.open_api_key_page")
        )
        self.web_search_api_key_page_button.clicked.connect(self._open_web_search_api_key_page)

        self.web_search_save_api_key_button = QPushButton(
            self.localization.t("settings.cloud_ai.api_key.save")
        )
        self.web_search_save_api_key_button.clicked.connect(self._save_web_search_api_key)

        self.web_search_delete_api_key_button = QPushButton(
            self.localization.t("settings.cloud_ai.api_key.delete")
        )
        self.web_search_delete_api_key_button.clicked.connect(self._delete_web_search_api_key)

        button_row = QWidget()
        button_layout = QHBoxLayout(button_row)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(8)
        button_layout.addWidget(self.web_search_api_key_page_button)
        button_layout.addWidget(self.web_search_save_api_key_button)
        button_layout.addWidget(self.web_search_delete_api_key_button)
        button_layout.addStretch()

        self.web_search_provider_combo.currentIndexChanged.connect(self._on_web_search_provider_changed)
        self.web_search_auth_mode_combo.currentIndexChanged.connect(self._update_web_search_auth_mode_ui)

        form_layout.addRow(self.localization.t("settings.web_search.enabled"), self.web_search_enabled_checkbox)
        form_layout.addRow(self.localization.t("settings.web_search.auto_enabled"), self.web_search_auto_enabled_checkbox)
        form_layout.addRow(self.localization.t("settings.web_search.provider"), self.web_search_provider_combo)
        form_layout.addRow(self.localization.t("settings.cloud_ai.auth_mode"), self.web_search_auth_mode_combo)
        form_layout.addRow(self.web_search_auth_input_label_widget, self.web_search_auth_input_stack)
        form_layout.addRow(self.localization.t("settings.cloud_ai.credential_id"), self.web_search_credential_id_edit)
        form_layout.addRow("", self.web_search_api_key_status_label)
        form_layout.addRow("", button_row)
        form_layout.addRow(self.localization.t("settings.web_search.base_url"), self.web_search_base_url_edit)
        form_layout.addRow(self.localization.t("settings.web_search.max_results"), self.web_search_max_results_edit)
        form_layout.addRow(self.localization.t("settings.web_search.timeout_seconds"), self.web_search_timeout_edit)

        layout.addLayout(form_layout)

        note_label = QLabel(self.localization.t("settings.web_search.note"))
        note_label.setWordWrap(True)
        note_label.setObjectName("SettingsNoteLabel")
        layout.addWidget(note_label)

        layout.addStretch()

        self._update_web_search_auth_mode_ui()
        self._update_web_search_api_key_page_button()
        self._update_web_search_api_key_status()
        self._connect_web_search_setting_change_handlers()
        self._apply_web_search_controls_to_settings()

        return tab

    def _create_advanced_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        description_label = QLabel(self.localization.t("settings.advanced.description"))
        description_label.setObjectName("SettingsDescriptionLabel")
        layout.addWidget(description_label)

        form_layout = QFormLayout()
        form_layout.setSpacing(10)

        self.developer_mode_checkbox = QCheckBox()
        self.developer_mode_checkbox.setChecked(self.settings.developer_mode)

        self.enable_tray_icon_checkbox = QCheckBox()
        self.enable_tray_icon_checkbox.setChecked(
            bool(getattr(self.settings, "enable_tray_icon", True))
        )

        self.close_button_behavior_combo = QComboBox()
        self.close_button_behavior_combo.addItem(
            self.localization.t("settings.close_button_behavior.exit"),
            "exit",
        )
        self.close_button_behavior_combo.addItem(
            self.localization.t("settings.close_button_behavior.minimize_to_tray"),
            "minimize_to_tray",
        )
        close_behavior = str(
            getattr(self.settings, "close_button_behavior", "minimize_to_tray")
            or "minimize_to_tray"
        ).strip()
        close_behavior_index = self.close_button_behavior_combo.findData(close_behavior)
        if close_behavior_index < 0:
            close_behavior_index = self.close_button_behavior_combo.findData("minimize_to_tray")
        if close_behavior_index >= 0:
            self.close_button_behavior_combo.setCurrentIndex(close_behavior_index)

        self.cloud_ai_usage_slider = QSlider(Qt.Orientation.Horizontal)
        self.cloud_ai_usage_slider.setMinimum(0)
        self.cloud_ai_usage_slider.setMaximum(100)
        self.cloud_ai_usage_slider.setSingleStep(5)
        self.cloud_ai_usage_slider.setPageStep(5)
        self.cloud_ai_usage_slider.setTickInterval(5)
        self.cloud_ai_usage_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        current_cloud_weight = int(getattr(self.settings, "cloud_ai_usage_weight_percent", 50) or 50)
        current_cloud_weight = max(0, min(100, round(current_cloud_weight / 5) * 5))
        self.cloud_ai_usage_slider.setValue(current_cloud_weight)
        self.cloud_ai_usage_label = QLabel(f"{current_cloud_weight}%")
        self.cloud_ai_usage_label.setObjectName("CloudAIWeightValueLabel")
        self.cloud_ai_usage_slider.valueChanged.connect(self._on_cloud_ai_usage_weight_changed)

        self.expand_chat_checkbox = QCheckBox()
        self.expand_chat_checkbox.setChecked(self.settings.expand_chat_over_character_area)

        self.embarrassed_when_occluded_checkbox = QCheckBox()
        self.embarrassed_when_occluded_checkbox.setChecked(
            self.settings.enable_avatar_embarrassed_when_occluded
        )

        self.avatar_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.avatar_opacity_slider.setMinimum(10)
        self.avatar_opacity_slider.setMaximum(100)
        self.avatar_opacity_slider.setSingleStep(10)
        self.avatar_opacity_slider.setPageStep(10)
        self.avatar_opacity_slider.setTickInterval(10)
        self.avatar_opacity_slider.setTickPosition(QSlider.TickPosition.TicksBelow)

        current_opacity_percent = round(self.settings.avatar_occluded_opacity * 100)
        current_opacity_percent = min(100, max(10, current_opacity_percent))
        current_opacity_percent = round(current_opacity_percent / 10) * 10

        self.avatar_opacity_slider.setValue(current_opacity_percent)

        self.avatar_opacity_label = QLabel(f"{current_opacity_percent}%")
        self.avatar_opacity_label.setObjectName("OpacityValueLabel")

        self.avatar_opacity_slider.valueChanged.connect(self._on_avatar_opacity_changed)

        form_layout.addRow(self.localization.t("settings.developer_mode"), self.developer_mode_checkbox)
        form_layout.addRow(self.localization.t("settings.enable_tray_icon"), self.enable_tray_icon_checkbox)
        form_layout.addRow(self.localization.t("settings.close_button_behavior"), self.close_button_behavior_combo)

        cloud_weight_widget = QWidget()
        cloud_weight_layout = QVBoxLayout(cloud_weight_widget)
        cloud_weight_layout.setContentsMargins(0, 0, 0, 0)
        cloud_weight_layout.setSpacing(4)
        cloud_weight_layout.addWidget(self.cloud_ai_usage_slider)
        cloud_weight_layout.addWidget(self.cloud_ai_usage_label)
        form_layout.addRow(self.localization.t("settings.cloud_ai_usage_weight"), cloud_weight_widget)

        form_layout.addRow(self.localization.t("settings.expand_chat_over_character_area"), self.expand_chat_checkbox)
        form_layout.addRow(self.localization.t("settings.avatar_embarrassed_when_occluded"), self.embarrassed_when_occluded_checkbox)

        opacity_widget = QWidget()
        opacity_layout = QVBoxLayout(opacity_widget)
        opacity_layout.setContentsMargins(0, 0, 0, 0)
        opacity_layout.setSpacing(4)
        opacity_layout.addWidget(self.avatar_opacity_slider)
        opacity_layout.addWidget(self.avatar_opacity_label)

        form_layout.addRow(self.localization.t("settings.avatar_occluded_opacity"), opacity_widget)

        layout.addLayout(form_layout)

        expand_description = QLabel(
            self.localization.t("settings.expand_chat_over_character_area.description")
        )
        expand_description.setWordWrap(True)
        expand_description.setObjectName("SettingsNoteLabel")
        layout.addWidget(expand_description)

        opacity_description = QLabel(
            self.localization.t("settings.avatar_occluded_opacity.description")
        )
        opacity_description.setWordWrap(True)
        opacity_description.setObjectName("SettingsNoteLabel")
        layout.addWidget(opacity_description)

        cloud_weight_description = QLabel(
            self.localization.t("settings.cloud_ai_usage_weight.description")
        )
        cloud_weight_description.setWordWrap(True)
        cloud_weight_description.setObjectName("SettingsNoteLabel")
        layout.addWidget(cloud_weight_description)

        close_behavior_description = QLabel(
            self.localization.t("settings.close_button_behavior.description")
        )
        close_behavior_description.setWordWrap(True)
        close_behavior_description.setObjectName("SettingsNoteLabel")
        layout.addWidget(close_behavior_description)

        layout.addStretch()

        return tab

    def _setup_policy_combo(
        self,
        combo_box: QComboBox,
        items: list[tuple[str, str]],
        current_value: str,
    ) -> None:
        for label_key, value in items:
            combo_box.addItem(self.localization.t(label_key), value)

        index = combo_box.findData(current_value)
        if index >= 0:
            combo_box.setCurrentIndex(index)

        self._finalize_combo_box(combo_box)

    def _setup_language_combo(self) -> None:
        for language in self.localization.available_languages:
            display_name = self._language_display_name(language)
            self.language_combo.addItem(display_name, language)

        index = self.language_combo.findData(self.settings.language)
        if index >= 0:
            self.language_combo.setCurrentIndex(index)

        self._finalize_combo_box(self.language_combo)

    def _setup_user_country_combo(self) -> None:
        items = [
            ("settings.user_country.auto_language", "auto_language"),
            ("settings.user_country.kr", "kr"),
            ("settings.user_country.jp", "jp"),
            ("settings.user_country.us", "us"),
            ("settings.user_country.eu", "eu"),
            ("settings.user_country.custom_option", "custom"),
            ("settings.user_country.ip_auto", "ip_auto"),
        ]
        for label_key, value in items:
            self.user_country_combo.addItem(self.localization.t(label_key), value)

        index = self.user_country_combo.findData(self.settings.user_country_preset)
        if index < 0:
            index = self.user_country_combo.findData("auto_language")
        if index >= 0:
            self.user_country_combo.setCurrentIndex(index)

        self._finalize_combo_box(self.user_country_combo)

    def _setup_preferred_unit_system_combo(self) -> None:
        items = [
            ("settings.preferred_unit_system.metric", "metric"),
            ("settings.preferred_unit_system.imperial", "imperial"),
        ]
        for label_key, value in items:
            self.preferred_unit_system_combo.addItem(self.localization.t(label_key), value)

        current_value = str(
            getattr(self.settings, "preferred_unit_system", AppSettings().preferred_unit_system)
            or AppSettings().preferred_unit_system
        ).strip().lower()
        index = self.preferred_unit_system_combo.findData(current_value)
        if index < 0:
            index = self.preferred_unit_system_combo.findData(AppSettings().preferred_unit_system)
        if index >= 0:
            self.preferred_unit_system_combo.setCurrentIndex(index)

        self._finalize_combo_box(self.preferred_unit_system_combo)

    def _country_region_for_preset(self, preset: str, language: str | None = None) -> tuple[str, str, str]:
        normalized = (preset or "auto_language").strip().lower()
        if normalized == "auto_language":
            app_language = (language or self.language_combo.currentData() or self.settings.language or "ko").lower()
            normalized = "kr" if app_language.startswith("ko") else "us"

        mapping = {
            "kr": ("KR", "South Korea", "south korea"),
            "jp": ("JP", "Japan", "japan"),
            "us": ("US", "United States", "united states"),
            # Europe is a broad region. Firecrawl can use location="Europe"; Tavily only accepts countries,
            # so leave tavily_country empty instead of forcing one European country.
            "eu": ("", "Europe", ""),
        }
        return mapping.get(normalized, ("", "", ""))

    def _format_user_country_text(self, country_code: str, location: str) -> str:
        code = str(country_code or "").strip().upper()
        loc = str(location or "").strip()
        if code and loc:
            return f"{code} - {loc}"
        return code or loc

    def _parse_user_country_input(self, text: str) -> tuple[str, str]:
        value = str(text or "").strip()
        if not value:
            return "", ""

        if "-" in value:
            left, right = value.split("-", 1)
            code = left.strip().upper()
            location = right.strip()
            if len(code) == 2 and code.isalpha():
                return code, location

        if len(value) == 2 and value.isalpha():
            code = value.upper()
            location = {
                "KR": "South Korea",
                "JP": "Japan",
                "US": "United States",
                "DE": "Germany",
                "FR": "France",
                "GB": "United Kingdom",
                "UK": "United Kingdom",
            }.get(code, "")
            return code, location

        return "", value

    def _update_user_country_ui(self) -> None:
        if not hasattr(self, "user_country_combo"):
            return

        preset = self.user_country_combo.currentData() or "auto_language"
        custom_enabled = preset == "custom"
        ip_enabled = preset == "ip_auto"

        self.user_country_location_edit.setEnabled(custom_enabled)
        self.user_country_detect_button.setEnabled(ip_enabled)

        if preset == "custom":
            return

        if preset == "ip_auto":
            text = self._format_user_country_text(
                self.settings.user_country_code,
                self.settings.user_country_location,
            )
            self.user_country_location_edit.setText(text)
            return

        code, location, _ = self._country_region_for_preset(preset)
        self.user_country_location_edit.setText(self._format_user_country_text(code, location))

    def _detect_user_country_by_ip(self) -> None:
        providers = (
            (
                "ipapi",
                "https://ipapi.co/json/",
                lambda data: (
                    str(data.get("country_code") or data.get("country") or "").strip().upper(),
                    str(data.get("country_name") or "").strip(),
                ),
            ),
            (
                "ipwho.is",
                "https://ipwho.is/",
                lambda data: (
                    str(data.get("country_code") or "").strip().upper(),
                    str(data.get("country") or "").strip(),
                ),
            ),
            (
                "country.is",
                "https://api.country.is/",
                lambda data: (
                    str(data.get("country") or "").strip().upper(),
                    "",
                ),
            ),
        )

        errors: list[str] = []
        country_code = ""
        country_name = ""
        selected_provider = ""

        for provider_name, url, parser in providers:
            try:
                response = httpx.get(url, timeout=8.0)
                response.raise_for_status()
                data = response.json()
                parsed_code, parsed_name = parser(data if isinstance(data, dict) else {})
                parsed_code = str(parsed_code or "").strip().upper()
                parsed_name = str(parsed_name or "").strip()
                if parsed_code or parsed_name:
                    country_code = parsed_code
                    country_name = parsed_name or self._country_name_from_code(parsed_code)
                    selected_provider = provider_name
                    break
                errors.append(f"{provider_name}: empty country response")
            except Exception as error:
                errors.append(f"{provider_name}: {error}")

        if not country_code and not country_name:
            detail = "; ".join(errors) if errors else "unknown error"
            QMessageBox.warning(
                self,
                self.localization.t("settings.user_country.detect_ip.title"),
                self.localization.t("settings.user_country.detect_ip.failed").format(error=detail),
            )
            return

        self.settings.user_country_code = country_code
        self.settings.user_country_location = country_name
        self.user_country_location_edit.setText(self._format_user_country_text(country_code, country_name))
        completed_text = self.localization.t("settings.user_country.detect_ip.completed").format(
            country=self._format_user_country_text(country_code, country_name)
        )
        if selected_provider:
            completed_text += f"\n(provider: {selected_provider})"
        QMessageBox.information(
            self,
            self.localization.t("settings.user_country.detect_ip.title"),
            completed_text,
        )

    def _country_name_from_code(self, country_code: str) -> str:
        code = str(country_code or "").strip().upper()
        return {
            "KR": "South Korea",
            "JP": "Japan",
            "US": "United States",
            "DE": "Germany",
            "FR": "France",
            "GB": "United Kingdom",
            "UK": "United Kingdom",
        }.get(code, "")

    def _setup_theme_combo(self) -> None:
        self.theme_combo.addItem(self.localization.t("settings.theme.character"), "character")

        for theme_id in self.theme_manager.available_theme_ids():
            theme = self.theme_manager.get_theme(theme_id)
            self.theme_combo.addItem(theme.name, theme.id)

        index = self.theme_combo.findData(self.settings.theme_id)
        if index >= 0:
            self.theme_combo.setCurrentIndex(index)

        self._finalize_combo_box(self.theme_combo)

    def _setup_character_combo(self) -> None:
        self.character_combo.clear()
        for pack in self.character_registry.packs:
            source_label = (
                self.localization.t("settings.character.builtin.short")
                if self.character_registry.is_builtin(pack.id)
                else self.localization.t("settings.character.user.short")
            )
            display_name = f"{pack.name} ({source_label})"
            self.character_combo.addItem(display_name, pack.id)

        index = self.character_combo.findData(self.settings.selected_character_id)
        if index < 0:
            default_pack = self.character_registry.get_default_pack()
            if default_pack is not None:
                index = self.character_combo.findData(default_pack.id)

        if index >= 0:
            self.character_combo.setCurrentIndex(index)

        self._finalize_combo_box(self.character_combo)

    def _reload_character_packs(self) -> None:
        current_character_id = self.character_combo.currentData()
        if current_character_id is None:
            current_character_id = self.settings.selected_character_id

        self.character_registry.load()
        self.character_registry_reloaded = True

        self.character_combo.blockSignals(True)
        self.character_combo.clear()
        for pack in self.character_registry.packs:
            source_label = (
                self.localization.t("settings.character.builtin.short")
                if self.character_registry.is_builtin(pack.id)
                else self.localization.t("settings.character.user.short")
            )
            self.character_combo.addItem(f"{pack.name} ({source_label})", pack.id)

        index = self.character_combo.findData(current_character_id)
        if index < 0:
            default_pack = self.character_registry.get_default_pack()
            if default_pack is not None:
                index = self.character_combo.findData(default_pack.id)

        if index >= 0:
            self.character_combo.setCurrentIndex(index)

        self.character_combo.blockSignals(False)
        self._update_character_info_label()

        QMessageBox.information(
            self,
            self.localization.t("settings.title"),
            self.localization.t(
                "settings.character.reload.completed",
                count=len(self.character_registry.packs),
            ),
        )

    def _on_avatar_opacity_changed(self, value: int) -> None:
        snapped_value = round(value / 10) * 10
        snapped_value = min(100, max(10, snapped_value))

        if snapped_value != value:
            self.avatar_opacity_slider.blockSignals(True)
            self.avatar_opacity_slider.setValue(snapped_value)
            self.avatar_opacity_slider.blockSignals(False)

        self.avatar_opacity_label.setText(f"{snapped_value}%")
        self.avatar_opacity_preview_changed.emit(snapped_value / 100.0)

    def _on_cloud_ai_usage_weight_changed(self, value: int) -> None:
        snapped_value = round(value / 5) * 5
        snapped_value = min(100, max(0, snapped_value))

        if snapped_value != value:
            self.cloud_ai_usage_slider.blockSignals(True)
            self.cloud_ai_usage_slider.setValue(snapped_value)
            self.cloud_ai_usage_slider.blockSignals(False)

        self.cloud_ai_usage_label.setText(f"{snapped_value}%")
        self.settings.cloud_ai_usage_weight_percent = snapped_value

    def _on_cloud_ai_provider_changed(self) -> None:
        if not hasattr(self, "cloud_ai_provider_combo"):
            return

        provider = self.cloud_ai_provider_combo.currentData() or "openai"
        defaults = self._cloud_ai_provider_defaults(provider)

        if hasattr(self, "cloud_ai_api_key_env_edit"):
            current_env = self.cloud_ai_api_key_env_edit.text().strip()
            if current_env in self._known_cloud_api_key_env_names():
                self.cloud_ai_api_key_env_edit.setText(str(defaults.get("api_key_env", "")))

        if hasattr(self, "cloud_ai_credential_id_edit"):
            current_credential_id = self.cloud_ai_credential_id_edit.text().strip()
            if current_credential_id in self._known_cloud_credential_ids():
                self.cloud_ai_credential_id_edit.setText(str(defaults.get("credential_id", "")))

        if hasattr(self, "cloud_ai_base_url_edit"):
            current_base_url = self.cloud_ai_base_url_edit.text().strip()
            if current_base_url in self._known_cloud_base_urls():
                self.cloud_ai_base_url_edit.setText(str(defaults.get("base_url", "")))

        self._sync_cloud_ai_model_list(preferred_model="")
        self._update_cloud_ai_auth_mode_ui()
        self._update_cloud_ai_api_key_page_button()
        self._update_cloud_ai_api_key_status()
        self._update_cloud_ai_base_url_visibility()

    def _on_cloud_ai_model_selection_changed(self) -> None:
        if self._updating_cloud_model_combo:
            return

        selected_items = self.cloud_ai_models_list.selectedItems()
        if not selected_items:
            self._set_selected_cloud_model("")
            return

        model_id = selected_items[0].data(Qt.ItemDataRole.UserRole)
        if model_id is None:
            model_id = selected_items[0].text().strip()

        self._set_selected_cloud_model(str(model_id).strip())

    def _sync_cloud_ai_model_list(self, preferred_model: str | None = None) -> None:
        if not hasattr(self, "cloud_ai_models_list"):
            return

        provider = self.cloud_ai_provider_combo.currentData() or self.settings.cloud_ai_provider
        default_models = [
            str(model)
            for model in self._cloud_ai_provider_defaults(provider).get("models", [])
            if str(model).strip()
        ]

        models: list[str] = []
        for model in self.settings.cloud_ai_models:
            model_text = str(model).strip()
            if model_text and model_text not in models:
                models.append(model_text)

        # If the list still looks like one of the built-in provider defaults, switch it to the
        # currently selected provider's default model list. This keeps provider switching intuitive.
        if self._is_default_cloud_model_list(models) or not models:
            models = list(default_models)

        if preferred_model is None:
            preferred_model = self._selected_cloud_model()
        preferred_model = str(preferred_model or "").strip()

        self._updating_cloud_model_combo = True
        self.cloud_ai_models_list.clear()
        for model in models:
            self.cloud_ai_models_list.addItem(model)
            item = self.cloud_ai_models_list.item(self.cloud_ai_models_list.count() - 1)
            item.setData(Qt.ItemDataRole.UserRole, model)

        if preferred_model:
            matching_items = self.cloud_ai_models_list.findItems(
                preferred_model,
                Qt.MatchFlag.MatchExactly,
            )
            if matching_items:
                self.cloud_ai_models_list.setCurrentItem(matching_items[0])
                self._set_selected_cloud_model(preferred_model)
            else:
                self.cloud_ai_models_list.clearSelection()
                self._set_selected_cloud_model("")
        else:
            self.cloud_ai_models_list.clearSelection()
            self._set_selected_cloud_model("")

        self._updating_cloud_model_combo = False

    def _set_selected_cloud_model(self, model_id: str) -> None:
        model_id = model_id.strip()
        self._selected_cloud_model_id = model_id

        if not hasattr(self, "cloud_model_selected_label"):
            return

        if model_id:
            self.cloud_model_selected_label.setText(f"<b>{model_id}</b>")
        else:
            self.cloud_model_selected_label.setText(
                self.localization.t("settings.cloud_ai.selected_model.none")
            )

    def _current_cloud_ai_model_list(self) -> list[str]:
        if not hasattr(self, "cloud_ai_models_list"):
            return list(self.settings.cloud_ai_models)

        models: list[str] = []
        for row in range(self.cloud_ai_models_list.count()):
            item = self.cloud_ai_models_list.item(row)
            model = str(item.data(Qt.ItemDataRole.UserRole) or item.text()).strip()
            if model and model not in models:
                models.append(model)

        return models

    def _cloud_ai_provider_defaults(self, provider: str) -> dict[str, object]:
        return cloud_ai_provider_defaults(provider)

    def _default_cloud_api_key_env(self, provider: str) -> str:
        return default_cloud_api_key_env(provider)

    def _default_cloud_credential_id(self, provider: str) -> str:
        return default_cloud_credential_id(provider)

    def _known_cloud_api_key_env_names(self) -> set[str]:
        return {
            str(self._cloud_ai_provider_defaults(provider).get("api_key_env", ""))
            for provider in self._known_cloud_provider_ids()
        }

    def _known_cloud_credential_ids(self) -> set[str]:
        return {
            str(self._cloud_ai_provider_defaults(provider).get("credential_id", ""))
            for provider in self._known_cloud_provider_ids()
        }

    def _known_cloud_base_urls(self) -> set[str]:
        return {
            str(self._cloud_ai_provider_defaults(provider).get("base_url", ""))
            for provider in self._known_cloud_provider_ids()
        }

    def _is_default_cloud_model_list(self, models: list[str]) -> bool:
        known_model_lists = {
            tuple(str(model) for model in self._cloud_ai_provider_defaults(provider).get("models", []))
            for provider in self._known_cloud_provider_ids()
        }
        return tuple(models) in known_model_lists

    def _known_cloud_provider_ids(self) -> tuple[str, ...]:
        return KNOWN_CLOUD_PROVIDER_IDS

    def _current_cloud_auth_config(self) -> CloudCredentialConfig:
        provider = self.cloud_ai_provider_combo.currentData() or "openai"
        return CloudCredentialConfig(
            provider=provider,
            auth_mode=self.cloud_ai_auth_mode_combo.currentData() or "secure_store",
            credential_id=self.cloud_ai_credential_id_edit.text().strip()
            or self._default_cloud_credential_id(provider),
            api_key_env=self.cloud_ai_api_key_env_edit.text().strip() or None,
        )

    def _cloud_ai_auth_input_label_text(self) -> str:
        if not hasattr(self, "cloud_ai_auth_mode_combo"):
            return self.localization.t("settings.cloud_ai.api_key")

        auth_mode = self.cloud_ai_auth_mode_combo.currentData() or "secure_store"
        if auth_mode == "env_var":
            return self.localization.t("settings.cloud_ai.api_key_env")

        return self.localization.t("settings.cloud_ai.api_key")

    def _update_cloud_ai_auth_mode_ui(self) -> None:
        if not hasattr(self, "cloud_ai_auth_mode_combo"):
            return

        auth_mode = self.cloud_ai_auth_mode_combo.currentData() or "secure_store"
        secure_store_enabled = auth_mode == "secure_store"
        env_var_enabled = auth_mode == "env_var"

        self.cloud_ai_auth_input_stack.setCurrentIndex(0 if secure_store_enabled else 1)
        self.cloud_ai_credential_id_edit.setEnabled(secure_store_enabled)
        self.cloud_ai_api_key_edit.setEnabled(secure_store_enabled)
        self.cloud_ai_save_api_key_button.setVisible(secure_store_enabled)
        self.cloud_ai_delete_api_key_button.setVisible(secure_store_enabled)
        self.cloud_ai_api_key_env_edit.setEnabled(env_var_enabled)

        if hasattr(self, "cloud_ai_auth_input_label_widget"):
            self.cloud_ai_auth_input_label_widget.setText(
                self._cloud_ai_auth_input_label_text()
            )

        self._update_cloud_ai_api_key_status()

    def _update_cloud_ai_api_key_status(self) -> None:
        if not hasattr(self, "cloud_ai_api_key_status_label"):
            return

        config = self._current_cloud_auth_config()
        auth_mode = config.auth_mode

        if auth_mode == "env_var":
            if config.api_key_env:
                self.cloud_ai_api_key_status_label.setText(
                    self.localization.t(
                        "settings.cloud_ai.api_key.status.env_var",
                        env=config.api_key_env,
                    )
                )
            else:
                self.cloud_ai_api_key_status_label.setText(
                    self.localization.t("settings.cloud_ai.api_key.status.missing")
                )
            return

        try:
            has_key = CloudAuthManager.has_api_key(config)
        except Exception:
            has_key = False

        if has_key:
            self.cloud_ai_api_key_status_label.setText(
                self.localization.t("settings.cloud_ai.api_key.status.saved")
            )
        else:
            self.cloud_ai_api_key_status_label.setText(
                self.localization.t("settings.cloud_ai.api_key.status.not_saved")
            )

    def _update_cloud_ai_base_url_visibility(self) -> None:
        if not hasattr(self, "cloud_ai_base_url_edit"):
            return

        provider = self.cloud_ai_provider_combo.currentData() or "openai"
        # For built-in providers, Base URL is an internal default and should not be a basic user setting.
        # Keep the field visible only for Custom provider.
        is_custom_provider = provider == "custom"
        self.cloud_ai_base_url_edit.setVisible(is_custom_provider)
        if hasattr(self, "cloud_ai_base_url_label_widget"):
            self.cloud_ai_base_url_label_widget.setVisible(is_custom_provider)

    def _save_cloud_ai_api_key(self) -> None:
        config = self._current_cloud_auth_config()
        api_key = self.cloud_ai_api_key_edit.text().strip()

        if not api_key:
            QMessageBox.warning(
                self,
                self.localization.t("settings.cloud_ai.message.title"),
                self.localization.t("settings.cloud_ai.api_key.empty"),
            )
            return

        try:
            CloudAuthManager.save_api_key(config.credential_id, api_key)
        except Exception as error:
            QMessageBox.critical(
                self,
                self.localization.t("settings.cloud_ai.message.title"),
                self.localization.t(
                    "settings.cloud_ai.api_key.save_failed",
                    error=str(error),
                ),
            )
            return

        self.cloud_ai_api_key_edit.clear()
        self._update_cloud_ai_api_key_status()
        QMessageBox.information(
            self,
            self.localization.t("settings.cloud_ai.message.title"),
            self.localization.t("settings.cloud_ai.api_key.saved"),
        )

    def _delete_cloud_ai_api_key(self) -> None:
        config = self._current_cloud_auth_config()

        try:
            CloudAuthManager.delete_api_key(config.credential_id)
        except Exception as error:
            QMessageBox.critical(
                self,
                self.localization.t("settings.cloud_ai.message.title"),
                self.localization.t(
                    "settings.cloud_ai.api_key.delete_failed",
                    error=str(error),
                ),
            )
            return

        self._update_cloud_ai_api_key_status()
        QMessageBox.information(
            self,
            self.localization.t("settings.cloud_ai.message.title"),
            self.localization.t("settings.cloud_ai.api_key.deleted"),
        )

    def _test_cloud_ai_connection(self) -> None:
        config = self._current_cloud_auth_config()

        if config.auth_mode == "secure_store" and self.cloud_ai_api_key_edit.text().strip():
            QMessageBox.warning(
                self,
                self.localization.t("settings.cloud_ai.message.title"),
                self.localization.t("settings.cloud_ai.test.save_first"),
            )
            return

        try:
            response = httpx.post(
                "http://127.0.0.1:10420/cloud-ai/test-connection",
                json={
                    "provider": config.provider,
                    "auth_mode": config.auth_mode,
                    "credential_id": config.credential_id,
                    "api_key_env": config.api_key_env,
                    "base_url": self.cloud_ai_base_url_edit.text().strip(),
                    "model": self._selected_cloud_model(),
                },
                timeout=15.0,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as error:
            QMessageBox.critical(
                self,
                self.localization.t("settings.cloud_ai.message.title"),
                self.localization.t(
                    "settings.cloud_ai.test.request_failed",
                    error=str(error),
                ),
            )
            return

        if data.get("ok"):
            QMessageBox.information(
                self,
                self.localization.t("settings.cloud_ai.message.title"),
                self.localization.t("settings.cloud_ai.test.succeeded"),
            )
            return

        QMessageBox.warning(
            self,
            self.localization.t("settings.cloud_ai.message.title"),
            self.localization.t(
                "settings.cloud_ai.test.failed",
                error=(
                    data.get("error_detail")
                    or data.get("error_code")
                    or data.get("state")
                    or "unknown"
                ),
            ),
        )

    def _refresh_cloud_ai_models_from_backend(self) -> None:
        config = self._current_cloud_auth_config()
        provider = (config.provider or "none").strip().lower()

        if provider == "none":
            QMessageBox.warning(
                self,
                self.localization.t("settings.cloud_ai.message.title"),
                self.localization.t("settings.cloud_ai.models.provider_disabled"),
            )
            return

        if (
            config.auth_mode == "secure_store"
            and self.cloud_ai_api_key_edit.text().strip()
        ):
            QMessageBox.warning(
                self,
                self.localization.t("settings.cloud_ai.message.title"),
                self.localization.t("settings.cloud_ai.models.save_first"),
            )
            return

        try:
            response = httpx.post(
                "http://127.0.0.1:10420/cloud-ai/models",
                json={
                    "provider": provider,
                    "auth_mode": config.auth_mode,
                    "credential_id": config.credential_id,
                    "api_key_env": config.api_key_env,
                    "base_url": self.cloud_ai_base_url_edit.text().strip(),
                },
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

        except Exception as error:
            QMessageBox.critical(
                self,
                self.localization.t("settings.cloud_ai.message.title"),
                self.localization.t(
                    "settings.cloud_ai.models.request_failed",
                    error=str(error),
                ),
            )
            return

        if not data.get("ok"):
            QMessageBox.warning(
                self,
                self.localization.t("settings.cloud_ai.message.title"),
                self.localization.t(
                    "settings.cloud_ai.models.failed",
                    error=data.get("error_code") or data.get("state") or "unknown",
                ),
            )
            return

        models = data.get("models") or []
        normalized_models: list[str] = []

        for model in models:
            model_id = str(model).strip()
            if model_id and model_id not in normalized_models:
                normalized_models.append(model_id)

        if not normalized_models:
            QMessageBox.warning(
                self,
                self.localization.t("settings.cloud_ai.message.title"),
                self.localization.t("settings.cloud_ai.models.empty"),
            )
            return

        previous_selected_model = self._selected_cloud_model()

        self._updating_cloud_model_combo = True
        try:
            self.cloud_ai_models_list.clear()

            for model_id in normalized_models:
                self.cloud_ai_models_list.addItem(model_id)
                item = self.cloud_ai_models_list.item(
                    self.cloud_ai_models_list.count() - 1
                )
                item.setData(Qt.ItemDataRole.UserRole, model_id)

            if previous_selected_model in normalized_models:
                matching_items = self.cloud_ai_models_list.findItems(
                    previous_selected_model,
                    Qt.MatchFlag.MatchExactly,
                )
                if matching_items:
                    self.cloud_ai_models_list.setCurrentItem(matching_items[0])
                    self._set_selected_cloud_model(previous_selected_model)
                else:
                    self.cloud_ai_models_list.clearSelection()
                    self._set_selected_cloud_model("")
            else:
                self.cloud_ai_models_list.clearSelection()
                self._set_selected_cloud_model("")

        finally:
            self._updating_cloud_model_combo = False

        QMessageBox.information(
            self,
            self.localization.t("settings.cloud_ai.message.title"),
            self.localization.t(
                "settings.cloud_ai.models.loaded",
                count=len(normalized_models),
            ),
        )

    def _finalize_combo_box(self, combo_box: QComboBox) -> None:
        combo_box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        combo_box.setMinimumContentsLength(0)
        combo_box.setEditable(False)

        if combo_box.lineEdit() is not None:
            combo_box.lineEdit().setAlignment(Qt.AlignmentFlag.AlignLeft)

        view = combo_box.view()
        if view is not None:
            view.setTextElideMode(Qt.TextElideMode.ElideNone)

    def _update_character_info_label(self) -> None:
        if not hasattr(self, "character_info_label"):
            return

        character_id = self.character_combo.currentData()
        pack = self.character_registry.get_pack(character_id)

        if pack is None:
            self.character_info_label.setText(
                self.localization.t("settings.character.not_found")
            )
            return

        source_label = (
            self.localization.t("settings.character.builtin")
            if self.character_registry.is_builtin(pack.id)
            else self.localization.t("settings.character.user")
        )

        description = pack.description or self.localization.t("settings.character.no_description")
        author = pack.author or self.localization.t("settings.character.unknown_author")

        warning_text = ""
        if pack.warnings:
            warning_label = self.localization.t("settings.character.warning")
            warning_text = f"\n\n{warning_label}:\n" + "\n".join(
                f"- {warning}" for warning in pack.warnings
            )

        theme_text = ""
        if pack.theme is not None:
            theme_label = self.localization.t("settings.character.theme")
            base_label = self.localization.t("settings.character.theme_base")
            override_label = self.localization.t("settings.character.theme_override")
            colors_label = self.localization.t("settings.character.theme_colors")

            theme_text = (
                f"\n\n{theme_label}:\n"
                f"- {base_label}: {pack.theme.base_theme}\n"
                f"- {override_label}: {len(pack.theme.palette_override)} {colors_label}"
            )

        self.character_info_label.setText(
            f"{pack.name}\n"
            f"{source_label} / v{pack.version}\n"
            f"by {author}\n\n"
            f"{description}"
            f"{theme_text}"
            f"{warning_text}"
        )

    def _language_display_name(self, language: str) -> str:
        if language == "ko":
            return "한국어"
        if language == "en":
            return "English"

        return language

    def _toggle_theme_palette_view(self) -> None:
        if not hasattr(self, "theme_palette_view"):
            return

        should_show = not self.theme_palette_view.isVisible()
        self.theme_palette_view.setVisible(should_show)
        self.theme_palette_button.setText(
            self.localization.t(
                "settings.theme.palette.hide"
                if should_show
                else "settings.theme.palette.show"
            )
        )

        if should_show:
            self._refresh_theme_palette_view()

    def _refresh_theme_palette_view(self) -> None:
        if not hasattr(self, "theme_palette_view"):
            return

        if not self.theme_palette_view.isVisible():
            return

        palette_data, override_keys = self._selected_theme_palette_info()
        self.theme_palette_view.setHtml(
            self._build_theme_palette_html(palette_data, override_keys)
        )

    def _selected_theme_palette_info(self) -> tuple[dict[str, str], set[str]]:
        theme_id = self.theme_combo.currentData() or self.settings.theme_id
        override_keys: set[str] = set()

        if theme_id == "character":
            character_id = self.character_combo.currentData() or self.settings.selected_character_id
            pack = self.character_registry.get_pack(character_id)
            if pack is not None and pack.theme is not None:
                override_keys = set(pack.theme.palette_override.keys())
                try:
                    theme = self.theme_manager.create_character_theme(
                        base_theme_id=pack.theme.base_theme,
                        palette_override=pack.theme.palette_override,
                        character_name=pack.name,
                    )
                    return theme.palette.model_dump(), override_keys
                except Exception:
                    pass

            theme_id = "light"

        try:
            theme = self.theme_manager.get_theme(theme_id)
        except Exception:
            theme = self.theme_manager.get_theme("light")

        return theme.palette.model_dump(), override_keys

    def _build_theme_palette_html(
        self,
        palette_data: dict[str, str],
        override_keys: set[str],
    ) -> str:
        rows: list[str] = []
        for key in ThemePalette.model_fields.keys():
            color = str(palette_data.get(key, "")).strip()
            square_color = self._normalize_theme_color(color)
            name_text = f"<b>{key}</b>" if key in override_keys else key
            rows.append(
                "<tr>"
                f"<td style='padding:2px 10px 2px 0; text-align:right;'>{name_text}</td>"
                f"<td style='padding:2px 10px 2px 0; font-family:monospace; text-align:right;'>{color}</td>"
                f"<td style='padding:2px 0; color:{square_color}; font-size:13pt; text-align:right;'>■</td>"
                "</tr>"
            )

        return (
            "<html><body>"
            "<table cellspacing='0' cellpadding='0' align='right'>"
            + "".join(rows)
            + "</table>"
            "</body></html>"
        )

    def _normalize_theme_color(self, color: str) -> str:
        if color.startswith("#") and len(color) in (4, 7, 9):
            return color
        return "#000000"

    def _open_cloud_ai_api_key_page(self) -> None:
        provider = self.cloud_ai_provider_combo.currentData() or "openai"
        url = str(self._cloud_ai_provider_defaults(provider).get("api_key_url", ""))

        if not url:
            return

        QDesktopServices.openUrl(QUrl(url))

    def _update_cloud_ai_api_key_page_button(self) -> None:
        if not hasattr(self, "cloud_ai_api_key_page_button"):
            return

        provider = self.cloud_ai_provider_combo.currentData() or "openai"
        url = str(self._cloud_ai_provider_defaults(provider).get("api_key_url", ""))
        self.cloud_ai_api_key_page_button.setEnabled(bool(url))


    def _open_web_search_api_key_page(self) -> None:
        provider = self.web_search_provider_combo.currentData() or "tavily"
        url = str(self._web_search_provider_defaults(provider).get("api_key_url", ""))

        if not url:
            return

        QDesktopServices.openUrl(QUrl(url))

    def _update_web_search_api_key_page_button(self) -> None:
        if not hasattr(self, "web_search_api_key_page_button"):
            return

        provider = self.web_search_provider_combo.currentData() or "tavily"
        url = str(self._web_search_provider_defaults(provider).get("api_key_url", ""))
        self.web_search_api_key_page_button.setEnabled(bool(url))


    def _connect_web_search_setting_change_handlers(self) -> None:
        """Keep dialog.settings synchronized while the Search tab is edited.

        The Search tab has several helper buttons that can be pressed without
        closing the dialog.  More importantly, users can switch tabs after
        editing search options and later hit Save; keeping the dialog-owned
        AppSettings object updated on every change prevents the tab from
        appearing to reset or from saving stale defaults.
        """
        if getattr(self, "_web_search_change_handlers_connected", False):
            return

        self._web_search_change_handlers_connected = True

        self.web_search_enabled_checkbox.toggled.connect(
            self._on_web_search_controls_changed
        )
        self.web_search_auto_enabled_checkbox.toggled.connect(
            self._on_web_search_controls_changed
        )
        self.web_search_provider_combo.currentIndexChanged.connect(
            self._on_web_search_controls_changed
        )
        self.web_search_auth_mode_combo.currentIndexChanged.connect(
            self._on_web_search_controls_changed
        )
        self.web_search_credential_id_edit.textChanged.connect(
            self._on_web_search_controls_changed
        )
        self.web_search_api_key_env_edit.textChanged.connect(
            self._on_web_search_controls_changed
        )
        self.web_search_base_url_edit.textChanged.connect(
            self._on_web_search_controls_changed
        )
        self.web_search_max_results_edit.textChanged.connect(
            self._on_web_search_controls_changed
        )
        self.web_search_timeout_edit.textChanged.connect(
            self._on_web_search_controls_changed
        )

    def _on_web_search_controls_changed(self, *args) -> None:
        self._apply_web_search_controls_to_settings()

    def _web_search_provider_defaults(self, provider: str) -> dict[str, object]:
        return web_search_provider_defaults(provider)

    def _default_web_search_api_key_env(self, provider: str) -> str:
        return default_web_search_api_key_env(provider)

    def _default_web_search_credential_id(self, provider: str) -> str:
        return default_web_search_credential_id(provider)

    def _current_web_search_auth_config(self) -> CloudCredentialConfig:
        provider = self.web_search_provider_combo.currentData() or "tavily"
        return CloudCredentialConfig(
            provider=provider,
            auth_mode=self.web_search_auth_mode_combo.currentData() or "secure_store",
            credential_id=self.web_search_credential_id_edit.text().strip()
            or self._default_web_search_credential_id(provider),
            api_key_env=self.web_search_api_key_env_edit.text().strip() or None,
        )

    def _web_search_auth_input_label_text(self) -> str:
        if not hasattr(self, "web_search_auth_mode_combo"):
            return self.localization.t("settings.cloud_ai.api_key")

        auth_mode = self.web_search_auth_mode_combo.currentData() or "secure_store"
        if auth_mode == "env_var":
            return self.localization.t("settings.cloud_ai.api_key_env")

        return self.localization.t("settings.cloud_ai.api_key")

    def _on_web_search_provider_changed(self) -> None:
        provider = self.web_search_provider_combo.currentData() or "tavily"
        current_env = self.web_search_api_key_env_edit.text().strip()
        current_credential_id = self.web_search_credential_id_edit.text().strip()

        known_envs = {
            "",
            *(str(defaults.get("api_key_env", "")) for defaults in WEB_SEARCH_PROVIDER_DEFAULTS.values()),
        }
        known_ids = {
            "",
            *(str(defaults.get("credential_id", "")) for defaults in WEB_SEARCH_PROVIDER_DEFAULTS.values()),
        }

        if current_env in known_envs:
            self.web_search_api_key_env_edit.setText(self._default_web_search_api_key_env(provider))
        if current_credential_id in known_ids:
            self.web_search_credential_id_edit.setText(self._default_web_search_credential_id(provider))

        self._update_web_search_api_key_page_button()
        self._update_web_search_api_key_status()
        self._apply_web_search_controls_to_settings()

    def _update_web_search_auth_mode_ui(self) -> None:
        if not hasattr(self, "web_search_auth_mode_combo"):
            return

        auth_mode = self.web_search_auth_mode_combo.currentData() or "secure_store"
        secure_store_enabled = auth_mode == "secure_store"
        env_var_enabled = auth_mode == "env_var"

        self.web_search_auth_input_stack.setCurrentIndex(0 if secure_store_enabled else 1)
        self.web_search_credential_id_edit.setEnabled(secure_store_enabled)
        self.web_search_api_key_edit.setEnabled(secure_store_enabled)
        self.web_search_save_api_key_button.setVisible(secure_store_enabled)
        self.web_search_delete_api_key_button.setVisible(secure_store_enabled)
        self.web_search_api_key_env_edit.setEnabled(env_var_enabled)

        if hasattr(self, "web_search_auth_input_label_widget"):
            self.web_search_auth_input_label_widget.setText(
                self._web_search_auth_input_label_text()
            )

        self._update_web_search_api_key_status()
        self._apply_web_search_controls_to_settings()

    def _update_web_search_api_key_status(self) -> None:
        if not hasattr(self, "web_search_api_key_status_label"):
            return

        config = self._current_web_search_auth_config()
        if config.auth_mode == "env_var":
            if config.api_key_env:
                self.web_search_api_key_status_label.setText(
                    self.localization.t(
                        "settings.cloud_ai.api_key.status.env_var",
                        env=config.api_key_env,
                    )
                )
            else:
                self.web_search_api_key_status_label.setText(
                    self.localization.t("settings.cloud_ai.api_key.status.missing")
                )
            return

        try:
            has_key = CloudAuthManager.has_api_key(config)
        except Exception:
            has_key = False

        if has_key:
            self.web_search_api_key_status_label.setText(
                self.localization.t("settings.cloud_ai.api_key.status.saved")
            )
        else:
            self.web_search_api_key_status_label.setText(
                self.localization.t("settings.cloud_ai.api_key.status.not_saved")
            )

    def _save_web_search_api_key(self) -> None:
        self._apply_web_search_controls_to_settings()
        config = self._current_web_search_auth_config()
        api_key = self.web_search_api_key_edit.text().strip()

        if not api_key:
            QMessageBox.warning(
                self,
                self.localization.t("settings.web_search.message.title"),
                self.localization.t("settings.cloud_ai.api_key.empty"),
            )
            return

        try:
            CloudAuthManager.save_api_key(config.credential_id, api_key)
        except Exception as error:
            QMessageBox.critical(
                self,
                self.localization.t("settings.web_search.message.title"),
                self.localization.t(
                    "settings.cloud_ai.api_key.save_failed",
                    error=str(error),
                ),
            )
            return

        self.web_search_api_key_edit.clear()
        self._update_web_search_api_key_status()
        QMessageBox.information(
            self,
            self.localization.t("settings.web_search.message.title"),
            self.localization.t("settings.cloud_ai.api_key.saved"),
        )

    def _delete_web_search_api_key(self) -> None:
        self._apply_web_search_controls_to_settings()
        config = self._current_web_search_auth_config()

        try:
            CloudAuthManager.delete_api_key(config.credential_id)
        except Exception as error:
            QMessageBox.critical(
                self,
                self.localization.t("settings.web_search.message.title"),
                self.localization.t(
                    "settings.cloud_ai.api_key.delete_failed",
                    error=str(error),
                ),
            )
            return

        self._update_web_search_api_key_status()
        QMessageBox.information(
            self,
            self.localization.t("settings.web_search.message.title"),
            self.localization.t("settings.cloud_ai.api_key.deleted"),
        )

    def _apply_web_search_controls_to_settings(self) -> None:
        if not hasattr(self, "web_search_enabled_checkbox"):
            return

        provider = str(
            self.web_search_provider_combo.currentData() or AppSettings().web_search_provider
        ).strip().lower()
        if provider not in {"none", "tavily", "firecrawl"}:
            provider = AppSettings().web_search_provider

        auth_mode = str(
            self.web_search_auth_mode_combo.currentData() or AppSettings().web_search_auth_mode
        ).strip().lower()
        if auth_mode not in {"secure_store", "env_var"}:
            auth_mode = AppSettings().web_search_auth_mode

        self.settings.web_search_enabled = self.web_search_enabled_checkbox.isChecked()
        self.settings.web_search_auto_enabled = self.web_search_auto_enabled_checkbox.isChecked()
        self.settings.web_search_provider = provider
        self.settings.web_search_auth_mode = auth_mode
        self.settings.web_search_credential_id = (
            self.web_search_credential_id_edit.text().strip()
            or self._default_web_search_credential_id(provider)
        )
        self.settings.web_search_api_key_env = (
            self.web_search_api_key_env_edit.text().strip()
            or self._default_web_search_api_key_env(provider)
        )
        self.settings.web_search_base_url = self.web_search_base_url_edit.text().strip()

        try:
            max_results = int(self.web_search_max_results_edit.text().strip())
        except ValueError:
            max_results = AppSettings().web_search_max_results
        self.settings.web_search_max_results = max(1, min(10, max_results))

        try:
            timeout_seconds = int(self.web_search_timeout_edit.text().strip())
        except ValueError:
            timeout_seconds = AppSettings().web_search_timeout_seconds
        self.settings.web_search_timeout_seconds = max(3, min(120, timeout_seconds))

    def apply_to_settings(self) -> None:
        self.settings.user_name = self.user_name_edit.text().strip() or AppSettings().user_name
        self.settings.language = self.language_combo.currentData()
        self.settings.user_country_preset = self.user_country_combo.currentData() or AppSettings().user_country_preset
        if self.settings.user_country_preset == "auto_language":
            code, location, _ = self._country_region_for_preset(
                "auto_language",
                language=self.settings.language,
            )
            self.settings.user_country_code = code
            self.settings.user_country_location = location
        elif self.settings.user_country_preset in {"kr", "jp", "us", "eu"}:
            code, location, _ = self._country_region_for_preset(self.settings.user_country_preset)
            self.settings.user_country_code = code
            self.settings.user_country_location = location
        elif self.settings.user_country_preset == "custom":
            code, location = self._parse_user_country_input(self.user_country_location_edit.text())
            self.settings.user_country_code = code
            self.settings.user_country_location = location
        elif self.settings.user_country_preset == "ip_auto":
            code, location = self._parse_user_country_input(self.user_country_location_edit.text())
            self.settings.user_country_code = code or self.settings.user_country_code
            self.settings.user_country_location = location or self.settings.user_country_location
        self.settings.preferred_unit_system = (
            self.preferred_unit_system_combo.currentData()
            or AppSettings().preferred_unit_system
        )
        self.settings.conversation_markdown_enabled = self.conversation_markdown_checkbox.isChecked()
        self.settings.enforce_response_language = self.enforce_response_language_checkbox.isChecked()
        self.settings.emphasize_character_style = self.emphasize_character_style_checkbox.isChecked()

        self.settings.theme_id = self.theme_combo.currentData()
        chat_font_family = str(self.chat_font_combo.currentText() or "").strip()
        self.settings.chat_font_family = chat_font_family or self._default_chat_font_family()
        try:
            chat_font_size = int(str(self.chat_font_size_combo.currentText() or "").strip())
        except (TypeError, ValueError):
            chat_font_size = AppSettings().chat_font_size
        self.settings.chat_font_size = max(1, min(200, chat_font_size))
        self.settings.selected_character_id = self.character_combo.currentData()

        self.settings.local_ai_provider = (
            self.local_ai_provider_combo.currentData() or AppSettings().local_ai_provider
        )
        self.settings.local_ai_base_url = (
            self.local_ai_base_url_edit.text().strip() or AppSettings().local_ai_base_url
        )

        # Retrieve the model from the editable combo box rather than the line edit.
        local_model = self.local_model_combo.currentText().strip() or AppSettings().local_model
        self.settings.local_model = local_model
        # Keep the style model identical to the selected local model. This ensures
        # the tone conversion model always matches the primary local AI model and
        # avoids divergence when editing settings.
        self.settings.style_model = local_model

        self.settings.runtime_install_policy = (
            self.runtime_install_policy_combo.currentData()
            or AppSettings().runtime_install_policy
        )
        self.settings.model_install_policy = (
            self.model_install_policy_combo.currentData()
            or AppSettings().model_install_policy
        )

        self.settings.auto_start_local_ai_server = self.auto_start_local_ai_server_checkbox.isChecked()
        self.settings.warn_large_local_model = self.warn_large_local_model_checkbox.isChecked()

        try:
            timeout_seconds = int(self.model_download_timeout_edit.text().strip())
        except ValueError:
            timeout_seconds = AppSettings().model_download_timeout_seconds

        self.settings.model_download_timeout_seconds = max(30, timeout_seconds)

        # Save local model update settings. If the checkbox is checked, enable
        # periodic update checks; otherwise disable them. The interval is
        # clamped between 1 and 60 days. If invalid input is provided, fall
        # back to the default from a fresh AppSettings instance.
        self.settings.local_model_update_check_enabled = (
            self.local_model_update_check_checkbox.isChecked()
        )
        try:
            interval_days = int(self.local_model_update_interval_edit.text().strip())
        except ValueError:
            interval_days = AppSettings().local_model_update_check_interval_days
        interval_days = max(1, min(60, interval_days))
        self.settings.local_model_update_check_interval_days = interval_days

        self.settings.cloud_ai_enabled = self.cloud_ai_enabled_checkbox.isChecked()
        self.settings.cloud_ai_provider = (
            self.cloud_ai_provider_combo.currentData() or AppSettings().cloud_ai_provider
        )
        self.settings.cloud_ai_base_url = self.cloud_ai_base_url_edit.text().strip()
        self.settings.cloud_ai_auth_mode = (
            self.cloud_ai_auth_mode_combo.currentData() or AppSettings().cloud_ai_auth_mode
        )
        self.settings.cloud_ai_credential_id = (
            self.cloud_ai_credential_id_edit.text().strip()
            or self._default_cloud_credential_id(self.settings.cloud_ai_provider)
        )
        self.settings.cloud_ai_api_key_env = (
            self.cloud_ai_api_key_env_edit.text().strip()
            or self._default_cloud_api_key_env(self.settings.cloud_ai_provider)
        )

        cloud_models = self._current_cloud_ai_model_list()
        selected_model = self._selected_cloud_model()

        self.settings.cloud_ai_models = cloud_models
        self.settings.cloud_model = selected_model


        self._apply_web_search_controls_to_settings()

        self.settings.developer_mode = self.developer_mode_checkbox.isChecked()
        self.settings.enable_tray_icon = self.enable_tray_icon_checkbox.isChecked()
        self.settings.close_button_behavior = (
            self.close_button_behavior_combo.currentData()
            or AppSettings().close_button_behavior
        )
        self.settings.cloud_ai_usage_weight_percent = max(0, min(100, round(self.cloud_ai_usage_slider.value() / 5) * 5))
        self.settings.expand_chat_over_character_area = self.expand_chat_checkbox.isChecked()
        self.settings.enable_avatar_embarrassed_when_occluded = (
            self.embarrassed_when_occluded_checkbox.isChecked()
        )
        self.settings.avatar_occluded_opacity = self.avatar_opacity_slider.value() / 100.0

    def _selected_cloud_model(self) -> str:
        if hasattr(self, "_selected_cloud_model_id"):
            return str(self._selected_cloud_model_id or "").strip()

        return self.settings.cloud_model

    def _parse_cloud_ai_models(self, text: str) -> list[str]:
        models: list[str] = []
        for raw_line in text.replace(",", "\n").splitlines():
            model = raw_line.strip()
            if model and model not in models:
                models.append(model)

        return models
