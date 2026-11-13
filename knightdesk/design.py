"""Theme palettes and shared drawing primitives for KnightDesk."""
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainterPath, QPen


@dataclass(frozen=True)
class Theme:
    label: str
    surface: str
    shade: str
    accent: str
    secondary: str
    layout: str = "studio"
    radius: int = 20
    mono: bool = False
    light: bool = False

    @property
    def ink(self):
        return QColor("#15263d" if self.light else "#f5f6fb")

    @property
    def muted(self):
        return QColor("#415773" if self.light else "#b0bacd")

    @property
    def on_accent(self):
        return QColor("#ffffff" if self.light else "#171524")

    def layer(self, opacity):
        return alpha(self.ink, opacity)


THEMES = {
    "nocturne": Theme("Nocturne", "#29223d", "#121420", "#c6adff", "#8ee1d0"),
    "graphite": Theme("Graphite", "#292b30", "#101115", "#f0f0f4", "#b3c2d9", "tiles", 25),
    "midnight": Theme("Midnight", "#182b44", "#0d1425", "#a6c9ff", "#77ded6"),
    "frost": Theme("Frosted Slate", "#e1ecf7", "#b7cbe2", "#165794", "#087260", "studio", 24, light=True),
    "iris": Theme("Iris", "#402650", "#1e152b", "#edbaff", "#b5c6ff", "tiles", 24),
    "knight": Theme("Dark Knight", "#352029", "#16121b", "#ff9ca5", "#eccaa5", "studio", 18),
    "cyberpunk": Theme("Cyberpunk", "#143542", "#111b2b", "#71f1e9", "#fc9ed9", "instrument", 12, mono=True),
    "steampunk": Theme("Steampunk", "#433126", "#211916", "#f1c08c", "#a8d5b9", "studio", 16),
    "dota2": Theme("Dota 2", "#462c2b", "#251919", "#f6cc87", "#b5db99", "tiles", 17),
    "terminal": Theme("Terminal", "#183626", "#101d18", "#97f0ad", "#eed897", "instrument", 10, mono=True),
    "dotmatrix": Theme("Dot Matrix", "#292b31", "#14151a", "#ff9b8c", "#ececf1", "tiles", 17, mono=True),
    "hud": Theme("Sci-Fi HUD", "#173244", "#111a27", "#8ee4ff", "#c1b2ff", "instrument", 12, mono=True),
    "bento": Theme("Bento", "#2b3142", "#151c2b", "#ffc392", "#b7dfcb", "tiles", 25),
    "synthwave": Theme("Synthwave", "#3e244e", "#1a172d", "#ffb0e5", "#87ebec", "instrument", 17, mono=True),
}

STYLES = {"invisible": "Text only", "glass": "Glass", "frosted": "Frosted", "dark": "Solid"}
OPACITY = {"invisible": 0, "glass": 207, "frosted": 237, "dark": 255}


def alpha(color, value):
    result = QColor(color)
    result.setAlpha(value)
    return result


def card(p, rect, theme, style, *, tint=None):
    opacity = OPACITY.get(style, OPACITY["glass"])
    if not opacity:
        return
    path = QPainterPath()
    inset = QRectF(rect).adjusted(.55, .55, -.55, -.55)
    radius = min(theme.radius, inset.height() / 2)
    path.addRoundedRect(inset, radius, radius)
    grad = QLinearGradient(inset.topLeft(), QPointF(inset.right() * .75, inset.bottom()))
    grad.setColorAt(0, alpha(tint or theme.surface, opacity))
    grad.setColorAt(1, alpha(theme.shade, opacity))
    p.fillPath(path, grad)
    border = QPen(theme.layer(round(opacity * (.26 if theme.light else .19))))
    border.setCosmetic(True)
    p.setPen(border)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(path)
    if theme.layout == "instrument":
        p.save()
        p.setClipPath(path)
        pen = QPen(alpha(theme.accent, opacity // 3))
        pen.setCosmetic(True)
        p.setPen(pen)
        p.drawLine(QPointF(inset.left() + 12, inset.top()), QPointF(inset.left() + 47, inset.top()))
        p.restore()


def panel(p, rect, color, radius=10, border=None):
    p.setBrush(QColor(color))
    p.setPen(QPen(border, 1) if border else Qt.PenStyle.NoPen)
    p.drawRoundedRect(QRectF(rect), radius, radius)


def glyph(p, name, rect, color, stroke=1.65):
    """Draw a simple vector symbol in a 24-unit coordinate system."""
    p.save()
    p.translate(rect.topLeft())
    p.scale(rect.width() / 24, rect.height() / 24)
    p.setPen(QPen(QColor(color), stroke, Qt.PenStyle.SolidLine,
                  Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)

    def lines(points):
        path = QPainterPath(QPointF(*points[0]))
        for x, y in points[1:]:
            path.lineTo(x, y)
        p.drawPath(path)

    if name == "start":
        for x in (3, 13):
            for y in (3, 13):
                p.fillRect(QRectF(x, y, 8, 8), QColor(color))
    elif name == "settings":
        p.drawEllipse(QPointF(12, 12), 7.5, 7.5)
        p.drawEllipse(QPointF(12, 12), 2.8, 2.8)
        for angle in range(0, 360, 60):
            p.save()
            p.translate(12, 12)
            p.rotate(angle)
            p.drawLine(QPointF(0, -7.5), QPointF(0, -10))
            p.restore()
    elif name == "more":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(color))
        for x in (5, 12, 19):
            p.drawEllipse(QPointF(x, 12), 1.6, 1.6)
    elif name in {"previous", "next"}:
        if name == "previous":
            p.translate(24, 0)
            p.scale(-1, 1)
        lines([(5, 5), (16, 12), (5, 19), (5, 5)])
        lines([(19, 5), (19, 19)])
    elif name == "play":
        lines([(8, 4), (20, 12), (8, 20), (8, 4)])
    elif name == "pause":
        lines([(8, 5), (8, 19)])
        lines([(16, 5), (16, 19)])
    elif name in {"left", "right"}:
        if name == "left":
            p.translate(24, 0)
            p.scale(-1, 1)
        lines([(9, 6), (15, 12), (9, 18)])
    elif name == "check":
        lines([(5, 12), (10, 17), (20, 7)])
    elif name == "plus":
        lines([(5, 12), (19, 12)])
        lines([(12, 5), (12, 19)])
    elif name == "music":
        lines([(9, 16), (9, 6), (19, 4), (19, 14)])
        p.drawEllipse(QPointF(6.5, 17.5), 2.6, 1.9)
        p.drawEllipse(QPointF(16.5, 15.5), 2.6, 1.9)
    elif name == "photo":
        p.drawRoundedRect(QRectF(3, 4, 18, 16), 3, 3)
        p.drawEllipse(QPointF(8.5, 9), 1.6, 1.6)
        lines([(4, 18), (10, 13), (13, 15), (17, 10), (20, 13)])
    elif name == "battery":
        p.drawRoundedRect(QRectF(3, 7, 17, 10), 2, 2)
        lines([(22, 10), (22, 14)])
    elif name == "tray":
        lines([(4, 7), (20, 7)])
        lines([(4, 12), (20, 12)])
        lines([(4, 17), (20, 17)])
        for x, y in ((9, 7), (15, 12), (8, 17)):
            p.setBrush(QColor(color))
            p.drawEllipse(QPointF(x, y), 1.7, 1.7)
    elif name == "app":
        p.drawRoundedRect(QRectF(4, 4, 16, 16), 4, 4)
        for x in (8, 14):
            for y in (8, 14):
                p.fillRect(QRectF(x, y, 2, 2), QColor(color))
    p.restore()
