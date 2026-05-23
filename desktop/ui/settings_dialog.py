from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QTabWidget,
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
        self.setMinimumSize(520, 420)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        self.tabs = QTabWidget()

        self.general_tab = self._create_general_tab()
        self.character_tab = self._create_character_tab()
        self.theme_tab = self._create_theme_tab()
        self.model_tab = self._create_model_tab()
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

        self.local_model_label = QLabel(self.settings.local_model)
        self.style_model_label = QLabel(self.settings.style_model)
        self.cloud_model_label = QLabel(self.settings.cloud_model)

        form_layout.addRow(
            self.localization.t("settings.model.local_ai"),
            self.local_model_label,
        )
        form_layout.addRow(
            self.localization.t("settings.model.style_ai"),
            self.style_model_label,
        )
        form_layout.addRow(
            self.localization.t("settings.model.cloud_ai"),
            self.cloud_model_label,
        )

        layout.addLayout(form_layout)

        note_label = QLabel(
            self.localization.t("settings.model.note")
        )
        note_label.setWordWrap(True)
        note_label.setObjectName("SettingsNoteLabel")
        layout.addWidget(note_label)

        layout.addStretch()

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

        self.avatar_opacity_combo = QComboBox()
        self._setup_avatar_opacity_combo()

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
        form_layout.addRow(
            self.localization.t("settings.avatar_occluded_opacity"),
            self.avatar_opacity_combo,
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
            self.localization.t(
                "settings.avatar_occluded_opacity.description"
            )
        )
        opacity_description.setWordWrap(True)
        opacity_description.setObjectName("SettingsNoteLabel")
        layout.addWidget(opacity_description)

        layout.addStretch()

        return tab

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

    def _setup_avatar_opacity_combo(self) -> None:
        for percent in range(10, 101, 10):
            value = percent / 100.0
            self.avatar_opacity_combo.addItem(f"{percent}%", value)

        current_percent = round(self.settings.avatar_occluded_opacity * 100)
        current_percent = min(100, max(10, current_percent))
        current_percent = round(current_percent / 10) * 10
        current_value = current_percent / 100.0

        index = self.avatar_opacity_combo.findData(current_value)
        if index >= 0:
            self.avatar_opacity_combo.setCurrentIndex(index)

        self._finalize_combo_box(self.avatar_opacity_combo)

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

    def apply_to_settings(self) -> None:
        self.settings.user_name = (
            self.user_name_edit.text().strip()
            or "익명의 선생님"
        )
        self.settings.language = self.language_combo.currentData()
        self.settings.theme_id = self.theme_combo.currentData()
        self.settings.selected_character_id = self.character_combo.currentData()
        self.settings.developer_mode = self.developer_mode_checkbox.isChecked()

        self.settings.expand_chat_over_character_area = (
            self.expand_chat_checkbox.isChecked()
        )
        self.settings.enable_avatar_embarrassed_when_occluded = (
            self.embarrassed_when_occluded_checkbox.isChecked()
        )
        self.settings.avatar_occluded_opacity = (
            self.avatar_opacity_combo.currentData()
        )