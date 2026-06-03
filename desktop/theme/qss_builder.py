from desktop.theme.theme_model import ThemeDefinition


def build_qss(theme: ThemeDefinition) -> str:
    p = theme.palette

    return f"""
    QMainWindow {{
        background-color: {p.window_bg};
    }}

    QWidget {{
        color: {p.text_primary};
        font-size: 10pt;
    }}

    QWidget#ContentArea {{
        background-color: {p.chat_bg};
    }}


    QWidget#BodyArea {{
        background-color: {p.chat_bg};
    }}

    QFrame#SessionSidebar {{
        background-color: transparent;
        border: none;
        border-radius: 10px;
    }}

    QLabel#SessionSidebarTitle {{
        color: {p.text_primary};
        font-size: 11pt;
        font-weight: bold;
        padding: 4px 2px;
    }}

    QListWidget#SessionList {{
        background-color: transparent;
        color: {p.text_primary};
        border: none;
        outline: none;
    }}

    QListWidget#SessionList::item {{
        padding: 4px;
        margin: 3px 0px;
        min-height: 52px;
        border-radius: 8px;
        color: {p.text_primary};
    }}

    QListWidget#SessionList::item:selected {{
        background-color: transparent;
        color: {p.text_primary};
    }}

    QListWidget#SessionList::item:hover {{
        background-color: {p.input_bg};
    }}

    QFrame#SessionListItemWidget {{
        background-color: transparent;
        border-radius: 10px;
    }}

    QFrame#SessionListItemWidget[currentSession="true"] {{
        background-color: {p.panel_bg};
        border-radius: 10px;
    }}

    QLabel#SessionListItemMarker {{
        color: {p.text_primary};
        background-color: transparent;
        padding-top: 2px;
        padding-bottom: 2px;
        font-weight: bold;
    }}

    QLabel#SessionListItemLabel {{
        color: {p.text_primary};
        background-color: transparent;
        padding-top: 2px;
        padding-bottom: 2px;
    }}

    QToolButton#SessionSidebarToggleButton,
    QToolButton#SessionSidebarRefreshButton {{
        background-color: {p.input_bg};
        color: {p.text_primary};
        border: 1px solid {p.border};
        border-radius: 7px;
        padding: 3px 6px;
        font-weight: bold;
    }}

    QToolButton#SessionSidebarToggleButton:hover,
    QToolButton#SessionSidebarRefreshButton:hover {{
        border: 1px solid {p.accent};
    }}

    QToolButton#SessionItemMenuButton {{
        background-color: transparent;
        color: {p.text_secondary};
        border: none;
        border-radius: 6px;
        padding: 2px 5px;
        font-weight: bold;
    }}

    QToolButton#SessionItemMenuButton:hover {{
        background-color: {p.panel_bg};
        color: {p.text_primary};
        border: 1px solid {p.border};
    }}

    QMenu {{
        background-color: {p.panel_bg};
        color: {p.text_primary};
        border: 1px solid {p.border};
        border-radius: 8px;
        padding: 4px;
    }}

    QMenu::item {{
        padding: 6px 18px;
        border-radius: 6px;
    }}

    QMenu::item:selected {{
        background-color: {p.input_bg};
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

    QPushButton#SessionSidebarButton {{
        background-color: {p.input_bg};
        color: {p.text_primary};
        border: 1px solid {p.border};
        border-radius: 8px;
        padding: 7px 8px;
        font-weight: bold;
    }}

    QPushButton#SessionSidebarButton:hover,
    QPushButton#SessionSidebarPrimaryButton:hover,
    QPushButton#SessionSidebarDangerButton:hover {{
        border: 1px solid {p.accent};
    }}

    QPushButton#SessionSidebarDangerButton {{
        background-color: {p.input_bg};
        color: {p.text_primary};
        border: 1px solid {p.border};
        border-radius: 8px;
        padding: 7px 8px;
        font-weight: bold;
    }}

    QDialog {{
        background-color: {p.window_bg};
    }}

    QTabWidget::pane {{
        border: 1px solid {p.border};
        border-radius: 12px;
        background-color: {p.panel_bg};
    }}

    QTabBar::tab {{
        padding: 8px 16px;
        background-color: {p.panel_bg};
        color: {p.text_primary};
        border: 1px solid {p.border};
        font-weight: bold;
    }}

    QTabBar::tab:selected {{
        background-color: {p.accent};
        color: {p.accent_text};
        border: 1px solid {p.accent};
    }}

    QFrame#HeaderBar {{
        background-color: {p.panel_bg};
        border-bottom: 1px solid {p.border};
    }}

    QLabel#HeaderTitle {{
        font-size: 13pt;
        font-weight: bold;
        color: {p.text_primary};
    }}

    QPushButton#HeaderButton {{
        padding: 6px 12px;
        border: 1px solid {p.border};
        border-radius: 8px;
        background-color: {p.input_bg};
        color: {p.text_primary};
        font-weight: bold;
    }}

    QPushButton#HeaderButton:hover {{
        border: 1px solid {p.accent};
    }}

    QScrollArea {{
        background-color: {p.chat_bg};
        border: none;
    }}

    QScrollBar:vertical {{
        width: 16px;
        margin: 0px;
        background-color: {p.chat_bg};
        border: none;
    }}

    QScrollBar::handle:vertical {{
        min-height: 36px;
        border-radius: 8px;
        background-color: {p.border};
    }}

    QScrollBar::handle:vertical:hover {{
        background-color: {p.accent};
    }}

    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical {{
        height: 0px;
        border: none;
        background: transparent;
    }}

    QScrollBar::add-page:vertical,
    QScrollBar::sub-page:vertical {{
        background: transparent;
    }}

    QScrollBar:horizontal {{
        height: 0px;
        background: transparent;
    }}

    QScrollBar::handle:horizontal {{
        background: transparent;
    }}

    QWidget#ChatContainer {{
        background-color: {p.chat_bg};
    }}

    QLabel#UserMessageBubble {{
        padding: 12px;
        border-radius: 10px;
        background-color: {p.user_bubble_bg};
        color: {p.text_primary};
        font-size: 10pt;
    }}

    QLabel#AssistantMessageBubble {{
        padding: 12px;
        border-radius: 10px;
        background-color: {p.assistant_bubble_bg};
        color: {p.text_primary};
        font-size: 10pt;
    }}

    QWidget#ChatBubbleStack {{
        background-color: transparent;
    }}

    QWidget#ChatMessageActions {{
        background-color: transparent;
    }}

    QPushButton#ChatMessageActionButton {{
        background-color: transparent;
        color: {p.text_secondary};
        border: none;
        border-radius: 6px;
        padding: 2px 6px;
        font-size: 9pt;
    }}

    QPushButton#ChatMessageActionButton[actionFlash="true"] {{
        color: {p.text_primary};
    }}

    QPushButton#ChatMessageActionButton:hover {{
        background-color: {p.input_bg};
        color: {p.text_primary};
    }}

    QPushButton#ChatMessagePendingCancelButton {{
        background-color: transparent;
        color: {p.warning};
        border: none;
        border-radius: 6px;
        padding: 2px 6px;
        font-size: 9pt;
        font-weight: normal;
    }}

    QPushButton#ChatMessagePendingCancelButton:hover {{
        background-color: {p.input_bg};
        color: {p.warning};
    }}

    QPushButton#ChatMessagePendingCancelButton:pressed {{
        font-weight: bold;
    }}

    QWidget#BottomOverlayArea {{
        background-color: transparent;
    }}

    QWidget#CharacterArea {{
        background-color: transparent;
    }}

    QFrame#CharacterDisplayBox {{
        background-color: transparent;
        border: none;
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

    QLabel#StateLabel {{
        color: {p.text_secondary};
        font-size: 9pt;
    }}

    QFrame#UserNameBox {{
        background-color: rgba(255, 255, 255, 185);
        border: 1px solid {p.border};
        border-radius: 8px;
    }}

    QLabel#UserLabel {{
        color: {p.text_secondary};
        font-size: 10pt;
        font-weight: bold;
    }}

    QLabel#UserNameLabel {{
        color: {p.text_primary};
        font-size: 10pt;
        font-weight: bold;
    }}

    QTextEdit {{
        background-color: {p.input_bg};
        color: {p.text_primary};
        border: 1px solid {p.input_border};
        border-radius: 12px;
        padding: 8px;
        font-size: 10pt;
    }}

    QLineEdit {{
        background-color: {p.input_bg};
        color: {p.text_primary};
        border: 1px solid {p.input_border};
        border-radius: 8px;
        padding: 6px;
    }}

    QComboBox {{
        background-color: #FFFFFF;
        color: #202123;
        border: 1px solid #CFCFD8;
        border-radius: 8px;
        padding: 6px 28px 6px 10px;
        font-size: 10pt;
        font-weight: bold;
        selection-background-color: #E7F0FF;
        selection-color: #202123;
    }}

    QComboBox:hover {{
        border: 1px solid {p.accent};
    }}

    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 28px;
        border-left: 1px solid #CFCFD8;
        border-top-right-radius: 8px;
        border-bottom-right-radius: 8px;
        background-color: #FFFFFF;
    }}

    QComboBox::down-arrow {{
        image: url(resources/app/icons/combo_arrow_down.svg);
        width: 12px;
        height: 8px;
    }}

    QComboBox QAbstractItemView {{
        background-color: #FFFFFF;
        color: #202123;
        border: 1px solid #CFCFD8;
        selection-background-color: #E7F0FF;
        selection-color: #202123;
        outline: none;
        padding: 4px;
    }}

    QComboBox QAbstractItemView::item {{
        min-height: 28px;
        padding: 4px 10px;
        color: #202123;
        background-color: #FFFFFF;
    }}

    QComboBox QAbstractItemView::item:selected {{
        background-color: #E7F0FF;
        color: #202123;
    }}

    QCheckBox {{
        color: {p.text_primary};
        spacing: 8px;
        font-weight: bold;
    }}

    QCheckBox::indicator {{
        width: 20px;
        height: 20px;
        border-radius: 6px;
        border: 2px solid {p.border};
        background-color: {p.input_bg};
    }}

    QCheckBox::indicator:hover {{
        border: 2px solid {p.accent};
    }}

    QCheckBox::indicator:checked {{
        background-color: {p.accent};
        border: 2px solid {p.accent};
    }}
    
    QLabel#OpacityValueLabel {{
        color: {p.text_secondary};
        font-size: 10pt;
        font-weight: bold;
    }}

    QSlider::groove:horizontal {{
        border: 1px solid {p.border};
        height: 8px;
        background-color: {p.input_bg};
        border-radius: 4px;
    }}

    QSlider::sub-page:horizontal {{
        background-color: {p.accent};
        border-radius: 4px;
    }}

    QSlider::add-page:horizontal {{
        background-color: {p.input_bg};
        border-radius: 4px;
    }}

    QSlider::handle:horizontal {{
        background-color: {p.accent};
        border: 2px solid {p.accent_text};
        width: 18px;
        height: 18px;
        margin: -6px 0;
        border-radius: 9px;
    }}

    QSlider::handle:horizontal:hover {{
        border: 2px solid {p.border};
    }}

    QPushButton#SendButton {{
        background-color: {p.accent};
        color: {p.accent_text};
        border: none;
        border-radius: 8px;
        padding: 8px 14px;
        font-weight: bold;
    }}

    QPushButton#SendButton:hover {{
        border: 1px solid {p.border};
    }}

    QPushButton#SendButton[responsePending="true"] {{
        background-color: {p.warning};
        color: {p.window_bg};
        border: 1px solid {p.border};
    }}

    QPushButton#SendButton[responsePending="true"]:hover {{
        border: 1px solid {p.accent};
    }}

    QPushButton#DialogSaveButton {{
        background-color: {p.accent};
        color: {p.accent_text};
        border: none;
        border-radius: 8px;
        padding: 8px 18px;
        font-weight: bold;
        min-width: 80px;
    }}

    QPushButton#DialogSaveButton:hover {{
        border: 1px solid {p.border};
    }}

    QPushButton#DialogCancelButton {{
        background-color: {p.input_bg};
        color: {p.text_primary};
        border: 1px solid {p.border};
        border-radius: 8px;
        padding: 8px 18px;
        font-weight: bold;
        min-width: 80px;
    }}

    QPushButton#DialogCancelButton:hover {{
        border: 1px solid {p.accent};
    }}

    QLabel#SettingsDescriptionLabel {{
        font-size: 11pt;
        font-weight: bold;
        color: {p.text_primary};
    }}

    QLabel#SettingsNoteLabel {{
        color: {p.text_secondary};
        font-size: 10pt;
    }}

    QLabel#CharacterInfoLabel {{
        color: {p.text_primary};
        background-color: {p.input_bg};
        border: 1px solid {p.border};
        border-radius: 10px;
        padding: 10px;
    }}
    """
