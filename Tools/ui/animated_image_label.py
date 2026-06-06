from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageSequence
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QImage, QMovie, QPixmap
from PySide6.QtWidgets import QLabel


STATIC_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
GIF_SUFFIXES = {".gif"}
APNG_SUFFIXES = {".apng"}


class AnimatedImageLabel(QLabel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._movie: QMovie | None = None
        self._static_pixmap: QPixmap | None = None
        self._apng_frame_cache: dict[Path, list[tuple[QPixmap, int]]] = {}
        self._apng_frames: list[tuple[QPixmap, int]] = []
        self._apng_frame_index = 0
        self._apng_timer = QTimer(self)
        self._apng_timer.setSingleShot(True)
        self._apng_timer.timeout.connect(self._advance_apng_frame)

    def set_image_path(self, path: Path | None, *, animate: bool = True) -> bool:
        self.stop_animation()
        self._static_pixmap = None

        if path is None:
            self.clear()
            return False

        suffix = path.suffix.lower()
        if animate and (suffix in APNG_SUFFIXES or (suffix == ".png" and self._is_apng(path))):
            return self._set_apng(path)

        if animate and suffix in GIF_SUFFIXES:
            return self._set_gif(path)

        return self._set_static_image(path)

    def stop_animation(self) -> None:
        if self._movie is not None:
            self._movie.stop()
            self._movie = None
        self.setMovie(None)
        self._apng_timer.stop()
        self._apng_frames = []
        self._apng_frame_index = 0

    def _set_static_image(self, path: Path) -> bool:
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return False
        self._static_pixmap = pixmap
        self._set_scaled_pixmap(pixmap)
        self.setText("")
        return True

    def _set_gif(self, path: Path) -> bool:
        movie = QMovie(str(path))
        if not movie.isValid():
            return self._set_static_image(path)
        movie.setScaledSize(self._calculate_scaled_size(movie.frameRect().size()))
        self._movie = movie
        self.setMovie(movie)
        movie.start()
        self.setText("")
        return True

    def _set_apng(self, path: Path) -> bool:
        try:
            frames = self._apng_frame_cache.get(path)
            if frames is None:
                frames = []
                with Image.open(path) as image:
                    for frame in ImageSequence.Iterator(image):
                        duration_ms = int(frame.info.get("duration", 100))
                        if duration_ms <= 0:
                            duration_ms = 100
                        frames.append((self._pil_frame_to_pixmap(frame), duration_ms))
                self._apng_frame_cache[path] = frames

            if not frames:
                return self._set_static_image(path)

            self._apng_frames = list(frames)
            self._apng_frame_index = 0
            self._show_current_apng_frame()
            return True
        except Exception:
            return self._set_static_image(path)

    def _pil_frame_to_pixmap(self, frame: Image.Image) -> QPixmap:
        rgba_frame = frame.convert("RGBA")
        width, height = rgba_frame.size
        data = rgba_frame.tobytes("raw", "RGBA")
        image = QImage(
            data,
            width,
            height,
            width * 4,
            QImage.Format.Format_RGBA8888,
        )
        return QPixmap.fromImage(image.copy())

    def _show_current_apng_frame(self) -> None:
        if not self._apng_frames:
            return
        pixmap, duration_ms = self._apng_frames[self._apng_frame_index]
        self._set_scaled_pixmap(pixmap)
        self.setText("")
        if len(self._apng_frames) > 1:
            self._apng_timer.start(duration_ms)

    def _advance_apng_frame(self) -> None:
        if not self._apng_frames:
            return
        self._apng_frame_index = (self._apng_frame_index + 1) % len(self._apng_frames)
        self._show_current_apng_frame()

    def _set_scaled_pixmap(self, pixmap: QPixmap) -> None:
        scaled = pixmap.scaled(
            max(1, self.width()),
            max(1, self.height()),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(scaled)

    def _calculate_scaled_size(self, original_size: QSize) -> QSize:
        if original_size.width() <= 0 or original_size.height() <= 0:
            return QSize(max(1, self.width()), max(1, self.height()))
        return original_size.scaled(
            QSize(max(1, self.width()), max(1, self.height())),
            Qt.AspectRatioMode.KeepAspectRatio,
        )

    def _is_apng(self, path: Path) -> bool:
        try:
            with path.open("rb") as file:
                return b"acTL" in file.read(1024 * 1024)
        except OSError:
            return False

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._movie is not None:
            self._movie.setScaledSize(self._calculate_scaled_size(self._movie.frameRect().size()))
            return
        if self._apng_frames:
            self._show_current_apng_frame()
            return
        if self._static_pixmap is not None:
            self._set_scaled_pixmap(self._static_pixmap)
