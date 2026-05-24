from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices

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
from desktop.localization.localization_manager import LocalizationManager
from desktop.settings.app_settings import AppSettings
from desktop.theme.theme_manager import ThemeManager
from desktop.theme.theme_model import ThemePalette


class SettingsDialog(QDialog):
    def __init__(
        self,
        settings: AppSettings,
        localization: LocalizationManager,
        theme_manager: ThemeManager,
        character_registry: CharacterRegistry,
        parent=None,
    ) -> None:
        super().__init__(parent)

        self.settings = settings
        self.localization = localization
        self.theme_manager = theme_manager
        self.character_registry = character_registry
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
        self.advanced_tab = self._create_advanced_tab()

        self.tabs.addTab(self.general_tab, self.localization.t("settings.tab.general"))
        self.tabs.addTab(self.character_tab, self.localization.t("settings.tab.character"))
        self.tabs.addTab(self.theme_tab, self.localization.t("settings.tab.theme"))
        self.tabs.addTab(self.model_tab, self.localization.t("settings.tab.model"))
        self.tabs.addTab(self.cloud_ai_tab, self.localization.t("settings.tab.cloud_ai"))
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

        form_layout.addRow(self.localization.t("settings.user_name"), self.user_name_edit)
        form_layout.addRow(self.localization.t("settings.language"), self.language_combo)

        layout.addLayout(form_layout)
        layout.addStretch()

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
            self.localization.t("settings.character.reload")
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

        form_layout.addRow(self.localization.t("settings.theme.select"), theme_select_widget)
        layout.addLayout(form_layout)

        self.theme_palette_view = QTextEdit()
        self.theme_palette_view.setReadOnly(True)
        self.theme_palette_view.setAcceptRichText(True)
        self.theme_palette_view.setMinimumHeight(220)
        self.theme_palette_view.setObjectName("ThemePaletteView")
        self.theme_palette_view.setVisible(False)
        layout.addWidget(self.theme_palette_view)

        note_label = QLabel(self.localization.t("settings.theme.character.description"))
        note_label.setWordWrap(True)
        note_label.setObjectName("SettingsNoteLabel")
        layout.addWidget(note_label)

        layout.addStretch()

        return tab

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

        self.local_model_edit = QLineEdit()
        self.local_model_edit.setText(self.settings.local_model)

        self.style_model_edit = QLineEdit()
        self.style_model_edit.setText(self.settings.style_model)

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

        form_layout.addRow(self.localization.t("settings.local_ai.provider"), self.local_ai_provider_combo)
        form_layout.addRow(self.localization.t("settings.local_ai.base_url"), self.local_ai_base_url_edit)
        form_layout.addRow(self.localization.t("settings.model.local_ai"), self.local_model_edit)
        form_layout.addRow(self.localization.t("settings.model.style_ai"), self.style_model_edit)
        form_layout.addRow(self.localization.t("settings.runtime_install_policy"), self.runtime_install_policy_combo)
        form_layout.addRow(self.localization.t("settings.model_install_policy"), self.model_install_policy_combo)
        form_layout.addRow(self.localization.t("settings.auto_start_local_ai_server"), self.auto_start_local_ai_server_checkbox)
        form_layout.addRow(self.localization.t("settings.warn_large_local_model"), self.warn_large_local_model_checkbox)
        form_layout.addRow(self.localization.t("settings.model_download_timeout_seconds"), self.model_download_timeout_edit)

        layout.addLayout(form_layout)

        note_label = QLabel(self.localization.t("settings.model.note"))
        note_label.setWordWrap(True)
        note_label.setObjectName("SettingsNoteLabel")
        layout.addWidget(note_label)

        layout.addStretch()

        return tab

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
        defaults: dict[str, dict[str, object]] = {
            "none": {
                "api_key_env": "",
                "credential_id": "CharAIface/openai/api_key",
                "api_key_url": "",
                "base_url": "",
                "model": "",
                "models": [],
            },
            "openai": {
                "api_key_env": "OPENAI_API_KEY",
                "credential_id": "CharAIface/openai/api_key",
                "api_key_url": "https://platform.openai.com/api-keys",
                "base_url": "",
                "model": "gpt-4.1-mini",
                "models": ["gpt-4.1-mini", "gpt-4.1", "gpt-5.1-mini", "gpt-5.1"],
            },
            "openrouter": {
                "api_key_env": "OPENROUTER_API_KEY",
                "credential_id": "CharAIface/openrouter/api_key",
                "api_key_url": "https://openrouter.ai/settings/keys",
                "base_url": "https://openrouter.ai/api/v1",
                "model": "openai/gpt-4.1-mini",
                "models": [
                    "openai/gpt-4.1-mini",
                    "openai/gpt-4.1",
                    "anthropic/claude-3-5-sonnet-latest",
                    "google/gemini-2.0-flash",
                ],
            },
            "anthropic": {
                "api_key_env": "ANTHROPIC_API_KEY",
                "credential_id": "CharAIface/anthropic/api_key",
                "api_key_url": "https://console.anthropic.com/settings/keys",
                "base_url": "",
                "model": "claude-3-5-sonnet-latest",
                "models": [
                    "claude-3-5-sonnet-latest",
                    "claude-3-5-haiku-latest",
                    "claude-3-opus-latest",
                ],
            },
            "gemini": {
                "api_key_env": "GEMINI_API_KEY",
                "credential_id": "CharAIface/gemini/api_key",
                "api_key_url": "https://aistudio.google.com/app/apikey",
                "base_url": "",
                "model": "gemini-2.0-flash",
                "models": ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
            },
            "custom": {
                "api_key_env": "CUSTOM_API_KEY",
                "credential_id": "CharAIface/custom/api_key",
                "api_key_url": "",
                "base_url": "",
                "model": "custom/model-id",
                "models": ["custom/model-id"],
            },
        }

        return defaults.get(provider, defaults["openai"])

    def _default_cloud_api_key_env(self, provider: str) -> str:
        return str(self._cloud_ai_provider_defaults(provider).get("api_key_env", ""))

    def _default_cloud_credential_id(self, provider: str) -> str:
        return str(
            self._cloud_ai_provider_defaults(provider).get(
                "credential_id",
                CloudAuthManager.default_credential_id(provider),
            )
        )

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
        return ("none", "openai", "openrouter", "anthropic", "gemini", "custom")

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
                f"<td style='padding:2px 0; color:{square_color}; font-size:18px; text-align:right;'>■</td>"
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

    def apply_to_settings(self) -> None:
        self.settings.user_name = self.user_name_edit.text().strip() or AppSettings().user_name
        self.settings.language = self.language_combo.currentData()

        self.settings.theme_id = self.theme_combo.currentData()
        self.settings.selected_character_id = self.character_combo.currentData()

        self.settings.local_ai_provider = (
            self.local_ai_provider_combo.currentData() or AppSettings().local_ai_provider
        )
        self.settings.local_ai_base_url = (
            self.local_ai_base_url_edit.text().strip() or AppSettings().local_ai_base_url
        )

        self.settings.local_model = self.local_model_edit.text().strip() or AppSettings().local_model
        self.settings.style_model = self.style_model_edit.text().strip() or self.settings.local_model

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

        self.settings.developer_mode = self.developer_mode_checkbox.isChecked()
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
