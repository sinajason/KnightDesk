"""KnightDesk's themed artwork. The desktop controller supplies data and scaling."""
import datetime
import math
import time
from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QBrush, QFont, QFontDatabase, QFontMetricsF, QLinearGradient, QPainter, QPainterPath, QPen

import design

A = design.alpha
AL = Qt.AlignmentFlag
W = QFont.Weight
STYLES = {"invisible": (0, 0), "glass": (154, 54), "frosted": (211, 77), "dark": (249, 90)}

THEMES = {
    "knight": dict(
        label="Dark Knight (default)", card="round", decor="round", gloss=28, shadow=120,
        text=(240, 245, 255), dim=(205, 210, 222, 225), tint=(20, 10, 15),
        accent=(200, 40, 50), start=(90, 170, 255),
        cpu=(235, 240, 255), ram=(255, 200, 60), gpu=(140, 120, 255), disk=(80, 205, 190),
        down=(100, 190, 255), up=(255, 140, 170), ok=(120, 220, 140), warn=(255, 200, 60),
        bad=(255, 90, 90), today=(200, 40, 50, 210), hol=(255, 120, 120),
        day=(240, 245, 255), time=(240, 245, 255), day_size=40, day_weight=W.Light,
        day_spacing=22, day_effect="none", time_fmt="- {t} -", orn="none", gears=False,
        display_fonts=["Cinzel", "Bahnschrift", "Segoe UI"], body_fonts=["Segoe UI"],
        names=dict(cpu="CPU", ram="RAM", gpu="GPU", disk="DISK", procs="TOP PROCESSES", notes="NOTES")),
    "cyberpunk": dict(
        label="Cyberpunk", card="chamfer", decor="chamfer", gloss=12, shadow=170,
        text=(225, 250, 255), dim=(120, 205, 225, 235), tint=(6, 10, 26),
        accent=(0, 240, 255), start=(0, 240, 255),
        cpu=(0, 240, 255), ram=(252, 238, 10), gpu=(255, 40, 160), disk=(0, 255, 150),
        down=(0, 240, 255), up=(255, 40, 160), ok=(0, 255, 150), warn=(252, 238, 10),
        bad=(255, 50, 90), today=(255, 0, 128, 225), hol=(255, 70, 120),
        day=(235, 252, 255), time=(252, 238, 10), day_size=38, day_weight=W.Bold,
        day_spacing=14, day_effect="glitch", time_fmt="// {t} //", orn="cyber", gears=False,
        display_fonts=["Orbitron", "Bahnschrift", "Consolas"],
        body_fonts=["Bahnschrift", "Consolas", "Segoe UI"],
        names=dict(cpu="CPU", ram="RAM", gpu="GPU", disk="DISK", procs="// TOP_PROCS", notes="// DATA_LOG")),
    "steampunk": dict(
        label="Steampunk", card="round", decor="brass", gloss=30, shadow=170, radius=12,
        text=(246, 232, 198), dim=(208, 178, 122, 235), tint=(40, 25, 16),
        accent=(205, 150, 60), start=(225, 170, 80),
        cpu=(228, 178, 84), ram=(208, 112, 62), gpu=(112, 188, 162), disk=(236, 216, 172),
        down=(150, 202, 172), up=(222, 142, 92), ok=(130, 200, 150), warn=(232, 190, 90),
        bad=(220, 90, 70), today=(190, 95, 45, 235), hol=(232, 112, 82),
        day=(232, 190, 110), time=(238, 208, 152), day_size=38, day_weight=W.DemiBold,
        day_spacing=10, day_effect="emboss", time_fmt="~ {t} ~", orn="diamond", gears=True,
        display_fonts=["Palatino Linotype", "Constantia", "Georgia", "Cambria"],
        body_fonts=["Constantia", "Georgia", "Cambria", "Segoe UI"],
        names=dict(cpu="ENGINE", ram="BOILER", gpu="LENS", disk="VAULT", procs="BUSY COGS", notes="CAPTAIN'S LOG")),
    "dota2": dict(
        label="Dota 2 inspired", card="bevel", decor="bevel", gloss=22, shadow=190,
        text=(236, 226, 202), dim=(192, 176, 142, 235), tint=(26, 24, 26),
        accent=(212, 170, 70), start=(212, 170, 70),
        cpu=(92, 200, 80), ram=(70, 140, 240), gpu=(214, 62, 56), disk=(228, 182, 72),
        down=(90, 170, 240), up=(214, 92, 82), ok=(92, 200, 80), warn=(228, 182, 72),
        bad=(214, 62, 56), today=(178, 34, 34, 235), hol=(232, 92, 82),
        day=(228, 188, 100), time=(226, 186, 98), day_size=38, day_weight=W.Bold,
        day_spacing=12, day_effect="outline", time_fmt="◆ {t} ◆", orn="diamond", gears=False,
        display_fonts=["Cinzel", "Trajan Pro", "Palatino Linotype", "Georgia"],
        body_fonts=["Constantia", "Palatino Linotype", "Segoe UI"],
        names=dict(cpu="HP", ram="MANA", gpu="GPU", disk="GOLD", procs="TOP HEROES", notes="SCROLL")),
}
TH = THEMES["knight"]
THEME_NAME = "knight"
WHITE = QColor(*TH["text"])
DIM = QColor(*TH["dim"])
BODY_FONT = DISPLAY_FONT = "Segoe UI"


def C(key, opacity=None):
    values = TH[key]
    return A(QColor(*values), opacity) if opacity is not None else QColor(*values)


def activate(name):
    global TH, THEME_NAME, WHITE, DIM, BODY_FONT, DISPLAY_FONT
    THEME_NAME = name
    TH = THEMES.get(name, THEMES["knight"])
    WHITE, DIM = C("text"), C("dim")
    families = set(QFontDatabase.families())
    BODY_FONT = next((family for family in TH["body_fonts"] if family in families), "Segoe UI")
    DISPLAY_FONT = next((family for family in TH["display_fonts"] if family in families), BODY_FONT)
    font.cache_clear()


def card_path(w, h, radius, kind):
    path = QPainterPath()
    if kind == "round" or radius >= min(w, h) / 2 - 1:
        path.addRoundedRect(QRectF(1, 1, w - 2, h - 2), radius, radius)
        return path
    c = 14 if kind == "chamfer" else 9
    if kind == "chamfer":      # cut top-left and bottom-right
        pts = [(1 + c, 1), (w - 1, 1), (w - 1, h - 1 - c), (w - 1 - c, h - 1), (1, h - 1), (1, 1 + c)]
    else:                      # bevel: all four corners
        pts = [(1 + c, 1), (w - 1 - c, 1), (w - 1, 1 + c), (w - 1, h - 1 - c),
               (w - 1 - c, h - 1), (1 + c, h - 1), (1, h - 1 - c), (1, 1 + c)]
    path.moveTo(*pts[0])
    for pt in pts[1:]:
        path.lineTo(*pt)
    path.closeSubpath()
    return path


def diamond(p, cx, cy, s, col):
    path = QPainterPath()
    path.moveTo(cx, cy - s)
    path.lineTo(cx + s, cy)
    path.lineTo(cx, cy + s)
    path.lineTo(cx - s, cy)
    path.closeSubpath()
    p.fillPath(path, col)


def decor_round(p, path, w, h, f, radius, kind):
    p.setPen(QPen(QColor(255, 255, 255, int(95 * f)), 1.4))
    p.drawPath(path)


def decor_chamfer(p, path, w, h, f, radius, kind):
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(0, 240, 255, int(55 * f)), 5))
    p.drawPath(path)
    p.setPen(QPen(QColor(0, 240, 255, int(235 * f)), 1.5))
    p.drawPath(path)
    p.setPen(QPen(QColor(255, 40, 160, int(255 * f)), 3))
    p.drawLine(QPointF(w - 44, 2), QPointF(w - 3, 2))
    p.setPen(QPen(QColor(252, 238, 10, int(255 * f)), 2.2))
    p.drawLine(QPointF(2, h - 32), QPointF(2, h - 4))
    p.save()
    p.setClipPath(path)
    p.setPen(QPen(QColor(0, 240, 255, 9), 1))
    for y in range(3, h, 4):
        p.drawLine(0, y, w, y)
    p.restore()


def decor_brass(p, path, w, h, f, radius, kind):
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(196, 148, 66, int(255 * f)), 2.4))
    p.drawPath(path)
    inner = card_path(w - 12, h - 12, max(2, radius - 5), kind)
    inner.translate(5, 5)
    p.setPen(QPen(QColor(150, 108, 48, int(190 * f)), 1))
    p.drawPath(inner)
    p.setPen(QPen(QColor(80, 52, 22, int(220 * f)), 1))
    p.setBrush(QColor(224, 178, 92, int(255 * f)))
    off = 11 if radius < min(w, h) / 2 - 1 else None
    if off:
        for x, y in ((off, off), (w - off, off), (off, h - off), (w - off, h - off)):
            p.drawEllipse(QPointF(x, y), 2.6, 2.6)


def decor_bevel(p, path, w, h, f, radius, kind):
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(208, 162, 66, int(255 * f)), 1.8))
    p.drawPath(path)
    inner = card_path(w - 10, h - 10, radius, kind)
    inner.translate(4, 4)
    p.setPen(QPen(QColor(118, 88, 40, int(210 * f)), 1))
    p.drawPath(inner)
    if radius < min(w, h) / 2 - 1:
        gold = QColor(226, 182, 80, int(255 * f))
        diamond(p, w / 2, 1.5, 4.5, gold)
        diamond(p, w / 2, h - 1.5, 4.5, gold)


DECORS = {"round": decor_round, "chamfer": decor_chamfer, "brass": decor_brass, "bevel": decor_bevel}


def draw_card(p, w, h, radius=18, min_alpha=0, min_outline=0, tint=None):
    a, ol = STYLES.get(CFG["style"], STYLES["glass"])
    a, ol = max(a, min_alpha), max(ol, min_outline)
    kind = TH["card"]
    if kind == "round" and TH.get("radius") and radius < min(w, h) / 2 - 1:
        radius = TH["radius"]
    path = card_path(w, h, radius, kind)
    tc = tint or TH["tint"]
    p.fillPath(path, QColor(tc[0], tc[1], tc[2], max(a, 1)))      # alpha 1 keeps it clickable
    if a:
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0, QColor(255, 255, 255, int(TH["gloss"] * min(1, a / 60))))
        g.setColorAt(0.5, QColor(255, 255, 255, 0))
        p.fillPath(path, g)
    if ol:
        DECORS[TH["decor"]](p, path, w, h, ol / 95, radius, kind)


def dt(p, rect, align, s):
    """draw text with a soft shadow so it stays readable on any wallpaper"""
    pen = p.pen()
    p.setPen(QColor(0, 0, 0, TH["shadow"]))
    rect = QRectF(rect)
    value = p.fontMetrics().elidedText(s, Qt.TextElideMode.ElideRight, max(0, int(rect.width())))
    p.drawText(rect.translated(1, 1), align, value)
    p.setPen(pen)
    p.drawText(rect, align, value)


@lru_cache(maxsize=128)
def font(size, weight=QFont.Weight.Normal, family=None, spacing=0):
    f = QFont(family or BODY_FONT, 1)
    f.setPointSizeF(size)
    f.setWeight(weight)
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return f


def gear(p, cx, cy, r, teeth, angle, col):
    import math
    ri, ro, tw = r * 0.80, r, 2 * math.pi / teeth
    a0 = math.radians(angle)
    pts = []
    for i in range(teeth):
        a = a0 + i * tw
        for rr, da in ((ri, 0), (ro, 0.12), (ro, 0.38), (ri, 0.5)):
            pts.append((cx + rr * math.cos(a + da * tw), cy + rr * math.sin(a + da * tw)))
    path = QPainterPath()
    path.moveTo(*pts[0])
    for pt in pts[1:]:
        path.lineTo(*pt)
    path.closeSubpath()
    path.addEllipse(QPointF(cx, cy), r * 0.28, r * 0.28)
    path.setFillRule(Qt.FillRule.OddEvenFill)
    p.setBrush(col)
    p.setPen(QPen(A(col, min(255, col.alpha() + 70)), 1))
    p.drawPath(path)


def alpha_style():
    return STYLES.get(CFG["style"], STYLES["glass"])


def txtbar(pct, n):
    k = int(round(n * max(0, min(100, pct)) / 100))
    return "#" * k + "." * (n - k)


def sparktxt(data, n, mx):
    sp = "▁▂▃▄▅▆▇█"
    return "".join(sp[min(7, int(max(0, v) / max(mx, 1) * 7.999))] for v in list(data)[-n:])


def draw_cal(p, wd, x, y, w, rowh, f_hdr, f_num, today_fn, hdr_col, num_col, hol_col):
    ttl, header, weeks, today, hol = wd.month_matrix(datetime.datetime.now())
    cw = w / 7
    p.setFont(f_hdr)
    for i, hn in enumerate(header):
        col = 6 - i if wd.jalali else i
        p.setPen(hol_col if i == hol else hdr_col)
        dt(p, QRectF(x + col * cw, y, cw, rowh), AL.AlignCenter, hn)
    for r, week in enumerate(weeks):
        for i, d in enumerate(week):
            if not d:
                continue
            col = 6 - i if wd.jalali else i
            cell = QRectF(x + col * cw, y + (r + 1) * rowh, cw, rowh)
            tc = today_fn(p, cell) if d == today else None
            p.setFont(f_num)
            p.setPen(tc or (hol_col if i == hol else num_col))
            dt(p, cell, AL.AlignCenter, fa(d) if wd.jalali else str(d))
    return ttl


def ring(p, cx, cy, r, wid, col, frac, bg=35, start=90, full=360):
    rect = QRectF(cx - r, cy - r, 2 * r, 2 * r)
    p.setBrush(Qt.BrushStyle.NoBrush)
    pen = QPen(A(col, bg), wid)
    pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    p.setPen(pen)
    p.drawArc(rect, int(start * 16), int(-full * 16))
    if frac > 0.003:
        pen = QPen(col, wid)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawArc(rect, int(start * 16), int(-full * min(1, frac) * 16))


def seg_ring(p, cx, cy, r, wid, col, frac, n=20):
    rect = QRectF(cx - r, cy - r, 2 * r, 2 * r)
    lit = int(round(n * min(1, max(0, frac))))
    step = 360 / n
    p.setBrush(Qt.BrushStyle.NoBrush)
    for i in range(n):
        p.setPen(QPen(col if i < lit else A(col, 35), wid))
        p.drawArc(rect, int((90 - i * step) * 16), int(-(step - 7) * 16))


def ticks(p, cx, cy, r0, r1, n, col, major=0):
    for i in range(n):
        th = math.radians(i * 360 / n)
        big = major and i % major == 0
        r_in = r0 - (4 if big else 0)
        p.setPen(QPen(col, 2 if big else 1))
        p.drawLine(QPointF(cx + r_in * math.sin(th), cy - r_in * math.cos(th)),
                   QPointF(cx + r1 * math.sin(th), cy - r1 * math.cos(th)))


def hands(p, cx, cy, n, lh, lm, ls, col_hm, col_s, wh=4, wm=3):
    for ang, ln, wid, col in (((n.hour % 12 + n.minute / 60) * 30, lh, wh, col_hm),
                              ((n.minute + n.second / 60) * 6, lm, wm, col_hm),
                              (n.second * 6, ls, 1.6, col_s)):
        th = math.radians(ang)
        pen = QPen(col, wid)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(cx, cy), QPointF(cx + ln * math.sin(th), cy - ln * math.cos(th)))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(col_s)
    p.drawEllipse(QPointF(cx, cy), 4, 4)


# ----------------------------------------------------------------- 1) TERMINAL
class Terminal:
    clock_row = True
    sizes = {"clock": (540, 214), "weather": (310, 104), "system": (310, 112), "rings": (310, 126),
             "forecast": (310, 126), "calendar_fa": (268, 187), "calendar": (268, 187),
             "disks": (310, 102), "procs": (310, 106),
             "net": (310, 112), "info": (310, 106), "notes": (310, 150), "analog": (170, 170)}

    def frame(self, wd, p, title):
        w, h = wd.width(), wd.height()
        a, ol = alpha_style()
        col = C("accent")
        p.fillRect(QRectF(0, 7, w, h - 7), QColor(2, 14, 7, max(a, 1)))
        p.setFont(font(8.5, W.Bold))
        tw = p.fontMetrics().horizontalAdvance(title) + 14
        if ol:
            p.setPen(QPen(A(col, int(180 * ol / 95)), 1))
            p.drawLine(QPointF(0.5, 7.5), QPointF(10, 7.5))
            p.drawLine(QPointF(10 + tw, 7.5), QPointF(w, 7.5))
            p.drawLine(QPointF(0.5, 7.5), QPointF(0.5, h))
            p.drawLine(QPointF(w - 0.5, 7.5), QPointF(w - 0.5, h))
            p.drawLine(QPointF(0.5, h - 0.5), QPointF(w, h - 0.5))
        p.setPen(col)
        dt(p, QRectF(10, 0, tw, 15), AL.AlignCenter, title)
        if a:
            p.setPen(QPen(QColor(0, 0, 0, 24), 1))
            for y in range(10, h, 4):
                p.drawLine(0, y, w, y)

    def cols(self, wd, p, used):
        p.setFont(font(9))
        return max(4, int((wd.width() - 24) / max(1, p.fontMetrics().horizontalAdvance("█"))) - used)

    def lines(self, wd, p, title, rows, y0=24):
        self.frame(wd, p, title)
        p.setFont(font(9))
        lh = p.fontMetrics().height() + 2
        y = y0
        for r in rows:
            txt, col = r if isinstance(r, tuple) else (r, WHITE)
            p.setPen(col)
            dt(p, QRectF(12, y, wd.width() - 24, lh), AL.AlignLeft | AL.AlignVCenter, txt)
            y += lh

    def p_clock(self, wd, p):
        self.frame(wd, p, "tty1")
        n, w, ac = datetime.datetime.now(), wd.width(), C("accent")
        p.setFont(font(9))
        p.setPen(DIM)
        dt(p, QRectF(14, 24, w, 16), AL.AlignLeft | AL.AlignVCenter,
           "$ date" + (" █" if n.second % 2 == 0 else ""))
        p.setFont(font(50, W.Bold))
        s = n.strftime("%H:%M:%S")
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            p.setPen(A(ac, 45))
            p.drawText(QRectF(14 + dx, 46 + dy, w, 70), AL.AlignLeft | AL.AlignVCenter, s)
        p.setPen(ac)
        p.drawText(QRectF(14, 46, w, 70), AL.AlignLeft | AL.AlignVCenter, s)
        p.setFont(font(11))
        p.setPen(WHITE)
        dt(p, QRectF(14, 122, w, 20), AL.AlignLeft | AL.AlignVCenter,
           f"{n.strftime('%A')}, {n.day} {n.strftime('%B')} {n.year}")
        if CFG["jalali_clock"]:
            jy, jm, jd = g2j(n.year, n.month, n.day)
            p.setPen(DIM)
            dt(p, QRectF(14, 144, w - 28, 20), AL.AlignLeft | AL.AlignVCenter,
               f"{FA_DAYS_MON0[n.weekday()]} {fa(jd)} {FA_MONTHS[jm - 1]} {fa(jy)}")
        p.setPen(DIM)
        up = int(time.time() - BOOT_TIME)
        dt(p, QRectF(14, 170, w - 28, 20), AL.AlignLeft | AL.AlignVCenter,
           f"up {up // 86400}d {up % 86400 // 3600}h {up % 3600 // 60}m")

    def p_weather(self, wd, p):
        d = wd.d
        rows = [(CFG["city"], DIM)]
        if d:
            name, _ = code_info(d["c"])
            rows += [(f"{conv(d['t'])}°{CFG['units'].upper()}  {name}", C("accent")),
                     (f"high {conv(d['hi'])}°   low {conv(d['lo'])}°", WHITE)]
        else:
            rows.append(("fetching...", DIM))
        self.lines(wd, p, "weather", rows)

    def p_system(self, wd, p):
        h, g = wd.hub, wd.hub.gpu_val
        n = self.cols(wd, p, 12)
        self.lines(wd, p, "top", [
            (f"cpu [{txtbar(h.cpu[-1], n)}] {h.cpu[-1]:3.0f}%", C("cpu")),
            (f"gpu [{txtbar(g[0] if g else 0, n)}] {(f'{g[0]:3.0f}%' if g else ' n/a')}", C("gpu")),
            (f"ram [{txtbar(h.ram[-1], n)}] {h.ram[-1]:3.0f}%", C("ram")),
            (f"net ↓ {fmt_speed(h.down[-1])}  ↑ {fmt_speed(h.up[-1])}", DIM)])

    def p_rings(self, wd, p):
        h, g = wd.hub, wd.hub.gpu_val
        n = self.cols(wd, p, 12)
        self.lines(wd, p, "htop", [
            (f"cpu {sparktxt(h.cpu, n, 100)} {h.cpu[-1]:3.0f}", C("cpu")),
            (f"ram {sparktxt(h.ram, n, 100)} {h.ram[-1]:3.0f}", C("ram")),
            (f"gpu {sparktxt(h.gpu, n, 100)} {(g[0] if g else 0):3.0f}", C("gpu")),
            (f"dsk {txtbar(h.disk_main, n)} {h.disk_main:3.0f}", C("disk"))])

    def p_forecast(self, wd, p):
        d = wd.d
        rows = [(f"{datetime.date.fromisoformat(x['d']).strftime('%a').lower()}  "
                 f"{code_info(x['c'])[0]:<14.14}{conv(x['hi']):>3}°/{conv(x['lo']):<3}°", WHITE)
                for x in (d["days"][:5] if d else [])] or [("loading...", DIM)]
        self.lines(wd, p, "forecast", rows)

    def p_calendar(self, wd, p):
        self.frame(wd, p, "cal")
        w = wd.width()
        p.setFont(font(9, W.Bold))
        p.setPen(C("accent"))
        ttl = wd.month_matrix(datetime.datetime.now())[0]
        dt(p, QRectF(0, 22, w, 18), AL.AlignCenter, ttl)

        def today(pp, cell):
            pp.fillRect(cell.adjusted(2, 2, -2, -2), C("accent"))
            return QColor(2, 14, 7)
        draw_cal(p, wd, 12, 42, w - 24, 19, font(8.5, W.Bold), font(9), today, DIM, WHITE, C("hol"))

    def p_disks(self, wd, p):
        n = self.cols(wd, p, 22)
        rows = [(f"{nm:<3} [{txtbar(pc, n)}] {pc:3.0f}% {(t - u) / 2**30:4.0f}G", C("disk") if pc < 90 else C("bad"))
                for nm, t, u, pc in wd.hub.disks] or [("no disks", DIM)]
        self.lines(wd, p, "df -h", rows)

    def p_procs(self, wd, p):
        rows = [(f"{nm[:16]:<16} {c:5.1f}% {m:6.0f}M", WHITE) for nm, c, m in wd.hub.procs]
        self.lines(wd, p, "ps", [("NAME              CPU     MEM", DIM)] + rows)

    def p_net(self, wd, p):
        h, ms = wd.hub, wd.hub.ping_ms
        n = self.cols(wd, p, 14)
        self.lines(wd, p, "net", [
            (f"ping {CFG['ping_host']}: " + (f"{ms:.0f} ms" if ms else "timeout"), C("ok") if ms else C("bad")),
            (f"rx {sparktxt(h.down, n, max(50e3, max(h.down)))} {fmt_speed(h.down[-1])}", C("down")),
            (f"tx {sparktxt(h.up, n, max(50e3, max(h.up)))} {fmt_speed(h.up[-1])}", C("up")),
            (f"total rx {h.total_down / 1048576:.0f} MB", DIM)])

    def p_info(self, wd, p):
        self.lines(wd, p, "uptime", [(f"{k.lower():<10}{v}", WHITE) for k, v in wd.hub.info])

    def p_notes(self, wd, p):
        self.frame(wd, p, "nano notes.txt")

    def p_analog(self, wd, p):
        w = wd.width()
        self.frame(wd, p, "clk")
        c, n = C("accent"), datetime.datetime.now()
        p.setPen(QPen(A(c, 120), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(w / 2, w / 2 + 6), 66, 66)
        ticks(p, w / 2, w / 2 + 6, 62, 66, 12, c, 3)
        hands(p, w / 2, w / 2 + 6, n, 32, 50, 58, c, C("warn"), 3, 2)


# ----------------------------------------------------------------- 2) DOT MATRIX
GLY = {
    "A": "01110,10001,10001,11111,10001,10001,10001", "B": "11110,10001,10001,11110,10001,10001,11110",
    "C": "01110,10001,10000,10000,10000,10001,01110", "D": "11110,10001,10001,10001,10001,10001,11110",
    "E": "11111,10000,10000,11110,10000,10000,11111", "F": "11111,10000,10000,11110,10000,10000,10000",
    "G": "01110,10001,10000,10111,10001,10001,01111", "H": "10001,10001,10001,11111,10001,10001,10001",
    "I": "01110,00100,00100,00100,00100,00100,01110", "J": "00111,00010,00010,00010,00010,10010,01100",
    "K": "10001,10010,10100,11000,10100,10010,10001", "L": "10000,10000,10000,10000,10000,10000,11111",
    "M": "10001,11011,10101,10101,10001,10001,10001", "N": "10001,11001,10101,10011,10001,10001,10001",
    "O": "01110,10001,10001,10001,10001,10001,01110", "P": "11110,10001,10001,11110,10000,10000,10000",
    "Q": "01110,10001,10001,10001,10101,10010,01101", "R": "11110,10001,10001,11110,10100,10010,10001",
    "S": "01111,10000,10000,01110,00001,00001,11110", "T": "11111,00100,00100,00100,00100,00100,00100",
    "U": "10001,10001,10001,10001,10001,10001,01110", "V": "10001,10001,10001,10001,10001,01010,00100",
    "W": "10001,10001,10001,10101,10101,11011,10001", "X": "10001,10001,01010,00100,01010,10001,10001",
    "Y": "10001,10001,01010,00100,00100,00100,00100", "Z": "11111,00001,00010,00100,01000,10000,11111",
    "0": "01110,10001,10011,10101,11001,10001,01110", "1": "00100,01100,00100,00100,00100,00100,01110",
    "2": "01110,10001,00001,00010,00100,01000,11111", "3": "11110,00001,00001,01110,00001,00001,11110",
    "4": "00010,00110,01010,10010,11111,00010,00010", "5": "11111,10000,11110,00001,00001,10001,01110",
    "6": "00110,01000,10000,11110,10001,10001,01110", "7": "11111,00001,00010,00100,01000,01000,01000",
    "8": "01110,10001,10001,01110,10001,10001,01110", "9": "01110,10001,10001,01111,00001,00010,01100",
    ":": "00000,00100,00100,00000,00100,00100,00000", ".": "00000,00000,00000,00000,00000,00110,00110",
    "%": "11001,11010,00010,00100,01000,01011,10011", "°": "01100,10010,10010,01100,00000,00000,00000",
    "/": "00001,00010,00010,00100,01000,01000,10000", "-": "00000,00000,00000,11111,00000,00000,00000",
    "↓": "00100,00100,00100,10101,01110,00100,00000", "↑": "00100,01110,10101,00100,00100,00100,00000",
}
GL = {k: v.split(",") for k, v in GLY.items()}
GL[" "] = ["00000"] * 7
D_ON, D_DIM, D_RED = QColor(245, 245, 245), QColor(245, 245, 245, 90), QColor(255, 56, 44)


def dot_w(text, d):
    return len(text) * 6 * d - d


def dots(p, x, y, text, d, col, ghost=0):
    rad = d * 0.36
    p.setPen(Qt.PenStyle.NoPen)
    cx = x
    for ch in text.upper():
        g = GL.get(ch, GL[" "])
        for r in range(7):
            for c in range(5):
                if g[r][c] == "1":
                    p.setBrush(col)
                elif ghost:
                    p.setBrush(QColor(255, 255, 255, ghost))
                else:
                    continue
                p.drawEllipse(QPointF(cx + c * d + d / 2, y + r * d + d / 2), rad, rad)
        cx += 6 * d
    return cx - x - d


def dots_c(p, cx, y, text, d, col, ghost=0):
    dots(p, cx - dot_w(text, d) / 2, y, text, d, col, ghost)


def dots_r(p, rx, y, text, d, col):
    dots(p, rx - dot_w(text, d), y, text, d, col)


def dot_bar(p, x, y, n, pitch, frac, col, rad=None):
    rad = rad or pitch * 0.36
    lit = int(round(n * min(1, max(0, frac))))
    p.setPen(Qt.PenStyle.NoPen)
    for i in range(n):
        p.setBrush(col if i < lit else QColor(245, 245, 245, 38))
        p.drawEllipse(QPointF(x + i * pitch + pitch / 2, y), rad, rad)


def dot_ring(p, cx, cy, r, n, frac, col, rad=2.3):
    lit = int(round(n * min(1, max(0, frac))))
    p.setPen(Qt.PenStyle.NoPen)
    for i in range(n):
        th = math.radians(i * 360 / n)
        p.setBrush(col if i < lit else QColor(245, 245, 245, 38))
        p.drawEllipse(QPointF(cx + r * math.sin(th), cy - r * math.cos(th)), rad, rad)


class DotMatrix:
    clock_row = True
    sizes = {"clock": (560, 232), "weather": (270, 138), "system": (300, 128), "rings": (350, 126),
             "forecast": (350, 126), "calendar_fa": (250, 216), "calendar": (250, 216),
             "disks": (300, 142), "procs": (300, 118),
             "net": (300, 128), "info": (300, 124), "notes": (270, 150), "analog": (180, 180)}

    def card(self, wd, p, radius=28):
        w, h = wd.width(), wd.height()
        a, ol = alpha_style()
        path = QPainterPath()
        path.addRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), min(radius, w / 2, h / 2), min(radius, w / 2, h / 2))
        p.fillPath(path, QColor(0, 0, 0, max(a, 1)))
        if ol:
            p.setPen(QPen(QColor(255, 255, 255, int(45 * ol / 95)), 1))
            p.drawPath(path)

    def label(self, p, x, y, w, text, align=AL.AlignLeft):
        p.setPen(QColor(245, 245, 245, 150))
        p.setFont(font(7.5, W.DemiBold, None, 1.6))
        p.drawText(QRectF(x, y, w, 14), align | AL.AlignVCenter, text.upper())

    def p_clock(self, wd, p):
        self.card(wd, p, 34)
        n, w = datetime.datetime.now(), wd.width()
        d = 12
        dots(p, 28, 22, n.strftime("%A"), 4, D_ON)
        dots_r(p, w - 28, 22, f"{n.day} {n.strftime('%b')} {n.year}", 4, D_DIM)
        hh, mm = n.strftime("%I"), n.strftime("%M")
        x = 28
        dots(p, x, 64, hh, d, D_ON, 22)
        dots(p, x + 12 * d, 64, ":", d, D_RED, 22)
        dots(p, x + 18 * d, 64, mm, d, D_ON, 22)
        dots(p, x + 31 * d + 16, 64 + 84 - 35, n.strftime("%p"), 5, D_DIM)
        dot_bar(p, 28, 176, 60, (w - 56) / 60, (n.second + 1) / 60, D_RED, 2.2)
        if CFG["jalali_clock"]:
            p.setPen(QColor(245, 245, 245, 150))
            p.setFont(font(11))
            jy, jm, jd = g2j(n.year, n.month, n.day)
            dt(p, QRectF(28, 192, w - 56, 26), AL.AlignLeft | AL.AlignVCenter,
               f"{FA_DAYS_MON0[n.weekday()]} {fa(jd)} {FA_MONTHS[jm - 1]} {fa(jy)}")

    def p_weather(self, wd, p):
        self.card(wd, p)
        d, w = wd.d, wd.width()
        dots(p, 22, 20, f"{conv(d['t'])}°" if d else "--°", 9, D_ON)
        name, icon = code_info(d["c"]) if d else ("loading", "☁")
        p.setPen(QColor(245, 245, 245))
        p.setFont(QFont("Segoe UI Emoji", 20))
        weather_icon(p, w - 64, 18, 44, d["c"] if d else 3)
        self.label(p, 22, 90, w - 44, f"{CFG['city']} · {name}")
        if d:
            dots(p, 22, 110, f"H{conv(d['hi'])} L{conv(d['lo'])}", 3, D_RED)

    def p_system(self, wd, p):
        self.card(wd, p)
        h, g, w = wd.hub, wd.hub.gpu_val, wd.width()
        for i, (nm, v, col) in enumerate((("CPU", h.cpu[-1], D_ON), ("GPU", g[0] if g else 0, D_ON), ("RAM", h.ram[-1], D_ON))):
            y = 20 + i * 32
            dots(p, 20, y, nm, 3, D_DIM)
            dot_bar(p, 84, y + 10, 16, 8.5, v / 100, D_RED if v > 85 else col, 2.6)
            dots_r(p, w - 20, y, f"{v:.0f}%" if (nm != "GPU" or g) else "N/A", 3, D_ON)

    def p_rings(self, wd, p):
        self.card(wd, p)
        h, g = wd.hub, wd.hub.gpu_val
        for i, (nm, v) in enumerate((("cpu", h.cpu[-1]), ("ram", h.ram[-1]), ("gpu", g[0] if g else 0), ("disk", h.disk_main))):
            cx = 44 + i * 86
            dot_ring(p, cx, 48, 30, 24, v / 100, D_RED if v > 85 else D_ON)
            dots_c(p, cx, 37, f"{v:.0f}", 3, D_ON)
            self.label(p, cx - 36, 88, 72, TH["names"][nm], AL.AlignHCenter)

    def p_forecast(self, wd, p):
        self.card(wd, p)
        d = wd.d
        for i, x in enumerate(d["days"][:5] if d else []):
            cx = 10 + i * 66 + 33
            dots_c(p, cx + 1, 14, datetime.date.fromisoformat(x["d"]).strftime("%a"), 2, D_DIM)
            p.setPen(D_ON)
            p.setFont(QFont("Segoe UI Emoji", 14))
            p.drawText(QRectF(cx - 30, 32, 60, 30), AL.AlignCenter, code_info(x["c"])[1])
            dots_c(p, cx, 68, f"{conv(x['hi'])}", 4, D_ON)
            dots_c(p, cx, 102, f"{conv(x['lo'])}", 2, D_DIM)

    def p_calendar(self, wd, p):
        self.card(wd, p)
        w = wd.width()
        ttl = wd.month_matrix(datetime.datetime.now())[0]
        p.setPen(QColor(245, 245, 245))
        p.setFont(font(11, W.DemiBold))
        dt(p, QRectF(0, 10, w, 26), AL.AlignCenter, ttl)

        def today(pp, cell):
            pp.setPen(Qt.PenStyle.NoPen)
            pp.setBrush(D_RED)
            pp.drawEllipse(cell.center(), 11, 11)
            return QColor(255, 255, 255)
        draw_cal(p, wd, 12, 40, w - 24, 25, font(8, W.DemiBold, None, 1), font(9.5), today,
                 QColor(245, 245, 245, 120), QColor(245, 245, 245), D_RED)

    def p_disks(self, wd, p):
        self.card(wd, p)
        w = wd.width()
        for i, (nm, t, u, pc) in enumerate(wd.hub.disks[:4]):
            y = 14 + i * 30
            dots(p, 20, y, nm.rstrip("\\/") or "/", 3, D_DIM)
            dot_bar(p, 66, y + 10, 16, 8, pc / 100, D_RED if pc > 90 else D_ON, 2.5)
            dots_r(p, w - 18, y, f"{(t - u) / 2**30:.0f}G", 3, D_ON)

    def p_procs(self, wd, p):
        self.card(wd, p)
        w = wd.width()
        for i, (nm, c, m) in enumerate(wd.hub.procs):
            y = 14 + i * 24
            p.setPen(QColor(245, 245, 245, 200))
            p.setFont(font(8.5, W.DemiBold, None, 1.2))
            p.drawText(QRectF(20, y, 170, 20), AL.AlignLeft | AL.AlignVCenter, nm[:16].upper())
            dots_r(p, w - 20, y + 2, f"{c:.0f}%", 3, D_RED if c > 50 else D_ON)

    def p_net(self, wd, p):
        self.card(wd, p)
        h, ms, w = wd.hub, wd.hub.ping_ms, wd.width()
        self.label(p, 22, 14, 100, "ping")
        dots(p, 22, 32, f"{ms:.0f}" if ms else "--", 8, D_ON if ms else D_RED)
        dots(p, 22 + dot_w(f"{ms:.0f}" if ms else "--", 8) + 10, 32 + 56 - 21, "MS", 3, D_DIM)
        dots_r(p, w - 20, 26, f"↓{h.down[-1] / 1024:.0f}K", 3, D_ON)
        dots_r(p, w - 20, 56, f"↑{h.up[-1] / 1024:.0f}K", 3, D_ON)
        dot_bar(p, 22, 108, 30, 8.6, 1 - min(1, (ms or 200) / 200), D_RED if not ms else D_ON, 2.4)

    def p_info(self, wd, p):
        self.card(wd, p)
        w = wd.width()
        for i, (k, v) in enumerate(wd.hub.info):
            y = 8 + i * 28
            self.label(p, 20, y + 4, 100, k)
            dots_r(p, w - 20, y, v.replace(" ⚡", ""), 3, D_ON)

    def p_notes(self, wd, p):
        self.card(wd, p)
        dots(p, 20, 10, "NOTES", 3, D_DIM)

    def p_analog(self, wd, p):
        w = wd.width()
        self.card(wd, p, w / 2)
        c, n = w / 2, datetime.datetime.now()
        dot_ring(p, c, c, 72, 60, 1, D_DIM, 1.2)
        dot_ring(p, c, c, 72, 12, 1, D_ON, 2.6)
        for ang, ln, col in (((n.hour % 12 + n.minute / 60) * 30, 6, D_ON), ((n.minute + n.second / 60) * 6, 9, D_ON)):
            th = math.radians(ang)
            for k in range(1, ln):
                p.setBrush(col)
                p.drawEllipse(QPointF(c + k * 7 * math.sin(th), c - k * 7 * math.cos(th)), 2.4, 2.4)
        th = math.radians(n.second * 6)
        p.setBrush(D_RED)
        p.drawEllipse(QPointF(c + 60 * math.sin(th), c - 60 * math.cos(th)), 3.2, 3.2)
        p.drawEllipse(QPointF(c, c), 3.4, 3.4)


# ----------------------------------------------------------------- 3) SCI-FI HUD
class Hud:
    sizes = {"clock": (460, 460), "weather": (230, 230), "system": (260, 260), "rings": (370, 128),
             "forecast": (380, 136), "calendar_fa": (250, 216), "calendar": (250, 216),
             "disks": (280, 152), "procs": (270, 124),
             "net": (230, 230), "info": (270, 124), "notes": (270, 150), "analog": (190, 190)}

    def frame(self, wd, p, title=None):
        w, h = wd.width(), wd.height()
        a, ol = alpha_style()
        p.fillRect(QRectF(0, 0, w, h), QColor(3, 14, 24, max(a, 1)))
        if ol:
            f = ol / 95
            p.setPen(QPen(A(C("accent"), int(240 * f)), 2))
            L = 14
            for x, y, dx, dy in ((1, 1, 1, 1), (w - 1, 1, -1, 1), (1, h - 1, 1, -1), (w - 1, h - 1, -1, -1)):
                p.drawLine(QPointF(x, y), QPointF(x + dx * L, y))
                p.drawLine(QPointF(x, y), QPointF(x, y + dy * L))
            p.fillRect(QRectF(w - 14, 6, 7, 7), A(C("warn"), int(255 * f)))
        if title:
            p.setPen(DIM)
            p.setFont(font(8, W.DemiBold, None, 2))
            dt(p, QRectF(14, 7, w - 40, 14), AL.AlignLeft | AL.AlignVCenter, "▸ " + title)

    def p_clock(self, wd, p):
        w = wd.width()
        cx = cy = w / 2
        n = datetime.datetime.now()
        a, ol = alpha_style()
        ac, org = C("accent"), C("warn")
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(3, 14, 24, max(a, 1)))
        p.drawEllipse(QPointF(cx, cy), 226, 226)
        ticks(p, cx, cy, 216, 224, 120, A(ac, 150), 10)
        ang = (time.time() * 10) % 360
        p.setPen(QPen(A(ac, 170), 3))
        p.setBrush(Qt.BrushStyle.NoBrush)
        for i in range(8):
            p.drawArc(QRectF(cx - 200, cy - 200, 400, 400), int((ang + i * 45) * 16), int(30 * 16))
        ring(p, cx, cy, 178, 7, ac, n.second / 60)
        ring(p, cx, cy, 158, 7, org, (n.minute + n.second / 60) / 60)
        ring(p, cx, cy, 138, 7, A(ac, 210), ((n.hour % 12) + n.minute / 60) / 12)
        th = math.radians(n.second * 6)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255))
        p.drawEllipse(QPointF(cx + 178 * math.sin(th), cy - 178 * math.cos(th)), 5, 5)
        p.setPen(QPen(A(ac, 70), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), 118, 118)
        p.setPen(DIM)
        p.setFont(font(10, W.DemiBold, None, 3))
        dt(p, QRectF(cx - 100, cy - 84, 200, 20), AL.AlignCenter, n.strftime("%A").upper())
        p.setPen(WHITE)
        p.setFont(font(42, W.Light))
        dt(p, QRectF(cx - 110, cy - 50, 220, 70), AL.AlignCenter, n.strftime("%I:%M").lstrip("0"))
        p.setPen(org)
        p.setFont(font(10, W.Bold, None, 2))
        dt(p, QRectF(cx - 60, cy + 20, 120, 18), AL.AlignCenter, n.strftime("%p"))
        p.setPen(WHITE)
        p.setFont(font(10.5))
        dt(p, QRectF(cx - 100, cy + 44, 200, 18), AL.AlignCenter, f"{n.day} {n.strftime('%B').upper()} {n.year}")
        if CFG["jalali_clock"]:
            jy, jm, jd = g2j(n.year, n.month, n.day)
            p.setPen(DIM)
            p.setFont(font(10))
            dt(p, QRectF(cx - 100, cy + 64, 200, 18), AL.AlignCenter, f"{fa(jd)} {FA_MONTHS[jm - 1]} {fa(jy)}")

    def p_weather(self, wd, p):
        w = wd.width()
        c = w / 2
        d, ac = wd.d, C("accent")
        ticks(p, c, c, 106, 112, 72, A(ac, 110), 6)
        ring(p, c, c, 96, 7, ac, ((d["t"] + 10) / 60) if d else 0, 40, 90, 300)
        name, icon = code_info(d["c"]) if d else ("LOADING", "☁")
        p.setPen(WHITE)
        p.setFont(QFont("Segoe UI Emoji", 18))
        dt(p, QRectF(c - 30, c - 78, 60, 34), AL.AlignCenter, icon)
        p.setFont(font(34, W.Light))
        dt(p, QRectF(c - 70, c - 40, 140, 56), AL.AlignCenter, f"{conv(d['t'])}°" if d else "--")
        p.setPen(DIM)
        p.setFont(font(8.5, W.DemiBold, None, 1.5))
        dt(p, QRectF(c - 80, c + 18, 160, 16), AL.AlignCenter, name.upper())
        if d:
            p.setPen(C("warn"))
            dt(p, QRectF(c - 80, c + 38, 160, 16), AL.AlignCenter, f"H {conv(d['hi'])}°   L {conv(d['lo'])}°")
        p.setPen(DIM)
        dt(p, QRectF(c - 80, c + 58, 160, 16), AL.AlignCenter, CFG["city"].upper())

    def p_system(self, wd, p):
        w = wd.width()
        c, h, g = w / 2, wd.hub, wd.hub.gpu_val
        rows = [("CPU", h.cpu[-1], C("cpu"), 116), ("RAM", h.ram[-1], C("ram"), 96), ("GPU", g[0] if g else 0, C("gpu"), 76)]
        for nm, v, col, r in rows:
            ring(p, c, c, r, 10, col, v / 100, 38, 90, 270)
            p.setPen(col)
            p.setFont(font(8, W.Bold, None, 1))
            dt(p, QRectF(c - 120, c - r - 7, 112, 14), AL.AlignRight | AL.AlignVCenter,
               f"{nm} {v:.0f}" if (nm != "GPU" or g) else "GPU N/A")
        p.setPen(DIM)
        p.setFont(font(8, W.DemiBold, None, 1.5))
        dt(p, QRectF(c - 60, c - 24, 120, 14), AL.AlignCenter, "SYSTEM")
        p.setPen(WHITE)
        p.setFont(font(9))
        dt(p, QRectF(c - 60, c - 6, 120, 14), AL.AlignCenter, f"↓ {fmt_speed(h.down[-1])}")
        dt(p, QRectF(c - 60, c + 10, 120, 14), AL.AlignCenter, f"↑ {fmt_speed(h.up[-1])}")

    def p_rings(self, wd, p):
        self.frame(wd, p)
        h, g = wd.hub, wd.hub.gpu_val
        for i, (nm, v, col) in enumerate((("cpu", h.cpu[-1], C("cpu")), ("ram", h.ram[-1], C("ram")),
                                          ("gpu", g[0] if g else 0, C("gpu")), ("disk", h.disk_main, C("disk")))):
            cx = 46 + i * 92
            seg_ring(p, cx, 52, 32, 6, col, v / 100, 24)
            p.setPen(WHITE)
            p.setFont(font(11, W.Bold))
            dt(p, QRectF(cx - 30, 40, 60, 24), AL.AlignCenter, f"{v:.0f}")
            p.setPen(DIM)
            p.setFont(font(7.5, W.DemiBold, None, 1.5))
            dt(p, QRectF(cx - 40, 94, 80, 16), AL.AlignCenter, TH["names"][nm])

    def p_forecast(self, wd, p):
        self.frame(wd, p, "5-DAY OUTLOOK")
        d, w, h = wd.d, wd.width(), wd.height()
        days = d["days"][:5] if d else []
        if not days:
            return
        his = [conv(x["hi"]) for x in days]
        lo, hi = min(his) - 2, max(his) + 2
        cw = (w - 40) / 5
        pts = []
        for i, x in enumerate(days):
            cx = 20 + i * cw + cw / 2
            y = 100 - (his[i] - lo) / max(1, hi - lo) * 44
            pts.append(QPointF(cx, y))
            p.setPen(DIM)
            p.setFont(font(8, W.DemiBold, None, 1.5))
            dt(p, QRectF(cx - 30, 24, 60, 14), AL.AlignCenter, datetime.date.fromisoformat(x["d"]).strftime("%a").upper())
            p.setPen(WHITE)
            p.setFont(QFont("Segoe UI Emoji", 11))
            dt(p, QRectF(cx - 20, 38, 40, 22), AL.AlignCenter, code_info(x["c"])[1])
        p.setPen(QPen(A(C("accent"), 200), 1.5))
        for a, b in zip(pts, pts[1:]):
            p.drawLine(a, b)
        for i, pt in enumerate(pts):
            p.setBrush(C("warn"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(pt, 3.5, 3.5)
            p.setPen(WHITE)
            p.setFont(font(8.5, W.Bold))
            dt(p, QRectF(pt.x() - 20, pt.y() + 5, 40, 14), AL.AlignCenter, f"{his[i]}°")

    def p_calendar(self, wd, p):
        ttl = wd.month_matrix(datetime.datetime.now())[0]
        self.frame(wd, p, ttl.upper() if not wd.jalali else ttl)

        def today(pp, cell):
            pp.setPen(QPen(C("warn"), 1.6))
            pp.setBrush(Qt.BrushStyle.NoBrush)
            pp.drawEllipse(cell.center(), 11, 11)
            return C("warn")
        draw_cal(p, wd, 12, 26, wd.width() - 24, 25, font(8, W.DemiBold, None, 1), font(9.5), today,
                 DIM, WHITE, C("hol"))

    def p_disks(self, wd, p):
        self.frame(wd, p, "STORAGE")
        w = wd.width()
        for i, (nm, t, u, pc) in enumerate(wd.hub.disks[:4]):
            y = 30 + i * 28
            p.setPen(WHITE)
            p.setFont(font(9, W.Bold))
            dt(p, QRectF(16, y, 40, 14), AL.AlignLeft | AL.AlignVCenter, nm)
            p.setPen(DIM)
            p.setFont(font(8))
            dt(p, QRectF(w - 130, y, 114, 14), AL.AlignRight | AL.AlignVCenter, f"{(t - u) / 2**30:.0f} GB FREE")
            col = C("disk") if pc < 80 else C("warn") if pc < 92 else C("bad")
            nseg, sw = 36, (w - 32) / 36
            for k in range(nseg):
                p.fillRect(QRectF(16 + k * sw, y + 17, sw - 2, 6), col if k < pc / 100 * nseg else A(col, 40))

    def p_procs(self, wd, p):
        self.frame(wd, p, "TOP PROCESSES")
        for i, (nm, c, m) in enumerate(wd.hub.procs):
            y = 28 + i * 21
            p.setPen(WHITE)
            p.setFont(font(9))
            dt(p, QRectF(16, y, 140, 18), AL.AlignLeft | AL.AlignVCenter, nm[:18])
            p.setPen(C("warn") if c > 40 else DIM)
            dt(p, QRectF(150, y, 50, 18), AL.AlignRight | AL.AlignVCenter, f"{c:.0f}%")
            p.setPen(DIM)
            dt(p, QRectF(200, y, 56, 18), AL.AlignRight | AL.AlignVCenter, f"{m:.0f}M")

    def p_net(self, wd, p):
        w = wd.width()
        c, h, ms = w / 2, wd.hub, wd.hub.ping_ms
        ac = C("accent")
        for r in (104, 70, 36):
            p.setPen(QPen(A(ac, 70), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(c, c), r, r)
        p.drawLine(QPointF(c - 104, c), QPointF(c + 104, c))
        p.drawLine(QPointF(c, c - 104), QPointF(c, c + 104))
        ang = (time.time() * 90) % 360
        for k in range(14):
            th = math.radians(ang - k * 3)
            p.setPen(QPen(A(ac, int(190 * (1 - k / 14))), 2))
            p.drawLine(QPointF(c, c), QPointF(c + 104 * math.sin(th), c - 104 * math.cos(th)))
        if ms:
            th = math.radians(40)
            rr = min(1, ms / 200) * 100
            bx, by = c + rr * math.sin(th), c - rr * math.cos(th)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(A(C("warn"), 70))
            p.drawEllipse(QPointF(bx, by), 9, 9)
            p.setBrush(C("warn"))
            p.drawEllipse(QPointF(bx, by), 3.5, 3.5)
        p.setPen(WHITE)
        p.setFont(font(9, W.Bold))
        dt(p, QRectF(c - 70, w - 36, 140, 14), AL.AlignCenter, f"PING {ms:.0f} MS" if ms else "NO ECHO")
        p.setPen(DIM)
        p.setFont(font(8))
        dt(p, QRectF(4, 4, 90, 14), AL.AlignLeft, f"↓ {fmt_speed(h.down[-1])}")
        dt(p, QRectF(4, 18, 90, 14), AL.AlignLeft, f"↑ {fmt_speed(h.up[-1])}")

    def p_info(self, wd, p):
        self.frame(wd, p, "SYSTEM INFO")
        for i, (k, v) in enumerate(wd.hub.info):
            y = 28 + i * 21
            p.setPen(DIM)
            p.setFont(font(8, W.DemiBold, None, 1.5))
            dt(p, QRectF(16, y, 90, 18), AL.AlignLeft | AL.AlignVCenter, k.upper())
            p.setPen(WHITE)
            p.setFont(font(9.5))
            dt(p, QRectF(100, y, wd.width() - 116, 18), AL.AlignRight | AL.AlignVCenter, v)

    def p_notes(self, wd, p):
        self.frame(wd, p, "DATA LOG")

    def p_analog(self, wd, p):
        w = wd.width()
        c, n, ac = w / 2, datetime.datetime.now(), C("accent")
        ticks(p, c, c, 84, 90, 60, A(ac, 120), 5)
        p.setPen(QPen(A(ac, 90), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(c, c), 76, 76)
        hands(p, c, c, n, 40, 62, 70, WHITE, C("warn"), 3, 2)


# ----------------------------------------------------------------- 4) BENTO TILES
BENTO_TA = {"invisible": 0, "glass": 160, "frosted": 220, "dark": 255}


class Bento:
    clock_row = True
    sizes = {"clock": (364, 175), "weather": (175, 175), "system": (364, 175), "rings": (175, 175),
             "forecast": (364, 175), "calendar_fa": (260, 232), "calendar": (260, 232),
             "disks": (175, 175), "procs": (175, 175), "net": (175, 175), "info": (175, 175),
             "notes": (175, 175), "analog": (175, 175)}

    def tile(self, wd, p, rgb, cap=None, dark=False):
        w, h = wd.width(), wd.height()
        ta = BENTO_TA.get(CFG["style"], 160)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 26, 26)
        p.fillPath(path, QColor(rgb[0], rgb[1], rgb[2], max(ta, 1)))
        if ta:
            g = QLinearGradient(0, 0, 0, h)
            g.setColorAt(0, QColor(255, 255, 255, 38))
            g.setColorAt(0.6, QColor(255, 255, 255, 0))
            p.fillPath(path, g)
        ink = QColor(24, 24, 28) if dark else QColor(255, 255, 255)
        if cap:
            p.setPen(A(ink, 160))
            p.setFont(font(8, W.Bold, None, 1.5))
            dt(p, QRectF(18, 12, w - 36, 14), AL.AlignLeft | AL.AlignVCenter, cap.upper())
        return ink

    def capsule(self, p, x, y, w, h, frac, col, track):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(QRectF(x, y, w, h), h / 2, h / 2)
        p.setBrush(col)
        p.drawRoundedRect(QRectF(x, y, max(h, w * min(1, max(0, frac))), h), h / 2, h / 2)

    def p_clock(self, wd, p):
        ink = self.tile(wd, p, (30, 30, 36))
        n = datetime.datetime.now()
        p.setPen(ink)
        p.setFont(font(62, W.Bold))
        s = n.strftime("%I:%M").lstrip("0")
        tw = p.fontMetrics().horizontalAdvance(s)
        dt(p, QRectF(20, 14, 300, 80), AL.AlignLeft | AL.AlignVCenter, s)
        p.setPen(QColor(255, 105, 60))
        p.setFont(font(16, W.Bold))
        dt(p, QRectF(26 + tw, 52, 60, 30), AL.AlignLeft | AL.AlignVCenter, n.strftime("%p"))
        p.setPen(ink)
        p.setFont(font(18, W.DemiBold))
        dt(p, QRectF(22, 100, 320, 26), AL.AlignLeft | AL.AlignVCenter, n.strftime("%A"))
        p.setPen(A(ink, 190))
        p.setFont(font(12))
        dt(p, QRectF(22, 126, 320, 20), AL.AlignLeft | AL.AlignVCenter, f"{n.day} {n.strftime('%B %Y')}")
        if CFG["jalali_clock"]:
            jy, jm, jd = g2j(n.year, n.month, n.day)
            dt(p, QRectF(22, 146, 320, 20), AL.AlignLeft | AL.AlignVCenter, f"{fa(jd)} {FA_MONTHS[jm - 1]} {fa(jy)}")

    def p_weather(self, wd, p):
        ink = self.tile(wd, p, (255, 138, 40), CFG["city"])
        d = wd.d
        name, icon = code_info(d["c"]) if d else ("Loading", "☁")
        p.setPen(ink)
        p.setFont(QFont("Segoe UI Emoji", 24))
        weather_icon(p, 16, 26, 40, d["c"] if d else 3)
        p.setFont(font(46, W.Bold))
        dt(p, QRectF(16, 64, 150, 54), AL.AlignLeft | AL.AlignVCenter, f"{conv(d['t'])}°" if d else "--")
        p.setFont(font(12, W.DemiBold))
        dt(p, QRectF(18, 120, 150, 20), AL.AlignLeft | AL.AlignVCenter, name)
        if d:
            p.setPen(A(ink, 200))
            p.setFont(font(11))
            dt(p, QRectF(18, 142, 150, 20), AL.AlignLeft | AL.AlignVCenter, f"H:{conv(d['hi'])}°  L:{conv(d['lo'])}°")

    def p_system(self, wd, p):
        ink = self.tile(wd, p, (84, 82, 214), "System")
        h, g = wd.hub, wd.hub.gpu_val
        cols = [("CPU", h.cpu[-1], f"{h.cpu[-1]:.0f}%"), ("GPU", g[0] if g else 0, f"{g[0]:.0f}%" if g else "N/A"),
                ("RAM", h.ram[-1], f"{h.ram[-1]:.0f}%")]
        for i, (nm, v, txt) in enumerate(cols):
            x = 22 + i * 112
            p.setPen(A(ink, 190))
            p.setFont(font(9, W.Bold, None, 1))
            dt(p, QRectF(x, 38, 100, 16), AL.AlignLeft | AL.AlignVCenter, nm)
            p.setPen(ink)
            p.setFont(font(30, W.Bold))
            dt(p, QRectF(x, 54, 104, 44), AL.AlignLeft | AL.AlignVCenter, txt)
            self.capsule(p, x, 106, 94, 10, v / 100, QColor(255, 255, 255), QColor(255, 255, 255, 60))
        p.setPen(A(ink, 210))
        p.setFont(font(11))
        dt(p, QRectF(22, 132, 320, 20), AL.AlignLeft | AL.AlignVCenter,
           f"↓ {fmt_speed(h.down[-1])}     ↑ {fmt_speed(h.up[-1])}" + (f"     {g[1]:.0f}°C GPU" if g and g[1] is not None else ""))

    def p_rings(self, wd, p):
        ink = self.tile(wd, p, (30, 30, 36))
        h, g = wd.hub, wd.hub.gpu_val
        items = [("cpu", h.cpu[-1], C("cpu")), ("ram", h.ram[-1], C("ram")),
                 ("gpu", g[0] if g else 0, C("gpu")), ("disk", h.disk_main, C("disk"))]
        for i, (nm, v, col) in enumerate(items):
            cx, cy = 48 + (i % 2) * 80, 48 + (i // 2) * 80
            ring(p, cx, cy, 28, 7, col, v / 100, 45)
            p.setPen(ink)
            p.setFont(font(10, W.Bold))
            dt(p, QRectF(cx - 24, cy - 12, 48, 16), AL.AlignCenter, f"{v:.0f}")
            p.setPen(A(ink, 150))
            p.setFont(font(6.5, W.DemiBold, None, 1))
            dt(p, QRectF(cx - 26, cy + 3, 52, 12), AL.AlignCenter, TH["names"][nm])

    def p_forecast(self, wd, p):
        ink = self.tile(wd, p, (0, 140, 160), CFG["city"] + " · 5 days")
        for i, x in enumerate(wd.d["days"][:5] if wd.d else []):
            cx = 22 + i * 64 + 32 - 11
            p.setPen(A(ink, 200))
            p.setFont(font(10, W.Bold))
            dt(p, QRectF(cx - 30, 38, 60, 18), AL.AlignCenter, datetime.date.fromisoformat(x["d"]).strftime("%a"))
            p.setPen(ink)
            p.setFont(QFont("Segoe UI Emoji", 20))
            weather_icon(p, cx - 18, 58, 36, x["c"])
            p.setFont(font(16, W.Bold))
            dt(p, QRectF(cx - 30, 106, 60, 24), AL.AlignCenter, f"{conv(x['hi'])}°")
            p.setPen(A(ink, 170))
            p.setFont(font(12))
            dt(p, QRectF(cx - 30, 132, 60, 20), AL.AlignCenter, f"{conv(x['lo'])}°")

    def p_calendar(self, wd, p):
        ink = self.tile(wd, p, (246, 246, 249), None, True)
        ttl = wd.month_matrix(datetime.datetime.now())[0]
        p.setPen(ink)
        p.setFont(font(14, W.Bold))
        dt(p, QRectF(18, 10, wd.width() - 36, 28), AL.AlignLeft | AL.AlignVCenter, ttl)

        def today(pp, cell):
            pp.setPen(Qt.PenStyle.NoPen)
            pp.setBrush(QColor(255, 59, 48))
            pp.drawEllipse(cell.center(), 12, 12)
            return QColor(255, 255, 255)
        draw_cal(p, wd, 14, 42, wd.width() - 28, 28, font(8.5, W.Bold), font(10), today,
                 QColor(24, 24, 28, 140), ink, QColor(255, 59, 48))

    def p_disks(self, wd, p):
        ink = self.tile(wd, p, (40, 164, 92), "Storage")
        for i, (nm, t, u, pc) in enumerate(wd.hub.disks[:4]):
            y = 32 + i * 35
            p.setPen(ink)
            p.setFont(font(11, W.Bold))
            dt(p, QRectF(18, y, 50, 18), AL.AlignLeft | AL.AlignVCenter, nm.rstrip("\\/") or "/")
            p.setFont(font(9))
            p.setPen(A(ink, 210))
            dt(p, QRectF(60, y, 98, 18), AL.AlignRight | AL.AlignVCenter, f"{(t - u) / 2**30:.0f} GB free")
            self.capsule(p, 18, y + 21, 139, 6, pc / 100, QColor(255, 255, 255), QColor(255, 255, 255, 60))

    def p_procs(self, wd, p):
        ink = self.tile(wd, p, (226, 72, 62), "Top apps")
        for i, (nm, c, m) in enumerate(wd.hub.procs):
            y = 34 + i * 34
            p.setPen(ink)
            p.setFont(font(11, W.DemiBold))
            dt(p, QRectF(18, y, 100, 20), AL.AlignLeft | AL.AlignVCenter, nm[:11])
            dt(p, QRectF(110, y, 48, 20), AL.AlignRight | AL.AlignVCenter, f"{c:.0f}%")
            p.setPen(A(ink, 170))
            p.setFont(font(8.5))
            dt(p, QRectF(18, y + 17, 140, 14), AL.AlignLeft | AL.AlignVCenter, f"{m:.0f} MB")

    def p_net(self, wd, p):
        ink = self.tile(wd, p, (30, 122, 232), "Network")
        ms, h = wd.hub.ping_ms, wd.hub
        p.setPen(ink)
        p.setFont(font(48, W.Bold))
        s = f"{ms:.0f}" if ms else "--"
        dt(p, QRectF(16, 34, 150, 62), AL.AlignLeft | AL.AlignVCenter, s)
        tw = p.fontMetrics().horizontalAdvance(s)
        p.setFont(font(14, W.DemiBold))
        dt(p, QRectF(22 + tw, 62, 50, 24), AL.AlignLeft | AL.AlignVCenter, "ms")
        p.setFont(font(11))
        p.setPen(A(ink, 220))
        dt(p, QRectF(18, 108, 150, 20), AL.AlignLeft | AL.AlignVCenter, f"↓ {fmt_speed(h.down[-1])}")
        dt(p, QRectF(18, 130, 150, 20), AL.AlignLeft | AL.AlignVCenter, f"↑ {fmt_speed(h.up[-1])}")

    def p_info(self, wd, p):
        ink = self.tile(wd, p, (92, 92, 102), "This PC")
        for i, (k, v) in enumerate(wd.hub.info):
            y = 34 + i * 34
            p.setPen(A(ink, 170))
            p.setFont(font(8.5, W.DemiBold, None, 1))
            dt(p, QRectF(18, y, 140, 12), AL.AlignLeft | AL.AlignVCenter, k.upper())
            p.setPen(ink)
            p.setFont(font(13, W.Bold))
            dt(p, QRectF(18, y + 11, 150, 20), AL.AlignLeft | AL.AlignVCenter, v)

    def p_notes(self, wd, p):
        self.tile(wd, p, (73, 60, 39), "Notes")

    def p_analog(self, wd, p):
        self.tile(wd, p, (250, 250, 252), None, True)
        c, n = wd.width() / 2, datetime.datetime.now()
        ticks(p, c, c, 70, 76, 60, QColor(24, 24, 28, 110), 5)
        hands(p, c, c, n, 38, 58, 62, QColor(24, 24, 28), QColor(255, 59, 48), 5, 3.5)


# ----------------------------------------------------------------- 5) SYNTHWAVE
def grad_text(p, cx, top, text, f, c0, c1, glow=None, outline=None):
    fm = QFontMetricsF(f)
    path = QPainterPath()
    path.addText(cx - fm.horizontalAdvance(text) / 2, top + fm.ascent(), f, text)
    g = QLinearGradient(0, top, 0, top + fm.height())
    g.setColorAt(0, c0)
    g.setColorAt(1, c1)
    if glow:
        p.strokePath(path, QPen(A(glow, 35), 11))
        p.strokePath(path, QPen(A(glow, 90), 5))
    if outline:
        p.strokePath(path, QPen(outline, 3))
    p.fillPath(path, g)


class Synthwave:
    clock_row = True
    sizes = {"clock": (720, 300), "weather": (270, 124), "system": (310, 124), "rings": (350, 124)}
    PINK, CYAN, PURPLE, YEL = QColor(255, 64, 180), QColor(70, 230, 255), QColor(160, 100, 255), QColor(255, 226, 90)

    def sfont(self, size, spacing=0):
        f = QFont(font(size, W.Black, None, spacing))
        f.setItalic(True)
        return f

    def p_clock(self, wd, p):
        w, h = wd.width(), wd.height()
        cx, hz = w / 2, 212
        n = datetime.datetime.now()
        p.save()
        p.setClipRect(QRectF(0, 0, w, hz))
        g = QLinearGradient(0, 30, 0, hz + 10)
        g.setColorAt(0, QColor(255, 236, 90))
        g.setColorAt(0.55, QColor(255, 80, 150))
        g.setColorAt(1, QColor(190, 50, 230))
        sun, stripes = QPainterPath(), QPainterPath()
        sun.addEllipse(QPointF(cx, 124), 98, 98)
        for k in range(7):
            stripes.addRect(QRectF(cx - 100, 128 + k * 13, 200, 1.2 + k * 1.05))
        p.fillPath(sun.subtracted(stripes), g)
        p.restore()
        p.save()
        p.setClipRect(QRectF(0, hz, w, h - hz))
        p.setPen(QPen(A(self.PINK, 150), 1.2))
        for i in range(-16, 17):
            p.drawLine(QPointF(cx + i * 9, hz), QPointF(cx + i * 85, h))
        ph = time.time() % 1.0
        for k in range(9):
            f = ((k + ph) / 9) ** 2
            y = hz + f * (h - hz)
            p.setPen(QPen(A(self.PINK, int(50 + 170 * f)), 1.2))
            p.drawLine(QPointF(0, y), QPointF(w, y))
        p.restore()
        p.setPen(QPen(A(self.CYAN, 230), 2))
        p.drawLine(QPointF(0, hz), QPointF(w, hz))
        p.setPen(self.CYAN)
        p.setFont(font(13, W.Bold, None, 9))
        dt(p, QRectF(0, 4, w, 24), AL.AlignCenter, n.strftime("%A").upper())
        grad_text(p, cx, 22, n.strftime("%I:%M").lstrip("0"), self.sfont(78), QColor(255, 255, 255),
                  QColor(150, 90, 255), self.PINK, QColor(30, 0, 60, 150))
        p.setPen(QColor(255, 255, 255))
        p.setFont(font(13, W.Bold, None, 4))
        dt(p, QRectF(0, 232, w, 24), AL.AlignCenter, f"{n.day} {n.strftime('%b').upper()} {n.year}  ·  {n.strftime('%p')}")
        if CFG["jalali_clock"]:
            jy, jm, jd = g2j(n.year, n.month, n.day)
            p.setPen(A(self.CYAN, 230))
            p.setFont(font(11))
            dt(p, QRectF(0, 262, w, 22), AL.AlignCenter, f"{FA_DAYS_MON0[n.weekday()]} {fa(jd)} {FA_MONTHS[jm - 1]} {fa(jy)}")

    def p_weather(self, wd, p):
        w, h = wd.width(), wd.height()
        draw_card(p, w, h)
        d = wd.d
        grad_text(p, 78, 8, f"{conv(d['t'])}°" if d else "--", self.sfont(46), self.YEL, self.PINK, self.PINK)
        name, icon = code_info(d["c"]) if d else ("Loading", "☁")
        p.setPen(QColor(255, 255, 255))
        p.setFont(QFont("Segoe UI Emoji", 22))
        weather_icon(p, w - 68, 10, 45, d["c"] if d else 3)
        p.setPen(self.CYAN)
        p.setFont(font(9.5, W.Bold, None, 1.5))
        dt(p, QRectF(18, 76, w - 36, 18), AL.AlignLeft | AL.AlignVCenter, f"{CFG['city']} · {name}".upper())
        if d:
            p.setPen(self.PINK)
            dt(p, QRectF(18, 96, w - 36, 18), AL.AlignLeft | AL.AlignVCenter, f"H {conv(d['hi'])}°   L {conv(d['lo'])}°")

    def p_system(self, wd, p):
        w, h = wd.width(), wd.height()
        draw_card(p, w, h)
        hub, g = wd.hub, wd.hub.gpu_val
        for i, (nm, v) in enumerate((("CPU", hub.cpu[-1]), ("GPU", g[0] if g else 0), ("RAM", hub.ram[-1]))):
            y = 22 + i * 30
            p.setPen(self.CYAN)
            p.setFont(font(9, W.Black, None, 1))
            dt(p, QRectF(18, y - 8, 40, 16), AL.AlignLeft | AL.AlignVCenter, nm)
            x0, bw = 60, w - 60 - 62
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 30))
            p.drawRoundedRect(QRectF(x0, y - 5, bw, 10), 5, 5)
            fw = max(10, bw * v / 100)
            gr = QLinearGradient(x0, 0, x0 + bw, 0)
            gr.setColorAt(0, self.PINK)
            gr.setColorAt(1, self.CYAN)
            p.setBrush(A(self.PINK, 50))
            p.drawRoundedRect(QRectF(x0 - 2, y - 8, fw + 4, 16), 8, 8)
            p.setBrush(gr)
            p.drawRoundedRect(QRectF(x0, y - 5, fw, 10), 5, 5)
            p.setPen(QColor(255, 255, 255))
            p.setFont(font(9, W.Bold))
            dt(p, QRectF(w - 58, y - 8, 42, 16), AL.AlignRight | AL.AlignVCenter, f"{v:.0f}%" if (nm != "GPU" or g) else "N/A")
        p.setPen(A(self.CYAN, 200))
        p.setFont(font(8.5))
        dt(p, QRectF(18, 100, w - 36, 16), AL.AlignLeft | AL.AlignVCenter,
           f"↓ {fmt_speed(hub.down[-1])}   ↑ {fmt_speed(hub.up[-1])}")

    def p_rings(self, wd, p):
        w, h = wd.width(), wd.height()
        draw_card(p, w, h)
        hub, g = wd.hub, wd.hub.gpu_val
        cols = (self.PINK, self.CYAN, self.PURPLE, self.YEL)
        for i, (nm, v) in enumerate((("cpu", hub.cpu[-1]), ("ram", hub.ram[-1]),
                                     ("gpu", g[0] if g else 0), ("disk", hub.disk_main))):
            cx, col = 44 + i * 87, cols[i]
            ring(p, cx, 52, 31, 14, col, 0, 0)
            ring(p, cx, 52, 31, 14, A(col, 0), 0, 0)
            rect = QRectF(cx - 31, 52 - 31, 62, 62)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(255, 255, 255, 28), 8))
            p.drawArc(rect, 0, 360 * 16)
            for wid, al in ((14, 40), (8, 255)):
                pen = QPen(A(col, al), wid)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                if v > 0.5:
                    p.drawArc(rect, 90 * 16, int(-min(v, 100) / 100 * 360 * 16))
            p.setPen(QColor(255, 255, 255))
            p.setFont(font(11, W.Black))
            dt(p, QRectF(cx - 28, 40, 56, 24), AL.AlignCenter, f"{v:.0f}")
            p.setPen(col)
            p.setFont(font(7.5, W.Black, None, 1.5))
            dt(p, QRectF(cx - 40, 94, 80, 16), AL.AlignCenter, TH["names"][nm])


# ----------------------------------------------------------------- register styles
def decor_line(p, path, w, h, f, radius, kind):
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(A(C("accent"), int(170 * f)), 1))
    p.drawPath(path)


def decor_none(p, path, w, h, f, radius, kind):
    pass


def decor_synth(p, path, w, h, f, radius, kind):
    p.setBrush(Qt.BrushStyle.NoBrush)
    for wid, al in ((7, 50), (1.8, 255)):
        g = QLinearGradient(0, 0, w, h)
        g.setColorAt(0, QColor(255, 64, 180, int(al * f)))
        g.setColorAt(1, QColor(70, 230, 255, int(al * f)))
        p.setPen(QPen(QBrush(g), wid))
        p.drawPath(path)


DECORS.update({"line": decor_line, "none": decor_none, "synth": decor_synth})


def mk(**kw):
    return dict(THEMES["knight"], **kw)


THEMES["terminal"] = mk(
    label="Terminal / Matrix (layout)", renderer=Terminal(), card="round", decor="line", radius=2,
    tint=(2, 14, 7), text=(150, 255, 175), dim=(75, 175, 108, 235), accent=(110, 255, 140), start=(110, 255, 140),
    cpu=(110, 255, 140), ram=(255, 200, 70), gpu=(120, 230, 255), disk=(170, 255, 120), down=(110, 255, 140),
    up=(255, 200, 70), ok=(110, 255, 140), warn=(255, 200, 70), bad=(255, 80, 80), today=(110, 255, 140, 230),
    hol=(255, 200, 70), display_fonts=["Cascadia Mono", "Consolas", "Courier New"],
    body_fonts=["Cascadia Mono", "Consolas", "Courier New"],
    names=dict(cpu="CPU", ram="RAM", gpu="GPU", disk="DISK", procs="PS", notes="NOTES"))
THEMES["dotmatrix"] = mk(
    label="Dot Matrix / Nothing-style (layout)", renderer=DotMatrix(), card="round", decor="none", radius=28,
    tint=(0, 0, 0), text=(245, 245, 245), dim=(200, 200, 200, 190), accent=(255, 56, 44), start=(255, 56, 44),
    cpu=(245, 245, 245), ram=(245, 245, 245), gpu=(245, 245, 245), disk=(245, 245, 245), down=(245, 245, 245),
    up=(245, 245, 245), today=(255, 56, 44, 240), hol=(255, 90, 80),
    body_fonts=["Bahnschrift", "Segoe UI"], display_fonts=["Bahnschrift", "Segoe UI"])
THEMES["hud"] = mk(
    label="Sci-Fi HUD (layout)", renderer=Hud(), card="round", decor="line", radius=3, tint=(3, 14, 24),
    text=(205, 242, 255), dim=(110, 190, 215, 230), accent=(90, 225, 255), start=(90, 225, 255),
    cpu=(90, 225, 255), ram=(255, 176, 60), gpu=(190, 130, 255), disk=(90, 255, 190), down=(90, 225, 255),
    up=(255, 176, 60), ok=(90, 255, 190), warn=(255, 176, 60), today=(255, 176, 60, 230), hol=(255, 120, 90),
    body_fonts=["Bahnschrift", "Segoe UI"], display_fonts=["Orbitron", "Bahnschrift"])
THEMES["bento"] = mk(
    label="Bento Tiles / flat color (layout)", renderer=Bento(), card="round", decor="none", radius=24,
    tint=(30, 30, 36), text=(255, 255, 255), dim=(235, 235, 240, 200), accent=(255, 105, 60), start=(10, 132, 255),
    cpu=(255, 255, 255), ram=(255, 214, 10), gpu=(190, 150, 255), disk=(80, 220, 130), down=(255, 255, 255),
    up=(255, 255, 255), today=(255, 59, 48, 240), hol=(255, 59, 48), notes_text=(30, 26, 0),
    body_fonts=["Segoe UI Variable Display", "Segoe UI"], display_fonts=["Segoe UI Variable Display", "Segoe UI"])
THEMES["synthwave"] = mk(
    label="Synthwave (layout)", renderer=Synthwave(), card="round", decor="synth", radius=22, gloss=18,
    tint=(24, 8, 48), text=(255, 240, 255), dim=(120, 225, 255, 235), accent=(255, 64, 180), start=(255, 64, 180),
    cpu=(255, 64, 180), ram=(70, 230, 255), gpu=(160, 100, 255), disk=(255, 226, 90), down=(70, 230, 255),
    up=(255, 64, 180), ok=(90, 255, 190), warn=(255, 226, 90), today=(255, 64, 180, 235), hol=(255, 226, 90),
    body_fonts=["Bahnschrift", "Segoe UI"], display_fonts=["Bahnschrift", "Segoe UI"])


class ThemeText:
    @staticmethod
    def text(p, rect, value, size, color, weight=W.Normal, align=AL.AlignLeft | AL.AlignVCenter):
        p.setFont(font(size, weight))
        p.setPen(QColor(color))
        value = p.fontMetrics().elidedText(value, Qt.TextElideMode.ElideRight, int(rect[2]))
        p.drawText(QRectF(*rect), align, value)

class Heritage(ThemeText):
    clock_row = True
    sizes = {"clock": (502, 184), "system": (318, 158), "weather": (258, 135)}

    def p_clock(self, wd, p):
        w = wd.width()
        theme = THEME_NAME
        now = datetime.datetime.now()
        draw_card(p, w, wd.height(), radius=18)
        accent = C("accent")
        if theme == "steampunk":
            for x, direction in ((61, -1), (w - 61, 1)):
                gear(p, x, 87, 30, 12, now.second * direction * 6, A(accent, 120))
                gear(p, x + 27 * direction, 123, 14, 9, now.second * direction * -8, A(accent, 112))
        elif theme == "dota2":
            diamond(p, 29, 84, 7, accent)
            diamond(p, w - 29, 84, 7, accent)

        day = now.strftime("%A").upper()
        label = QRectF(78, 17, w - 156, 64)
        p.setFont(font(TH["day_size"] * .67, TH["day_weight"], DISPLAY_FONT, TH["day_spacing"] / 2))
        if TH["day_effect"] == "glitch":
            for x, color in ((-2, QColor(255, 40, 160, 175)), (2, QColor(0, 240, 255, 175))):
                p.setPen(color)
                p.drawText(label.translated(x, 0), AL.AlignCenter, day)
        elif TH["day_effect"] in {"outline", "emboss"}:
            p.setPen(QColor(9, 6, 4, 215))
            p.drawText(label.translated(1, 2), AL.AlignCenter, day)
        p.setPen(C("day"))
        dt(p, label, AL.AlignCenter, day)

        self.text(p, (20, 83, w - 40, 43), TH["time_fmt"].format(t=now.strftime("%H:%M")),
                  23, C("time"), W.DemiBold, AL.AlignCenter)
        self.text(p, (20, 126, w - 40, 20), now.strftime("%d %B %Y"), 10, DIM, W.DemiBold, AL.AlignCenter)
        if CFG["jalali_clock"]:
            y, m, d = g2j(now.year, now.month, now.day)
            self.text(p, (20, 147, w - 40, 21), f"{fa(d)} {FA_MONTHS[m - 1]} {fa(y)}", 10, DIM, align=AL.AlignCenter)

    def p_weather(self, wd, p):
        w, d = wd.width(), wd.d
        draw_card(p, w, wd.height())
        self.text(p, (18, 11, w - 36, 20), CFG["city"], 9, C("accent"), W.DemiBold)
        if not d:
            self.text(p, (18, 53, w - 36, 25), "Waiting for weather", 10, DIM)
            return
        self.text(p, (18, 35, w - 88, 45), f"{conv(d['t'])}°", 29, WHITE, W.DemiBold)
        weather_icon(p, w - 65, 34, 43, d["c"])
        p.setPen(QPen(A(C("accent"), 70), 1))
        p.drawLine(QPointF(18, 89), QPointF(w - 18, 89))
        self.text(p, (18, 97, w - 105, 20), code_info(d["c"])[0], 9, DIM)
        self.text(p, (w - 89, 97, 70, 20), f"{conv(d['lo'])}° / {conv(d['hi'])}°", 9, DIM,
                  align=AL.AlignRight | AL.AlignVCenter)

    def p_system(self, wd, p):
        w, h, hub = wd.width(), wd.height(), wd.hub
        draw_card(p, w, h)
        self.text(p, (17, 10, w - 34, 22), "System activity", 10, WHITE, W.DemiBold)
        for i, (key, history, value) in enumerate((
            ("cpu", hub.cpu, hub.cpu[-1]), ("ram", hub.ram, hub.ram[-1]),
            ("gpu", hub.gpu, hub.gpu_val[0] if hub.gpu_val else None),
        )):
            label, color = TH["names"][key], C(key)
            reading = f"{value:.0f}%" if value is not None else "—"
            if THEME_NAME == "steampunk":
                x = 62 + i * 97
                ticks(p, x, 77, 26, 30, 30, A(color, 110), 5)
                ring(p, x, 77, 25, 3.4, color, (value or 0) / 100)
                self.text(p, (x - 28, 61, 56, 30), reading, 10, WHITE, W.DemiBold, AL.AlignCenter)
                self.text(p, (x - 33, 115, 66, 20), label, 9, DIM, W.DemiBold, AL.AlignCenter)
                continue
            y = 36 + i * 33
            self.text(p, (17, y, 60, 23), label, 9, color, W.DemiBold)
            if THEME_NAME == "dota2":
                design.panel(p, QRectF(79, y + 6, 170, 13), A(color, 32), 3)
                if value:
                    design.panel(p, QRectF(79, y + 6, max(3, 170 * value / 100), 13), A(color, 190), 3)
            else:
                spark(p, QRectF(80, y + 4, 166, 16), history, color)
            self.text(p, (255, y, 46, 23), reading, 10, WHITE, W.DemiBold, AL.AlignRight | AL.AlignVCenter)


for name in ("knight", "cyberpunk", "steampunk", "dota2"):
    THEMES[name]["renderer"] = Heritage()


def setup(config, *, format_speed, weather_code, convert_temperature, solar_date, persian_digits,
          persian_months, persian_days, boot_time, paint_weather_icon, paint_spark):
    global CFG, fmt_speed, code_info, conv, g2j, fa, FA_MONTHS, FA_DAYS_MON0, BOOT_TIME, weather_icon, spark
    CFG = config
    fmt_speed, code_info, conv = format_speed, weather_code, convert_temperature
    g2j, fa = solar_date, persian_digits
    FA_MONTHS, FA_DAYS_MON0, BOOT_TIME = persian_months, persian_days, boot_time
    weather_icon = paint_weather_icon
    spark = paint_spark


def active_renderer():
    return THEMES.get(THEME_NAME, {}).get("renderer")


def paint_surface(p, widget):
    renderer = active_renderer()
    w, h = widget.width(), widget.height()
    if THEME_NAME == "terminal":
        renderer.frame(widget, p, widget.label)
    elif THEME_NAME == "dotmatrix":
        renderer.card(widget, p)
    elif THEME_NAME == "frost":
        design.card(p, QRectF(0, 0, w, h), design.THEMES["frost"], CFG["style"])
    elif THEME_NAME == "hud":
        draw_card(p, w, h, radius=6)
    elif THEME_NAME == "bento":
        renderer.tile(widget, p, TH["tint"])
    else:
        draw_card(p, w, h)
class MidnightStudio(ThemeText):
    sizes = {"clock": (350, 162), "weather": (254, 139), "system": (314, 155)}

    def p_clock(self, wd, p):
        w, h = wd.width(), wd.height()
        draw_card(p, w, h, radius=19)
        now = datetime.datetime.now()
        t = now.strftime("%H:%M")
        self.text(p, (18, 11, w - 36, 22), now.strftime("%A, %d %B"), 10, "#a8c8ff", W.DemiBold)
        self.text(p, (16, 36, w - 126, 70), t, 43, "#f2f4ff", W.DemiBold)
        if CFG["jalali_clock"]:
            y, m, d = g2j(now.year, now.month, now.day)
            self.text(p, (19, 119, w - 38, 20), f"{fa(d)} {FA_MONTHS[m - 1]} {fa(y)}", 10, "#b6c9e8")
        p.setPen(QPen(A(QColor("#9cc7ff"), 115), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(w - 56, 78), 27, 27)
        hands(p, w - 56, 78, now, 12, 19, 21, QColor("#e6efff"), QColor("#89b7fd"), 2.7, 1.7)

    def p_system(self, wd, p):
        w, h, hub = wd.width(), wd.height(), wd.hub
        draw_card(p, w, h)
        self.text(p, (16, 10, w - 32, 20), "System activity", 10, "#c7d9ff", W.DemiBold)
        values = (("CPU", hub.cpu[-1], C("cpu")), ("RAM", hub.ram[-1], C("ram")),
                  ("GPU", hub.gpu_val[0] if hub.gpu_val else None, C("gpu")))
        for i, (label, value, color) in enumerate(values):
            x = 62 + i * 95
            ring(p, x, 78, 29, 4, color, (value or 0) / 100)
            self.text(p, (x - 27, 63, 54, 30), f"{value:.0f}%" if value is not None else "—", 11, color, W.DemiBold, AL.AlignCenter)
            self.text(p, (x - 40, 119, 80, 17), label, 8, "#b8c9e9", W.DemiBold, AL.AlignCenter)

    def p_weather(self, wd, p):
        w, h = wd.width(), wd.height()
        draw_card(p, w, h)
        self.text(p, (16, 10, w - 32, 20), CFG["city"], 10, "#bfd2ef", W.DemiBold)
        d = wd.d
        if not d:
            self.text(p, (16, 54, w - 32, 28), "Waiting for weather", 10, "#bfcee5")
            return
        weather_icon(p, w - 73, 42, 49, d["c"])
        self.text(p, (16, 37, w - 90, 56), f"{conv(d['t'])}°", 33, "#f4f7ff", W.DemiBold)
        self.text(p, (16, 100, w - 32, 24), f"{code_info(d['c'])[0]}   {conv(d['lo'])}° / {conv(d['hi'])}°", 9, "#bfd2ef")


class IrisStudio:
    sizes = {"clock": (244, 186), "weather": (229, 172), "system": (328, 161)}

    def p_clock(self, wd, p):
        w, h = wd.width(), wd.height()
        draw_card(p, w, h, radius=25)
        now = datetime.datetime.now()
        x = 17
        for width, value in ((100, now.strftime("%H")), (100, now.strftime("%M"))):
            design.panel(p, QRectF(x, 41, width, 80), QColor(239, 177, 255, 42), 14)
            ThemeText.text(p, (x, 46, width, 68), value, 36, "#fff5ff", W.DemiBold, AL.AlignCenter)
            x += width + 10
        ThemeText.text(p, (16, 12, w - 32, 20), now.strftime("%A"), 10, "#ebbfff", W.DemiBold, AL.AlignCenter)
        ThemeText.text(p, (16, 133, w - 32, 20), now.strftime("%d %B %Y"), 10, "#f1d6f6", align=AL.AlignCenter)
        if CFG["jalali_clock"]:
            y, m, d = g2j(now.year, now.month, now.day)
            ThemeText.text(p, (16, 155, w - 32, 19), f"{fa(d)} {FA_MONTHS[m - 1]} {fa(y)}", 9, "#e5b8f1", align=AL.AlignCenter)

    def p_weather(self, wd, p):
        w, h = wd.width(), wd.height()
        draw_card(p, w, h, radius=25)
        d = wd.d
        ThemeText.text(p, (14, 10, w - 28, 21), CFG["city"], 10, "#f0c4ff", W.DemiBold, AL.AlignCenter)
        if not d:
            ThemeText.text(p, (14, 70, w - 28, 22), "Waiting for weather", 10, "#efd1f7", align=AL.AlignCenter)
            return
        weather_icon(p, (w - 56) / 2, 37, 56, d["c"])
        ThemeText.text(p, (15, 94, w - 30, 43), f"{conv(d['t'])}°", 27, "#fff5ff", W.DemiBold, AL.AlignCenter)
        ThemeText.text(p, (15, 141, w - 30, 20), code_info(d["c"])[0], 9, "#efd1f7", align=AL.AlignCenter)

    def p_system(self, wd, p):
        w, h, hub = wd.width(), wd.height(), wd.hub
        draw_card(p, w, h, radius=25)
        ThemeText.text(p, (16, 10, w - 32, 23), "System activity", 10, "#f0c4ff", W.DemiBold)
        gpu = hub.gpu_val[0] if hub.gpu_val else None
        for i, (name, value) in enumerate((("CPU", hub.cpu[-1]), ("RAM", hub.ram[-1]), ("GPU", gpu))):
            x = 15 + 101 * i
            design.panel(p, QRectF(x, 42, 93, 100), QColor(239, 177, 255, 38), 18)
            ThemeText.text(p, (x + 8, 61, 77, 37), f"{value:.0f}%" if value is not None else "—",
                          18, "#fff5ff", W.DemiBold, AL.AlignCenter)
            ThemeText.text(p, (x + 8, 107, 77, 20), name, 9, "#e8bdff", W.DemiBold, AL.AlignCenter)


class FrostStudio:
    sizes = {"clock": (289, 149), "system": (337, 168)}

    def p_clock(self, wd, p):
        w, h = wd.width(), wd.height()
        design.card(p, QRectF(0, 0, w, h), design.THEMES["frost"], CFG["style"])
        now = datetime.datetime.now()
        for x, width, fill in ((15, 156, QColor("#d8e9fa")), (181, 93, QColor("#a9cce9"))):
            if CFG["style"] != "invisible":
                design.panel(p, QRectF(x, 16, width, 117), fill, 16)
        ThemeText.text(p, (25, 37, 139, 60), now.strftime("%H:%M"), 31, "#133754", W.DemiBold, AL.AlignCenter)
        ThemeText.text(p, (22, 105, 140, 20), now.strftime("%A"), 9, "#234867", align=AL.AlignCenter)
        ThemeText.text(p, (185, 31, 84, 58), str(now.day),
                      33, "#15334d", W.DemiBold, AL.AlignCenter)
        ThemeText.text(p, (184, 95, 87, 27), now.strftime("%B"), 9, "#15334d", align=AL.AlignCenter)
        if CFG["jalali_clock"]:
            y, m, d = g2j(now.year, now.month, now.day)
            ThemeText.text(p, (22, 119, 140, 14), f"{fa(d)} {FA_MONTHS[m - 1]} {fa(y)}", 7, "#234867", align=AL.AlignCenter)

    def p_system(self, wd, p):
        w, h, hub = wd.width(), wd.height(), wd.hub
        theme = design.THEMES["frost"]
        design.card(p, QRectF(0, 0, w, h), theme, CFG["style"])
        ThemeText.text(p, (16, 11, w - 32, 21), "System activity", 10, theme.ink, W.DemiBold)
        for i, (name, value, color) in enumerate((
            ("CPU", hub.cpu[-1], QColor("#236095")),
            ("Memory", hub.ram[-1], QColor("#127463")),
            ("GPU", hub.gpu_val[0] if hub.gpu_val else None, QColor("#385d88")),
        )):
            x = 17 + 103 * i
            height = max(3, min(63, round((value or 0) * .63)))
            if CFG["style"] != "invisible":
                design.panel(p, QRectF(x, 42, 91, 71), QColor("#d9e8f6"), 8)
            design.panel(p, QRectF(x + 6, 110 - height, 79, height), A(color, 85), 4)
            ThemeText.text(p, (x + 4, 53, 83, 41), f"{value:.0f}%" if value is not None else "—",
                          15, theme.ink, W.DemiBold, AL.AlignCenter)
            ThemeText.text(p, (x + 2, 123, 87, 23), name, 9, theme.muted, align=AL.AlignCenter)


THEMES["midnight"] = mk(renderer=MidnightStudio(), tint=(13, 25, 43), accent=(148, 193, 250), radius=20, decor="line")
THEMES["iris"] = mk(renderer=IrisStudio(), tint=(54, 30, 67), accent=(217, 165, 242), radius=25, decor="line")
THEMES["frost"] = mk(renderer=FrostStudio(), tint=(23, 51, 79), accent=(128, 201, 247), radius=23, decor="round")
