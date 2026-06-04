from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QSize, Qt, Signal
from PySide6.QtGui import QMovie, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from characters.character_pack_archive import ReactionImage
from localization.localization_manager import LocalizationManager

from ui.constants import REACTION_TYPES


class ReactionTile(QFrame):
    selected = Signal(object)

    def __init__(
        self,
        image: ReactionImage,
        localization: LocalizationManager,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.image = image
        self.localization = localization
        self.setObjectName("ReactionTile")
        self.setFixedSize(200, 346)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.preview = QLabel()
        self.preview.setObjectName("ReactionTileImage")
        self.preview.setFixedSize(200, 300)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.preview)

        self.combo = QComboBox()
        self.combo.addItems(REACTION_TYPES)
        self.combo.setCurrentText(image.reaction)
        self.combo.setFixedWidth(200)
        self.combo.setFixedHeight(30)
        self.combo.currentTextChanged.connect(self._reaction_changed)
        layout.addWidget(self.combo)

        self._set_image(image.path)

    def _reaction_changed(self, reaction: str) -> None:
        self.image.reaction = reaction

    def _set_image(self, path: Path) -> None:
        if path.suffix.lower() == ".gif":
            movie = QMovie(str(path))
            movie.setScaledSize(QSize(200, 300))
            self.preview.setMovie(movie)
            movie.start()
            return

        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.preview.setText(self.localization.t("editor.empty_tile"))
            return
        scaled = pixmap.scaled(
            self.preview.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview.setPixmap(scaled)

    def mousePressEvent(self, event) -> None:
        self.selected.emit(self.image)
        super().mousePressEvent(event)


class ReactionTimeline(QObject):
    image_selected = Signal(object)

    def __init__(self, localization: LocalizationManager, parent=None) -> None:
        super().__init__(parent)
        self.localization = localization

    def rebuild(self, images: list[ReactionImage]) -> QWidget:
        container = QFrame()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        for image in images:
            tile = ReactionTile(image, self.localization)
            tile.selected.connect(self.image_selected.emit)
            layout.addWidget(tile)

        if not images:
            layout.addStretch(1)

        width = (
            len(images) * 200 + max(0, len(images) - 1) * 8
            if images
            else 1
        )
        container.setFixedSize(width, 346)
        return container
