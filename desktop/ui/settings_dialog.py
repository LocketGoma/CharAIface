from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QPushButton,
    QLabel,
    QLineEdit,
    QSlider,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from desktop.characters.character_registry import CharacterRegistry
from desktop.localization.localization_manager import LocalizationManager
from desktop.settings.app_settings import AppSettings
from desktop.theme.theme_manager import ThemeManager


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

        self.setWindowTitle(self.localization.t("settings.title"))
        self.setMinimumSize(560, 460)

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

        self.tabs.addTab(
            self.general_tab,
            self.localization.t("settings.tab.general"),
        )
        self.tabs.addTab(
            self.character_tab,
            self.localization.t("settings.tab.character"),
        )
        self.tabs.addTab(
            self.theme_tab,
            self.localization.t("settings.tab.theme"),
        )
        self.tabs.addTab(
            self.model_tab,
            self.localization.t("settings.tab.model"),
        )
        self.tabs.addTab(
            self.cloud_ai_tab,
            self.localization.t("settings.tab.cloud_ai"),
        )
        self.tabs.addTab(
            self.advanced_tab,
            self.localization.t("settings.tab.advanced"),
        )

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

        description_label = QLabel(
            self.localization.t("settings.general.description")
        )
        description_label.setObjectName("SettingsDescriptionLabel")
        layout.addWidget(description_label)

        form_layout = QFormLayout()
        form_layout.setSpacing(10)

        self.user_name_edit = QLineEdit()
        self.user_name_edit.setText(self.settings.user_name)

        self.language_combo = QComboBox()
        self._setup_language_combo()

        form_layout.addRow(
            self.localization.t("settings.user_name"),
            self.user_name_edit,
        )
        form_layout.addRow(
            self.localization.t("settings.language"),
            self.language_combo,
        )

        layout.addLayout(form_layout)
        layout.addStretch()

        return tab

    def _create_character_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        description_label = QLabel(
            self.localization.t("settings.character.description")
        )
        description_label.setObjectName("SettingsDescriptionLabel")
        layout.addWidget(description_label)

        form_layout = QFormLayout()
        form_layout.setSpacing(10)

        self.character_combo = QComboBox()
        self._setup_character_combo()

        self.character_info_label = QLabel()
        self.character_info_label.setWordWrap(True)
        self.character_info_label.setObjectName("CharacterInfoLabel")

        self.character_combo.currentIndexChanged.connect(
            self._update_character_info_label
        )

        form_layout.addRow(
            self.localization.t("settings.character.select"),
            self.character_combo,
        )

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

        description_label = QLabel(
            self.localization.t("settings.theme.description")
        )
        description_label.setObjectName("SettingsDescriptionLabel")
        layout.addWidget(description_label)

        form_layout = QFormLayout()
        form_layout.setSpacing(10)

        self.theme_combo = QComboBox()
        self._setup_theme_combo()

        form_layout.addRow(
            self.localization.t("settings.theme.select"),
            self.theme_combo,
        )

        layout.addLayout(form_layout)

        note_label = QLabel(
            self.localization.t("settings.theme.character.description")
        )
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

        description_label = QLabel(
            self.localization.t("settings.model.description")
        )
        description_label.setObjectName("SettingsDescriptionLabel")
        layout.addWidget(description_label)

        form_layout = QFormLayout()
        form_layout.setSpacing(10)

        self.local_ai_provider_combo = QComboBox()
        self.local_ai_provider_combo.addItem(
            self.localization.t("settings.local_ai.provider.ollama"),
            "ollama",
        )
        provider_index = self.local_ai_provider_combo.findData(
            self.settings.local_ai_provider
        )
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
        self.warn_large_local_model_checkbox.setChecked(
            self.settings.warn_large_local_model
        )

        self.model_download_timeout_edit = QLineEdit()
        self.model_download_timeout_edit.setText(
            str(self.settings.model_download_timeout_seconds)
        )

        form_layout.addRow(
            self.localization.t("settings.local_ai.provider"),
            self.local_ai_provider_combo,
        )
        form_layout.addRow(
            self.localization.t("settings.local_ai.base_url"),
            self.local_ai_base_url_edit,
        )
        form_layout.addRow(
            self.localization.t("settings.model.local_ai"),
            self.local_model_edit,
        )
        form_layout.addRow(
            self.localization.t("settings.model.style_ai"),
            self.style_model_edit,
        )
        form_layout.addRow(
            self.localization.t("settings.runtime_install_policy"),
            self.runtime_install_policy_combo,
        )
        form_layout.addRow(
            self.localization.t("settings.model_install_policy"),
            self.model_install_policy_combo,
        )
        form_layout.addRow(
            self.localization.t("settings.auto_start_local_ai_server"),
            self.auto_start_local_ai_server_checkbox,
        )
        form_layout.addRow(
            self.localization.t("settings.warn_large_local_model"),
            self.warn_large_local_model_checkbox,
        )
        form_layout.addRow(
            self.localization.t("settings.model_download_timeout_seconds"),
            self.model_download_timeout_edit,
        )

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

        description_label = QLabel(
            self.localization.t("settings.cloud_ai.description")
        )
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
                ("settings.cloud_ai.provider.openrouter", "openrouter"),
                ("settings.cloud_ai.provider.anthropic", "anthropic"),
                ("settings.cloud_ai.provider.gemini", "gemini"),
                ("settings.cloud_ai.provider.custom", "custom"),
            ],
            current_value=self.settings.cloud_ai_provider,
        )

        self.cloud_ai_base_url_edit = QLineEdit()
        self.cloud_ai_base_url_edit.setText(self.settings.cloud_ai_base_url)
        self.cloud_ai_base_url_edit.setPlaceholderText(
            self.localization.t("settings.cloud_ai.base_url.placeholder")
        )

        self.cloud_ai_api_key_env_edit = QLineEdit()
        self.cloud_ai_api_key_env_edit.setText(self.settings.cloud_ai_api_key_env)

        self.cloud_model_edit = QLineEdit()
        self.cloud_model_edit.setText(self.settings.cloud_model)

        self.cloud_ai_models_edit = QTextEdit()
        self.cloud_ai_models_edit.setPlainText(
            "\n".join(self.settings.cloud_ai_models)
        )
        self.cloud_ai_models_edit.setPlaceholderText(
            self.localization.t("settings.cloud_ai.model_list.placeholder")
        )
        self.cloud_ai_models_edit.setAcceptRichText(False)
        self.cloud_ai_models_edit.setMinimumHeight(96)

        self.cloud_ai_provider_combo.currentIndexChanged.connect(
            self._on_cloud_ai_provider_changed
        )
        
        self.cloud_ai_api_key_page_button = QPushButton(
            self.localization.t("settings.cloud_ai.open_api_key_page")
        )
        self.cloud_ai_api_key_page_button.clicked.connect(
            self._open_cloud_ai_api_key_page
        )

        form_layout.addRow(
            self.localization.t("settings.cloud_ai.enabled"),
            self.cloud_ai_enabled_checkbox,
        )
        form_layout.addRow(
            self.localization.t("settings.cloud_ai.provider"),
            self.cloud_ai_provider_combo,
        )
        form_layout.addRow(
            self.localization.t("settings.cloud_ai.base_url"),
            self.cloud_ai_base_url_edit,
        )
        form_layout.addRow(
            self.localization.t("settings.cloud_ai.api_key_env"),
            self.cloud_ai_api_key_env_edit,
        )
        form_layout.addRow(
            "",
            self.cloud_ai_api_key_page_button,
        )
        form_layout.addRow(
            self.localization.t("settings.cloud_ai.default_model"),
            self.cloud_model_edit,
        )
        form_layout.addRow(
            self.localization.t("settings.cloud_ai.model_list"),
            self.cloud_ai_models_edit,
        )

        layout.addLayout(form_layout)

        note_label = QLabel(self.localization.t("settings.cloud_ai.note"))
        note_label.setWordWrap(True)
        note_label.setObjectName("SettingsNoteLabel")
        layout.addWidget(note_label)

        layout.addStretch()

        self._update_cloud_ai_api_key_page_button()

        return tab

    def _create_advanced_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        description_label = QLabel(
            self.localization.t("settings.advanced.description")
        )
        description_label.setObjectName("SettingsDescriptionLabel")
        layout.addWidget(description_label)

        form_layout = QFormLayout()
        form_layout.setSpacing(10)

        self.developer_mode_checkbox = QCheckBox()
        self.developer_mode_checkbox.setChecked(self.settings.developer_mode)

        self.expand_chat_checkbox = QCheckBox()
        self.expand_chat_checkbox.setChecked(
            self.settings.expand_chat_over_character_area
        )

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

        form_layout.addRow(
            self.localization.t("settings.developer_mode"),
            self.developer_mode_checkbox,
        )
        form_layout.addRow(
            self.localization.t("settings.expand_chat_over_character_area"),
            self.expand_chat_checkbox,
        )
        form_layout.addRow(
            self.localization.t("settings.avatar_embarrassed_when_occluded"),
            self.embarrassed_when_occluded_checkbox,
        )

        # Character Opacity Settings
        opacity_widget = QWidget()
        opacity_layout = QVBoxLayout(opacity_widget)
        opacity_layout.setContentsMargins(0, 0, 0, 0)
        opacity_layout.setSpacing(4)

        opacity_layout.addWidget(self.avatar_opacity_slider)
        opacity_layout.addWidget(self.avatar_opacity_label)

        form_layout.addRow(
            self.localization.t("settings.avatar_occluded_opacity"),
            opacity_widget,
        )

        layout.addLayout(form_layout)

        expand_description = QLabel(
            self.localization.t(
                "settings.expand_chat_over_character_area.description"
            )
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
        self.theme_combo.addItem(
            self.localization.t("settings.theme.character"),
            "character",
        )

        for theme_id in self.theme_manager.available_theme_ids():
            theme = self.theme_manager.get_theme(theme_id)
            self.theme_combo.addItem(theme.name, theme.id)

        index = self.theme_combo.findData(self.settings.theme_id)
        if index >= 0:
            self.theme_combo.setCurrentIndex(index)

        self._finalize_combo_box(self.theme_combo)

    def _setup_character_combo(self) -> None:
        for pack in self.character_registry.packs:
            source_label = (
                self.localization.t("settings.character.builtin.short")
                if self.character_registry.is_builtin(pack.id)
                else self.localization.t("settings.character.user.short")
            )
            display_name = f"{pack.name} ({source_label})"
            self.character_combo.addItem(display_name, pack.id)

        index = self.character_combo.findData(self.settings.selected_character_id)
        if index >= 0:
            self.character_combo.setCurrentIndex(index)

        self._finalize_combo_box(self.character_combo)

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
                self.cloud_ai_api_key_env_edit.setText(
                    str(defaults.get("api_key_env", ""))
                )

        if hasattr(self, "cloud_ai_base_url_edit"):
            current_base_url = self.cloud_ai_base_url_edit.text().strip()
            if current_base_url in self._known_cloud_base_urls():
                self.cloud_ai_base_url_edit.setText(
                    str(defaults.get("base_url", ""))
                )

        if hasattr(self, "cloud_model_edit"):
            current_model = self.cloud_model_edit.text().strip()
            if current_model in self._known_cloud_default_models():
                self.cloud_model_edit.setText(
                    str(defaults.get("default_model", ""))
                )

        if hasattr(self, "cloud_ai_models_edit"):
            current_models = self._parse_cloud_ai_models(
                self.cloud_ai_models_edit.toPlainText()
            )
            if self._is_default_cloud_model_list(current_models):
                default_models = defaults.get("models", [])
                self.cloud_ai_models_edit.setPlainText(
                    "\n".join(str(model) for model in default_models)
                )

        self._update_cloud_ai_api_key_page_button()

    def _cloud_ai_provider_defaults(self, provider: str) -> dict[str, object]:
        defaults: dict[str, dict[str, object]] = {
            "none": {
                "api_key_env": "",
                "base_url": "",
                "default_model": "",
                "models": [],
                "api_key_url": "",
            },
            "openai": {
                "api_key_env": "OPENAI_API_KEY",
                "base_url": "",
                "default_model": "gpt-5.1",
                "models": [
                    "gpt-5.1",
                    "gpt-5.1-mini",
                    "gpt-4.1",
                    "gpt-4.1-mini",
                ],
                "api_key_url": "https://platform.openai.com/api-keys",
            },
            "openrouter": {
                "api_key_env": "OPENROUTER_API_KEY",
                "base_url": "https://openrouter.ai/api/v1",
                "default_model": "openai/gpt-5.1",
                "models": [
                    "openai/gpt-5.1",
                    "openai/gpt-5.1-mini",
                    "anthropic/claude-sonnet-4.5",
                    "google/gemini-2.5-pro",
                ],
                "api_key_url": "https://openrouter.ai/settings/keys",
            },
            "anthropic": {
                "api_key_env": "ANTHROPIC_API_KEY",
                "base_url": "",
                "default_model": "claude-sonnet-4-5",
                "models": [
                    "claude-sonnet-4-5",
                    "claude-opus-4-1",
                    "claude-haiku-4-5",
                ],
                "api_key_url": "https://console.anthropic.com/settings/keys",
            },
            "gemini": {
                "api_key_env": "GEMINI_API_KEY",
                "base_url": "",
                "default_model": "gemini-2.5-pro",
                "models": [
                    "gemini-2.5-pro",
                    "gemini-2.5-flash",
                    "gemini-2.0-flash",
                ],
                "api_key_url": "https://aistudio.google.com/apikey",
            },
            "custom": {
                "api_key_env": "",
                "base_url": "",
                "default_model": "",
                "models": [],
                "api_key_url": "",
            },
        }

        return defaults.get(provider, defaults["openai"])

    def _known_cloud_api_key_env_names(self) -> set[str]:
        return {
            str(defaults.get("api_key_env", ""))
            for defaults in self._all_cloud_provider_defaults()
        }

    def _known_cloud_base_urls(self) -> set[str]:
        return {
            str(defaults.get("base_url", ""))
            for defaults in self._all_cloud_provider_defaults()
        }

    def _known_cloud_default_models(self) -> set[str]:
        return {
            str(defaults.get("default_model", ""))
            for defaults in self._all_cloud_provider_defaults()
        }

    def _is_default_cloud_model_list(self, models: list[str]) -> bool:
        known_model_lists = {
            tuple(str(model) for model in defaults.get("models", []))
            for defaults in self._all_cloud_provider_defaults()
        }
        return tuple(models) in known_model_lists

    def _all_cloud_provider_defaults(self) -> list[dict[str, object]]:
        return [
            self._cloud_ai_provider_defaults("none"),
            self._cloud_ai_provider_defaults("openai"),
            self._cloud_ai_provider_defaults("openrouter"),
            self._cloud_ai_provider_defaults("anthropic"),
            self._cloud_ai_provider_defaults("gemini"),
            self._cloud_ai_provider_defaults("custom"),
        ]

    def _default_cloud_api_key_env(self, provider: str) -> str:
        return str(
            self._cloud_ai_provider_defaults(provider).get("api_key_env", "")
        )

    def _finalize_combo_box(self, combo_box: QComboBox) -> None:
        combo_box.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToContents
        )
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

        description = (
            pack.description
            or self.localization.t("settings.character.no_description")
        )
        author = (
            pack.author
            or self.localization.t("settings.character.unknown_author")
        )

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
            override_label = self.localization.t(
                "settings.character.theme_override"
            )
            colors_label = self.localization.t("settings.character.theme_colors")

            theme_text = (
                f"\n\n{theme_label}:\n"
                f"- {base_label}: {pack.theme.base_theme}\n"
                f"- {override_label}: "
                f"{len(pack.theme.palette_override)} {colors_label}"
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
        # General
        self.settings.user_name = (
            self.user_name_edit.text().strip() or AppSettings().user_name
        )
        self.settings.language = self.language_combo.currentData()

        # Character / Theme
        self.settings.theme_id = self.theme_combo.currentData()
        self.settings.selected_character_id = self.character_combo.currentData()

        # Model / Local AI
        self.settings.local_ai_provider = (
            self.local_ai_provider_combo.currentData()
            or AppSettings().local_ai_provider
        )
        self.settings.local_ai_base_url = (
            self.local_ai_base_url_edit.text().strip()
            or AppSettings().local_ai_base_url
        )

        self.settings.local_model = (
            self.local_model_edit.text().strip() or AppSettings().local_model
        )
        self.settings.style_model = (
            self.style_model_edit.text().strip() or self.settings.local_model
        )

        self.settings.runtime_install_policy = (
            self.runtime_install_policy_combo.currentData()
            or AppSettings().runtime_install_policy
        )
        self.settings.model_install_policy = (
            self.model_install_policy_combo.currentData()
            or AppSettings().model_install_policy
        )

        self.settings.auto_start_local_ai_server = (
            self.auto_start_local_ai_server_checkbox.isChecked()
        )
        self.settings.warn_large_local_model = (
            self.warn_large_local_model_checkbox.isChecked()
        )

        try:
            timeout_seconds = int(self.model_download_timeout_edit.text().strip())
        except ValueError:
            timeout_seconds = AppSettings().model_download_timeout_seconds

        self.settings.model_download_timeout_seconds = max(30, timeout_seconds)

        # Cloud AI
        self.settings.cloud_ai_enabled = self.cloud_ai_enabled_checkbox.isChecked()
        self.settings.cloud_ai_provider = (
            self.cloud_ai_provider_combo.currentData()
            or AppSettings().cloud_ai_provider
        )
        self.settings.cloud_ai_base_url = self.cloud_ai_base_url_edit.text().strip()
        self.settings.cloud_ai_api_key_env = (
            self.cloud_ai_api_key_env_edit.text().strip()
            or self._default_cloud_api_key_env(self.settings.cloud_ai_provider)
        )
        self.settings.cloud_model = (
            self.cloud_model_edit.text().strip() or AppSettings().cloud_model
        )

        cloud_models = self._parse_cloud_ai_models(
            self.cloud_ai_models_edit.toPlainText()
        )
        if self.settings.cloud_model not in cloud_models:
            cloud_models.insert(0, self.settings.cloud_model)
        self.settings.cloud_ai_models = cloud_models

        # Advanced
        self.settings.developer_mode = self.developer_mode_checkbox.isChecked()

        self.settings.expand_chat_over_character_area = (
            self.expand_chat_checkbox.isChecked()
        )
        self.settings.enable_avatar_embarrassed_when_occluded = (
            self.embarrassed_when_occluded_checkbox.isChecked()
        )
        self.settings.avatar_occluded_opacity = (
            self.avatar_opacity_slider.value() / 100.0
        )

    def _parse_cloud_ai_models(self, text: str) -> list[str]:
        models: list[str] = []
        for raw_line in text.replace(",", "\n").splitlines():
            model = raw_line.strip()
            if model and model not in models:
                models.append(model)

        if not models:
            return list(AppSettings().cloud_ai_models)

        return models
