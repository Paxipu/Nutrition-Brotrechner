"""Gestaltungssystem der Oberfläche.

Statt Farben und Abstände über die Widgets zu verstreuen, definiert dieses
Modul einen kleinen Satz *Design-Tokens* und erzeugt daraus ein Stylesheet.
Damit lässt sich das Aussehen an einer Stelle ändern, und Hell- und
Dunkelmodus unterscheiden sich nur in den Tokenwerten, nicht im Regelwerk.

Der Modus richtet sich standardmäßig nach dem Betriebssystem und lässt sich in
den Einstellungen festnageln.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette

__all__ = ["SPACING", "ThemeMode", "Tokens", "build_stylesheet", "resolve_tokens"]


class ThemeMode(Enum):
    """Gewählter Farbmodus."""

    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"

    @property
    def label(self) -> str:
        return {
            ThemeMode.SYSTEM: "Wie das System",
            ThemeMode.LIGHT: "Hell",
            ThemeMode.DARK: "Dunkel",
        }[self]


@dataclass(frozen=True, slots=True)
class Tokens:
    """Farb- und Formwerte eines Modus."""

    name: str
    background: str
    surface: str
    surface_alt: str
    sidebar: str
    sidebar_text: str
    sidebar_active: str
    border: str
    text: str
    text_muted: str
    accent: str
    accent_hover: str
    accent_text: str
    success: str
    warning: str
    danger: str
    radius: int = 10
    radius_small: int = 6

    @property
    def is_dark(self) -> bool:
        return self.name == "dark"


#: Einheitliche Abstände in Pixeln. Alles Sichtbare rastert auf diesem Raster,
#: damit die Oberfläche ruhig wirkt.
SPACING: Final[dict[str, int]] = {
    "xs": 4,
    "sm": 8,
    "md": 12,
    "lg": 18,
    "xl": 26,
}

LIGHT: Final = Tokens(
    name="light",
    background="#F4F6F4",
    surface="#FFFFFF",
    surface_alt="#F0F3F0",
    sidebar="#1F2A22",
    sidebar_text="#C6D2C8",
    sidebar_active="#2F6B3A",
    border="#DCE2DC",
    text="#1B211C",
    text_muted="#69736B",
    accent="#2F6B3A",
    accent_hover="#3A8248",
    accent_text="#FFFFFF",
    success="#2E7D32",
    warning="#B26A00",
    danger="#B3261E",
)

DARK: Final = Tokens(
    name="dark",
    background="#141715",
    surface="#1D211E",
    surface_alt="#242925",
    sidebar="#101311",
    sidebar_text="#A9B5AB",
    sidebar_active="#3F8C4E",
    border="#2E342F",
    text="#E6EAE6",
    text_muted="#96A198",
    accent="#4CA35D",
    accent_hover="#5CB86E",
    accent_text="#0E120F",
    success="#5CB86E",
    warning="#E0A030",
    danger="#E4645A",
)


def system_prefers_dark() -> bool:
    """True, wenn die Systemfarben auf einen dunklen Modus hindeuten.

    Qt liefert das Systemschema erst ab 6.5 zuverlässig über
    :meth:`QStyleHints.colorScheme`; als Rückfallebene wird die Helligkeit der
    Fensterfarbe ausgewertet.
    """
    app = QGuiApplication.instance()
    if app is None:  # pragma: no cover - ohne QApplication nicht sinnvoll
        return False

    hints = QGuiApplication.styleHints()
    scheme = getattr(hints, "colorScheme", None)
    if callable(scheme):
        try:
            return bool(scheme() == Qt.ColorScheme.Dark)
        except (AttributeError, TypeError):  # pragma: no cover - ältere Qt-Version
            pass

    window: QColor = QGuiApplication.palette().color(QPalette.ColorRole.Window)
    return window.lightness() < 128


def resolve_tokens(mode: ThemeMode) -> Tokens:
    """Wählt den Tokensatz für den gewünschten Modus."""
    if mode is ThemeMode.DARK:
        return DARK
    if mode is ThemeMode.LIGHT:
        return LIGHT
    return DARK if system_prefers_dark() else LIGHT


def build_stylesheet(t: Tokens) -> str:
    """Erzeugt das Qt-Stylesheet für einen Tokensatz."""
    return f"""
/* ── Grundflächen ───────────────────────────────────────────── */
QWidget {{
    color: {t.text};
    font-size: 10pt;
}}
QMainWindow, QDialog {{ background: {t.background}; }}
QToolTip {{
    background: {t.surface};
    color: {t.text};
    border: 1px solid {t.border};
    padding: 5px 7px;
    border-radius: {t.radius_small}px;
}}

/* ── Seitenleiste ───────────────────────────────────────────── */
QListWidget#NavRail {{
    background: {t.sidebar};
    border: none;
    outline: none;
    padding: {SPACING["md"]}px {SPACING["sm"]}px;
}}
QListWidget#NavRail::item {{
    color: {t.sidebar_text};
    padding: {SPACING["md"]}px {SPACING["md"]}px;
    margin-bottom: {SPACING["xs"]}px;
    border-radius: {t.radius}px;
}}
QListWidget#NavRail::item:hover {{ background: rgba(255, 255, 255, 0.07); }}
QListWidget#NavRail::item:selected {{
    background: {t.sidebar_active};
    color: #FFFFFF;
}}
QLabel#NavBrand {{
    color: #FFFFFF;
    font-size: 15pt;
    font-weight: 600;
    padding: {SPACING["lg"]}px {SPACING["md"]}px {SPACING["sm"]}px {SPACING["md"]}px;
}}
QLabel#NavVersion {{
    color: {t.sidebar_text};
    font-size: 8pt;
    padding: 0 {SPACING["md"]}px {SPACING["lg"]}px {SPACING["md"]}px;
}}

/* ── Karten und Überschriften ───────────────────────────────── */
QFrame#Card {{
    background: {t.surface};
    border: 1px solid {t.border};
    border-radius: {t.radius}px;
}}
QFrame#StatCard {{
    background: {t.surface};
    border: 1px solid {t.border};
    border-radius: {t.radius}px;
}}
QLabel#CardTitle {{
    font-size: 11pt;
    font-weight: 600;
    color: {t.text};
}}
QLabel#PageTitle {{
    font-size: 17pt;
    font-weight: 600;
    color: {t.text};
}}
QLabel#PageSubtitle, QLabel#Muted {{ color: {t.text_muted}; }}
QLabel#StatValue {{ font-size: 19pt; font-weight: 600; color: {t.accent}; }}
QLabel#StatCaption {{ color: {t.text_muted}; font-size: 8.5pt; }}
QLabel#Warning {{ color: {t.warning}; }}
QLabel#Danger {{ color: {t.danger}; }}

/* ── Eingabefelder ──────────────────────────────────────────── */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit, QDateEdit {{
    background: {t.surface};
    border: 1px solid {t.border};
    border-radius: {t.radius_small}px;
    padding: 5px 8px;
    /* Ohne Mindesthöhe schneidet Qt bei manchen Systemschriften Ober- und
       Unterlängen ab, sobald ein eigenes Padding gesetzt ist. */
    min-height: 20px;
    selection-background-color: {t.accent};
    selection-color: {t.accent_text};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QPlainTextEdit:focus, QTextEdit:focus, QDateEdit:focus {{
    border: 1px solid {t.accent};
}}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
    background: {t.surface_alt};
    color: {t.text_muted};
}}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {t.surface};
    border: 1px solid {t.border};
    selection-background-color: {t.accent};
    selection-color: {t.accent_text};
    outline: none;
}}

/* ── Schaltflächen ──────────────────────────────────────────── */
QPushButton {{
    background: {t.surface};
    border: 1px solid {t.border};
    border-radius: {t.radius_small}px;
    padding: 7px 14px;
    color: {t.text};
}}
QPushButton:hover {{ background: {t.surface_alt}; }}
QPushButton:pressed {{ background: {t.border}; }}
QPushButton:disabled {{ color: {t.text_muted}; background: {t.surface_alt}; }}
QPushButton[accent="true"] {{
    background: {t.accent};
    border: 1px solid {t.accent};
    color: {t.accent_text};
    font-weight: 600;
}}
QPushButton[accent="true"]:hover {{ background: {t.accent_hover}; border-color: {t.accent_hover}; }}
QPushButton[danger="true"] {{ color: {t.danger}; }}
QPushButton:flat {{ border: none; background: transparent; }}

/* ── Tabellen ───────────────────────────────────────────────── */
QTableView, QTreeView, QListView {{
    background: {t.surface};
    alternate-background-color: {t.surface_alt};
    border: 1px solid {t.border};
    border-radius: {t.radius_small}px;
    gridline-color: {t.border};
    selection-background-color: {t.accent};
    selection-color: {t.accent_text};
    outline: none;
}}
QTableView::item, QTreeView::item, QListView::item {{ padding: 4px 6px; }}
QHeaderView::section {{
    background: {t.surface_alt};
    color: {t.text_muted};
    border: none;
    border-bottom: 1px solid {t.border};
    border-right: 1px solid {t.border};
    padding: 7px 6px;
    font-weight: 600;
}}
QHeaderView::section:last {{ border-right: none; }}
QTableCornerButton::section {{ background: {t.surface_alt}; border: none; }}

/* ── Sonstiges ──────────────────────────────────────────────── */
QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 11px; margin: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 0; }}
QScrollBar::handle {{ background: {t.border}; border-radius: 5px; min-height: 28px; }}
QScrollBar::handle:hover {{ background: {t.text_muted}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QGroupBox {{
    border: 1px solid {t.border};
    border-radius: {t.radius_small}px;
    margin-top: 14px;
    padding-top: 10px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {t.text_muted};
}}
QCheckBox, QRadioButton {{ spacing: 7px; }}
QSplitter::handle {{ background: transparent; }}
QSplitter::handle:horizontal {{ width: {SPACING["md"]}px; }}
QSplitter::handle:vertical {{ height: {SPACING["md"]}px; }}
QStatusBar {{ background: {t.surface}; border-top: 1px solid {t.border}; color: {t.text_muted}; }}
QStatusBar::item {{ border: none; }}
QMenuBar {{ background: {t.surface}; border-bottom: 1px solid {t.border}; }}
QMenuBar::item:selected {{ background: {t.surface_alt}; }}
QMenu {{ background: {t.surface}; border: 1px solid {t.border}; padding: 5px; }}
QMenu::item {{ padding: 6px 24px 6px 20px; border-radius: {t.radius_small}px; }}
QMenu::item:selected {{ background: {t.accent}; color: {t.accent_text}; }}
QFrame[role="separator"] {{ background: {t.border}; max-height: 1px; border: none; }}
"""
