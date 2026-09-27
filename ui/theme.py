"""
Central theme definitions for the JARVIS desktop interface.

Keeping every color, spacing and font choice in one module means the rest
of the UI code never hardcodes a hex value: change the palette here and the
whole application follows.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------

BG_APP = "#070b10"          # window background
BG_PANEL = "#10161f"         # cards / frames
BG_PANEL_ALT = "#0c121a"     # nested surfaces (text areas, inputs)
BG_RAISED = "#152230"        # hovered / active surfaces

BORDER = "#1f3646"
BORDER_ACCENT = "#2b5468"
BORDER_STRONG = "#3d7f9c"

ACCENT = "#4fd8ff"           # primary cyan
ACCENT_DIM = "#2f7c96"
ACCENT_SOFT = "#173947"

TEXT_PRIMARY = "#dcefff"
TEXT_SECONDARY = "#7fa0b3"
TEXT_MUTED = "#4d626e"

SUCCESS = "#55ff99"
SUCCESS_SOFT = "#10251c"
WARNING = "#ffb454"
WARNING_SOFT = "#2a2113"
ERROR = "#ff5c72"
ERROR_SOFT = "#2a1117"

# Role colors for the conversation timeline
ROLE_USER = "#9fe6ff"
ROLE_JARVIS = ACCENT
ROLE_SYSTEM = TEXT_SECONDARY
ROLE_TOOL = "#c9a6ff"

FONT_FAMILY = "Segoe UI, DejaVu Sans, sans-serif"
FONT_MONO = "Cascadia Code, Consolas, DejaVu Sans Mono, monospace"

# Mapping of state name (as emitted by the worker) -> accent color, used by
# both the animated core and the status badges so they always agree.
STATE_COLORS = {
    "SYSTEMS ONLINE": ACCENT_DIM,
    "STARTING": ACCENT,
    "LISTENING": ACCENT,
    "RECORDING COMMAND": "#7fffb0",
    "RECORDING": "#7fffb0",
    "TRANSCRIBING": "#ffd47f",
    "THINKING": ACCENT,
    "TOOL EXECUTION": ROLE_TOOL,
    "SPEAKING": "#7fd1ff",
    "ERROR": ERROR,
}


def state_color(state: str) -> str:
    return STATE_COLORS.get(state.upper(), ACCENT)


def stylesheet() -> str:
    """Return the application-wide QSS."""
    return f"""
        QMainWindow, QWidget {{
            background-color: {BG_APP};
            color: {TEXT_PRIMARY};
            font-family: {FONT_FAMILY};
        }}

        QToolTip {{
            background-color: {BG_RAISED};
            color: {TEXT_PRIMARY};
            border: 1px solid {BORDER_ACCENT};
            padding: 4px 6px;
        }}

        QFrame#panel {{
            background-color: {BG_PANEL};
            border: 1px solid {BORDER};
            border-radius: 12px;
        }}

        QFrame#panel_flat {{
            background-color: transparent;
            border: none;
        }}

        QLabel#main_title {{
            color: {ACCENT};
            font-size: 26px;
            font-weight: 800;
            letter-spacing: 6px;
        }}

        QLabel#subtitle {{
            color: {TEXT_MUTED};
            font-size: 10px;
            letter-spacing: 3px;
        }}

        QLabel#online_badge {{
            color: {SUCCESS};
            background-color: {SUCCESS_SOFT};
            border: 1px solid #245d40;
            border-radius: 9px;
            padding: 7px 12px;
            font-weight: 600;
            font-size: 11px;
        }}

        QLabel#offline_badge {{
            color: {ERROR};
            background-color: {ERROR_SOFT};
            border: 1px solid #6b2430;
            border-radius: 9px;
            padding: 7px 12px;
            font-weight: 600;
            font-size: 11px;
        }}

        QLabel#model_badge {{
            color: {ACCENT};
            background-color: {ACCENT_SOFT};
            border: 1px solid {BORDER_ACCENT};
            border-radius: 9px;
            padding: 7px 12px;
            font-weight: 600;
            font-size: 11px;
        }}

        QLabel#section_title {{
            color: {ACCENT};
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 2px;
            padding: 2px 0 6px 0;
        }}

        QLabel#state_label {{
            color: {ACCENT};
            font-size: 14px;
            font-weight: 700;
            padding: 6px;
            letter-spacing: 1px;
        }}

        QLabel#hint {{
            color: {TEXT_MUTED};
            font-size: 11px;
        }}

        /* ---- sidebar nav ---- */
        QPushButton#nav_button {{
            background-color: transparent;
            color: {TEXT_SECONDARY};
            border: 1px solid transparent;
            border-radius: 9px;
            text-align: left;
            padding: 10px 12px;
            font-size: 12px;
            font-weight: 600;
        }}

        QPushButton#nav_button:hover {{
            background-color: {BG_RAISED};
            color: {TEXT_PRIMARY};
        }}

        QPushButton#nav_button:checked {{
            background-color: {ACCENT_SOFT};
            border: 1px solid {BORDER_ACCENT};
            color: {ACCENT};
        }}

        /* ---- generic buttons ---- */
        QPushButton {{
            background-color: {BG_RAISED};
            color: {ACCENT};
            border: 1px solid {BORDER_ACCENT};
            border-radius: 10px;
            font-size: 12px;
            font-weight: 700;
            padding: 9px 14px;
        }}

        QPushButton:hover {{
            background-color: #1c3245;
            border-color: {ACCENT};
        }}

        QPushButton:pressed {{
            background-color: #0d2735;
        }}

        QPushButton:disabled {{
            color: {TEXT_MUTED};
            border-color: {BORDER};
            background-color: #10151a;
        }}

        QPushButton#primary_button {{
            background-color: #123f54;
            border: 1px solid {ACCENT};
            font-size: 14px;
        }}

        QPushButton#primary_button:hover {{
            background-color: #18536d;
        }}

        QPushButton#danger_button {{
            border-color: #6b2430;
            color: {ERROR};
        }}

        QPushButton#danger_button:hover {{
            background-color: {ERROR_SOFT};
        }}

        /* ---- inputs ---- */
        QTextEdit, QLineEdit, QPlainTextEdit {{
            background-color: {BG_PANEL_ALT};
            color: {TEXT_PRIMARY};
            border: 1px solid {BORDER};
            border-radius: 10px;
            padding: 8px;
            selection-background-color: {ACCENT_DIM};
        }}

        QComboBox {{
            background-color: {BG_PANEL_ALT};
            color: {TEXT_PRIMARY};
            border: 1px solid {BORDER};
            border-radius: 8px;
            padding: 6px 8px;
        }}

        QComboBox QAbstractItemView {{
            background-color: {BG_PANEL};
            color: {TEXT_PRIMARY};
            selection-background-color: {ACCENT_SOFT};
        }}

        QSlider::groove:horizontal {{
            height: 4px;
            background: {BORDER};
            border-radius: 2px;
        }}

        QSlider::handle:horizontal {{
            background: {ACCENT};
            width: 14px;
            margin: -6px 0;
            border-radius: 7px;
        }}

        QScrollArea {{
            border: none;
            background: transparent;
        }}

        QScrollBar:vertical {{
            background: transparent;
            width: 9px;
            margin: 0;
        }}

        QScrollBar::handle:vertical {{
            background: {BORDER_ACCENT};
            border-radius: 4px;
            min-height: 24px;
        }}

        QScrollBar::handle:vertical:hover {{
            background: {ACCENT_DIM};
        }}

        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}

        /* ---- metric cards ---- */
        QFrame#metric_card {{
            background-color: {BG_PANEL_ALT};
            border: 1px solid {BORDER};
            border-radius: 10px;
        }}

        QLabel#metric_title {{
            color: {TEXT_MUTED};
            font-size: 9px;
            font-weight: 700;
            letter-spacing: 1px;
        }}

        QLabel#metric_value {{
            color: {ACCENT};
            font-size: 13px;
            font-weight: 700;
        }}

        QProgressBar {{
            border: 1px solid {BORDER};
            border-radius: 5px;
            background-color: {BG_PANEL_ALT};
            text-align: center;
            color: {TEXT_SECONDARY};
            font-size: 9px;
            max-height: 10px;
        }}

        QProgressBar::chunk {{
            background-color: {ACCENT};
            border-radius: 4px;
        }}

        QTabWidget::pane {{
            border: 1px solid {BORDER};
            border-radius: 10px;
            top: -1px;
        }}

        QTabBar::tab {{
            background: transparent;
            color: {TEXT_SECONDARY};
            padding: 6px 12px;
            font-size: 11px;
            font-weight: 600;
        }}

        QTabBar::tab:selected {{
            color: {ACCENT};
            border-bottom: 2px solid {ACCENT};
        }}
    """
