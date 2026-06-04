from __future__ import annotations

from theme.theme_model import ThemeDefinition


def build_stylesheet(theme: ThemeDefinition) -> str:
    p = theme.palette
    return f"""
QMainWindow {{
    background-color: {p.window_bg};
}}
QWidget {{
    color: {p.text_primary};
    font-size: 10pt;
}}
QMenuBar, QMenu, QToolBar {{
    background-color: {p.panel_bg};
    color: {p.text_primary};
    border-bottom: 1px solid {p.border};
}}
QMenuBar::item:selected, QMenu::item:selected {{
    background-color: {p.input_bg};
}}
QFrame#PreviewPanel,
QFrame#EditorPanel,
QFrame#MetadataPanel,
QFrame#PalettePanel {{
    background-color: {p.panel_bg};
    border: 1px solid {p.border};
    border-radius: 8px;
}}
QLabel#PreviewTitle,
QLabel#PanelTitle {{
    color: {p.text_primary};
    font-size: 15px;
    font-weight: 600;
}}
QWidget#MainChatPreview {{
    background-color: {p.chat_bg};
    border: 1px solid {p.border};
    border-radius: 8px;
}}
QFrame#SessionSidebar {{
    background-color: transparent;
    border: none;
}}
QLabel#SessionSidebarTitle {{
    color: {p.text_primary};
    font-size: 11pt;
    font-weight: bold;
}}
QPushButton#SessionSidebarPrimaryButton {{
    background-color: {p.accent};
    color: {p.accent_text};
    border: none;
    border-radius: 8px;
    padding: 8px 10px;
    font-weight: bold;
    text-align: left;
}}
QFrame#SessionListItemWidget {{
    background-color: {p.panel_bg};
    border-radius: 10px;
}}
QLabel#SessionListItemLabel {{
    color: {p.text_primary};
}}
QFrame#HeaderBar {{
    background-color: {p.panel_bg};
    border-bottom: 1px solid {p.border};
}}
QLabel#HeaderTitle {{
    color: {p.text_primary};
    font-size: 13pt;
    font-weight: bold;
}}
QLabel#StateLabel {{
    color: {p.text_secondary};
    font-size: 9pt;
}}
QWidget#ContentArea,
QWidget#BodyArea,
QWidget#ChatContainer {{
    background-color: {p.chat_bg};
}}
QFrame#CharacterDisplayBox {{
    background-color: transparent;
    border: none;
}}
QWidget#CharacterArea {{
    background-color: transparent;
}}
QLabel#AvatarPlaceholder {{
    background-color: transparent;
    border: none;
    color: {p.text_primary};
}}
QFrame#CharacterInfoBox {{
    background-color: rgba(255, 255, 255, 185);
    border: 1px solid {p.border};
    border-radius: 12px;
}}
QLabel#CharacterNameLabel {{
    color: {p.text_primary};
    font-size: 12pt;
    font-weight: bold;
}}
QLabel#UserMessageBubble {{
    padding: 12px;
    border-radius: 10px;
    background-color: {p.user_bubble_bg};
    color: {p.text_primary};
}}
QLabel#AssistantMessageBubble {{
    padding: 12px;
    border-radius: 10px;
    background-color: {p.assistant_bubble_bg};
    color: {p.text_primary};
}}
QWidget#BottomOverlayArea {{
    background-color: transparent;
}}
QFrame#ComposerFrame {{
    background-color: transparent;
    border: none;
}}
QWidget#ComposerStack {{
    background-color: transparent;
}}
QLabel#AttachmentLabel {{
    color: {p.text_secondary};
    background-color: {p.input_bg};
    border: 1px solid {p.border};
    border-radius: 8px;
    padding: 5px 8px;
}}
QFrame#ReactionTile {{
    background-color: {p.panel_bg};
    border: 1px solid {p.border};
    border-radius: 0px;
}}
QFrame#ReactionTile:hover {{
    border-color: {p.accent};
}}
QLabel#ReactionTileImage {{
    background-color: {p.input_bg};
    color: {p.text_secondary};
    border: none;
}}
QPushButton,
QComboBox,
QLineEdit,
QTextEdit {{
    background-color: {p.input_bg};
    border: 1px solid {p.input_border};
    border-radius: 8px;
    color: {p.text_primary};
    padding: 5px;
}}
QPushButton:hover,
QComboBox:hover {{
    border: 1px solid {p.accent};
}}
QPushButton#AddImageButton {{
    font-size: 18px;
    font-weight: 700;
}}
QPushButton#SendButton {{
    background-color: {p.accent};
    color: {p.accent_text};
    border: none;
    border-radius: 8px;
    padding: 8px 14px;
    font-weight: bold;
}}
QPushButton#AttachFileButton {{
    background-color: {p.input_bg};
    color: {p.text_primary};
    border: 1px solid {p.border};
    border-radius: 8px;
    font-weight: bold;
}}
QPushButton#AttachFileButton:hover {{
    border: 1px solid {p.accent};
}}
QScrollArea {{
    background-color: {p.chat_bg};
    border: none;
}}
QScrollArea#PaletteScrollArea {{
    background-color: {p.panel_bg};
    border: 1px solid {p.border};
    border-radius: 8px;
}}
QScrollArea#PaletteScrollArea QWidget {{
    background-color: {p.panel_bg};
}}
QLabel#PaletteKeyLabel {{
    color: {p.text_secondary};
    font-size: 8pt;
}}
QLineEdit#PaletteColorInput {{
    font-size: 9pt;
    padding: 3px 6px;
}}
QPushButton#PaletteSwatchButton {{
    border: 1px solid {p.border};
    border-radius: 6px;
    padding: 0px;
}}
QScrollBar:horizontal {{
    height: 14px;
    margin: 0px;
    background-color: {p.chat_bg};
    border: none;
}}
QScrollBar::handle:horizontal {{
    min-width: 36px;
    border-radius: 7px;
    background-color: {p.border};
}}
QScrollBar::handle:horizontal:hover {{
    background-color: {p.accent};
}}
QScrollBar:vertical {{
    width: 14px;
    margin: 0px;
    background-color: {p.panel_bg};
    border: none;
}}
QScrollBar::handle:vertical {{
    min-height: 36px;
    border-radius: 7px;
    background-color: {p.border};
}}
QScrollBar::handle:vertical:hover {{
    background-color: {p.accent};
}}
"""
