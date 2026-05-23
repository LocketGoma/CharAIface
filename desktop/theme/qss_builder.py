from desktop.theme.theme_model import ThemeDefinition


def build_qss(theme: ThemeDefinition) -> str:
    p = theme.palette

    return f"""
    QMainWindow {{
        background-color: {p.window_bg};
    }}

    QWidget {{
        color: {p.text_primary};
        font-size: 14px;
    }}

    QWidget#ContentArea {{
        background-color: {p.chat_bg};
    }}

    QFrame#HeaderBar {{
        background-color: {p.panel_bg};
        border-bottom: 1px solid {p.border};
    }}

    QLabel#HeaderTitle {{
        font-size: 18px;
        font-weight: bold;
        color: {p.text_primary};
    }}

    QPushButton#HeaderButton {{
        padding: 6px 12px;
        border: 1px solid {p.border};
        border-radius: 8px;
        background-color: {p.input_bg};
        color: {p.text_primary};
    }}

    QPushButton#HeaderButton:hover {{
        border: 1px solid {p.accent};
    }}

    QScrollArea {{
        background-color: {p.chat_bg};
        border: none;
    }}

    QWidget#ChatContainer {{
        background-color: {p.chat_bg};
    }}

    QLabel#UserMessageBubble {{
        padding: 12px;
        border-radius: 10px;
        background-color: {p.user_bubble_bg};
        color: {p.text_primary};
        font-size: 14px;
    }}

    QLabel#AssistantMessageBubble {{
        padding: 12px;
        border-radius: 10px;
        background-color: {p.assistant_bubble_bg};
        color: {p.text_primary};
        font-size: 14px;
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
        font-size: 16px;
        font-weight: bold;
    }}

    QLabel#StateLabel {{
        color: {p.text_secondary};
        font-size: 12px;
    }}

    QFrame#UserNameBox {{
        background-color: rgba(255, 255, 255, 185);
        border: 1px solid {p.border};
        border-radius: 8px;
    }}

    QLabel#UserLabel {{
        color: {p.text_secondary};
        font-size: 14px;
        font-weight: bold;
    }}

    QLabel#UserNameLabel {{
        color: {p.text_primary};
        font-size: 14px;
        font-weight: bold;
    }}

    QTextEdit {{
        background-color: {p.input_bg};
        color: {p.text_primary};
        border: 1px solid {p.input_border};
        border-radius: 12px;
        padding: 8px;
        font-size: 14px;
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
    """