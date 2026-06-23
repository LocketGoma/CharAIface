from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSize, Qt, QRect, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from desktop.localization.localization_manager import LocalizationManager


class SessionListItemWidget(QFrame):
    selected = Signal(str)
    export_requested = Signal(str)
    rename_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(
        self,
        *,
        session_id: str,
        title: str,
        message_count: int,
        updated_at: str,
        is_current: bool,
        labels: dict[str, str],
        export_visible: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.session_id = session_id
        self.labels = labels
        self.export_visible = bool(export_visible)
        self.setObjectName("SessionListItemWidget")
        self.setProperty("currentSession", bool(is_current))
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(8, 10, 8, 10)
        root_layout.setSpacing(6)
        self.setMinimumHeight(46)

        normalized_title = " ".join(str(title or "").strip().split())
        if not normalized_title:
            normalized_title = labels["default_title"]

        self.marker_label = QLabel("▶" if is_current else "")
        self.marker_label.setObjectName("SessionListItemMarker")
        self.marker_label.setFixedWidth(20)
        self.marker_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.marker_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        self.label = QLabel(normalized_title)
        self.label.setObjectName("SessionListItemLabel")
        self.label.setWordWrap(False)
        self.label.setMinimumHeight(22)
        self.label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        self.menu_button = QToolButton()
        self.menu_button.setObjectName("SessionItemMenuButton")
        self.menu_button.setText("≡")
        self.menu_button.setToolTip(self.labels["options_tooltip"])
        self.menu_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.menu_button.clicked.connect(self._show_menu)

        root_layout.addWidget(self.marker_label)
        root_layout.addWidget(self.label, stretch=1)
        root_layout.addWidget(self.menu_button, alignment=Qt.AlignmentFlag.AlignTop)

    def mousePressEvent(self, event) -> None:  # noqa: ANN001
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self.session_id)
        super().mousePressEvent(event)

    def _show_menu(self) -> None:
        menu = QMenu(self)
        export_action = (
            menu.addAction(self.labels["export"]) if self.export_visible else None
        )
        rename_action = menu.addAction(self.labels["rename"])
        delete_action = menu.addAction(self.labels["delete"])
        action = menu.exec(self.menu_button.mapToGlobal(self.menu_button.rect().bottomLeft()))
        if export_action is not None and action == export_action:
            self.export_requested.emit(self.session_id)
        elif action == rename_action:
            self.rename_requested.emit(self.session_id)
        elif action == delete_action:
            self.delete_requested.emit(self.session_id)

    def set_export_visible(self, visible: bool) -> None:
        self.export_visible = bool(visible)


class SessionSidebar(QFrame):
    new_session_requested = Signal()
    refresh_requested = Signal()
    session_selected = Signal(str)
    session_export_requested = Signal(str)
    session_rename_requested = Signal(str)
    session_delete_requested = Signal(str)
    collapsed_changed = Signal(bool)

    # Match the left character / user-name column width.
    EXPANDED_WIDTH = 220
    COLLAPSED_HEADER_HEIGHT = 44

    def __init__(
        self,
        localization: LocalizationManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.localization = localization

        self.setObjectName("SessionSidebar")
        self.setFixedWidth(self.EXPANDED_WIDTH)

        self._current_session_id: str | None = None
        self._is_refreshing = False
        self._collapsed = False
        self._session_export_visible = True

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(8)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)

        self.toggle_button = QToolButton()
        self.toggle_button.setObjectName("SessionSidebarToggleButton")
        self.toggle_button.setText("▾")
        self.toggle_button.setToolTip("Toggle sessions")
        self.toggle_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_button.clicked.connect(self.toggle_collapsed)

        self.title_label = QLabel()
        self.title_label.setObjectName("SessionSidebarTitle")

        self.refresh_button = QToolButton()
        self.refresh_button.setObjectName("SessionSidebarRefreshButton")
        self.refresh_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_button.clicked.connect(self.refresh_requested.emit)

        header_layout.addWidget(self.toggle_button)
        header_layout.addWidget(self.title_label, stretch=1)
        header_layout.addWidget(self.refresh_button)

        self.new_button = QPushButton()
        self.new_button.setObjectName("SessionSidebarPrimaryButton")
        self.new_button.clicked.connect(self.new_session_requested.emit)

        self.session_list = QListWidget()
        self.session_list.setObjectName("SessionList")
        self.session_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.session_list.itemClicked.connect(self._on_item_clicked)

        root_layout.addLayout(header_layout)
        root_layout.addWidget(self.new_button)
        root_layout.addWidget(self.session_list, stretch=1)

        self.retranslate_ui()
        self._apply_collapsed_state()

    def retranslate_ui(self) -> None:
        self.title_label.setText(self.localization.t("session.sidebar.title"))
        self.new_button.setText(self.localization.t("session.sidebar.new_chat"))
        self.refresh_button.setText(self.localization.t("session.sidebar.refresh"))
        self.refresh_button.setToolTip(self.localization.t("session.sidebar.refresh.tooltip"))
        self.toggle_button.setToolTip(self.localization.t("session.sidebar.toggle.tooltip"))

    def is_collapsed(self) -> bool:
        return self._collapsed

    def toggle_collapsed(self) -> None:
        self.set_collapsed(not self._collapsed)

    def set_collapsed(self, collapsed: bool) -> None:
        if self._collapsed == collapsed:
            return
        self._collapsed = collapsed
        self._apply_collapsed_state()
        self.collapsed_changed.emit(self._collapsed)

    def _apply_collapsed_state(self) -> None:
        self.setFixedWidth(self.EXPANDED_WIDTH)
        self.title_label.show()
        self.refresh_button.show()
        if self._collapsed:
            self.new_button.hide()
            self.session_list.hide()
            self.toggle_button.setText("▸")
        else:
            self.new_button.show()
            self.session_list.show()
            self.toggle_button.setText("▾")

    def preferred_height(self, available_height: int) -> int:
        if self._collapsed:
            return min(max(self.COLLAPSED_HEADER_HEIGHT, 1), max(1, available_height))
        return max(1, available_height)

    def session_item_global_rects(self) -> list[QRect]:
        if self._collapsed or not self.isVisible() or not self.session_list.isVisible():
            return []

        rects: list[QRect] = []
        viewport = self.session_list.viewport()
        viewport_global_rect = viewport.rect().translated(
            viewport.mapToGlobal(viewport.rect().topLeft())
        )

        for index in range(self.session_list.count()):
            item = self.session_list.item(index)
            item_rect = self.session_list.visualItemRect(item)
            if item_rect.isNull() or not item_rect.isValid():
                continue
            global_rect = item_rect.translated(viewport.mapToGlobal(item_rect.topLeft()) - item_rect.topLeft())
            visible_rect = global_rect.intersected(viewport_global_rect)
            if not visible_rect.isEmpty():
                rects.append(visible_rect)

        return rects

    def set_sessions(
        self,
        sessions: list[dict[str, Any]],
        current_session_id: str | None,
    ) -> None:
        self._is_refreshing = True
        self._current_session_id = current_session_id
        self.session_list.clear()

        for session in sessions:
            session_id = str(session.get("session_id") or "").strip()
            if not session_id:
                continue

            title = " ".join(str(session.get("title") or "").strip().split())
            if not title:
                title = self.localization.t("session.default_title")
            message_count = int(session.get("message_count", 0) or 0)
            updated_at = str(session.get("updated_at") or "").strip()
            is_current = session_id == current_session_id

            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, session_id)
            item.setSizeHint(QSize(0, 52))

            widget = SessionListItemWidget(
                session_id=session_id,
                title=title,
                message_count=message_count,
                updated_at=updated_at,
                is_current=is_current,
                labels=self._item_labels(),
                export_visible=self._session_export_visible,
            )
            widget.selected.connect(self._emit_session_selected)
            widget.export_requested.connect(self.session_export_requested.emit)
            widget.rename_requested.connect(self.session_rename_requested.emit)
            widget.delete_requested.connect(self.session_delete_requested.emit)

            self.session_list.addItem(item)
            self.session_list.setItemWidget(item, widget)

            if is_current:
                self.session_list.setCurrentItem(item)

        self._is_refreshing = False

    def set_session_export_visible(self, visible: bool) -> None:
        self._session_export_visible = bool(visible)
        for index in range(self.session_list.count()):
            item = self.session_list.item(index)
            widget = self.session_list.itemWidget(item)
            if isinstance(widget, SessionListItemWidget):
                widget.set_export_visible(self._session_export_visible)

    def _item_labels(self) -> dict[str, str]:
        return {
            "options_tooltip": self.localization.t("session.menu.options.tooltip"),
            "export": self.localization.t("session.menu.export"),
            "rename": self.localization.t("session.menu.rename"),
            "delete": self.localization.t("session.menu.delete"),
            "default_title": self.localization.t("session.default_title"),
        }

    def selected_session_id(self) -> str | None:
        item = self.session_list.currentItem()
        if item is None:
            return None
        session_id = item.data(Qt.ItemDataRole.UserRole)
        if not session_id:
            return None
        return str(session_id)

    def handle_global_mouse_press(self, global_pos) -> bool:  # noqa: ANN001
        """Select a session row even when the character overlay receives the click.

        The avatar/bottom overlay can visually overlap the session list. When it
        receives a mouse press, MainWindow can call this coordinate-based fallback
        instead of redispatching the Qt event, which avoids recursive eventFilter
        loops.
        """
        if self._collapsed or not self.isVisible() or global_pos is None:
            return False

        for index in range(self.session_list.count()):
            item = self.session_list.item(index)
            widget = self.session_list.itemWidget(item)
            if widget is None or not widget.isVisible():
                continue

            top_left = widget.mapToGlobal(widget.rect().topLeft())
            item_rect = widget.rect().translated(top_left)
            if not item_rect.contains(global_pos):
                continue

            if isinstance(widget, SessionListItemWidget):
                menu_top_left = widget.menu_button.mapToGlobal(widget.menu_button.rect().topLeft())
                menu_rect = widget.menu_button.rect().translated(menu_top_left)
                if menu_rect.contains(global_pos):
                    widget._show_menu()
                else:
                    self.session_list.setCurrentItem(item)
                    widget.selected.emit(widget.session_id)
                return True

            session_id = item.data(Qt.ItemDataRole.UserRole)
            if session_id:
                self.session_list.setCurrentItem(item)
                self._emit_session_selected(str(session_id))
                return True

        return False

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        if self._is_refreshing:
            return
        session_id = item.data(Qt.ItemDataRole.UserRole)
        if not session_id:
            return
        self._emit_session_selected(str(session_id))

    def _emit_session_selected(self, session_id: str) -> None:
        if self._is_refreshing:
            return
        if session_id == self._current_session_id:
            return
        self.session_selected.emit(session_id)
