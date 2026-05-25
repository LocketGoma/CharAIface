from pathlib import Path

from PIL import Image, ImageSequence
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QImage, QMovie, QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy


STATIC_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
ANIMATED_GIF_EXTENSIONS = {".gif"}
APNG_EXTENSIONS = {".apng"}


STATE_FALLBACKS = {
    "idle": ["idle"],
    "user_typing": ["user_typing", "idle"],
    "thinking": ["thinking", "idle"],
    "searching": ["searching", "thinking", "idle"],
    "assistant_typing": ["assistant_typing", "thinking", "idle"],
    "assistant_done": ["assistant_done", "idle"],
    "embarrassed": ["embarrassed", "idle"],
    "error": ["error", "idle"],
    "panic": ["panic", "error", "idle"],
}


class AvatarWidget(QLabel):
    def __init__(self, size: int = 160) -> None:
        super().__init__()

        self.avatar_size = size
        self.current_state = "idle"
        self.state_images: dict[str, Path] = {}

        self._movie: QMovie | None = None
        self._current_image_path: Path | None = None
        self._static_pixmap_cache: dict[Path, QPixmap] = {}
        self._apng_frame_cache: dict[Path, list[tuple[QPixmap, int]]] = {}

        self._apng_timer = QTimer(self)
        self._apng_timer.setSingleShot(True)
        self._apng_timer.timeout.connect(self._advance_apng_frame)
        self._apng_frames: list[tuple[QPixmap, int]] = []
        self._apng_frame_index = 0

        self._current_static_pixmap: QPixmap | None = None

        self.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
        self.setMinimumSize(size, size)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self.setObjectName("AvatarPlaceholder")
        self.setText("Avatar")

    def set_state_images(self, state_images: dict[str, str | Path]) -> None:
        # A character pack reload may point the same state names to different
        # files. Reset playback and image caches so stale/static frames are not
        # reused across character changes or manual character reloads.
        self._stop_all_animation()
        self._current_image_path = None
        self._current_static_pixmap = None
        self._static_pixmap_cache.clear()
        self._apng_frame_cache.clear()

        self.state_images = {
            state: Path(path)
            for state, path in state_images.items()
            if path
        }

        self.set_state(self.current_state)

    def set_state(self, state: str) -> None:
        self.current_state = state

        image_path = self._resolve_image_path(state)

        if image_path is None:
            self._set_placeholder_text(state)
            return

        # Do not reload/re-decode the same avatar asset while it is already
        # playing. Repeated state updates during chat generation should not
        # restart APNG/GIF playback or block the UI thread.
        if image_path == self._current_image_path and (self._movie is not None or self._apng_frames or self._current_static_pixmap is not None):
            return

        self._set_image(image_path)

    def _resolve_image_path(self, state: str) -> Path | None:
        fallback_states = STATE_FALLBACKS.get(state, [state, "idle"])

        for fallback_state in fallback_states:
            path = self.state_images.get(fallback_state)

            if path and path.exists():
                return path

        return None

    def _set_image(self, path: Path) -> None:
        suffix = path.suffix.lower()

        self._stop_all_animation()
        self._current_image_path = path

        if suffix in APNG_EXTENSIONS:
            self._set_apng(path)
            return

        if suffix == ".png" and self._is_apng(path):
            self._set_apng(path)
            return

        if suffix in ANIMATED_GIF_EXTENSIONS:
            self._set_gif(path)
            return

        if suffix in STATIC_IMAGE_EXTENSIONS:
            self._set_static_image(path)
            return

        self._set_placeholder_text(f"Unsupported\n{suffix}")

    def _set_static_image(self, path: Path) -> None:
        pixmap = self._static_pixmap_cache.get(path)
        if pixmap is None:
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                self._static_pixmap_cache[path] = pixmap

        if pixmap.isNull():
            self._set_placeholder_text("Image\nError")
            return

        self._current_static_pixmap = pixmap
        self._set_scaled_pixmap(pixmap)
        self.setText("")

    def _set_gif(self, path: Path) -> None:
        movie = QMovie(str(path))

        if not movie.isValid():
            self._set_placeholder_text("GIF\nError")
            return

        scaled_size = self._calculate_width_based_size(
            original_size=movie.frameRect().size()
        )

        movie.setScaledSize(scaled_size)
        self._movie = movie
        self.setMovie(movie)
        movie.start()
        self.setText("")

    def _set_apng(self, path: Path) -> None:
        try:
            frames = self._apng_frame_cache.get(path)
            if frames is None:
                frames = []

                with Image.open(path) as image:
                    for frame in ImageSequence.Iterator(image):
                        duration_ms = int(frame.info.get("duration", 100))

                        if duration_ms <= 0:
                            duration_ms = 100

                        pixmap = self._pil_frame_to_pixmap(frame)
                        frames.append((pixmap, duration_ms))

                if frames:
                    self._apng_frame_cache[path] = frames

            if not frames:
                self._set_placeholder_text("APNG\nError")
                return

            # Keep the cached frame list immutable from the playback state.
            # _stop_apng() resets the active playback list, and it must not
            # clear the cached frames by reference.
            self._apng_frames = list(frames)
            self._apng_frame_index = 0
            self._show_current_apng_frame()

        except Exception as error:
            print(f"[AvatarWidget] Failed to load APNG: {path} / {error}")
            self._set_placeholder_text("APNG\nError")

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

        self._apng_frame_index = (
            self._apng_frame_index + 1
        ) % len(self._apng_frames)

        self._show_current_apng_frame()

    def _set_scaled_pixmap(self, pixmap: QPixmap) -> None:
        target_width = max(1, self.width())
        target_height = max(1, self.height())

        scaled = pixmap.scaled(
            target_width,
            target_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        self.setMinimumHeight(self.avatar_size)
        self.setPixmap(scaled)

    def _calculate_width_based_size(self, original_size: QSize) -> QSize:
        target_width = max(1, self.width())
        target_height = max(1, self.height())

        if original_size.width() <= 0 or original_size.height() <= 0:
            return QSize(target_width, target_height)

        scaled_size = original_size.scaled(
            QSize(target_width, target_height),
            Qt.AspectRatioMode.KeepAspectRatio,
        )

        self.setMinimumHeight(self.avatar_size)

        return scaled_size


    def _set_placeholder_text(self, text: str) -> None:
        self._stop_all_animation()
        self._current_image_path = None
        self._current_static_pixmap = None
        self.clear()
        self.setText(text)

    def _stop_all_animation(self) -> None:
        self._stop_movie()
        self._stop_apng()

    def _stop_movie(self) -> None:
        if self._movie is not None:
            self._movie.stop()
            self._movie = None

        self.setMovie(None)

    def _stop_apng(self) -> None:
        self._apng_timer.stop()
        # Do not call clear() here. _apng_frames can reference cached APNG
        # frames; clearing it would mutate the cache and make the next playback
        # fail with an empty cached frame list.
        self._apng_frames = []
        self._apng_frame_index = 0

    def _is_apng(self, path: Path) -> bool:
        try:
            with path.open("rb") as file:
                data = file.read(1024 * 1024)

            return b"acTL" in data

        except OSError:
            return False

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)

        if self._movie is not None:
            original_size = self._movie.frameRect().size()
            self._movie.setScaledSize(self._calculate_width_based_size(original_size))
            return

        if self._apng_frames:
            self._show_current_apng_frame()
            return

        if self._current_static_pixmap is not None:
            self._set_scaled_pixmap(self._current_static_pixmap)