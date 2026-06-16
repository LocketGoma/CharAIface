from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

from desktop.localization.localization_manager import LocalizationManager
from desktop.settings.app_settings import AppSettings
from shared.runtime_paths import app_data_root, character_data_root


class SetupWizardDialog(QWizard):
    def __init__(
        self,
        settings: AppSettings,
        localization: LocalizationManager,
        parent=None,
    ) -> None:
        super().__init__(parent)

        self.settings = settings
        self.localization = localization

        self.setWindowTitle(self.localization.t("setup.title"))
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)
        self.setMinimumSize(560, 420)

        self.addPage(self._create_welcome_page())
        self.addPage(self._create_profile_page())
        self.addPage(self._create_local_ai_page())
        self.addPage(self._create_options_page())

        self.setButtonText(QWizard.WizardButton.BackButton, self.localization.t("setup.button.back"))
        self.setButtonText(QWizard.WizardButton.NextButton, self.localization.t("setup.button.next"))
        self.setButtonText(QWizard.WizardButton.FinishButton, self.localization.t("setup.button.finish"))
        self.setButtonText(QWizard.WizardButton.CancelButton, self.localization.t("setup.button.skip"))

    def apply_to_settings(self) -> None:
        self.settings.setup_wizard_completed = True
        self.settings.language = self.language_combo.currentData() or self.settings.language
        self.settings.user_name = self.user_name_edit.text().strip() or AppSettings().user_name
        self.settings.local_model = self.local_model_combo.currentText().strip() or AppSettings().local_model
        self.settings.style_model = self.settings.local_model
        self.settings.auto_start_local_ai_server = self.auto_start_local_ai_checkbox.isChecked()
        self.settings.runtime_install_policy = (
            self.runtime_install_policy_combo.currentData()
            or AppSettings().runtime_install_policy
        )
        self.settings.model_install_policy = (
            self.model_install_policy_combo.currentData()
            or AppSettings().model_install_policy
        )
        self.settings.close_button_behavior = (
            self.close_button_behavior_combo.currentData()
            or AppSettings().close_button_behavior
        )
        self.settings.cloud_ai_enabled = self.cloud_ai_enabled_checkbox.isChecked()
        self.settings.developer_mode = self.developer_mode_checkbox.isChecked()

    def _create_welcome_page(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle(self.localization.t("setup.welcome.title"))
        page.setSubTitle(self.localization.t("setup.welcome.subtitle"))

        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        message = QLabel(self.localization.t("setup.welcome.body"))
        message.setWordWrap(True)
        message.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(message)

        data_path_label = QLabel(self.localization.t("setup.paths.data"))
        data_path_label.setObjectName("SettingsSectionLabel")
        layout.addWidget(data_path_label)

        data_path = QLabel(str(app_data_root()))
        data_path.setWordWrap(True)
        data_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(data_path)

        character_path_label = QLabel(self.localization.t("setup.paths.character"))
        character_path_label.setObjectName("SettingsSectionLabel")
        layout.addWidget(character_path_label)

        character_path = QLabel(str(character_data_root()))
        character_path.setWordWrap(True)
        character_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(character_path)
        layout.addStretch(1)
        return page

    def _create_profile_page(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle(self.localization.t("setup.profile.title"))
        page.setSubTitle(self.localization.t("setup.profile.subtitle"))

        layout = QFormLayout(page)
        layout.setSpacing(10)

        self.language_combo = QComboBox()
        for language in self.localization.available_languages:
            self.language_combo.addItem(self._language_display_name(language), language)
        language_index = self.language_combo.findData(self.settings.language)
        if language_index >= 0:
            self.language_combo.setCurrentIndex(language_index)

        self.user_name_edit = QLineEdit()
        self.user_name_edit.setText(self.settings.user_name)

        layout.addRow(self.localization.t("settings.language"), self.language_combo)
        layout.addRow(self.localization.t("settings.user_name"), self.user_name_edit)
        return page

    def _create_local_ai_page(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle(self.localization.t("setup.local_ai.title"))
        page.setSubTitle(self.localization.t("setup.local_ai.subtitle"))

        layout = QFormLayout(page)
        layout.setSpacing(10)

        self.local_model_combo = QComboBox()
        self.local_model_combo.setEditable(True)
        for model_name in self._default_local_models():
            self.local_model_combo.addItem(model_name)
        if self.local_model_combo.findText(self.settings.local_model) < 0:
            self.local_model_combo.addItem(self.settings.local_model)
        self.local_model_combo.setCurrentText(self.settings.local_model)

        self.auto_start_local_ai_checkbox = QCheckBox()
        self.auto_start_local_ai_checkbox.setChecked(self.settings.auto_start_local_ai_server)

        self.runtime_install_policy_combo = QComboBox()
        self.runtime_install_policy_combo.addItem(
            self.localization.t("settings.runtime_install_policy.ask"),
            "ask",
        )
        self.runtime_install_policy_combo.addItem(
            self.localization.t("settings.runtime_install_policy.never"),
            "never",
        )
        self._set_combo_data(self.runtime_install_policy_combo, self.settings.runtime_install_policy)

        self.model_install_policy_combo = QComboBox()
        self.model_install_policy_combo.addItem(
            self.localization.t("settings.model_install_policy.ask"),
            "ask",
        )
        self.model_install_policy_combo.addItem(
            self.localization.t("settings.model_install_policy.auto"),
            "auto",
        )
        self.model_install_policy_combo.addItem(
            self.localization.t("settings.model_install_policy.never"),
            "never",
        )
        self._set_combo_data(self.model_install_policy_combo, self.settings.model_install_policy)

        layout.addRow(self.localization.t("settings.model.local_ai"), self.local_model_combo)
        layout.addRow(
            self.localization.t("settings.auto_start_local_ai_server"),
            self.auto_start_local_ai_checkbox,
        )
        layout.addRow(
            self.localization.t("settings.runtime_install_policy"),
            self.runtime_install_policy_combo,
        )
        layout.addRow(
            self.localization.t("settings.model_install_policy"),
            self.model_install_policy_combo,
        )
        return page

    def _create_options_page(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle(self.localization.t("setup.options.title"))
        page.setSubTitle(self.localization.t("setup.options.subtitle"))

        layout = QFormLayout(page)
        layout.setSpacing(10)

        self.cloud_ai_enabled_checkbox = QCheckBox()
        self.cloud_ai_enabled_checkbox.setChecked(self.settings.cloud_ai_enabled)

        self.developer_mode_checkbox = QCheckBox()
        self.developer_mode_checkbox.setChecked(self.settings.developer_mode)

        self.close_button_behavior_combo = QComboBox()
        self.close_button_behavior_combo.addItem(
            self.localization.t("settings.close_button_behavior.exit"),
            "exit",
        )
        self.close_button_behavior_combo.addItem(
            self.localization.t("settings.close_button_behavior.minimize_to_tray"),
            "minimize_to_tray",
        )
        self._set_combo_data(
            self.close_button_behavior_combo,
            self.settings.close_button_behavior,
        )

        layout.addRow(
            self.localization.t("settings.close_button_behavior"),
            self.close_button_behavior_combo,
        )
        layout.addRow(self.localization.t("settings.cloud_ai.enabled"), self.cloud_ai_enabled_checkbox)
        layout.addRow(self.localization.t("settings.developer_mode"), self.developer_mode_checkbox)

        note = QLabel(self.localization.t("setup.options.note"))
        note.setWordWrap(True)
        layout.addRow(note)
        return page

    def _language_display_name(self, language: str) -> str:
        if language == "ko":
            return "한국어"
        if language == "en":
            return "English"
        return language

    def _default_local_models(self) -> list[str]:
        defaults = [
            "qwen2.5:3b",
            "llama3.2:1b",
            "llama3.1:8b",
        ]
        return list(dict.fromkeys([self.settings.local_model, *defaults]))

    def _set_combo_data(self, combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)
