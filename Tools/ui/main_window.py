from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QFileDialog,
    QComboBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from characters.character_pack_archive import (
    SUPPORTED_IMAGE_SUFFIXES,
    CharacterPackDraft,
    ReactionImage,
    load_charpack,
    write_charpack,
)
from localization.localization_manager import LocalizationManager
from theme.theme_model import ThemeDefinition, ThemePalette
from theme.theme_manager import ThemeManager
from ui.preview_panel import FullscreenPreview, PreviewPanel
from ui.reaction_timeline import ReactionTimeline
from ui.styles import build_stylesheet


TOOLS_DIR = Path(__file__).resolve().parents[1]
LOCALE_PATH = TOOLS_DIR / "locales" / "ui.csv"
THEMES_DIR = TOOLS_DIR / "themes"
WORKSPACE_DIR = TOOLS_DIR / ".charactersetgenerator_workspace"
SIDE_PANEL_WIDTH = 340


class CharacterSetGeneratorWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.localization = LocalizationManager(LOCALE_PATH)
        self.theme_manager = ThemeManager(THEMES_DIR)
        self.current_theme_id = "dark"
        self.palette_overrides: dict[str, str] = {}
        self.palette_inputs: dict[str, QLineEdit] = {}
        self.palette_swatches: dict[str, QPushButton] = {}
        self.images: list[ReactionImage] = []
        self.selected_image: ReactionImage | None = None

        self.setWindowTitle(self.localization.t("app.title"))
        self.resize(1400, 1040)
        self.setMinimumSize(1100, 960)

        self._create_actions()
        self._create_menu_bar()
        self._create_toolbar()
        self._create_body()
        self._apply_theme()

    def _create_actions(self) -> None:
        self.new_action = QAction(self.localization.t("menu.new"), self)
        self.open_action = QAction(self.localization.t("menu.open"), self)
        self.save_action = QAction(self.localization.t("menu.save"), self)
        self.exit_action = QAction(self.localization.t("menu.exit"), self)
        self.undo_action = QAction(self.localization.t("menu.undo"), self)
        self.redo_action = QAction(self.localization.t("menu.redo"), self)
        self.preferences_action = QAction(self.localization.t("menu.preferences"), self)
        self.fullscreen_action = QAction(self.localization.t("menu.fullscreen_preview"), self)
        self.about_action = QAction(self.localization.t("menu.about"), self)

        self.new_action.triggered.connect(self.new_pack)
        self.open_action.triggered.connect(self.open_charpack)
        self.save_action.triggered.connect(self.save_charpack)
        self.exit_action.triggered.connect(self.close)
        self.fullscreen_action.triggered.connect(self.show_fullscreen_preview)
        self.about_action.triggered.connect(self.show_about)

    def _create_menu_bar(self) -> None:
        file_menu = self.menuBar().addMenu(self.localization.t("menu.file"))
        file_menu.addAction(self.new_action)
        file_menu.addAction(self.open_action)
        file_menu.addAction(self.save_action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)

        edit_menu = self.menuBar().addMenu(self.localization.t("menu.edit"))
        edit_menu.addAction(self.undo_action)
        edit_menu.addAction(self.redo_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.preferences_action)

        view_menu = self.menuBar().addMenu(self.localization.t("menu.view"))
        view_menu.addAction(self.fullscreen_action)

        help_menu = self.menuBar().addMenu(self.localization.t("menu.help"))
        help_menu.addAction(self.about_action)

    def _create_toolbar(self) -> None:
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.addAction(self.new_action)
        toolbar.addAction(self.open_action)
        toolbar.addAction(self.save_action)
        toolbar.addSeparator()
        toolbar.addAction(self.fullscreen_action)
        self.addToolBar(toolbar)

    def _create_body(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        top = QHBoxLayout()
        self.preview = PreviewPanel(self.localization)
        self.preview.fullscreen_button.clicked.connect(self.show_fullscreen_preview)
        top.addWidget(self.preview, 1)

        metadata = self._create_metadata_panel()
        top.addWidget(metadata, 0)
        root.addLayout(top, 1)

        editor_panel = QFrame()
        editor_panel.setObjectName("EditorPanel")
        editor_panel.setFixedHeight(398)
        editor_layout = QHBoxLayout(editor_panel)
        editor_layout.setContentsMargins(10, 10, 10, 10)
        editor_layout.setSpacing(10)

        timeline_panel = QWidget()
        timeline_layout = QVBoxLayout(timeline_panel)
        timeline_layout.setContentsMargins(0, 0, 0, 0)
        timeline_layout.setSpacing(8)

        editor_header = QHBoxLayout()
        editor_title = QLabel(self.localization.t("editor.title"))
        editor_title.setObjectName("PanelTitle")
        editor_header.addWidget(editor_title)
        editor_header.addStretch(1)

        add_button = QPushButton(self.localization.t("editor.add"))
        add_button.setObjectName("AddImageButton")
        add_button.setToolTip(self.localization.t("editor.add.tooltip"))
        add_button.setFixedSize(34, 30)
        add_button.clicked.connect(self.add_images)
        editor_header.addWidget(add_button)
        timeline_layout.addLayout(editor_header)

        self.timeline_scroll = QScrollArea()
        self.timeline_scroll.setFixedHeight(350)
        self.timeline_scroll.setWidgetResizable(False)
        self.timeline_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.timeline_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        timeline_layout.addWidget(self.timeline_scroll)

        editor_layout.addWidget(timeline_panel, 1)
        editor_layout.addWidget(self._create_palette_panel(), 0)
        root.addWidget(editor_panel, 0)

        self.setCentralWidget(central)
        self._rebuild_timeline()

    def _theme_changed(self) -> None:
        theme_id = self.theme_combo.currentData()
        if theme_id:
            self.current_theme_id = theme_id
            self.palette_overrides.clear()
            self._refresh_palette_editor()
            self._apply_theme()

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            build_stylesheet(self._current_theme())
        )

    def _current_theme(self) -> ThemeDefinition:
        base_theme = self.theme_manager.get_theme(self.current_theme_id)
        palette_data = asdict(base_theme.palette)
        palette_data.update(self.palette_overrides)
        return ThemeDefinition(
            id=base_theme.id,
            name=base_theme.name,
            palette=ThemePalette(**palette_data),
        )

    def _create_metadata_panel(self) -> QFrame:
        metadata = QFrame()
        metadata.setObjectName("MetadataPanel")
        metadata.setFixedWidth(SIDE_PANEL_WIDTH)
        metadata_layout = QVBoxLayout(metadata)
        metadata_layout.setContentsMargins(14, 14, 14, 14)
        metadata_layout.setSpacing(10)

        metadata_title = QLabel(self.localization.t("metadata.title"))
        metadata_title.setObjectName("PanelTitle")
        metadata_layout.addWidget(metadata_title)

        form = QFormLayout()
        self.id_input = QLineEdit("example_character")
        self.name_input = QLineEdit("Example Character")
        self.version_input = QLineEdit("1.0.0")
        self.author_input = QLineEdit("")
        self.description_input = QLineEdit("")
        form.addRow(self.localization.t("metadata.id"), self.id_input)
        form.addRow(self.localization.t("metadata.name"), self.name_input)
        form.addRow(self.localization.t("metadata.version"), self.version_input)
        form.addRow(self.localization.t("metadata.author"), self.author_input)
        form.addRow(self.localization.t("metadata.description"), self.description_input)

        self.theme_combo = QComboBox()
        for theme in self.theme_manager.themes:
            label_key = f"theme.{theme.id}"
            label = self.localization.t(label_key)
            if label == f"{{{label_key}}}":
                label = theme.name
            self.theme_combo.addItem(label, theme.id)
        theme_index = self.theme_combo.findData(self.current_theme_id)
        if theme_index >= 0:
            self.theme_combo.setCurrentIndex(theme_index)
        self.theme_combo.currentIndexChanged.connect(self._theme_changed)
        form.addRow(self.localization.t("theme.label"), self.theme_combo)

        metadata_layout.addLayout(form)

        self.style_input = QTextEdit()
        self.style_input.setPlaceholderText(self.localization.t("metadata.style"))
        self.style_input.setPlainText("Respond in this character's voice.")
        metadata_layout.addWidget(QLabel(self.localization.t("metadata.style")))
        metadata_layout.addWidget(self.style_input, 1)
        return metadata

    def _create_palette_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("PalettePanel")
        panel.setFixedWidth(SIDE_PANEL_WIDTH)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(8)

        palette_title = QLabel(self.localization.t("palette.title"))
        palette_title.setObjectName("PanelTitle")
        layout.addWidget(palette_title)

        palette_scroll = QScrollArea()
        palette_scroll.setObjectName("PaletteScrollArea")
        palette_scroll.setWidgetResizable(True)
        palette_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        palette_container = QWidget()
        self.palette_grid = QGridLayout()
        self.palette_grid.setContentsMargins(6, 8, 4, 8)
        self.palette_grid.setHorizontalSpacing(5)
        self.palette_grid.setVerticalSpacing(6)
        palette_container.setLayout(self.palette_grid)
        palette_scroll.setWidget(palette_container)
        layout.addWidget(palette_scroll, 1)

        self._create_palette_editor()
        return panel

    def _create_palette_editor(self) -> None:
        base_palette = asdict(self.theme_manager.get_theme(self.current_theme_id).palette)
        for row, key in enumerate(base_palette):
            label = QLabel(key)
            label.setObjectName("PaletteKeyLabel")
            label.setToolTip(key)

            swatch = QPushButton()
            swatch.setObjectName("PaletteSwatchButton")
            swatch.setFixedSize(24, 24)
            swatch.clicked.connect(lambda _checked=False, color_key=key: self._pick_palette_color(color_key))

            input_field = QLineEdit()
            input_field.setObjectName("PaletteColorInput")
            input_field.setFixedHeight(28)
            input_field.setFixedWidth(92)
            input_field.editingFinished.connect(lambda color_key=key: self._palette_input_changed(color_key))

            self.palette_grid.addWidget(label, row, 0)
            self.palette_grid.addWidget(swatch, row, 1)
            self.palette_grid.addWidget(input_field, row, 2)
            self.palette_swatches[key] = swatch
            self.palette_inputs[key] = input_field

        self._refresh_palette_editor()

    def _refresh_palette_editor(self) -> None:
        if not self.palette_inputs:
            return

        base_palette = asdict(self.theme_manager.get_theme(self.current_theme_id).palette)
        for key, input_field in self.palette_inputs.items():
            color = self.palette_overrides.get(key) or base_palette[key]
            input_field.blockSignals(True)
            input_field.setText(color)
            input_field.blockSignals(False)
            self._set_palette_swatch(key, color)

    def _pick_palette_color(self, key: str) -> None:
        current_color = self.palette_inputs[key].text().strip()
        color = QColorDialog.getColor(QColor(current_color), self, key)
        if not color.isValid():
            return

        self.palette_inputs[key].setText(color.name())
        self._set_palette_override(key, color.name())

    def _palette_input_changed(self, key: str) -> None:
        color = self.palette_inputs[key].text().strip()
        if not QColor(color).isValid():
            self._refresh_palette_editor()
            return

        self._set_palette_override(key, QColor(color).name())

    def _set_palette_override(self, key: str, color: str) -> None:
        base_palette = asdict(self.theme_manager.get_theme(self.current_theme_id).palette)
        if color.lower() == base_palette[key].lower():
            self.palette_overrides.pop(key, None)
        else:
            self.palette_overrides[key] = color

        self._set_palette_swatch(key, color)
        self._apply_theme()

    def _set_palette_swatch(self, key: str, color: str) -> None:
        swatch = self.palette_swatches.get(key)
        if swatch is not None:
            swatch.setStyleSheet(f"background-color: {color};")

    def add_images(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            self.localization.t("editor.add.tooltip"),
            "",
            self.localization.t("dialog.image_filter"),
        )
        for file_name in files:
            path = Path(file_name)
            if path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES:
                self.images.append(ReactionImage(path=path))
        self._rebuild_timeline()
        if self.selected_image is None and self.images:
            self.select_reaction_image(self.images[0])

    def select_reaction_image(self, image: ReactionImage) -> None:
        self.selected_image = image
        self.preview.set_image(image.path)

    def new_pack(self) -> None:
        self.images.clear()
        self.selected_image = None
        self.id_input.setText("example_character")
        self.name_input.setText("Example Character")
        self.version_input.setText("1.0.0")
        self.author_input.setText("")
        self.description_input.setText("")
        self.style_input.setPlainText("Respond in this character's voice.")
        self.current_theme_id = "dark"
        self.palette_overrides.clear()
        theme_index = self.theme_combo.findData(self.current_theme_id)
        if theme_index >= 0:
            self.theme_combo.setCurrentIndex(theme_index)
        self._refresh_palette_editor()
        self._apply_theme()
        self.preview.set_image(None)
        self._rebuild_timeline()

    def open_charpack(self) -> None:
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            self.localization.t("dialog.open_charpack"),
            "",
            self.localization.t("dialog.charpack_filter"),
        )
        if not file_name:
            return
        try:
            WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
            draft = load_charpack(Path(file_name), WORKSPACE_DIR)
            self._apply_draft(draft)
        except Exception as error:
            QMessageBox.critical(
                self,
                self.localization.t("error.title"),
                f"{self.localization.t('error.open_failed')}\n{error}",
            )

    def save_charpack(self) -> None:
        if not self.images:
            QMessageBox.warning(
                self,
                self.localization.t("error.title"),
                self.localization.t("error.no_images"),
            )
            return

        if "idle" not in {image.reaction for image in self.images}:
            QMessageBox.warning(
                self,
                self.localization.t("error.title"),
                self.localization.t("error.missing_idle"),
            )
            return

        file_name, _ = QFileDialog.getSaveFileName(
            self,
            self.localization.t("dialog.save_charpack"),
            f"{self.id_input.text().strip() or 'character'}.charpack",
            self.localization.t("dialog.charpack_filter"),
        )
        if not file_name:
            return

        target = Path(file_name)
        if target.suffix.lower() != ".charpack":
            target = target.with_suffix(".charpack")

        try:
            write_charpack(target, self._current_draft())
        except Exception as error:
            QMessageBox.critical(
                self,
                self.localization.t("error.title"),
                f"{self.localization.t('error.save_failed')}\n{error}",
            )

    def show_fullscreen_preview(self) -> None:
        dialog = FullscreenPreview(
            self.selected_image.path if self.selected_image else None,
            self.localization,
            None,
        )
        dialog.setStyleSheet(build_stylesheet(self._current_theme()))
        dialog.exec()

    def show_about(self) -> None:
        QMessageBox.information(
            self,
            self.localization.t("menu.about"),
            self.localization.t("about.text"),
        )

    def _current_draft(self) -> CharacterPackDraft:
        return CharacterPackDraft(
            character_id=self.id_input.text().strip() or "example_character",
            name=self.name_input.text().strip() or "Example Character",
            version=self.version_input.text().strip() or "1.0.0",
            author=self.author_input.text().strip(),
            description=self.description_input.text().strip(),
            style_prompt=self.style_input.toPlainText(),
            images=self.images,
            theme_base=self.current_theme_id,
            palette_override=self.palette_overrides.copy(),
        )

    def _apply_draft(self, draft: CharacterPackDraft) -> None:
        self.id_input.setText(draft.character_id)
        self.name_input.setText(draft.name)
        self.version_input.setText(draft.version)
        self.author_input.setText(draft.author)
        self.description_input.setText(draft.description)
        self.style_input.setPlainText(draft.style_prompt)
        self.current_theme_id = draft.theme_base
        theme_index = self.theme_combo.findData(self.current_theme_id)
        if theme_index >= 0:
            self.theme_combo.blockSignals(True)
            self.theme_combo.setCurrentIndex(theme_index)
            self.theme_combo.blockSignals(False)
        self.palette_overrides = dict(draft.palette_override or {})
        self._refresh_palette_editor()
        self._apply_theme()
        self.images = list(draft.images)
        self.selected_image = None
        self._rebuild_timeline()
        if self.images:
            self.select_reaction_image(self.images[0])
        else:
            self.preview.set_image(None)

    def _rebuild_timeline(self) -> None:
        self.timeline_builder = ReactionTimeline(self.localization, self)
        self.timeline_builder.image_selected.connect(self.select_reaction_image)
        self.timeline_scroll.setWidget(self.timeline_builder.rebuild(self.images))
