# -*- coding: utf-8 -*-
"""
KnightDesk - desktop widgets (clock, weather, system monitor) + floating dock
for Windows 10/11.  Python + PySide6.
"""
import sys, os, json, math, copy, shutil, socket, subprocess, threading, time, datetime, calendar, urllib.request
from collections import deque
from concurrent.futures import CancelledError, ThreadPoolExecutor
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pathlib import Path

import psutil
import design
import theme_art
from media_session import MediaSession
from windows_shell import prepare_dock_image
from PySide6.QtCore import (Qt, QTimer, QRect, QRectF, QPointF, QObject, Signal,
                            QFileInfo, QSharedMemory, QSize, QPoint, QDate, QUrl, QEvent)
from PySide6.QtGui import (QPainter, QColor, QFont, QPen, QPainterPath, QIcon,
                           QPixmap, QFontDatabase, QLinearGradient, QCursor, QImage, QImageReader, QDesktopServices)
from PySide6.QtWidgets import (QApplication, QWidget, QSystemTrayIcon, QMenu,
                               QFileDialog, QFileIconProvider, QPlainTextEdit, QFrame,
                               QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QPushButton, QScrollArea, QStackedWidget, QButtonGroup,
                               QVBoxLayout, QMessageBox, QInputDialog, QSlider, QDialog, QDialogButtonBox, QDateEdit, QListWidgetItem,
                               QAbstractItemView, QStyledItemDelegate, QStyle, QToolTip)

APP = "KnightDesk"
IS_WIN = sys.platform == "win32"
if IS_WIN:
    from windows_shell import (shell_icon, resource_icon, taskbar_pins,
                               packaged_path, hosted_app_path, packaged_icon, installed_package_paths, window_icon, window_identity)
    from taskbar import TaskbarReplacement, read_monitor_info, run_guard

NOWIN = 0x08000000 if IS_WIN else 0

# ----------------------------------------------------------------- config
CFG_DIR = Path(os.environ.get("APPDATA", str(Path.home() / ".config"))) / APP
CFG_FILE = CFG_DIR / "config.json"


def default_pins():
    cands = [
        ("File Explorer", shutil.which("explorer.exe")),
        ("Chrome", r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        ("Chrome", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        ("Edge", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    ]
    pins, seen = [], set()
    for name, path in cands:
        if path and os.path.exists(path) and name not in seen:
            pins.append({"name": name, "path": path})
            seen.add(name)
    return pins


DEFAULTS = {
    "city": "Qeshm", "lat": 26.96, "lon": 56.27, "units": "C",
    "locked": False, "show_dock": True, "replace_taskbar": False,
    "pinned": None, "positions": {}, "placements": {}, "widget_scales": {}, "style": "glass",
    "hidden": ["info", "notes", "calendar", "analog", "focus", "world"], "notes": "",
    "ping_host": "1.1.1.1", "ping_port": 443, "jalali_clock": True, "theme": "nocturne",
    "keep_windows_tray": True, "dock_order": [],
    "dock_size": 44, "dock_icon_scale": 1.0, "dock_edge": "bottom", "dock_clock": True, "dock_24h": True,
    "dock_fullscreen": True, "sample_seconds": 2, "gpu_enabled": True,
    "ping_enabled": True, "settings_seen": False,
    "sync_taskbar": True, "dock_surface": "glass", "dock_opacity": 36, "dock_monitor": "",
    "photo_files": [], "photo_mono": True, "photo_square": False, "reminders": [], "quick_links": [], "widget_layout": "classic",
    "tasks": [], "widget_scale": 1.0, "graphite_previous": None, "focus_minutes": 25, "world_zone": "Europe/Berlin",
}
CFG = dict(DEFAULTS)


def load_cfg():
    stored = {}
    try:
        stored = json.loads(CFG_FILE.read_text(encoding="utf-8"))
        CFG.update(stored)
    except (OSError, ValueError, TypeError):
        stored = {}
    if CFG["pinned"] is None:
        CFG["pinned"] = default_pins()
    if "replace_taskbar" not in stored:
        CFG["replace_taskbar"] = bool(stored.get("hide_native_taskbar"))
    CFG.pop("hide_native_taskbar", None)
    if "dock_opacity" not in stored:
        if CFG["dock_surface"] == "obsidian":
            CFG["dock_surface"] = "glass"
    if not CFG.get("nocturne_migrated"):
        if CFG["theme"] == "midnight":
            CFG["theme"] = "nocturne"
            for key in CFG["placements"].copy():
                if key.endswith("@midnight"):
                    CFG["placements"].setdefault(key[:-len("midnight")] + "nocturne", CFG["placements"][key])
            for key in CFG["positions"].copy():
                if key.endswith("@midnight"):
                    CFG["positions"].setdefault(key[:-len("midnight")] + "nocturne", CFG["positions"][key])
        CFG["nocturne_migrated"] = True
    if not CFG.get("layout_v12"):
        CFG["hidden"] = sorted(set(CFG["hidden"]) | {"focus", "world"})
        CFG["layout_v12"] = True
    if not CFG.get("bento_v16"):
        CFG["hidden"] = sorted(set(CFG["hidden"]) | set(BENTO_WIDGETS))
        CFG["bento_v16"] = True
    if not CFG.get("tasks_v17"):
        if stored and CFG["widget_layout"] != "graphite":
            CFG["hidden"] = sorted(set(CFG["hidden"]) | {"tasks"})
        CFG["tasks_v17"] = True
    if not CFG["settings_seen"]:
        if CFG["theme"] == "knight":
            CFG["theme"] = "nocturne"
        CFG["settings_seen"] = True
    save_cfg()


def save_cfg():
    try:
        CFG_DIR.mkdir(parents=True, exist_ok=True)
        pending = CFG_FILE.with_suffix(".tmp")
        pending.write_text(json.dumps(CFG, indent=2, ensure_ascii=False), encoding="utf-8")
        pending.replace(CFG_FILE)
    except Exception:
        pass


# ----------------------------------------------------------------- win32
if IS_WIN:
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    dwmapi = ctypes.windll.dwmapi
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetWindow.restype = wintypes.HWND
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
    user32.IsZoomed.argtypes = [wintypes.HWND]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.MonitorFromWindow.restype = wintypes.HMONITOR

    def foreground_fullscreen(display_name=None):
        hwnd = foreground()
        if not hwnd:
            return False
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == os.getpid():
            return False
        cls = ctypes.create_unicode_buffer(128)
        user32.GetClassNameW(hwnd, cls, len(cls))
        if cls.value in ("Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
            return False
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd) or user32.IsZoomed(hwnd):
            return False
        rect = wintypes.RECT()
        monitor = user32.MonitorFromWindow(hwnd, 2)
        info = read_monitor_info(user32, monitor)
        if info is None:
            return False
        if display_name and info.device.casefold() != display_name.casefold():
            return False
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return False
        bounds = info.monitor
        return (rect.left <= bounds.left and rect.top <= bounds.top
                and rect.right >= bounds.right and rect.bottom >= bounds.bottom)


    _window_processes = {}
    _window_identities = {}

    def list_windows():
        out, me = [], os.getpid()
        seen = set()
        seen_windows = set()

        def cb(hwnd, _):
            try:
                if not user32.IsWindowVisible(hwnd):
                    return True
                ex = user32.GetWindowLongW(hwnd, -20)
                appwin = bool(ex & 0x40000)
                if user32.GetWindow(hwnd, 4) and not appwin:   # owned window
                    return True
                if (ex & 0x80) and not appwin:                 # tool window
                    return True
                cloaked = ctypes.c_int(0)
                dwmapi.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), 4)
                if cloaked.value or user32.GetWindowTextLengthW(hwnd) == 0:
                    return True
                cls = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, cls, 256)
                if cls.value in ("Progman", "WorkerW", "Shell_TrayWnd"):
                    return True
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value == me:
                    return True
                title = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(hwnd, title, 256)
                seen.add(pid.value)
                window_key = hwnd, pid.value
                seen_windows.add(window_key)
                expires, identity, icon = _window_identities.get(window_key, (0, "", ""))
                if expires <= time.monotonic():
                    try:
                        identity, icon = window_identity(hwnd)
                    except (OSError, ValueError, AttributeError, ctypes.ArgumentError):
                        identity, icon = "", ""
                    _window_identities[window_key] = time.monotonic() + 15, identity, icon
                process, exe = _window_processes.get(pid.value, (None, ""))
                if process is None or not process.is_running():
                    try:
                        process = psutil.Process(pid.value)
                        exe = packaged_path(pid.value) or process.exe()
                    except (OSError, psutil.Error):
                        exe = ""
                    _window_processes[pid.value] = (process, exe)
                if "!" in identity:
                    exe = "shell:AppsFolder\\" + identity
                elif cls.value == "ApplicationFrameWindow":
                    exe = hosted_app_path(hwnd) or exe
                if not exe or exe.lower().endswith("\\applicationframehost.exe"):
                    exe = f"window:{pid.value}:{hwnd}"
                out.append((hwnd, title.value, exe, icon))
            except Exception:
                pass
            return True

        user32.EnumWindows(WNDENUMPROC(cb), 0)
        for pid in _window_processes.keys() - seen:
            _window_processes.pop(pid, None)
        for key in _window_identities.keys() - seen_windows:
            _window_identities.pop(key, None)
        return out

    def activate(hwnd):
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)
        user32.keybd_event(0x12, 0, 0, 0)
        user32.SetForegroundWindow(hwnd)
        user32.keybd_event(0x12, 0, 2, 0)

    def minimize(hwnd):
        user32.ShowWindow(hwnd, 6)

    def close_window(hwnd):
        user32.PostMessageW(hwnd, 0x0010, 0, 0)

    def foreground():
        return user32.GetForegroundWindow()

    def press_win_key(key=None):
        user32.keybd_event(0x5B, 0, 0, 0)
        if key is not None:
            user32.keybd_event(key, 0, 0, 0)
            user32.keybd_event(key, 0, 2, 0)
        user32.keybd_event(0x5B, 0, 2, 0)
else:
    def list_windows(): return []
    def activate(h): pass
    def minimize(h): pass
    def close_window(h): pass
    def foreground(): return None
    def foreground_fullscreen(display_name=None): return False
    def press_win_key(key=None): pass


def autostart_enabled():
    if not IS_WIN:
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
            winreg.QueryValueEx(k, APP)
            return True
    except OSError:
        return False


def set_autostart(on):
    if not IS_WIN:
        return
    import winreg
    cmd = f'"{sys.executable}" --background' if getattr(sys, "frozen", False) else \
        f'"{sys.executable.replace("python.exe", "pythonw.exe")}" "{os.path.abspath(__file__)}"'
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                        r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                        winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, APP, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(k, APP)
            except OSError:
                pass


# ----------------------------------------------------------------- themes
AL = Qt.AlignmentFlag
W = QFont.Weight
THEMES = design.THEMES
STYLE_LABELS = design.STYLES
THEME_NAME = "nocturne"
THEME = THEMES[THEME_NAME]
BODY_FONT = DISPLAY_FONT = "Segoe UI"
A = design.alpha
MONO_FONTS = ("IBM Plex Mono", "Cascadia Mono", "Consolas", "DejaVu Sans Mono")
BODY_FONTS = ("Inter", "Segoe UI", "DejaVu Sans")
DISPLAY_FONTS = ("Inter", "Segoe UI Variable Display", "Segoe UI", "DejaVu Sans")


def apply_theme(name):
    global THEME, THEME_NAME, BODY_FONT, DISPLAY_FONT
    THEME_NAME = name if name in THEMES else "nocturne"
    THEME = THEMES[THEME_NAME]
    theme_art.activate(THEME_NAME)
    families = set(QFontDatabase.families())
    body = MONO_FONTS if THEME.mono else BODY_FONTS
    display = MONO_FONTS if THEME.mono else DISPLAY_FONTS
    BODY_FONT = next((family for family in body if family in families), "Segoe UI")
    DISPLAY_FONT = next((family for family in display if family in families), BODY_FONT)
    font.cache_clear()


def pos_id(key):
    return f"{key}@{THEME_NAME}"


def stored_position(mapping, key):
    # Four older themes stored positions under the plain widget name.
    value = CFG[mapping].get(pos_id(key))
    if value is None and THEME_NAME in {"knight", "cyberpunk", "steampunk", "dota2"}:
        value = CFG[mapping].get(key)
    return value


@lru_cache(maxsize=128)
def font(size, weight=QFont.Weight.Normal, family=None, spacing=0):
    f = QFont(family or BODY_FONT, 1)
    f.setPointSizeF(size)
    f.setWeight(weight)
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return f


FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
fa = lambda n: str(n).translate(FA)
FA_MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
             "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
FA_DAYS_MON0 = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]
FA_SHORT = ["ش", "ی", "د", "س", "چ", "پ", "ج"]           # Saturday first


def g2j(gy, gm, gd):
    gdm = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = (355666 + 365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100 +
            (gy2 + 399) // 400 + gd + gdm[gm - 1])
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        return jy, 1 + days // 31, 1 + days % 31
    return jy, 7 + (days - 186) // 30, 1 + (days - 186) % 30


def j2g(jy, jm, jd):
    jy += 1595
    days = (-355668 + 365 * jy + (jy // 33) * 8 + ((jy % 33) + 3) // 4 + jd +
            ((jm - 1) * 31 if jm < 7 else (jm - 7) * 30 + 186))
    gy = 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    leap = (gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0
    ml = [0, 31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 0
    while gm < 13 and gd > ml[gm]:
        gd -= ml[gm]
        gm += 1
    return gy, gm, gd


def j_month_len(jy, jm):
    if jm < 7:
        return 31
    if jm < 12:
        return 30
    return 30 if g2j(*j2g(jy, 12, 30)) == (jy, 12, 30) else 29


# ----------------------------------------------------------------- data sources
def fmt_speed(b):
    kb = b / 1024
    return f"{kb:.0f} KB/s" if kb < 1024 else f"{kb / 1024:.1f} MB/s"


def code_info(c):
    table = [({0}, "Clear", "☀"), ({1}, "Mostly clear", "🌤"), ({2}, "Partly cloudy", "⛅"),
             ({3}, "Overcast", "☁"), ({45, 48}, "Fog", "🌫"),
             ({51, 53, 55, 56, 57}, "Drizzle", "🌦"), ({61, 63, 65, 66, 67}, "Rain", "🌧"),
             ({71, 73, 75, 77, 85, 86}, "Snow", "🌨"), ({80, 81, 82}, "Showers", "🌦"),
             ({95, 96, 99}, "Thunderstorm", "⛈")]
    for codes, name, icon in table:
        if c in codes:
            return name, icon
    return "—", "☁"


class WeatherService(QObject):
    data = Signal(object)

    def __init__(self):
        super().__init__()
        self.last = None
        self.data.connect(self._store)
        self._changed = threading.Event()
        self.active = False
        threading.Thread(target=self.loop, daemon=True).start()

    def _store(self, d):
        self.last = d

    def configure(self, active, refresh=False):
        if self.active != active or refresh:
            self.active = active
            if refresh:
                self.data.emit(None)
            self._changed.set()

    def loop(self):
        while True:
            self._changed.clear()
            if not self.active:
                self._changed.wait()
                continue
            location = (CFG["lat"], CFG["lon"])
            wait = 900
            try:
                url = ("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
                       "&current=temperature_2m,weather_code"
                       "&hourly=temperature_2m,weather_code"
                       "&daily=weather_code,temperature_2m_max,temperature_2m_min"
                       "&forecast_days=6&timezone=auto" % location)
                with urllib.request.urlopen(url, timeout=10) as r:
                    j = json.load(r)
                dd = j["daily"]
                hourly = j.get("hourly", {})
                hours = [{"time": timestamp, "t": temperature, "c": code}
                         for timestamp, temperature, code in zip(
                             hourly.get("time", ()), hourly.get("temperature_2m", ()), hourly.get("weather_code", ()))
                         if timestamp >= j["current"]["time"] and temperature is not None and code is not None][:6]
                if location != (CFG["lat"], CFG["lon"]) or not self.active:
                    continue
                self.data.emit({
                    "hours": hours, "t": j["current"]["temperature_2m"], "c": j["current"]["weather_code"],
                    "hi": dd["temperature_2m_max"][0], "lo": dd["temperature_2m_min"][0],
                    "days": [{"d": dd["time"][i], "c": dd["weather_code"][i],
                              "hi": dd["temperature_2m_max"][i], "lo": dd["temperature_2m_min"][i]}
                             for i in range(1, len(dd["time"]))]})
            except Exception:
                wait = 60
            self._changed.wait(wait)


class Hub(QObject):
    """one place that samples CPU / RAM / GPU / network / disks / processes"""
    ticked = Signal()
    N = 40

    def __init__(self):
        super().__init__()
        mk = lambda: deque([0.0] * self.N, maxlen=self.N)
        self.cpu, self.ram, self.gpu, self.down, self.up, self.ping = [mk() for _ in range(6)]
        self.gpu_val = None
        self.ping_ms = None
        self.procs, self.disks, self.disk_main = [], [], 0
        self.info = []
        self.total_down = 0
        self._net = None
        self._sample_at = 0
        self.visible = frozenset()
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.CoarseTimer)
        self._timer.timeout.connect(self.sample)
        self._slow_worker = threading.Thread(target=self.read_slow_metrics, daemon=True)
        self._slow_worker.start()
        threading.Thread(target=self.gpu_loop, daemon=True).start()
        threading.Thread(target=self.ping_loop, daemon=True).start()

    def configure(self, visible):
        visible = frozenset(visible) & {"system", "rings", "net", "disks", "procs", "info"}
        interval = CFG["sample_seconds"] * 1000
        if visible == self.visible and self._timer.interval() == interval:
            return
        self.visible = visible
        self._timer.setInterval(interval)
        if visible & {"system", "rings", "net"}:
            if not self._timer.isActive():
                self._net = None
                psutil.cpu_percent(None)
                self._timer.start()
            self.sample()
        else:
            self._timer.stop()

    def sample(self):
        self.cpu.append(psutil.cpu_percent(None))
        self.ram.append(psutil.virtual_memory().percent)
        now = time.monotonic()
        n = psutil.net_io_counters()
        if n and self._net:
            d = max(0, n.bytes_recv - self._net.bytes_recv)
            u = max(0, n.bytes_sent - self._net.bytes_sent)
            elapsed = max(0.001, now - self._sample_at)
            self.down.append(d / elapsed)
            self.up.append(u / elapsed)
            self.total_down += d
        self._net, self._sample_at = n, now
        self.gpu.append(self.gpu_val[0] if self.gpu_val and CFG["gpu_enabled"] else 0)
        self.ping.append(self.ping_ms or 0)
        self.ticked.emit()

    slow_updated = Signal(str)

    def read_slow_metrics(self):
        deadlines = {}
        while True:
            visible = self.visible
            now = time.monotonic()
            for key, wanted, interval, read in (
                ("procs", {"procs"}, 6, self.read_procs),
                ("disks", {"disks", "rings"}, 25, self.read_disks),
                ("info", {"info"}, 10, info_data),
            ):
                if not visible & wanted:
                    deadlines.pop(key, None)
                elif now >= deadlines.get(key, 0):
                    deadlines[key] = now + interval
                    try:
                        result = read()
                        if key == "info":
                            self.info = result
                        self.slow_updated.emit(key)
                    except (OSError, psutil.Error):
                        pass
            time.sleep(1)

    def read_procs(self):
        cores, rows = psutil.cpu_count() or 1, []
        for p in psutil.process_iter(["name", "cpu_percent", "memory_info"]):
            i = p.info
            if not i["name"] or p.pid == 0:
                continue
            mi = i["memory_info"]
            rows.append((i["name"].replace(".exe", ""), (i["cpu_percent"] or 0) / cores,
                         mi.rss / 1048576 if mi else 0))
        rows.sort(key=lambda r: (-r[1], -r[2]))
        self.procs = rows[:4]

    def read_disks(self):
        out = []
        for part in psutil.disk_partitions(all=False):
            if "cdrom" in part.opts or not part.fstype:
                continue
            try:
                u = psutil.disk_usage(part.mountpoint)
            except Exception:
                continue
            out.append((part.mountpoint.rstrip("\\") or part.mountpoint, u.total, u.used, u.percent))
        self.disks = out[:4]
        main = next((d for d in out if d[0].upper().startswith("C")), out[0] if out else None)
        self.disk_main = main[3] if main else 0

    def gpu_loop(self):
        smi = shutil.which("nvidia-smi")
        ps_cmd = ("(Get-Counter '\\GPU Engine(*engtype_3D)\\Utilization Percentage')"
                  ".CounterSamples | Measure-Object CookedValue -Sum | % Sum")
        while True:
            if not CFG["gpu_enabled"] or not self.visible & {"system", "rings"}:
                self.gpu_val = None
                time.sleep(2)
                continue
            try:
                if smi:
                    out = subprocess.check_output(
                        [smi, "--query-gpu=utilization.gpu,temperature.gpu",
                         "--format=csv,noheader,nounits"],
                        text=True, timeout=5, creationflags=NOWIN)
                    u, t = [float(x) for x in out.strip().splitlines()[0].split(",")]
                    self.gpu_val = (u, t)
                elif IS_WIN:
                    out = subprocess.check_output(
                        ["powershell", "-NoProfile", "-Command", ps_cmd],
                        text=True, timeout=8, creationflags=NOWIN)
                    self.gpu_val = (min(100.0, float(out.strip())), None)
            except Exception:
                self.gpu_val = None
            time.sleep(5 if smi else 20)

    def ping_loop(self):
        while True:
            if not CFG["ping_enabled"] or "net" not in self.visible:
                self.ping_ms = None
                time.sleep(2)
                continue
            try:
                t0 = time.perf_counter()
                socket.create_connection((CFG["ping_host"], int(CFG["ping_port"])), timeout=2).close()
                self.ping_ms = (time.perf_counter() - t0) * 1000
            except Exception:
                self.ping_ms = None
            time.sleep(5)


def spark(p, r, data, color, maxv=100.0):
    p.setPen(QPen(QColor(255, 255, 255, 25), 1))
    p.drawLine(QPointF(r.left(), r.bottom()), QPointF(r.right(), r.bottom()))
    path, n = QPainterPath(), data.maxlen
    for i, v in enumerate(data):
        x = r.left() + r.width() * i / (n - 1)
        y = r.bottom() - r.height() * max(0.0, min(1.0, v / maxv))
        path.moveTo(x, y) if i == 0 else path.lineTo(x, y)
    p.setPen(QPen(color, 1.5))
    p.drawPath(path)


# ----------------------------------------------------------------- base widget
def screen_id(screen):
    return "|".join((screen.name(), screen.serialNumber()))


def screen_for(identifier):
    app = QApplication.instance()
    return next((screen for screen in app.screens() if screen_id(screen) == identifier), app.primaryScreen())


def widget_percent(key):
    return round(100 * CFG["widget_scales"].get(key, 1.0))


def monitor_scale(bounds):
    return min(1.25, max(.72, min(bounds.width() / 1366, bounds.height() / 768)))


class DesktopWidget(QWidget):
    placement_changed = Signal()
    label = ""

    def __init__(self, key, w, h):
        super().__init__()
        self.key = key
        self.base_size = self.design_size = (w, h)
        self._painting = False
        self.fit_factor = 1.0
        self.setFixedSize(w, h)
        self._drag = None
        self._resize = None
        self.tick = None
        self.apply_lock()
        self.setMouseTracking(True)

    def width(self):
        return self.design_size[0] if self._painting else super().width()

    def height(self):
        return self.design_size[1] if self._painting else super().height()

    def save_position(self):
        screen = QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        CFG["placements"][pos_id(self.key)] = [screen_id(screen),
            max(0, min(1, (self.x() - area.left()) / max(1, area.width() - self.width()))),
            max(0, min(1, (self.y() - area.top()) / max(1, area.height() - self.height())))]
        save_cfg()


    def set_tick(self, interval, callback=None):
        self.tick = QTimer(self)
        self.tick.setInterval(interval)
        self.tick.timeout.connect(callback or self.update)

    def showEvent(self, event):
        if self.tick:
            self.tick.start()
        super().showEvent(event)

    def hideEvent(self, event):
        if self.tick:
            self.tick.stop()
        super().hideEvent(event)

    def update_if_visible(self):
        if self.isVisible():
            self.update()

    def apply_lock(self):
        flags = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool |
                 Qt.WindowType.WindowStaysOnBottomHint)
        if CFG["locked"]:
            flags |= Qt.WindowType.WindowTransparentForInput
        was = self.isVisible()
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        if was:
            self.show()

    def painter(self):
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        p.fillRect(self.rect(), QColor(0, 0, 0, 1))
        return p

    def paintEvent(self, _):
        p = self.painter()
        try:
            self.render_art(p, self.width(), self.height())
        finally:
            p.end()

    def render_art(self, p, width, height):
        p.save()
        p.scale(width / self.design_size[0], height / self.design_size[1])
        self._painting = True
        try:
            renderer = theme_art.active_renderer()
            key = "calendar" if self.key.startswith("calendar") else self.key
            draw = getattr(renderer, "p_" + key, None)
            if draw:
                draw(self, p)
            else:
                self.paint_default(p)
        finally:
            self._painting = False
            p.restore()

    def at_resize_corner(self, position):
        return position.x() >= self.width() - 15 and position.y() >= self.height() - 15

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or CFG["locked"]:
            return
        pointer = event.globalPosition().toPoint()
        if self.at_resize_corner(event.position()):
            self._resize = pointer, self.width()
        else:
            self._drag = pointer - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        pointer = event.globalPosition().toPoint()
        if self._resize:
            origin, initial = self._resize
            screen = QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen()
            area = screen.availableGeometry()
            width, height = self.design_size
            delta = pointer - origin
            dx, dy = delta.x(), delta.y() * width / height
            proposed = initial + (dx if abs(dx) >= abs(dy) else dy)
            scale = monitor_scale(area) * CFG["widget_scale"] * self.fit_factor
            limit = min((area.right() - self.x() + 1) / width, (area.bottom() - self.y() + 1) / height)
            factor = min(limit, scale * 2.2, max(scale * .55, proposed / width))
            self.setFixedSize(max(1, round(width * factor)), max(1, round(height * factor)))
        elif self._drag is not None:
            self.move(pointer - self._drag)
        else:
            self.setCursor(Qt.CursorShape.SizeFDiagCursor if self.at_resize_corner(event.position())
                           else Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._resize:
            screen = QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen()
            base = monitor_scale(screen.availableGeometry()) * CFG["widget_scale"] * self.fit_factor
            relative = self.width() / self.design_size[0] / max(.01, base)
            CFG["widget_scales"][self.key] = max(.55, min(2.2, relative))
            self._resize = None
        elif self._drag is None:
            return
        self._drag = None
        self.save_position()
        self.placement_changed.emit()


# ----------------------------------------------------------------- widget views
ALIGN_LEFT = AL.AlignLeft | AL.AlignVCenter
ALIGN_RIGHT = AL.AlignRight | AL.AlignVCenter


def draw_text(p, rect, value, size=10, color=None, weight=W.Normal, align=ALIGN_LEFT, *, display=False):
    p.setFont(font(size, weight, DISPLAY_FONT if display else BODY_FONT))
    p.setPen(QColor(color) if color is not None else THEME.ink)
    clipped = p.fontMetrics().elidedText(str(value), Qt.TextElideMode.ElideRight, max(0, round(rect[2])))
    p.drawText(QRectF(*rect), align, clipped)


def widget_card(p, widget, heading=None):
    w, h = widget.width(), widget.height()
    if THEME_NAME in {"knight", "cyberpunk", "steampunk", "dota2", "synthwave"}:
        theme_art.paint_surface(p, widget)
    else:
        design.card(p, QRectF(0, 0, w, h), THEME, CFG["style"])
    if heading:
        draw_text(p, (16, 11, w - 32, 20), heading, 10, THEME.muted, W.DemiBold)


def meter(p, rect, fraction, color=None):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(THEME.layer(37))
    radius = rect.height() / 2
    p.drawRoundedRect(rect, radius, radius)
    if fraction > 0:
        p.setBrush(QColor(color or THEME.accent))
        p.drawRoundedRect(QRectF(rect.x(), rect.y(), rect.width() * min(1, fraction), rect.height()), radius, radius)


def divider(p, x0, x1, y):
    pen = QPen(THEME.layer(37))
    pen.setCosmetic(True)
    p.setPen(pen)
    p.drawLine(QPointF(x0, y), QPointF(x1, y))


def weather_icon(p, x, y, size, code):
    p.save()
    p.translate(x, y)
    p.scale(size / 40, size / 40)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(THEME.accent), 1.9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    if code in (0, 1, 2):
        cx, cy = (20, 19) if code == 0 else (15, 13)
        p.drawEllipse(QPointF(cx, cy), 7, 7)
        for ray in range(8):
            angle = ray * math.pi / 4
            dx, dy = math.cos(angle), math.sin(angle)
            p.drawLine(QPointF(cx + 11 * dx, cy + 11 * dy), QPointF(cx + 14 * dx, cy + 14 * dy))
    if code != 0:
        p.setPen(QPen(THEME.ink, 1.9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        cloud = QPainterPath(QPointF(11, 28))
        cloud.cubicTo(3, 28, 3, 18, 13, 18)
        cloud.cubicTo(15, 8, 29, 9, 31, 19)
        cloud.cubicTo(39, 19, 39, 28, 32, 28)
        cloud.closeSubpath()
        p.fillPath(cloud, QColor(THEME.surface))
        p.drawPath(cloud)
        if code >= 51:
            p.setPen(QPen(QColor(THEME.secondary), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            for drop in (13, 21, 29):
                if code in (71, 73, 75, 77, 85, 86):
                    p.drawEllipse(QPointF(drop, 34), 1, 1)
                else:
                    p.drawLine(QPointF(drop, 32), QPointF(drop - 2, 36))
        elif code in (45, 48):
            p.drawLine(QPointF(9, 33), QPointF(31, 33))
            p.drawLine(QPointF(14, 37), QPointF(28, 37))
    p.restore()


def persian_date(now):
    y, m, d = g2j(now.year, now.month, now.day)
    return f"{FA_DAYS_MON0[now.weekday()]} {fa(d)} {FA_MONTHS[m - 1]} {fa(y)}"


def gpu_reading(hub):
    return hub.gpu_val if CFG["gpu_enabled"] else None


def paint_clock(p, w, h):
    now = datetime.datetime.now()
    if THEME.layout == "tiles":
        draw_text(p, (16, 17, w - 32, 76), now.strftime("%H:%M"), 52, weight=W.DemiBold,
                  align=AL.AlignCenter, display=True)
        draw_text(p, (16, 99, w - 32, 23), now.strftime("%A, %d %B"), 12, THEME.muted,
                  align=AL.AlignCenter)
        if CFG["jalali_clock"]:
            draw_text(p, (16, 128, w - 32, 21), persian_date(now), 10, THEME.accent, align=AL.AlignCenter)
        return
    draw_text(p, (17, 10, w - 34, 24), now.strftime("%A, %d %B"), 10, THEME.accent, W.DemiBold)
    value = now.strftime("%H:%M:%S" if THEME.layout == "instrument" else "%H:%M")
    draw_text(p, (15, 37, w - 30, 71), value, 39 if THEME.mono else 49, weight=W.DemiBold, display=True)
    label = persian_date(now) if CFG["jalali_clock"] else now.strftime("%Y")
    draw_text(p, (18, 113, w - 36, 24), label, 10, THEME.muted)


def paint_system(p, widget):
    w, h, hub = widget.width(), widget.height(), widget.hub
    gpu = gpu_reading(hub)
    items = [("CPU", hub.cpu, f"{hub.cpu[-1]:.0f}%", THEME.accent),
             ("Memory", hub.ram, f"{hub.ram[-1]:.0f}%", THEME.secondary),
             ("GPU", hub.gpu, f"{gpu[0]:.0f}%" if gpu else "—", THEME.accent)]
    if THEME.layout == "instrument":
        for i, (label, data, value, color) in enumerate(items):
            y = 39 + i * 28
            draw_text(p, (16, y, 86, 24), label, 9, THEME.muted)
            spark(p, QRectF(111, y + 5, w - 200, 13), data, QColor(color))
            draw_text(p, (w - 81, y, 63, 24), value, 10, color, W.DemiBold, ALIGN_RIGHT)
    else:
        width = (w - 46) / 3
        for i, (label, data, value, color) in enumerate(items):
            x = 16 + i * (width + 7)
            design.panel(p, QRectF(x, 38, width, h - 56), THEME.layer(21), 11)
            draw_text(p, (x + 9, 46, width - 18, 20), label, 9, color)
            draw_text(p, (x + 9, 70, width - 18, 34), value, 20, weight=W.DemiBold, display=True)
            spark(p, QRectF(x + 10, h - 60, width - 20, 14), data, QColor(color))
    detail = f"↓ {fmt_speed(hub.down[-1])}     ↑ {fmt_speed(hub.up[-1])}"
    if gpu and gpu[1] is not None:
        detail += f"     GPU {gpu[1]:.0f}°C"
    draw_text(p, (16, h - 35, w - 32, 18), detail, 8, THEME.muted)


def paint_calendar(p, widget):
    w = widget.width()
    heading, days, weeks, today, holiday = widget.month_matrix(datetime.datetime.now())
    draw_text(p, (15, 10, w - 30, 27), heading, 13, THEME.ink, W.DemiBold)
    cell_width = (w - 24) / 7
    for index, label in enumerate(days):
        column = 6 - index if widget.jalali else index
        draw_text(p, (12 + column * cell_width, 43, cell_width, 24), label, 9, THEME.muted, align=AL.AlignCenter)
    divider(p, 16, w - 16, 70)
    for row, week in enumerate(weeks):
        for index, day in enumerate(week):
            if not day:
                continue
            column = 6 - index if widget.jalali else index
            x, y = 12 + column * cell_width, 75 + row * 24
            color = THEME.muted if index == holiday else THEME.ink
            if day == today:
                design.panel(p, QRectF(x + 3, y, cell_width - 6, 23), THEME.accent, 7)
                color = THEME.on_accent
            draw_text(p, (x, y, cell_width, 24), fa(day) if widget.jalali else day,
                      9, color, W.DemiBold if day == today else W.Normal, AL.AlignCenter)


def ring(p, cx, cy, radius, width, color, fraction):
    rect = QRectF(cx - radius, cy - radius, 2 * radius, 2 * radius)
    p.setBrush(Qt.BrushStyle.NoBrush)
    pen = QPen(THEME.layer(42), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.drawArc(rect, 0, 360 * 16)
    if fraction > 0:
        pen.setColor(QColor(color))
        p.setPen(pen)
        p.drawArc(rect, 90 * 16, round(-360 * 16 * min(fraction, 1)))


def paint_analog(p, widget):
    center = widget.width() / 2
    now = datetime.datetime.now()
    for i in range(60):
        angle = math.radians(i * 6)
        dx, dy = math.sin(angle), -math.cos(angle)
        outer = center - 15
        inner = outer - (8 if i % 5 == 0 else 3)
        p.setPen(QPen(THEME.layer(165 if i % 5 == 0 else 65), 1.8 if i % 5 == 0 else 1))
        p.drawLine(QPointF(center + inner * dx, center + inner * dy),
                   QPointF(center + outer * dx, center + outer * dy))
    for angle, length, width, color in (
        ((now.hour % 12 + now.minute / 60) * 30, 36, 4.4, THEME.ink),
        ((now.minute + now.second / 60) * 6, 57, 3, THEME.ink),
        (now.second * 6, 62, 1.5, QColor(THEME.accent)),
    ):
        radians = math.radians(angle)
        p.setPen(QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(center, center),
                   QPointF(center + length * math.sin(radians), center - length * math.cos(radians)))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(THEME.accent))
    p.drawEllipse(QPointF(center, center), 3.4, 3.4)


class ClockWidget(DesktopWidget):
    label = "Big clock"

    def __init__(self):
        super().__init__("clock", 318, 166)
        self._minute = None
        self.set_tick(1000, self.update_time)

    def update_time(self):
        minute = datetime.datetime.now().replace(second=0, microsecond=0)
        if THEME.layout == "instrument" or THEME_NAME in {"dotmatrix", "steampunk", "midnight"} or minute != self._minute:
            self._minute = minute
            self.update()

    def paint_default(self, p):
        widget_card(p, self)
        paint_clock(p, self.width(), self.height())


class WeatherWidget(DesktopWidget):
    label = "Weather"

    def __init__(self, svc):
        super().__init__("weather", 234, 152)
        self.d = svc.last
        svc.data.connect(self.on_data)

    def on_data(self, d):
        self.d = d
        self.update_if_visible()

    def paint_default(self, p):
        w = self.width()
        widget_card(p, self, CFG["city"])
        data = self.d
        if not data:
            draw_text(p, (16, 61, w - 32, 36), "Waiting for weather", 11, THEME.muted)
            return
        weather_icon(p, w - 77, 36, 57, data["c"])
        draw_text(p, (14, 39, w - 91, 55), f"{conv(data['t'])}°", 37, weight=W.DemiBold, display=True)
        draw_text(p, (17, 98, w - 34, 22), code_info(data["c"])[0], 11)
        draw_text(p, (17, 122, w - 34, 19), f"High {conv(data['hi'])}°   Low {conv(data['lo'])}°", 9, THEME.muted)


def conv(c):
    return round(c * 9 / 5 + 32) if CFG["units"].upper() == "F" else round(c)


class ForecastWidget(DesktopWidget):
    label = "5-day forecast"

    def __init__(self, svc):
        super().__init__("forecast", 318, 158)
        self.d = svc.last
        svc.data.connect(self.on_data)

    def on_data(self, d):
        self.d = d
        self.update_if_visible()

    def paint_default(self, p):
        widget_card(p, self, "Five-day forecast")
        if not self.d:
            draw_text(p, (16, 53, 282, 36), "Waiting for forecast", 11, THEME.muted)
            return
        for i, day in enumerate(self.d["days"][:5]):
            x = 12 + i * 59
            label = datetime.date.fromisoformat(day["d"]).strftime("%a")
            design.panel(p, QRectF(x, 39, 55, 106), THEME.layer(19), 10)
            draw_text(p, (x, 44, 55, 19), label, 9, THEME.muted, align=AL.AlignCenter)
            weather_icon(p, x + 11, 66, 33, day["c"])
            draw_text(p, (x, 103, 55, 19), f"{conv(day['hi'])}°", 10, THEME.ink, W.DemiBold, AL.AlignCenter)
            draw_text(p, (x, 122, 55, 17), f"{conv(day['lo'])}°", 8, THEME.muted, align=AL.AlignCenter)


class SystemWidget(DesktopWidget):
    label = "CPU / GPU / RAM graphs"

    def __init__(self, hub):
        super().__init__("system", 334, 170)
        self.hub = hub
        hub.ticked.connect(self.update_if_visible)

    def paint_default(self, p):
        widget_card(p, self, "System activity")
        paint_system(p, self)


class RingsWidget(DesktopWidget):
    label = "Ring gauges"

    def __init__(self, hub):
        super().__init__("rings", 318, 148)
        self.hub = hub
        hub.ticked.connect(self.update_if_visible)

    def paint_default(self, p):
        widget_card(p, self, "Resource usage")
        hub, gpu = self.hub, gpu_reading(self.hub)
        rows = [("CPU", hub.cpu[-1], THEME.accent), ("Memory", hub.ram[-1], THEME.secondary),
                ("GPU", gpu[0] if gpu else None, THEME.accent),
                ("Disk", hub.disk_main if hub.disks else None, THEME.secondary)]
        for index, (name, value, color) in enumerate(rows):
            x = 48 + index * 74
            ring(p, x, 79, 27, 4, color, (value or 0) / 100)
            draw_text(p, (x - 26, 62, 52, 32), "—" if value is None else f"{value:.0f}%", 10, weight=W.DemiBold,
                      align=AL.AlignCenter)
            draw_text(p, (x - 36, 114, 72, 19), name, 8, THEME.muted, align=AL.AlignCenter)


class NetWidget(DesktopWidget):
    label = "Network & ping"

    def __init__(self, hub):
        super().__init__("net", 300, 170)
        self.hub = hub
        hub.ticked.connect(self.update_if_visible)

    def paint_default(self, p):
        widget_card(p, self, "Network")
        hub = self.hub
        ms = hub.ping_ms
        rows = [
            ("Download", fmt_speed(hub.down[-1]), hub.down, THEME.accent, max(50e3, max(hub.down))),
            ("Upload", fmt_speed(hub.up[-1]), hub.up, THEME.secondary, max(50e3, max(hub.up))),
            ("Latency", f"{ms:.0f} ms" if ms is not None and CFG["ping_enabled"] else "—",
             hub.ping, THEME.accent, max(60, max(hub.ping))),
        ]
        for index, (label, value, data, color, maximum) in enumerate(rows):
            y = 41 + 31 * index
            draw_text(p, (16, y, 84, 21), label, 9, THEME.muted)
            spark(p, QRectF(104, y + 4, 75, 12), data, QColor(color), maximum)
            draw_text(p, (186, y, 95, 21), value, 9, THEME.ink, W.DemiBold, ALIGN_RIGHT)
        draw_text(p, (16, 141, 270, 20), f"Session downloaded  {self.hub.total_down / 2**20:.0f} MB", 8, THEME.muted)


class DisksWidget(DesktopWidget):
    label = "Disks"

    def __init__(self, hub):
        super().__init__("disks", 294, 192)
        self.hub = hub
        hub.slow_updated.connect(lambda key: self.update_if_visible() if key == "disks" else None)

    def paint_default(self, p):
        widget_card(p, self, "Storage")
        if not self.hub.disks:
            draw_text(p, (16, 45, 264, 25), "Waiting for disk usage", 10, THEME.muted)
        for index, (name, total, used, percent) in enumerate(self.hub.disks[:4]):
            y = 37 + 37 * index
            draw_text(p, (16, y, 95, 21), name, 10, weight=W.DemiBold)
            draw_text(p, (104, y, 174, 21), f"{(total - used) / 2**30:.0f} GB free", 9, THEME.muted, align=ALIGN_RIGHT)
            meter(p, QRectF(16, y + 23, 262, 5), percent / 100, THEME.secondary if percent < 85 else THEME.accent)


class ProcsWidget(DesktopWidget):
    label = "Top processes"

    def __init__(self, hub):
        super().__init__("procs", 296, 167)
        self.hub = hub
        hub.slow_updated.connect(lambda key: self.update_if_visible() if key == "procs" else None)

    def paint_default(self, p):
        widget_card(p, self, "Top processes")
        draw_text(p, (17, 37, 118, 17), "App", 8, THEME.muted)
        draw_text(p, (152, 37, 48, 17), "CPU", 8, THEME.muted, align=ALIGN_RIGHT)
        draw_text(p, (207, 37, 68, 17), "Memory", 8, THEME.muted, align=ALIGN_RIGHT)
        for index, (name, cpu, mem) in enumerate(self.hub.procs):
            y = 60 + index * 24
            if index % 2 == 0:
                design.panel(p, QRectF(13, y, 269, 22), THEME.layer(15), 5)
            draw_text(p, (18, y, 123, 22), name, 9)
            draw_text(p, (152, y, 48, 22), f"{cpu:.0f}%", 9, THEME.accent, align=ALIGN_RIGHT)
            draw_text(p, (205, y, 70, 22), f"{mem:.0f} MB", 9, THEME.muted, align=ALIGN_RIGHT)


class InfoWidget(DesktopWidget):
    label = "System info (battery, uptime)"

    def __init__(self, hub):
        super().__init__("info", 284, 158)
        self.hub = hub
        hub.slow_updated.connect(lambda key: self.update_if_visible() if key == "info" else None)

    def paint_default(self, p):
        widget_card(p, self, "This PC")
        for index, (label, value) in enumerate(self.hub.info):
            x = 14 + (index % 2) * 132
            y = 39 + (index // 2) * 55
            design.panel(p, QRectF(x, y, 124, 48), THEME.layer(22), 8)
            draw_text(p, (x + 8, y + 3, 108, 17), label, 8, THEME.muted)
            draw_text(p, (x + 8, y + 20, 108, 21), value, 9, THEME.ink, W.DemiBold)


class CalendarWidget(DesktopWidget):
    def __init__(self, key, jalali):
        super().__init__(key, 264, 235)
        self.jalali = jalali
        self.label = "Persian calendar" if jalali else "Calendar"
        self.set_tick(30000)

    def month_matrix(self, n):
        """returns title, header list, weeks (list of 7 items, 0 = blank), today, holiday column"""
        if self.jalali:
            jy, jm, jd = g2j(n.year, n.month, n.day)
            gy, gm, gd = j2g(jy, jm, 1)
            off = (datetime.date(gy, gm, gd).weekday() + 2) % 7
            cells = [0] * off + list(range(1, j_month_len(jy, jm) + 1))
            cells += [0] * (-len(cells) % 7)
            weeks = [cells[i:i + 7] for i in range(0, len(cells), 7)]
            return f"{FA_MONTHS[jm - 1]} {fa(jy)}", FA_SHORT, weeks, jd, 6
        weeks = calendar.monthcalendar(n.year, n.month)
        return n.strftime("%B %Y"), ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"], weeks, n.day, 6

    def paint_default(self, p):
        widget_card(p, self)
        paint_calendar(p, self)


class AnalogWidget(DesktopWidget):
    label = "Analog clock"

    def __init__(self):
        super().__init__("analog", 176, 176)
        self.set_tick(1000)

    def paint_default(self, p):
        widget_card(p, self)
        paint_analog(p, self)


class NotesWidget(DesktopWidget):
    label = "Notes"

    def __init__(self):
        super().__init__("notes", 300, 177)
        self.edit = QPlainTextEdit(self)
        self.edit.setGeometry(12, 35, 276, 131)
        self.edit.setFrameShape(QFrame.Shape.NoFrame)
        self.restyle()
        self.edit.setPlaceholderText("Write a note…  (unlock widgets to type)")
        self.edit.setPlainText(CFG.get("notes", ""))
        self._t = QTimer(self)
        self._t.setSingleShot(True)
        self._t.timeout.connect(self.save)
        self.edit.textChanged.connect(lambda: self._t.start(700))

    def resizeEvent(self, event):
        if hasattr(self, "edit"):
            sx = self.width() / self.design_size[0]
            sy = self.height() / self.design_size[1]
            self.edit.setGeometry(round(12 * sx), round(35 * sy), self.width() - round(24 * sx),
                                  self.height() - round(46 * sy))
            self.restyle()
        super().resizeEvent(event)

    def restyle(self):
        scale = self.height() / self.design_size[1]
        self.edit.setStyleSheet(f"""
            QPlainTextEdit {{
                background: {THEME.layer(19).name(QColor.NameFormat.HexArgb)};
                color: {THEME.ink.name()}; selection-background-color: {THEME.accent};
                selection-color: {THEME.on_accent.name()}; border: 0; border-radius: {8 * scale:.1f}px;
                font-size: {10 * scale:.1f}pt; font-family: '{BODY_FONT}';
            }}
        """)

    def save(self):
        CFG["notes"] = self.edit.toPlainText()
        save_cfg()

    def paint_default(self, p):
        widget_card(p, self, "Notes")



class Dock(QWidget):
    pins_changed = Signal()
    native_pins_ready = Signal(object)
    icon_ready = Signal(object, QImage)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool |
                            Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.setStyleSheet(
            "QToolTip { background: #252731; color: #f4f5fc; "
            "border: 1px solid #4d5161; padding: 5px 8px; }"
        )
        self.provider = QFileIconProvider()
        self.icons = {}
        self.pixmaps = {}
        self.loading_icons = set()
        self.icons_closed = False
        self.icon_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="KnightDesk icons") if IS_WIN else None
        self.icon_ready.connect(self.receive_icon)
        self.native_pins = []
        self.native_pins_ready.connect(self.receive_pins)
        self.pin_timer = QTimer(self)
        self.pin_timer.setInterval(30000)
        self.pin_timer.timeout.connect(self.sync_pins)
        self.sync_running = False
        self.items, self.order, self.sig = [], [], None
        self.groups = {}
        self.last_scan = 0.0
        self.last_foreground = None
        self.slots, self.hover = [], -1
        self.tray_hover = False
        self.pressed_app = None
        self.press_origin = None
        self.drop_index = None
        self.dragging = False
        self.settings_requested = lambda: None
        self.restore_requested = lambda: None
        self.replacement = TaskbarReplacement(self) if IS_WIN else None
        self.timer = QTimer(self)
        self.timer.setInterval(550)
        self.timer.timeout.connect(self.refresh)
        self.configure()

    def sync_pins(self):
        if IS_WIN and CFG["sync_taskbar"] and not self.sync_running:
            self.sync_running = True
            def read():
                result = taskbar_pins()
                try:
                    self.native_pins_ready.emit(result)
                except RuntimeError:
                    pass
            threading.Thread(target=read, daemon=True).start()

    def receive_pins(self, pins):
        self.sync_running = False
        if pins is not None and pins != self.native_pins:
            self.native_pins = pins
            self.pixmaps.clear()
            if IS_WIN:
                shell_icon.cache_clear()
                resource_icon.cache_clear()
                packaged_icon.cache_clear()
                installed_package_paths.cache_clear()
            self.sig = None
            self.refresh()

    def target_screen(self):
        return screen_for(CFG["dock_monitor"])

    def size_dock(self):
        monitor_factor = monitor_scale(self.target_screen().geometry())
        scale = CFG["dock_size"] / 44 * monitor_factor
        self.S = round(44 * scale)
        requested_icon = max(14, round(34 * CFG["dock_icon_scale"] * monitor_factor))
        self.H = max(round(62 * scale), requested_icon + 16)
        self.ICON = requested_icon
        self.APP_SLOT = max(self.S, self.ICON + max(6, round(self.S * .15)))
        self.PAD = round(13 * scale)
        self.radius = round(21 * scale)
        self.clock_type = max(7, 10 * scale)
        self.CLOCK_W = round(84 * scale) if CFG["dock_clock"] else 0
        self.TRAY_W = max(26, round(self.S * .75)) if IS_WIN else 0
        if CFG["show_dock"]:
            self.layout_items()
            self.update()

    def configure(self):
        self.size_dock()
        self.sig = None
        self.last_scan = 0.0
        if CFG["show_dock"]:
            self.refresh()
            self.timer.start()
            if IS_WIN and CFG["sync_taskbar"]:
                if not self.pin_timer.isActive():
                    self.sync_pins()
                    self.pin_timer.start()
            else:
                self.pin_timer.stop()
        else:
            self.timer.stop()
            self.pin_timer.stop()
            self.hide()

    # --- data
    @staticmethod
    def norm(path):
        if path.lower().startswith(("shell:", "window:")):
            return path.casefold()
        return os.path.normcase(os.path.abspath(path))

    def icon_for(self, path):
        if len(self.icons) >= 128 and path not in self.icons:
            self.icons.clear()
        if path not in self.icons:
            self.icons[path] = self.provider.icon(QFileInfo(path))
        return self.icons[path]

    def app_pixmap(self, item, logical_size=None):
        dpr = self.devicePixelRatioF()
        logical_size = logical_size or self.ICON
        target, shortcut = item["path"], item.get("shortcut")
        spec = item.get("icon") or ""
        hwnd = next(iter(item.get("hwnds", ())), 0)
        key = (target, shortcut, spec, logical_size, dpr, hwnd)
        if key in self.pixmaps:
            return self.pixmaps[key]
        if self.icons_closed:
            return QPixmap()
        pixels = max(1, round(logical_size * dpr))
        if self.icon_pool:
            if key not in self.loading_icons and len(self.loading_icons) < 80:
                self.loading_icons.add(key)
                future = self.icon_pool.submit(self.native_app_icon, target, shortcut, spec, hwnd, pixels)

                def ready(job):
                    try:
                        image = job.result()
                    except CancelledError:
                        return
                    except (OSError, ValueError, RuntimeError, AttributeError, TypeError, ctypes.ArgumentError):
                        image = QImage()
                    try:
                        self.icon_ready.emit(key, image)
                    except RuntimeError:
                        pass

                future.add_done_callback(ready)
            return QPixmap()
        return self.receive_icon(key, QImage())

    def receive_icon(self, key, image):
        self.loading_icons.discard(key)
        if self.icons_closed:
            return QPixmap()
        if len(self.pixmaps) >= 256:
            self.pixmaps.clear()
        target, shortcut, _, logical_size, dpr, _ = key
        if image.isNull() and not target.startswith("window:"):
            image = self.icon_for(shortcut or target).pixmap(QSize(logical_size, logical_size), dpr).toImage()
        pixels = max(1, round(logical_size * dpr))
        pixmap = QPixmap.fromImage(prepare_dock_image(image, pixels))
        if not pixmap.isNull():
            pixmap.setDevicePixelRatio(dpr)
        self.pixmaps[key] = pixmap
        self.update()
        return pixmap

    def shutdown_icons(self):
        self.icons_closed = True
        if self.icon_pool:
            pool, self.icon_pool = self.icon_pool, None
            pool.shutdown(wait=False, cancel_futures=True)

    @staticmethod
    def native_app_icon(target, shortcut, spec, hwnd, pixels):
        icon_path, separator, icon_index = spec.rpartition(",")
        image = QImage()
        if separator and icon_path.strip() and icon_index.strip().lstrip("-").isdigit():
            icon_path = os.path.expandvars(icon_path.strip().strip('"'))
            image = resource_icon(icon_path, pixels, int(icon_index))
        elif spec.strip() and not separator:
            image = resource_icon(os.path.expandvars(spec.strip().strip('"')), pixels)
        if target.casefold().startswith("shell:appsfolder\\"):
            asset = packaged_icon(target, pixels)
            if not asset.isNull() and min(asset.width(), asset.height()) >= min(pixels, min(image.width(), image.height())):
                return asset
        if not image.isNull():
            return image
        image = resource_icon(target, pixels) if target.lower().endswith((".exe", ".ico")) else QImage()
        if not image.isNull() and min(image.width(), image.height()) >= pixels:
            return image

        shell_size = max(48, 1 << (pixels - 1).bit_length())
        for path in dict.fromkeys(path for path in (target, shortcut) if path and not path.startswith("window:")):
            shell = shell_icon(path, shell_size)
            if not shell.isNull() and min(shell.width(), shell.height()) > min(image.width(), image.height()):
                image = shell
            if not image.isNull() and min(image.width(), image.height()) >= pixels:
                return image
        if hwnd:
            live = window_icon(hwnd)
            if not live.isNull() and min(live.width(), live.height()) > min(image.width(), image.height()):
                image = live
        return image

    def refresh(self):
        if self.pressed_app is not None:
            return
        if not CFG["show_dock"]:
            return
        if CFG["dock_fullscreen"] and foreground_fullscreen(self.target_screen().name()):
            if self.isVisible():
                self.hide()
            return
        if not self.isVisible():
            self.show()
        fg = foreground()
        now = time.monotonic()
        if fg != self.last_foreground or now - self.last_scan >= 1.6:
            groups = {}
            for hwnd, title, exe, icon in list_windows():
                name = title if exe.startswith(("shell:", "window:")) else Path(exe).stem
                group = groups.setdefault(self.norm(exe), {"path": exe, "name": name, "hwnds": [], "icon": icon})
                group["hwnds"].append(hwnd)
                if icon and not group["icon"]:
                    group["icon"] = icon
            self.groups = groups
            self.last_scan, self.last_foreground = now, fg
        groups = self.groups
        native = self.native_pins if CFG["sync_taskbar"] else []
        pins = {}
        for pin in native:
            pins.setdefault(self.norm(pin["path"]), dict(pin, native=True))
        for pin in CFG["pinned"]:
            if pin.get("path"):
                pins.setdefault(self.norm(pin["path"]), pin)
        keys = [k for k in pins] + [k for k in self.order if k in groups and k not in pins]
        for k in groups:
            if k not in keys:
                keys.append(k)
        rank = {key: index for index, key in enumerate(CFG["dock_order"])}
        keys.sort(key=lambda key: rank.get(key, len(rank)))
        for index, key in enumerate(self.order):
            if key.startswith("window:") and key in keys:
                keys.remove(key)
                keys.insert(min(index, len(keys)), key)
        self.order = keys
        items = []
        for k in keys:
            g = groups.get(k)
            pin = pins.get(k)
            items.append({
                "key": k, "path": (pin or g)["path"], "name": (pin or g)["name"],
                "hwnds": g["hwnds"] if g else [], "pinned": bool(pin),
                "shortcut": pin.get("shortcut") if pin else None,
                "icon": (pin or {}).get("icon") or (g or {}).get("icon"),
                "native": bool(pin and pin.get("native")),
                "active": bool(g and fg in g["hwnds"])})
        old_keys = [i["key"] for i in self.items]
        self.items = items
        sig = tuple((i["key"], tuple(i["hwnds"]), i["icon"], i["active"]) for i in items) + (
            self.minute() if self.CLOCK_W else "",)
        if sig != self.sig:
            if self.sig is None or old_keys != [i["key"] for i in items]:
                self.layout_items()
            self.sig = sig
            self.update()

    @staticmethod
    def minute():
        return datetime.datetime.now().strftime("%H:%M")

    def horizontal_lane(self):
        screen = self.target_screen()
        replacement = self.replacement
        if replacement and replacement.active:
            return replacement.lane(screen, CFG["dock_edge"] == "top")
        geometry = screen.geometry()
        return geometry.left(), geometry.right() + 1

    def layout_items(self):
        slot, height, pad = self.S, self.H, self.PAD
        left, right = self.horizontal_lane()
        available = max(0, right - left - 2 * pad - self.CLOCK_W - self.TRAY_W - 2 * slot - 24)
        self.visible_count = min(len(self.items), available // self.APP_SLOT)
        self.overflow = self.visible_count < len(self.items)
        if self.overflow:
            self.visible_count = max(0, min(self.visible_count, (available - slot) // self.APP_SLOT))
        widths = [slot, *([self.APP_SLOT] * self.visible_count)]
        if self.overflow:
            widths.append(slot)
        widths.append(slot)
        x = pad
        self.slots = []
        for width in widths:
            self.slots.append(QRect(x, 5, width, height - 10))
            x += width
        self.tray_rect = QRect(x, 5, self.TRAY_W, height - 10)
        x += self.TRAY_W
        self.clock_rect = QRect(x + 7, 0, self.CLOCK_W, height)
        self.setFixedSize(x + pad + self.CLOCK_W + (7 if self.CLOCK_W else 0), height)
        self.tray_hover = self.underMouse() and self.tray_rect.contains(self.mapFromGlobal(QCursor.pos()))
        if self.underMouse():
            self.hover = self.hit(self.mapFromGlobal(QCursor.pos()))
        else:
            self.hover = -1
        self.reposition()

    def reposition(self):
        screen = self.target_screen()
        top = CFG["dock_edge"] == "top"
        replacement = self.replacement
        replacing = replacement and replacement.active
        g = screen.geometry() if replacing else screen.availableGeometry()
        left, right = self.horizontal_lane()
        x = left + max(0, (right - left - self.width()) // 2)
        y = g.top() + 6 if top else g.bottom() - self.height() - 5
        if self.pos() != QPoint(x, y) and (not replacing or self.screen() != screen):
            self.move(x, y)
        if replacing:
            edge = replacement.reserve(screen, self.height() + 8, top,
                                       compact=self.width() > right - left)
            if edge is not None:
                y = edge + 4 if top else edge - self.height() - 4
            else:
                QTimer.singleShot(0, replacement.reservation_failed)
        self.move(x, y)

    def event(self, event):
        if event.type() == QEvent.Type.ToolTip:
            if self.toolTip() and not self.dragging:
                point = event.pos()
                index = self.hit(point)
                area = self.slots[index] if index >= 0 else self.tray_rect
                # Anchor above a bottom dock and below a top dock, clear of the artwork.
                y = self.height() + 3 if CFG["dock_edge"] == "top" else -36
                x = max(area.left(), point.x() - 16)
                QToolTip.showText(self.mapToGlobal(QPoint(x, y)), self.toolTip(), self, area)
            return True
        return super().event(event)

    def nativeEvent(self, event_type, message):
        if getattr(self, "replacement", None):
            native = wintypes.MSG.from_address(int(message))
            if self.replacement.notify(native.message, native.wParam):
                return True, 0
        return super().nativeEvent(event_type, message)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        shell = QRectF(self.rect()).adjusted(.55, .55, -.55, -.55)
        upper, lower, rim = {
            "obsidian": ("#24252c", "#0d0e13", "#aeb2c3"),
            "glass": ("#586779", "#171e2a", "#c3cfe5"),
            "violet": ("#3b2b56", "#1a1329", "#ccb6f4"),
        }.get(CFG["dock_surface"], ("#24252c", "#0d0e13", "#aeb2c3"))
        opacity = max(0, min(100, CFG["dock_opacity"])) / 100
        fill = QLinearGradient(shell.topLeft(), shell.bottomLeft())
        fill.setColorAt(0, A(upper, max(1, round(203 * opacity))))
        fill.setColorAt(1, A(lower, max(1, round(248 * opacity))))
        outline = QPen(A(rim, round(108 * opacity)))
        outline.setCosmetic(True)
        p.setPen(outline if opacity else Qt.PenStyle.NoPen)
        p.setBrush(fill)
        p.drawRoundedRect(shell, self.radius, self.radius)

        for index, slot in enumerate(self.slots):
            entry = self.items[index - 1] if 1 <= index <= self.visible_count else None
            if entry:
                self.paint_app(p, slot, entry, index == self.hover)
            else:
                self.paint_control(p, slot, index)

        if self.dragging and self.drop_index is not None and self.visible_count:
            position = self.drop_index
            x = self.slots[position + 1].left() if position < self.visible_count else self.slots[self.visible_count].right() + 1
            design.panel(p, QRectF(x - 1, 9, 2, self.H - 18), QColor("#c4b6ff"), 1)

        if self.TRAY_W:
            rect = QRectF(self.tray_rect)
            size = min(21, rect.width() - 8)
            if self.tray_hover:
                design.panel(p, rect.adjusted(2, 7, -2, -7), QColor(207, 219, 242, 28), 9)
            design.glyph(p, "tray", QRectF(rect.center().x() - size / 2, rect.center().y() - size / 2, size, size), "#d4dded")

        if self.CLOCK_W:
            x = self.clock_rect.left() - 4
            line = QPen(QColor(218, 227, 246, round(74 * opacity)))
            line.setCosmetic(True)
            p.setPen(line)
            p.drawLine(QPointF(x, self.H * .25), QPointF(x, self.H * .75))
            now = datetime.datetime.now()
            text = now.strftime("%H:%M") if CFG["dock_24h"] else now.strftime("%I:%M %p").lstrip("0")
            clock = self.clock_rect
            draw_text(p, (clock.x(), self.H * .12, clock.width(), self.H * .43), text,
                      self.clock_type, "#f5f6fb", W.DemiBold, AL.AlignCenter)
            draw_text(p, (clock.x(), self.H * .54, clock.width(), self.H * .32), now.strftime("%d %b"),
                      self.clock_type * .75, "#b8c0d4", align=AL.AlignCenter)

    def paint_control(self, p, slot, index):
        kind = "start" if index == 0 else "settings" if index == len(self.slots) - 1 else "more"
        size = self.S * .53
        rect = QRectF(slot.center().x() - size / 2, self.H / 2 - size / 2 - 1, size, size)
        if index == self.hover:
            design.panel(p, QRectF(slot).adjusted(4, 4, -4, -4), QColor(207, 219, 242, 28), self.radius * .52)
        design.glyph(p, kind, rect, "#f3f5fb" if index == self.hover else "#c9d2e5")

    def paint_app(self, p, slot, entry, hovered):
        center = QPointF(slot.x() + slot.width() / 2, self.H / 2 - 2)
        icon = self.app_pixmap(entry)
        if not icon.isNull():
            extent = icon.deviceIndependentSize()
            dpr = self.devicePixelRatioF()
            x = round((center.x() - extent.width() / 2) * dpr) / dpr
            y = round((center.y() - extent.height() / 2) * dpr) / dpr
            p.save()
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
            if self.dragging and self.pressed_app == entry["key"]:
                p.setOpacity(.52)
            p.drawPixmap(QPointF(x, y), icon)
            p.restore()
        else:
            size = min(self.ICON, 20)
            design.glyph(p, "app", QRectF(center.x() - size / 2, center.y() - size / 2, size, size), "#c9d2e5")
        if hovered or entry["hwnds"]:
            width = 19 if entry["active"] else 11 if hovered else 4
            fill = QColor("#eef2ff") if hovered else QColor("#bac8ff") if entry["active"] else QColor("#7e899f")
            height = 2 if hovered or entry["active"] else 3
            y = 6 if CFG["dock_edge"] == "top" else self.H - 7
            design.panel(p, QRectF(center.x() - width / 2, y, width, height), fill, 1.5)

    # --- interaction
    def hit(self, pos):
        for i, r in enumerate(self.slots):
            if r.contains(pos):
                return i
        return -1

    def mouseMoveEvent(self, event):
        point = event.position().toPoint()
        index = self.hit(point)
        if self.pressed_app is not None and event.buttons() & Qt.MouseButton.LeftButton:
            distance = (event.globalPosition().toPoint() - self.press_origin).manhattanLength()
            if self.dragging or distance >= QApplication.startDragDistance():
                if not self.dragging:
                    self.dragging = True
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)
                    self.setToolTip("")
                    QToolTip.hideText()
                destination = self.insertion_at(point.x()) if self.rect().adjusted(-18, -24, 18, 24).contains(point) else None
                if destination != self.drop_index:
                    self.drop_index = destination
                    self.update()
                return
        tray_hover = self.tray_rect.contains(point)
        if index != self.hover or tray_hover != self.tray_hover:
            self.hover = index
            self.tray_hover = tray_hover
            self.update()
        if tray_hover:
            label = "Windows controls"
        elif 0 < index <= self.visible_count:
            label = self.items[index - 1]["name"]
        elif index == 0:
            label = "Windows Start"
        elif index == len(self.slots) - 1:
            label = "KnightDesk Settings"
        elif index >= 0:
            label = "More apps"
        else:
            label = ""
        if label != self.toolTip():
            self.setToolTip(label)

    def insertion_at(self, x):
        for index, slot in enumerate(self.slots[1:self.visible_count + 1]):
            if x < slot.x() + slot.width() / 2:
                return index
        return self.visible_count

    def reorder_app(self, key, destination):
        current = [item["key"] for item in self.items]
        if key not in current:
            return
        source = current.index(key)
        position = min(len(current), max(0, destination))
        current.pop(source)
        current.insert(position - (source < position), key)
        self.order = current[:]
        # Keep the places of apps that are currently closed, and discard old window-only IDs.
        current = [item for item in current if not item.startswith("window:")]
        known = set(current)
        replacements = iter(current)
        stored = [next(replacements) if old in known else old for old in dict.fromkeys(CFG["dock_order"])]
        stored.extend(replacements)
        CFG["dock_order"] = stored[-512:]
        self.sig = None
        save_cfg()
        self.refresh()
        self.pins_changed.emit()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self.pressed_app is None:
            return super().mouseReleaseEvent(event)
        key, dragged, destination = self.pressed_app, self.dragging, self.drop_index
        self.pressed_app = self.press_origin = self.drop_index = None
        self.dragging = False
        self.unsetCursor()
        point = event.position().toPoint()
        index = self.hit(point)
        self.hover = index
        if dragged:
            if destination is not None and self.rect().adjusted(-18, -24, 18, 24).contains(point):
                self.reorder_app(key, self.insertion_at(point.x()))
        elif 0 < index <= self.visible_count and self.items[index - 1]["key"] == key:
            self.click_item(self.items[index - 1])
        self.update()

    def hideEvent(self, event):
        self.pressed_app = self.press_origin = self.drop_index = None
        self.dragging = False
        self.unsetCursor()
        QToolTip.hideText()
        super().hideEvent(event)

    def leaveEvent(self, e):
        self.hover = -1
        self.tray_hover = False
        self.setToolTip("")
        self.update()

    def windows_controls(self):
        menu = QMenu(self)
        if not self.replacement.active or self.replacement.preserve_tray:
            menu.addAction("System tray", lambda: press_win_key(0x42))
        else:
            menu.addAction("Restore Windows taskbar", self.restore_requested)
        menu.addAction("Quick Settings · sound and network", lambda: press_win_key(0x41))
        if sys.getwindowsversion().build >= 22000:
            menu.addAction("Notifications and calendar", lambda: press_win_key(0x4E))
        menu.addAction("Task View · open windows", lambda: press_win_key(0x09))
        menu.addAction("Show desktop", lambda: press_win_key(0x44))
        point = self.tray_rect.bottomLeft() if CFG["dock_edge"] == "top" else self.tray_rect.topLeft()
        position = self.mapToGlobal(point)
        if CFG["dock_edge"] == "bottom":
            position -= QPoint(0, menu.sizeHint().height() + 4)
        menu.exec(position)

    def mousePressEvent(self, e):
        point = e.position().toPoint()
        if IS_WIN and self.tray_rect.contains(point):
            self.windows_controls()
            return
        i = self.hit(point)
        if i < 0:
            if e.button() == Qt.MouseButton.RightButton:
                menu = QMenu(self)
                menu.addAction("KnightDesk Settings…", self.settings_requested)
                if self.replacement and self.replacement.active:
                    menu.addAction("Restore Windows taskbar", self.restore_requested)
                if IS_WIN:
                    menu.addAction("Windows Quick Settings", lambda: press_win_key(0x41))
                    menu.addAction("Show desktop", lambda: press_win_key(0x44))
                    menu.addAction("Task View", lambda: press_win_key(0x09))
                menu.exec(e.globalPosition().toPoint())
            elif self.clock_rect.contains(e.position().toPoint()) and IS_WIN:
                press_win_key(0x4E if sys.getwindowsversion().build >= 22000 else 0x41)
            return
        if i == len(self.slots) - 1:
            if e.button() == Qt.MouseButton.RightButton and self.replacement and self.replacement.active:
                menu = QMenu(self)
                menu.addAction("KnightDesk Settings…", self.settings_requested)
                menu.addAction("Restore Windows taskbar", self.restore_requested)
                menu.exec(e.globalPosition().toPoint())
            else:
                self.settings_requested()
            return
        if self.overflow and i == len(self.slots) - 2:
            menu = QMenu(self)
            for item in self.items[self.visible_count:]:
                action = menu.addAction(QIcon(self.app_pixmap(item, 20)), item["name"])
                action.triggered.connect(lambda _, entry=item: self.click_item(entry))
            menu.exec(e.globalPosition().toPoint())
            return
        if i == 0:
            if e.button() == Qt.MouseButton.LeftButton:
                press_win_key()
            elif IS_WIN and e.button() == Qt.MouseButton.RightButton:
                menu = QMenu(self)
                menu.addAction("Windows power user menu", lambda: press_win_key(0x58))
                menu.addAction("Task Manager", lambda: os.startfile(
                    str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/Taskmgr.exe")))
                menu.exec(e.globalPosition().toPoint())
            return
        it = self.items[i - 1]
        if e.button() == Qt.MouseButton.LeftButton:
            self.pressed_app = it["key"]
            self.press_origin = e.globalPosition().toPoint()
        elif e.button() == Qt.MouseButton.RightButton:
            self.menu_item(it)

    def click_item(self, it):
        hw = it["hwnds"]
        if not hw:
            try:
                if IS_WIN and it["path"].startswith("shell:") and not it.get("shortcut"):
                    explorer = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "explorer.exe"
                    subprocess.Popen([str(explorer), it["path"]])
                elif IS_WIN:
                    os.startfile(it.get("shortcut") or it["path"])
                else:
                    subprocess.Popen([it["path"]])
            except Exception:
                pass
        elif it["active"]:
            if len(hw) == 1:
                minimize(hw[0])
            else:
                fg = foreground()
                activate(hw[(hw.index(fg) + 1) % len(hw)] if fg in hw else hw[0])
        else:
            activate(hw[0])
        self.last_scan = 0.0
        QTimer.singleShot(250, self.refresh)

    def menu_item(self, it):
        m = QMenu()
        pin = m.addAction("Pinned in Windows" if it["native"] else "Unpin from dock" if it["pinned"] else "Pin to dock")
        pin.setEnabled(not it["native"] and not it["path"].startswith("window:"))
        index = self.items.index(it)
        left = m.addAction("Move left")
        right = m.addAction("Move right")
        left.setEnabled(index > 0)
        right.setEnabled(index < len(self.items) - 1)
        close = m.addAction("Close window") if it["hwnds"] else None
        a = m.exec(QCursor.pos())
        if a == pin:
            if it["pinned"]:
                CFG["pinned"] = [p for p in CFG["pinned"] if self.norm(p["path"]) != it["key"]]
            else:
                CFG["pinned"].append({"name": it["name"], "path": it["path"]})
            save_cfg()
            self.pins_changed.emit()
        elif a == left:
            self.reorder_app(it["key"], index - 1)
        elif a == right:
            self.reorder_app(it["key"], index + 2)
        elif close is not None and a == close:
            for h in it["hwnds"]:
                close_window(h)
        self.sig = None
        self.refresh()


def info_data():
    b = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
    up = int(time.time() - psutil.boot_time())
    vm = psutil.virtual_memory()
    return [("Power", f"{b.percent:.0f}%{' ⚡' if b.power_plugged else ''}" if b else "AC"),
            ("Uptime", f"{up // 86400}d {up % 86400 // 3600}h {up % 3600 // 60}m"),
            ("Processes", str(len(psutil.pids()))),
            ("Memory", f"{vm.used / 2**30:.1f}/{vm.total / 2**30:.0f} GB")]


class FocusWidget(DesktopWidget):
    label = "Focus timer"

    def __init__(self):
        super().__init__("focus", 236, 132)
        self.deadline = None
        self.set_tick(1000)

    def start_focus(self):
        self.deadline = time.monotonic() + CFG["focus_minutes"] * 60
        self.update()

    def reset_focus(self):
        self.deadline = None
        self.update()

    def paint_default(self, p):
        w = self.width()
        total = CFG["focus_minutes"] * 60
        seconds = max(0, math.ceil(self.deadline - time.monotonic())) if self.deadline is not None else total
        label = "Session complete" if self.deadline is not None and not seconds else "Focus timer"
        widget_card(p, self, label)
        draw_text(p, (16, 36, w - 32, 55), f"{seconds // 60:02}:{seconds % 60:02}", 31,
                  weight=W.DemiBold, display=True)
        meter(p, QRectF(17, 107, w - 34, 6), seconds / total)


class WorldWidget(DesktopWidget):
    label = "World clock"

    def __init__(self):
        super().__init__("world", 236, 132)
        self.set_tick(15000)

    def paint_default(self, p):
        zone = CFG["world_zone"]
        try:
            now = datetime.datetime.now(ZoneInfo(zone))
        except ZoneInfoNotFoundError:
            now = datetime.datetime.now(datetime.timezone.utc)
            zone = "UTC"
        widget_card(p, self, zone.rsplit("/", 1)[-1].replace("_", " "))
        draw_text(p, (16, 34, 204, 58), now.strftime("%H:%M"), 32, weight=W.DemiBold, display=True)
        draw_text(p, (16, 99, 204, 22), now.strftime("%a, %d %b · %Z"), 9, THEME.accent)


BENTO_WIDGETS = ("flip", "photos", "reminders", "agenda", "battery", "media", "shortcuts", "weather_board")
GRAPHITE_PRESET = ("photos", "flip", "battery", "weather_board", "tasks", "reminders", "agenda", "media", "shortcuts")


class CardWidget(DesktopWidget):
    def __init__(self, key, w, h):
        super().__init__(key, w, h)
        self.buttons = []

    def paint_default(self, p):
        self.buttons.clear()
        widget_card(p, self, self.label)
        self.paint_content(p)

    def button(self, p, x, y, w, h, text, call, *, icon=None, primary=False):
        rect = QRectF(x, y, w, h)
        fill = A(THEME.accent, 87) if primary else THEME.layer(27)
        design.panel(p, rect, fill, 10, THEME.layer(39))
        if icon:
            edge = min(w, h) * .61
            design.glyph(p, icon, QRectF(x + (w - edge) / 2, y + (h - edge) / 2, edge, edge), THEME.ink)
        elif text:
            draw_text(p, (x + 3, y, w - 6, h), text, 9, THEME.ink, W.DemiBold, AL.AlignCenter)
        self.buttons.append((rect, call))

    def mousePressEvent(self, event):
        if (event.button() == Qt.MouseButton.LeftButton and not CFG["locked"]
                and not self.at_resize_corner(event.position())):
            point = QPointF(event.position().x() * self.design_size[0] / self.width(),
                            event.position().y() * self.design_size[1] / self.height())
            for rect, call in self.buttons:
                if rect.contains(point):
                    call()
                    return
        super().mousePressEvent(event)


class FlipClock(CardWidget):
    label = "Flip clock"

    def __init__(self):
        super().__init__("flip", 324, 148)
        self.set_tick(1000)

    def paint_content(self, p):
        now = datetime.datetime.now()
        for index, digits in enumerate(now.strftime("%H %M %S").split()):
            x = 15 + index * 100
            rect = QRectF(x, 38, 94, 71)
            design.panel(p, rect, THEME.layer(27), 11, THEME.layer(51))
            draw_text(p, (x + 3, 39, 88, 68), digits, 33, THEME.ink, W.DemiBold, AL.AlignCenter)
            p.setPen(QPen(A(THEME.shade, 150), 1))
            p.drawLine(QPointF(x + 1, 73.5), QPointF(x + 93, 73.5))
        draw_text(p, (16, 117, 292, 20), now.strftime("%A, %d %B"), 9, THEME.muted, align=AL.AlignCenter)


class PhotoWidget(CardWidget):
    label = "Photo gallery"

    def __init__(self):
        super().__init__("photos", 324, 180)
        self.index = 0
        self.cache = None, QPixmap()
        self.set_tick(15000, lambda: self.advance(1))

    def advance(self, step):
        paths = CFG["photo_files"]
        if paths:
            self.index = (self.index + step) % len(paths)
            self.update()

    def choose_photos(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Choose gallery photos", "", "Images (*.jpg *.jpeg *.png *.webp *.bmp)")
        if paths:
            CFG["photo_files"] = paths
            self.index = 0
            save_cfg()
            self.update()

    def paint_content(self, p):
        paths = CFG["photo_files"]
        if paths:
            path = paths[self.index % len(paths)]
            if self.cache[0] != path:
                reader = QImageReader(path)
                reader.setAutoTransform(True)
                size = reader.size()
                if size.isValid() and max(size.width(), size.height()) > 2048:
                    size.scale(QSize(2048, 2048), Qt.AspectRatioMode.KeepAspectRatio)
                    reader.setScaledSize(size)
                image = reader.read()
                if CFG["photo_mono"] and not image.isNull():
                    image = image.convertToFormat(QImage.Format.Format_Grayscale8)
                self.cache = path, QPixmap.fromImage(image)
            pixmap = self.cache[1]
            if not pixmap.isNull():
                rect = QRectF(1, 1, self.width() - 2, self.height() - 2)
                clip = QPainterPath()
                clip.addRoundedRect(rect, THEME.radius, THEME.radius)
                p.save()
                p.setClipPath(clip)
                p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                ratio = max(rect.width() / pixmap.width(), rect.height() / pixmap.height())
                src = QRectF(0, 0, rect.width() / ratio, rect.height() / ratio)
                src.moveCenter(QPointF(pixmap.width() / 2, pixmap.height() / 2))
                p.drawPixmap(rect, pixmap, src)
                if len(paths) > 1:
                    shade = QLinearGradient(0, self.height() - 54, 0, self.height())
                    shade.setColorAt(0, QColor(0, 0, 0, 0))
                    shade.setColorAt(1, QColor(0, 0, 0, 160))
                    p.fillRect(QRectF(0, self.height() - 54, self.width(), 54), shade)
                p.restore()
                if len(paths) > 1:
                    self.button(p, self.width() - 72, self.height() - 38, 26, 25, "", lambda: self.advance(-1), icon="left")
                    self.button(p, self.width() - 40, self.height() - 38, 26, 25, "", lambda: self.advance(1), icon="right")
                return
        design.glyph(p, "photo", QRectF(17, 45, 28, 28), THEME.accent)
        draw_text(p, (16, 75, self.width() - 32, 24), "Display your own photos", 10, THEME.muted)
        self.button(p, 16, 106, 129, 32, "Choose photos…", self.choose_photos)

    def menu_actions(self, menu):
        menu.addAction("Choose photos…", self.choose_photos)
        action = menu.addAction("Grayscale")
        action.setCheckable(True)
        action.setChecked(CFG["photo_mono"])
        action.toggled.connect(self.set_monochrome)
        square = menu.addAction("Square card")
        square.setCheckable(True)
        square.setChecked(CFG["photo_square"])
        square.toggled.connect(self.set_square)

    def set_square(self, checked):
        CFG["photo_square"] = checked
        self.save_position()
        self.placement_changed.emit()

    def set_monochrome(self, checked):
        CFG["photo_mono"] = checked
        self.cache = None, QPixmap()
        save_cfg()
        self.update()


def edit_reminder(parent, reminder=None):
    dialog = QDialog(parent)
    dialog.setWindowTitle("Edit reminder" if reminder else "New reminder")
    dialog.setMinimumWidth(350)
    layout = QFormLayout(dialog)
    name = QLineEdit(reminder["text"] if reminder else "")
    name.setMaxLength(120)
    date = QDateEdit(QDate.currentDate())
    date.setCalendarPopup(True)
    date.setDisplayFormat("yyyy-MM-dd")
    if reminder:
        date.setDate(QDate.fromString(reminder["date"], Qt.DateFormat.ISODate))
    layout.addRow("Reminder", name)
    layout.addRow("Date", date)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addRow(buttons)
    if dialog.exec() and name.text().strip():
        return {"text": name.text().strip(), "date": date.date().toString(Qt.DateFormat.ISODate),
                "done": reminder["done"] if reminder else False}
    return None


class ReminderWidget(CardWidget):
    label = "Reminders"
    updated = Signal()

    def __init__(self):
        super().__init__("reminders", 324, 180)

    def commit(self):
        save_cfg()
        self.update()
        self.updated.emit()

    def add(self):
        reminder = edit_reminder(self)
        if reminder:
            CFG["reminders"].append(reminder)
            self.commit()

    def toggle(self, reminder):
        reminder["done"] = not reminder["done"]
        self.commit()

    def menu_actions(self, menu):
        menu.addAction("Add reminder…", self.add)
        edit = menu.addMenu("Edit reminder")
        remove = menu.addMenu("Remove reminder")
        for reminder in CFG["reminders"]:
            edit.addAction(reminder["text"], lambda _, r=reminder: self.edit(r))
            remove.addAction(reminder["text"], lambda _, r=reminder: self.remove(r))
        edit.setEnabled(bool(CFG["reminders"]))
        remove.setEnabled(bool(CFG["reminders"]))

    def edit(self, reminder):
        entry = edit_reminder(self, reminder)
        if entry:
            reminder.update(entry)
            self.commit()

    def remove(self, reminder):
        for i, entry in enumerate(CFG["reminders"]):
            if entry is reminder:
                del CFG["reminders"][i]
                break
        self.commit()

    def paint_content(self, p):
        rows = sorted(CFG["reminders"], key=lambda r: (r["done"], r["date"]))
        remaining = sum(not r["done"] for r in rows)
        self.button(p, 260, 9, 47, 24, "", self.add, icon="plus")
        draw_text(p, (16, 41, 55, 51), str(remaining), 29, THEME.ink, W.DemiBold)
        draw_text(p, (18, 92, 63, 20), "Open", 9, THEME.muted)
        if not rows:
            draw_text(p, (87, 47, 210, 29), "No reminders yet", 11, THEME.muted)
        for i, reminder in enumerate(rows[:4]):
            y = 42 + i * 28
            ink = THEME.muted if reminder["done"] else THEME.ink
            box = QRectF(85, y + 3, 15, 15)
            design.panel(p, box, THEME.accent if reminder["done"] else THEME.layer(16), 5, THEME.layer(85))
            if reminder["done"]:
                design.glyph(p, "check", box.adjusted(1, 1, -1, -1), THEME.on_accent, 2.2)
            draw_text(p, (108, y, 194, 22), reminder["text"], 9, ink)
            self.buttons.append((QRectF(80, y, 230, 25), lambda r=reminder: self.toggle(r)))
        if len(rows) > 4:
            draw_text(p, (86, 154, 220, 17), f"+ {len(rows) - 4} more · Right-click to manage", 8, THEME.muted)


class AgendaWidget(CardWidget):
    label = "Agenda"

    def __init__(self):
        super().__init__("agenda", 324, 180)
        self.set_tick(60000)

    def paint_content(self, p):
        today = datetime.date.today()
        for index in range(3):
            day = today + datetime.timedelta(days=index)
            x = 15 + index * 100
            design.panel(p, QRectF(x, 37, 94, 126), THEME.layer(33 if index == 0 else 18), 11)
            draw_text(p, (x + 8, 44, 78, 19), "Today" if index == 0 else day.strftime("%a"), 9, THEME.muted)
            draw_text(p, (x + 8, 63, 78, 35), str(day.day), 20, THEME.ink, W.DemiBold)
            items = [row["text"] for row in CFG["reminders"] if row["date"] == day.isoformat() and not row["done"]]
            for row, text in enumerate(items[:2] or ["No items"]):
                draw_text(p, (x + 8, 104 + row * 20, 78, 18), text, 8, THEME.muted)


class BatteryWidget(CardWidget):
    label = "Battery"

    def __init__(self):
        super().__init__("battery", 164, 148)
        self.level = None
        self.set_tick(30000, self.sample)

    def showEvent(self, event):
        super().showEvent(event)
        self.sample()

    def sample(self):
        try:
            self.level = psutil.sensors_battery()
        except (OSError, psutil.Error):
            self.level = None
        self.update()

    def paint_content(self, p):
        level = self.level
        percent = level.percent if level else 0
        ring(p, 82, 77, 38, 5, THEME.accent, percent / 100)
        design.glyph(p, "battery", QRectF(72, 49, 20, 20), THEME.secondary)
        draw_text(p, (22, 69, 120, 34), f"{percent:.0f}%" if level else "AC", 16, THEME.ink, W.DemiBold, AL.AlignCenter)
        caption = "Plugged in" if level and level.power_plugged else "On battery" if level else "No battery detected"
        draw_text(p, (10, 121, 144, 18), caption, 8, THEME.muted, align=AL.AlignCenter)


class MusicWidget(CardWidget):
    label = "Now playing"
    media_ready = Signal(dict)

    def __init__(self):
        super().__init__("media", 324, 148)
        self.report = {}
        self.cover = QPixmap()
        self.session = MediaSession(self.media_ready.emit) if IS_WIN else None
        self.media_ready.connect(self.receive)

    def showEvent(self, event):
        super().showEvent(event)
        if self.session:
            self.session.set_active(True)

    def hideEvent(self, event):
        super().hideEvent(event)
        if self.session:
            self.session.set_active(False)

    def receive(self, report):
        if report.get("cover") != self.report.get("cover"):
            self.cover = QPixmap()
            if report.get("cover"):
                self.cover.loadFromData(report["cover"])
        self.report = report
        self.update_if_visible()

    def command(self, action):
        if self.session and self.report.get("title"):
            self.session.command(action)
        elif IS_WIN:
            key = {"previous": 0xB1, "toggle": 0xB3, "next": 0xB0}[action]
            user32.keybd_event(key, 0, 0, 0)
            user32.keybd_event(key, 0, 2, 0)

    def paint_content(self, p):
        rect = QRectF(16, 38, 88, 88)
        design.panel(p, rect, THEME.layer(24), 12, THEME.layer(51))
        if not self.cover.isNull():
            clip = QPainterPath()
            clip.addRoundedRect(rect, 12, 12)
            p.save()
            p.setClipPath(clip)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            edge = min(self.cover.width(), self.cover.height())
            src = QRectF((self.cover.width() - edge) / 2, (self.cover.height() - edge) / 2, edge, edge)
            p.drawPixmap(rect, self.cover, src)
            p.restore()
        else:
            design.glyph(p, "music", QRectF(42, 63, 36, 36), THEME.accent)
        draw_text(p, (119, 40, 187, 23), self.report.get("title") or "No active track", 12, THEME.ink, W.DemiBold)
        caption = self.report.get("artist") or ("Windows media keys" if IS_WIN else "Available on Windows")
        draw_text(p, (119, 65, 187, 20), caption, 9, THEME.muted)
        playback = "pause" if self.report.get("playing") else "play"
        for i, (name, icon) in enumerate((("previous", "previous"), ("toggle", playback), ("next", "next"))):
            self.button(p, 119 + i * 61, 96, 55, 30, "", lambda n=name: self.command(n),
                        icon=icon, primary=name == "toggle")


class ShortcutsWidget(CardWidget):
    label = "Quick launch"

    def __init__(self):
        super().__init__("shortcuts", 324, 148)
        self.provider = QFileIconProvider()
        self.icons = {}

    def save(self):
        self.icons.clear()
        save_cfg()
        self.update()

    def add_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose an app or file")
        if path:
            CFG["quick_links"].append({"label": Path(path).stem, "target": path})
            self.save()

    def add_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Choose a folder")
        if path:
            CFG["quick_links"].append({"label": Path(path).name or path, "target": path})
            self.save()

    def add_website(self):
        value, ok = QInputDialog.getText(self, "Add website", "Website URL")
        if ok and value.strip():
            url = QUrl.fromUserInput(value.strip())
            if url.isValid() and url.scheme() in {"https", "http"} and url.host():
                CFG["quick_links"].append({"label": url.host(), "target": url.toString()})
                self.save()
            else:
                QMessageBox.information(self, "Add website", "Enter a valid HTTP or HTTPS URL.")

    def menu_actions(self, menu):
        menu.addAction("Add app or file…", self.add_file)
        menu.addAction("Add folder…", self.add_folder)
        menu.addAction("Add website…", self.add_website)
        extra = menu.addMenu("Open shortcut")
        remove = menu.addMenu("Remove shortcut")
        for entry in CFG["quick_links"]:
            extra.addAction(entry["label"], lambda _, target=entry["target"]: self.open(target))
            remove.addAction(entry["label"], lambda _, item=entry: self.remove(item))
        extra.setEnabled(bool(CFG["quick_links"]))
        remove.setEnabled(bool(CFG["quick_links"]))

    def open(self, target):
        if target.startswith(("https://", "http://")):
            QDesktopServices.openUrl(QUrl(target))
        elif IS_WIN:
            try:
                os.startfile(target)
            except OSError as error:
                QMessageBox.warning(self, self.label, str(error))
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(target))

    def remove(self, entry):
        CFG["quick_links"].remove(entry)
        self.save()

    def paint_content(self, p):
        self.button(p, 260, 9, 47, 24, "", self.add_file, icon="plus")
        if not CFG["quick_links"]:
            draw_text(p, (16, 54, 292, 25), "Add apps, folders or websites", 11, THEME.muted)
        for i, entry in enumerate(CFG["quick_links"][:4]):
            x = 16 + i * 75
            target = entry["target"]
            self.button(p, x, 42, 66, 62, "", lambda t=target: self.open(t))
            if target not in self.icons:
                self.icons[target] = (self.provider.icon(QFileIconProvider.IconType.Network)
                                      if target.startswith(("https://", "http://")) else self.provider.icon(QFileInfo(target)))
            self.icons[target].paint(p, QRect(x + 17, 55, 32, 32))
            draw_text(p, (x, 109, 66, 20), entry["label"], 8, THEME.ink, align=AL.AlignCenter)


class WeatherBoard(CardWidget):
    label = "Weather board"

    def __init__(self, service):
        super().__init__("weather_board", 324, 244)
        self.data = service.last
        service.data.connect(self.receive)

    def receive(self, data):
        self.data = data
        self.update_if_visible()

    def paint_content(self, p):
        data = self.data
        if not data:
            draw_text(p, (16, 74, 290, 26), "Waiting for weather", 11, THEME.muted)
            return
        draw_text(p, (16, 31, 172, 18), CFG["city"], 10, THEME.ink, W.DemiBold)
        draw_text(p, (14, 49, 170, 53), f"{conv(data['t'])}°", 31, THEME.ink, W.DemiBold)
        weather_icon(p, 247, 33, 55, data["c"])
        draw_text(p, (129, 81, 173, 19), code_info(data["c"])[0], 9, THEME.muted, align=AL.AlignRight | AL.AlignVCenter)
        for index, hour in enumerate(data.get("hours", [])[:6]):
            x = 10 + index * 51
            draw_text(p, (x, 112, 48, 17), hour["time"][-5:], 8, THEME.muted, align=AL.AlignCenter)
            weather_icon(p, x + 12, 130, 25, hour["c"])
            draw_text(p, (x, 158, 48, 20), f"{conv(hour['t'])}°", 9, THEME.ink, W.DemiBold, AL.AlignCenter)
        divider(p, 16, 308, 186)
        for index, day in enumerate(data.get("days", [])[:5]):
            x = 13 + index * 61
            name = datetime.date.fromisoformat(day["d"]).strftime("%a")
            draw_text(p, (x, 193, 57, 18), name, 8, THEME.muted, align=AL.AlignCenter)
            draw_text(p, (x, 213, 57, 18), f"{conv(day['lo'])}°/{conv(day['hi'])}°", 8, THEME.ink, align=AL.AlignCenter)


class TaskDelegate(QStyledItemDelegate):
    def __init__(self, task_list):
        super().__init__(task_list)
        self.scale = 1.0

    def sizeHint(self, option, index):
        return QSize(0, max(18, round(30 * self.scale)))

    def check_rect(self, rect):
        edge = max(12, round(17 * self.scale))
        return QRectF(rect.x() + 8 * self.scale, rect.y() + (rect.height() - edge) / 2, edge, edge)

    def paint(self, p, option, index):
        p.save()
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        rect = QRectF(option.rect).adjusted(1, 1, -2, -1)
        if option.state & QStyle.StateFlag.State_Selected:
            design.panel(p, rect, A(THEME.accent, 52), max(3, 6 * self.scale))
        elif index.row() % 2 == 0:
            design.panel(p, rect, THEME.layer(16), max(3, 6 * self.scale))

        done = index.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked.value
        box = self.check_rect(option.rect)
        design.panel(p, box, THEME.accent if done else THEME.layer(14), max(3, 4 * self.scale),
                     None if done else THEME.layer(95))
        if done:
            design.glyph(p, "check", box.adjusted(2, 2, -2, -2), THEME.on_accent, 2.3)

        face = QFont(font(max(7, 10 * self.scale)))
        face.setStrikeOut(done)
        p.setFont(face)
        p.setPen(THEME.muted if done else THEME.ink)
        text_rect = QRectF(box.right() + 8 * self.scale, rect.y(), rect.right() - box.right() - 14 * self.scale,
                           rect.height())
        text = p.fontMetrics().elidedText(index.data(Qt.ItemDataRole.DisplayRole),
                                         Qt.TextElideMode.ElideRight, max(0, int(text_rect.width())))
        p.drawText(text_rect, ALIGN_LEFT, text)
        p.restore()

    def editorEvent(self, event, model, option, index):
        if CFG["locked"]:
            return False
        if event.type() == QEvent.Type.MouseButtonRelease:
            if event.button() != Qt.MouseButton.LeftButton or not self.check_rect(option.rect).contains(event.position()):
                return False
        elif event.type() == QEvent.Type.KeyPress:
            if event.key() not in (Qt.Key.Key_Space, Qt.Key.Key_Select):
                return False
        else:
            return False
        current = index.data(Qt.ItemDataRole.CheckStateRole)
        next_state = Qt.CheckState.Unchecked if current == Qt.CheckState.Checked.value else Qt.CheckState.Checked
        return model.setData(index, next_state.value, Qt.ItemDataRole.CheckStateRole)


class TasksWidget(DesktopWidget):
    label = "Tasks"

    def __init__(self):
        super().__init__("tasks", 340, 228)
        self.list = QListWidget(self)
        self.list.setObjectName("taskList")
        self.list.setFrameShape(QFrame.Shape.NoFrame)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.list.setAccessibleName("Task checklist")
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self.open_task_menu)
        self.delegate = TaskDelegate(self.list)
        self.list.setItemDelegate(self.delegate)
        self.list.itemChanged.connect(self.checked)
        self.list.itemDoubleClicked.connect(self.edit)

        self.input = QLineEdit(self)
        self.input.setObjectName("taskInput")
        self.input.setPlaceholderText("New task")
        self.input.setAccessibleName("New task")
        self.input.setMaxLength(180)
        self.input.returnPressed.connect(self.add)
        self.add_button = QPushButton("Add", self)
        self.add_button.setObjectName("taskAdd")
        self.add_button.clicked.connect(self.add)
        self.add_button.setEnabled(False)
        self.input.textChanged.connect(lambda text: self.add_button.setEnabled(bool(text.strip())))
        self.reload()
        self.layout_controls()

    def reload(self, selected=-1):
        offset = self.list.verticalScrollBar().value()
        self.list.blockSignals(True)
        self.list.clear()
        for row in CFG["tasks"]:
            item = QListWidgetItem(row["text"])
            item.setToolTip(row["text"])
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if row["done"] else Qt.CheckState.Unchecked)
            self.list.addItem(item)
        if selected >= 0 and self.list.count():
            self.list.setCurrentRow(min(selected, self.list.count() - 1))
            self.list.scrollToItem(self.list.currentItem())
        else:
            self.list.verticalScrollBar().setValue(offset)
        self.list.blockSignals(False)
        self.list.setVisible(bool(CFG["tasks"]))
        self.update()

    def add(self):
        value = self.input.text().strip()
        if not value or CFG["locked"]:
            return
        CFG["tasks"].append({"text": value, "done": False})
        self.input.clear()
        self.commit(len(CFG["tasks"]) - 1)
        self.input.setFocus()

    def checked(self, item):
        index = self.list.row(item)
        if 0 <= index < len(CFG["tasks"]):
            CFG["tasks"][index]["done"] = item.checkState() == Qt.CheckState.Checked
            save_cfg()
            self.update()

    def edit(self, item=None):
        index = self.list.row(item) if isinstance(item, QListWidgetItem) else self.list.currentRow()
        if index < 0 or CFG["locked"]:
            return
        value, ok = QInputDialog.getText(self, "Edit task", "Task", text=CFG["tasks"][index]["text"])
        if ok and value.strip():
            CFG["tasks"][index]["text"] = value.strip()[:180]
            self.commit(index)

    def remove(self):
        index = self.list.currentRow()
        if index >= 0:
            del CFG["tasks"][index]
            self.commit(index)

    def clear_completed(self):
        CFG["tasks"] = [item for item in CFG["tasks"] if not item["done"]]
        self.commit()

    def commit(self, selected=-1):
        save_cfg()
        self.reload(selected)

    def menu_actions(self, menu):
        has_selection = self.list.currentRow() >= 0
        menu.addAction("Edit selected task…", self.edit).setEnabled(has_selection)
        menu.addAction("Remove selected task", self.remove).setEnabled(has_selection)
        menu.addAction("Clear completed tasks", self.clear_completed).setEnabled(any(row["done"] for row in CFG["tasks"]))

    def open_task_menu(self, point):
        menu = QMenu(self)
        item = self.list.itemAt(point)
        if item:
            self.list.setCurrentItem(item)
        self.menu_actions(menu)
        menu.exec(self.list.viewport().mapToGlobal(point))

    def resizeEvent(self, event):
        if hasattr(self, "list"):
            self.layout_controls()
        super().resizeEvent(event)

    def layout_controls(self):
        sx = self.width() / self.design_size[0]
        sy = self.height() / self.design_size[1]
        for control, (x, y, width, height) in (
            (self.list, (14, 47, 312, 123)),
            (self.input, (14, 180, 242, 34)),
            (self.add_button, (264, 180, 62, 34)),
        ):
            control.setGeometry(round(x * sx), round(y * sy), max(1, round(width * sx)), max(1, round(height * sy)))
        self.delegate.scale = sy
        self.list.doItemsLayout()
        self.restyle()

    def restyle(self):
        scale = self.height() / self.design_size[1]
        ink, selected_text = THEME.ink.name(), THEME.on_accent.name()
        layer = THEME.layer(31).name(QColor.NameFormat.HexArgb)
        outline = THEME.layer(63).name(QColor.NameFormat.HexArgb)
        thumb = THEME.layer(102).name(QColor.NameFormat.HexArgb)
        self.setStyleSheet(f"""
            QListWidget#taskList {{ background: transparent; color: {ink}; border: 0; }}
            QListWidget#taskList::item {{ background: transparent; }}
            QLineEdit#taskInput, QPushButton#taskAdd {{
                font: {max(7, 10 * scale):.1f}pt '{BODY_FONT}';
                color: {ink}; border-radius: {max(4, round(8 * scale))}px;
            }}
            QLineEdit#taskInput {{
                background: {THEME.surface}; border: 1px solid {outline};
                padding: 0 {max(3, round(8 * scale))}px; selection-background-color: {THEME.accent};
                selection-color: {selected_text};
            }}
            QLineEdit#taskInput:focus {{ border-color: {THEME.accent}; }}
            QPushButton#taskAdd {{ background: {THEME.accent}; color: {selected_text}; border: 0; }}
            QPushButton#taskAdd:disabled {{ background: {layer}; color: {THEME.muted.name()}; }}
            QScrollBar:vertical {{ background: transparent; width: {max(5, round(7 * scale))}px; }}
            QScrollBar::handle:vertical {{ background: {thumb}; border-radius: 2px; min-height: 12px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        self.list.viewport().update()

    def paint_default(self, p):
        widget_card(p, self, self.label)
        tasks = CFG["tasks"]
        if tasks:
            done = sum(row["done"] for row in tasks)
            draw_text(p, (159, 11, 166, 21), f"{done} of {len(tasks)} complete", 8.5, THEME.muted, align=ALIGN_RIGHT)
            meter(p, QRectF(16, 36, 308, 4), done / len(tasks), THEME.secondary)
        else:
            draw_text(p, (17, 70, 305, 25), "No tasks yet", 13, weight=W.DemiBold)
            draw_text(p, (17, 102, 305, 23), "Type a task below and press Enter.", 9, THEME.muted)


# ----------------------------------------------------------------- tray + main
ORDER = ["clock", "weather", "system", "rings", "forecast", "calendar_fa", "disks",
         "procs", "net", "info", "notes", "calendar", "analog", "focus", "world", "tasks", *BENTO_WIDGETS]


def graphite_layout(widgets, bounds, visible):
    """Pack the Graphite preset into a repeatable three-column desktop grid."""
    if not visible:
        return 1.0, {}
    margin = min(22, max(2, bounds.width() // 20), max(2, bounds.height() // 20))
    available = bounds.adjusted(margin, margin, -margin, -margin)
    gap = 12
    columns = min(3, max(1, (available.width() + gap) // 270), len(visible))
    ordered = [key for key in (*GRAPHITE_PRESET, *(k for k in ORDER if k not in GRAPHITE_PRESET)) if key in visible]

    def pack(factor):
        widths, heights = [0] * columns, [0] * columns
        cells = {}
        for key in ordered:
            widget = widgets[key]
            width = max(1, round(widget.width() * factor))
            height = max(1, round(widget.height() * factor))
            column = min(range(columns), key=heights.__getitem__)
            cells[key] = column, heights[column]
            widths[column] = max(widths[column], width)
            heights[column] += height + gap
        total_width = sum(widths) + gap * (columns - 1)
        total_height = max(heights) - gap
        return widths, total_width, total_height, cells

    factor = 1.0
    widths, total_width, total_height, cells = pack(factor)
    if total_width > available.width() or total_height > available.height():
        low, high = 0.0, 1.0
        for _ in range(13):
            middle = (low + high) / 2
            _, width, height, _ = pack(middle)
            if width <= available.width() and height <= available.height():
                low = middle
            else:
                high = middle
        factor = low
        widths, total_width, _, cells = pack(factor)
    origins = [available.left() + max(0, (available.width() - total_width) // 2)]
    for width in widths[:-1]:
        origins.append(origins[-1] + width + gap)
    return factor, {key: (origins[column], available.top() + top) for key, (column, top) in cells.items()}


def flow_positions(widgets, scr, automatic=None, *, factor=1.0, clock_row=False):
    margin, gap = min(22, max(2, scr.width() // 20), max(2, scr.height() // 20)), 12
    left, top = scr.left() + margin, scr.top() + margin
    limit = scr.right() - margin
    if automatic is None:
        automatic = set(widgets) - set(CFG["hidden"])
    x, y, row_height = left, top, 0
    positions = {}
    for key in (key for key in ORDER if key in automatic):
        widget = widgets[key]
        width, height = max(1, round(widget.width() * factor)), max(1, round(widget.height() * factor))
        if x > left and x + width > limit:
            x, y, row_height = left, y + row_height + gap, 0
        positions[key] = (x, y)
        x += width + gap
        row_height = max(row_height, height)
        if key == "clock" and clock_row:
            x, y, row_height = left, y + row_height + gap, 0
    return positions


def fit_flow(widgets, bounds, visible, clock_row):
    def pack(factor, own_row):
        positions = flow_positions(widgets, bounds, visible, factor=factor, clock_row=own_row)
        fits = all(bounds.contains(QRect(x, y, max(1, round(widgets[key].width() * factor)),
                                         max(1, round(widgets[key].height() * factor))))
                   for key, (x, y) in positions.items())
        return fits, positions

    fits, positions = pack(1.0, clock_row)
    if not fits and clock_row:
        fits, positions = pack(1.0, False)
    if fits:
        return 1.0, positions
    low, high = 0.0, 1.0
    for _ in range(12):
        middle = (low + high) / 2
        if pack(middle, False)[0]:
            low = middle
        else:
            high = middle
    return low, pack(low, False)[1]


def make_tray_icon():
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(20, 24, 36))
    p.setPen(QPen(QColor(200, 40, 50), 4))
    p.drawRoundedRect(4, 4, 56, 56, 14, 14)
    p.setPen(THEME.ink)
    p.setFont(font(26, QFont.Weight.Bold))
    p.drawText(QRectF(0, 0, 64, 64), AL.AlignCenter, "K")
    p.end()
    return QIcon(pm)


class ScaleSlider(QWidget):
    changed = Signal(int)

    def __init__(self, label, value, minimum, maximum, suffix="%"):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(minimum, maximum)
        self.slider.setSingleStep(1)
        self.slider.setPageStep(10)
        self.slider.setAccessibleName(label)
        self.slider.setValue(value)
        self.readout = QLabel()
        self.readout.setObjectName("value")
        self.readout.setMinimumWidth(58)
        self.readout.setAlignment(ALIGN_RIGHT)
        self.suffix = suffix
        self.show_value(self.slider.value())
        self.slider.valueChanged.connect(self.show_value)
        self.slider.valueChanged.connect(self.changed.emit)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.readout)

    def show_value(self, value):
        self.readout.setText(f"{value}{self.suffix}")

    def sync(self, value):
        self.slider.blockSignals(True)
        self.slider.setValue(value)
        self.show_value(self.slider.value())
        self.slider.blockSignals(False)


class ThemePreview(QWidget):
    def __init__(self, widgets):
        super().__init__()
        self.widgets = widgets
        self.setFixedHeight(170)
        self.setAccessibleName("Theme preview")

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        bounds = QRectF(self.rect())
        design.panel(p, bounds, QColor("#0d1018"), 12, QColor("#303749"))
        for widget, cell in zip(self.widgets, (
            QRectF(12, 12, (bounds.width() - 34) * .55, bounds.height() - 24),
            QRectF(22 + (bounds.width() - 34) * .55, 12, (bounds.width() - 34) * .45, bounds.height() - 24),
        )):
            width, height = widget.design_size
            factor = min(cell.width() / width, cell.height() / height, 1.0)
            p.save()
            p.translate(cell.center() - QPointF(width * factor / 2, height * factor / 2))
            widget.render_art(p, width * factor, height * factor)
            p.restore()


class SettingsWindow(QWidget):
    changed = Signal(str)
    reset_layout = Signal()
    reset_sizes = Signal()
    graphite_requested = Signal()
    graphite_ended = Signal()
    widget_scale_changed = Signal(str, int)

    def __init__(self, widgets, dock):
        super().__init__()
        self.dock = dock
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(240)
        self.save_timer.timeout.connect(save_cfg)
        self.setWindowTitle("KnightDesk Settings")
        self.setWindowIcon(make_tray_icon())
        self.resize(910, 690)
        self.setMinimumSize(590, 370)
        self.setStyleSheet("""
            QWidget { background: #10131c; color: #eff1f8; font-family: 'Segoe UI'; font-size: 13px; }
            QFrame#sidebar { background: #171b27; border-right: 1px solid #303648; }
            QFrame#modeCard { background: #1c2030; border: 1px solid #43405d; border-radius: 13px; }
            QLabel, QCheckBox, QPushButton#nav { background: transparent; }
            QLabel#brand { font-size: 20px; font-weight: 700; padding: 5px 4px; }
            QLabel#heading { font-size: 30px; font-weight: 700; }
            QLabel#hint { color: #a9b1c6; }
            QLabel#status { color: #c9bdff; font-weight: 600; }
            QLabel#section { font-size: 15px; font-weight: 650; padding-top: 5px; }
            QLabel#value { color: #d9d0ff; font-weight: 600; }
            QFrame#widgetRow { background: #191e2b; border: 1px solid #2d3548; border-radius: 10px; }
            QPushButton#primary { background: #ac98f4; color: #151125; border: 1px solid #c2b1ff; font-weight: 650; }
            QPushButton#primary:hover { background: #c7b6ff; }
            QPushButton#primary:disabled { background: #2a2841; color: #aaa3c2; border-color: #45405a; }
            QScrollArea { border: none; }
            QComboBox, QLineEdit, QDoubleSpinBox, QListWidget {
                background: #1b1e2b; border: 1px solid #383e54; border-radius: 8px; padding: 7px;
            }
            QComboBox:focus, QLineEdit:focus, QDoubleSpinBox:focus { border-color: #a68af8; }
            QListWidget::item { padding: 7px; }
            QListWidget::item:selected { background: #433968; }
            QPushButton { background: #272842; border: 1px solid #47466b; border-radius: 8px; padding: 8px 12px; }
            QPushButton:hover { background: #373456; }
            QPushButton:disabled { color: #85899d; }
            QPushButton#nav { text-align: left; border: 1px solid transparent; padding: 10px; color: #bac0d4; }
            QPushButton#nav:hover { background: #202234; }
            QPushButton#nav:checked { background: #30294b; color: #e5dcff; border-color: #524675; font-weight: 600; }
            QCheckBox { spacing: 10px; padding: 5px 0; }
            QCheckBox::indicator { width: 16px; height: 16px; border-radius: 5px; border: 1px solid #66708b; background: #171a25; }
            QCheckBox::indicator:checked { background: #b09af7; border: 3px solid #443660; }
            QSlider { background: transparent; }
            QSlider::groove:horizontal { height: 5px; border-radius: 2px; background: #34384b; }
            QSlider::sub-page:horizontal { background: #a48aef; border-radius: 2px; }
            QSlider::handle:horizontal { background: #e3d9ff; width: 14px; margin: -5px 0; border-radius: 7px; }
            QScrollBar:vertical { width: 8px; background: transparent; }
            QScrollBar::handle:vertical { background: #42465d; min-height: 26px; border-radius: 4px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(170)
        root.addWidget(sidebar)
        self.navigation = QVBoxLayout(sidebar)
        self.navigation.setContentsMargins(12, 20, 12, 14)
        brand = QLabel("KnightDesk")
        brand.setObjectName("brand")
        self.navigation.addWidget(brand)
        self.navigation.addSpacing(16)
        self.nav_group = QButtonGroup(self)
        body = QVBoxLayout()
        body.setContentsMargins(28, 20, 26, 16)
        root.addLayout(body, 1)
        self.page_title = QLabel()
        self.page_title.setObjectName("heading")
        body.addWidget(self.page_title)
        tabs = QStackedWidget()
        body.addWidget(tabs, 1)

        layout = self.tab(tabs, "Widgets")
        preset_card = QFrame()
        preset_card.setObjectName("modeCard")
        preset_box = QVBoxLayout(preset_card)
        preset_box.setContentsMargins(14, 10, 14, 12)
        self.layout_status = QLabel()
        self.layout_status.setObjectName("status")
        preset_box.addWidget(self.layout_status)
        actions = QHBoxLayout()
        self.preset_button = QPushButton("Apply Graphite Bento")
        self.preset_button.setObjectName("primary")
        self.preset_button.clicked.connect(self.graphite_requested.emit)
        actions.addWidget(self.preset_button)
        self.restore_button = QPushButton("Exit Graphite layout")
        self.restore_button.clicked.connect(self.graphite_ended.emit)
        actions.addWidget(self.restore_button)
        actions.addStretch(1)
        preset_box.addLayout(actions)
        layout.addWidget(preset_card)
        self.refresh_layout_status()

        self.checkbox(layout, "Lock widget positions and make widgets click-through", "locked")
        self.global_scale = self.config_slider(layout, "All widgets", "widget_scale", 55, 160, factor=100)
        actions = QHBoxLayout()
        reset = QPushButton("Reset positions")
        reset.clicked.connect(self.reset_layout.emit)
        actions.addWidget(reset)
        reset_size = QPushButton("Reset widget sizes")
        reset_size.clicked.connect(self.reset_sizes.emit)
        actions.addWidget(reset_size)
        actions.addStretch(1)
        layout.addLayout(actions)

        heading = QLabel("Widget visibility and size")
        heading.setObjectName("section")
        layout.addWidget(heading)
        self.widget_controls, self.widget_sliders = {}, {}
        first = ("tasks", *BENTO_WIDGETS)
        for key in (*first, *(key for key in ORDER if key not in first)):
            frame = QFrame()
            frame.setObjectName("widgetRow")
            row = QHBoxLayout(frame)
            row.setContentsMargins(11, 5, 10, 5)
            label = widgets[key].label
            check = QCheckBox(label)
            check.setChecked(key not in CFG["hidden"])
            check.toggled.connect(lambda shown, k=key: self.set_widget(k, shown))
            self.widget_controls[key] = check
            row.addWidget(check, 2)
            slider = ScaleSlider(f"{label} size", widget_percent(key), 55, 220)
            slider.changed.connect(lambda value, k=key: self.widget_scale_changed.emit(k, value))
            self.widget_sliders[key] = slider
            row.addWidget(slider, 3)
            layout.addWidget(frame)

        self.choice(layout, "Focus session length", "focus_minutes",
                    [(f"{n} minutes", n) for n in (15, 25, 45, 60)])
        self.choice(layout, "World clock city", "world_zone",
                    [(city, zone) for city, zone in (
                        ("Berlin", "Europe/Berlin"), ("Tehran", "Asia/Tehran"), ("Dubai", "Asia/Dubai"),
                        ("London", "Europe/London"), ("New York", "America/New_York"),
                        ("Tokyo", "Asia/Tokyo"), ("UTC", "UTC"),
                    )])
        layout = self.tab(tabs, "Appearance")
        self.theme_choice = self.choice(layout, "Widget theme", "theme", [(theme.label, key) for key, theme in THEMES.items()])
        self.choice(layout, "Widget surface", "style", [(text, key) for key, text in STYLE_LABELS.items()])
        self.theme_preview = ThemePreview((widgets["clock"], widgets["system"]))
        layout.addWidget(self.theme_preview)
        self.checkbox(layout, "Show the Persian date on the clock", "jalali_clock")

        layout = self.tab(tabs, "Taskbar")
        self.checkbox(layout, "Show KnightDesk dock", "show_dock")
        mode = QFrame()
        mode.setObjectName("modeCard")
        mode_layout = QVBoxLayout(mode)
        mode_layout.setContentsMargins(14, 9, 14, 10)
        self.replace_control = self.checkbox(mode_layout, "Replace Windows taskbar", "replace_taskbar")
        self.replace_control.setEnabled(IS_WIN)
        self.keep_tray_control = self.checkbox(mode_layout, "Keep the Windows system tray", "keep_windows_tray")
        self.keep_tray_control.setEnabled(IS_WIN)
        self.taskbar_status = QLabel()
        self.taskbar_status.setObjectName("status")
        self.taskbar_status.setWordWrap(True)
        mode_layout.addWidget(self.taskbar_status)
        self.show_taskbar_status()
        layout.addWidget(mode)
        self.checkbox(layout, "Hide the dock over fullscreen apps", "dock_fullscreen")
        self.checkbox(layout, "Show clock and date", "dock_clock")
        self.checkbox(layout, "Use 24-hour time in the dock", "dock_24h")
        self.choice(layout, "Position", "dock_edge", [("Bottom center", "bottom"), ("Top center", "top")])
        self.config_slider(layout, "Dock size", "dock_size", 30, 76, suffix=" px")
        self.config_slider(layout, "App icon size", "dock_icon_scale", 55, 175, factor=100)
        sync = self.checkbox(layout, "Follow pinned Windows taskbar shortcuts", "sync_taskbar")
        sync.setEnabled(IS_WIN)
        self.choice(layout, "Dock material", "dock_surface",
                    [("Obsidian", "obsidian"), ("Smoked glass", "glass"), ("Violet", "violet")])
        self.config_slider(layout, "Background opacity", "dock_opacity", 0, 100)
        self.display_choice = self.choice(layout, "Display", "dock_monitor", [])
        self.refresh_displays()
        layout.addWidget(QLabel("Additional pinned apps"))
        self.pins = QListWidget()
        self.pins.setFixedHeight(130)
        layout.addWidget(self.pins)
        row = QHBoxLayout()
        for text, handler in (("Add app…", self.add_pin), ("Move up", lambda: self.move_pin(-1)),
                              ("Move down", lambda: self.move_pin(1)), ("Remove", self.remove_pin)):
            button = QPushButton(text)
            button.clicked.connect(handler)
            row.addWidget(button)
        layout.addLayout(row)
        self.reload_pins()

        layout = self.tab(tabs, "Weather")
        self.choice(layout, "Temperature", "units", [("Celsius", "C"), ("Fahrenheit", "F")])
        form = QFormLayout()
        self.city = QLineEdit(CFG["city"])
        self.city.setMaxLength(48)
        form.addRow("City label", self.city)
        self.lat, self.lon = QDoubleSpinBox(), QDoubleSpinBox()
        for name, field, key, bound in (("Latitude", self.lat, "lat", 90), ("Longitude", self.lon, "lon", 180)):
            field.setDecimals(4)
            field.setRange(-bound, bound)
            field.setValue(CFG[key])
            form.addRow(name, field)
        layout.addLayout(form)
        apply = QPushButton("Apply weather location")
        apply.clicked.connect(self.apply_weather)
        layout.addWidget(apply)

        layout = self.tab(tabs, "Performance")
        self.choice(layout, "System sampling", "sample_seconds",
                    [("Responsive · 1 s", 1), ("Balanced · 2 s", 2), ("Low activity · 5 s", 5)])
        self.checkbox(layout, "Read GPU usage while system widgets are visible", "gpu_enabled")
        self.checkbox(layout, "Measure latency while the network widget is visible", "ping_enabled")
        if IS_WIN:
            startup = QCheckBox("Run KnightDesk at Windows sign-in")
            startup.setChecked(autostart_enabled())
            startup.toggled.connect(self.toggle_startup)
            layout.addWidget(startup)
        quit_button = QPushButton("Quit KnightDesk")
        quit_button.clicked.connect(QApplication.instance().quit)
        self.navigation.addStretch(1)
        self.navigation.addWidget(quit_button)
        self.nav_group.button(0).click()

    def refresh_layout_status(self):
        active = CFG["widget_layout"] == "graphite"
        has_previous = bool(CFG["graphite_previous"])
        self.layout_status.setText("Graphite Bento layout" if active else "Custom layout")
        self.preset_button.setVisible(not active)
        self.restore_button.setEnabled(active)
        self.restore_button.setText("Restore previous layout" if has_previous else "Exit Graphite layout")
        self.restore_button.updateGeometry()
        self.restore_button.setVisible(active)

    def sync_sizes(self):
        self.global_scale.sync(round(100 * CFG["widget_scale"]))
        for key, slider in self.widget_sliders.items():
            slider.sync(widget_percent(key))

    def config_slider(self, layout, title, key, minimum, maximum, factor=1, suffix="%"):
        control = ScaleSlider(title, round(CFG[key] * factor), minimum, maximum, suffix)
        def change(value):
            CFG[key] = value / factor if factor != 1 else value
            self.save_timer.start()
            self.changed.emit(key)
        control.changed.connect(change)
        form = QFormLayout()
        form.addRow(title, control)
        layout.addLayout(form)
        return control

    def sync_widget_controls(self):
        for key, control in self.widget_controls.items():
            control.blockSignals(True)
            control.setChecked(key not in CFG["hidden"])
            control.blockSignals(False)
        self.theme_choice.blockSignals(True)
        self.theme_choice.setCurrentIndex(max(0, self.theme_choice.findData(CFG["theme"])))
        self.theme_choice.blockSignals(False)
        self.refresh_layout_status()
        self.theme_preview.update()

    def show_taskbar_status(self):
        replacement = self.dock.replacement
        if not replacement:
            text = "Available on Windows."
        elif replacement.error:
            text = replacement.error
        elif replacement.active:
            if replacement.tray_fallback:
                text = "Windows taskbar kept visible because its tray could not be separated."
            elif replacement.preserve_tray and replacement.tray:
                text = "Replacement active  ·  Windows tray kept at the edge."
            else:
                text = "Replacement active  ·  Right-click the gear to restore Windows."
            if replacement.hotkey_registered:
                text += "  Ctrl + Alt + Shift + F12 also restores it."
        elif CFG["replace_taskbar"] and not CFG["show_dock"]:
            text = "Turn on the KnightDesk dock to enable replacement."
        else:
            text = "Windows taskbar is visible."
        self.taskbar_status.setText(text)

    def tab(self, tabs, label):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(2, 12, 12, 12)
        layout.setSpacing(10)
        layout.setAlignment(AL.AlignTop)
        scroll.setWidget(page)
        index = tabs.addWidget(scroll)
        nav = QPushButton(label)
        nav.setObjectName("nav")
        nav.setCheckable(True)
        self.nav_group.addButton(nav, index)
        self.navigation.addWidget(nav)
        def select():
            tabs.setCurrentIndex(index)
            self.page_title.setText(label)
        nav.clicked.connect(select)
        return layout

    def checkbox(self, layout, text, key):
        check = QCheckBox(text)
        check.setChecked(CFG[key])
        check.toggled.connect(lambda value: self.set_value(key, value))
        layout.addWidget(check)
        return check

    def choice(self, layout, text, key, choices):
        combo = QComboBox()
        for label, value in choices:
            combo.addItem(label, value)
        combo.setCurrentIndex(max(0, combo.findData(CFG[key])))
        combo.currentIndexChanged.connect(lambda _: self.set_value(key, combo.currentData()))
        form = QFormLayout()
        form.addRow(text, combo)
        layout.addLayout(form)
        return combo

    def refresh_displays(self):
        combo = self.display_choice
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("Primary display", "")
        for display in QApplication.screens():
            combo.addItem(display.name(), screen_id(display))
        combo.setCurrentIndex(max(0, combo.findData(CFG["dock_monitor"])))
        combo.blockSignals(False)

    def set_value(self, key, value):
        CFG[key] = value
        save_cfg()
        self.changed.emit(key)

    def set_widget(self, key, shown):
        hidden = set(CFG["hidden"])
        if shown:
            hidden.discard(key)
        else:
            hidden.add(key)
        self.set_value("hidden", sorted(hidden))

    def apply_weather(self):
        city = self.city.text().strip()
        if not city:
            QMessageBox.information(self, APP, "Enter a city label.")
            return
        CFG.update(city=city, lat=self.lat.value(), lon=self.lon.value())
        save_cfg()
        self.changed.emit("weather_location")

    def reload_pins(self, selection=0):
        self.pins.clear()
        order = {key: index for index, key in enumerate(CFG["dock_order"])}
        self.pin_entries = sorted(CFG["pinned"], key=lambda pin: order.get(self.dock.norm(pin["path"]), len(order)))
        for entry in self.pin_entries:
            self.pins.addItem(entry["name"])
            self.pins.item(self.pins.count() - 1).setToolTip(entry["path"])
        if self.pins.count():
            self.pins.setCurrentRow(min(selection, self.pins.count() - 1))

    def add_pin(self):
        path, _ = QFileDialog.getOpenFileName(self, "Add app to dock", "", "Programs (*.exe);;All files (*)")
        if path and all(self.dock.norm(pin["path"]) != self.dock.norm(path) for pin in CFG["pinned"]):
            self.set_value("pinned", CFG["pinned"] + [{"name": Path(path).stem, "path": path}])
            self.reload_pins(len(CFG["pinned"]) - 1)

    def move_pin(self, step):
        index = self.pins.currentRow()
        pins = self.pin_entries[:]
        target = index + step
        if index >= 0 and 0 <= target < len(pins):
            moving, adjacent = (self.dock.norm(pins[i]["path"]) for i in (index, target))
            order = [item["key"] for item in self.dock.items]
            if moving in order and adjacent in order:
                self.dock.reorder_app(moving, order.index(adjacent) + (step > 0))
            elif moving in CFG["dock_order"] or adjacent in CFG["dock_order"]:
                order = [key for key in CFG["dock_order"] if key != moving]
                if adjacent in order:
                    order.insert(order.index(adjacent) + (step > 0), moving)
                else:
                    order.extend((moving, adjacent) if step < 0 else (adjacent, moving))
                CFG["dock_order"] = order
            pins[index], pins[target] = pins[target], pins[index]
            self.set_value("pinned", pins)
            self.reload_pins(target)

    def remove_pin(self):
        index = self.pins.currentRow()
        if index >= 0:
            self.set_value("pinned", [pin for pin in CFG["pinned"] if pin is not self.pin_entries[index]])
            self.reload_pins(index)

    def toggle_startup(self, enabled):
        try:
            set_autostart(enabled)
        except OSError as error:
            button = self.sender()
            button.blockSignals(True)
            button.setChecked(autostart_enabled())
            button.blockSignals(False)
            QMessageBox.warning(self, APP, str(error))


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName(APP)
    shm = QSharedMemory(APP + "-single-instance")
    if not shm.create(1):
        return 0
    load_cfg()
    theme_art.setup(CFG, format_speed=fmt_speed, weather_code=code_info, convert_temperature=conv,
                    solar_date=g2j, persian_digits=fa, persian_months=FA_MONTHS, persian_days=FA_DAYS_MON0,
                    boot_time=psutil.boot_time(), paint_weather_icon=weather_icon, paint_spark=spark)
    apply_theme(CFG["theme"])

    hub, svc = Hub(), WeatherService()
    widgets = {
        "clock": ClockWidget(), "weather": WeatherWidget(svc), "system": SystemWidget(hub),
        "rings": RingsWidget(hub), "forecast": ForecastWidget(svc),
        "calendar_fa": CalendarWidget("calendar_fa", True), "disks": DisksWidget(hub),
        "procs": ProcsWidget(hub), "net": NetWidget(hub), "info": InfoWidget(hub),
        "notes": NotesWidget(), "calendar": CalendarWidget("calendar", False),
        "analog": AnalogWidget(), "focus": FocusWidget(), "world": WorldWidget(),
        "flip": FlipClock(), "photos": PhotoWidget(), "reminders": ReminderWidget(),
        "agenda": AgendaWidget(), "battery": BatteryWidget(), "media": MusicWidget(),
        "shortcuts": ShortcutsWidget(), "weather_board": WeatherBoard(svc), "tasks": TasksWidget(),
    }
    widgets["reminders"].updated.connect(widgets["agenda"].update_if_visible)
    dock = Dock()
    settings = SettingsWindow(widgets, dock)
    app.setWindowIcon(make_tray_icon())

    def show_settings():
        settings.showNormal()
        settings.raise_()
        settings.activateWindow()

    dock.settings_requested = show_settings
    replacement = dock.replacement

    def restore_windows():
        settings.replace_control.setChecked(False)

    dock.restore_requested = restore_windows

    def apply_taskbar():
        if not replacement:
            return
        if CFG["show_dock"] and CFG["replace_taskbar"]:
            if replacement.start(CFG["keep_windows_tray"]):
                dock.layout_items()
        else:
            replacement.stop()
        settings.show_taskbar_status()

    def replacement_changed():
        dock.layout_items()
        settings.show_taskbar_status()

    if replacement:
        replacement.changed.connect(replacement_changed)
        replacement.restore_requested.connect(restore_windows)
        app.aboutToQuit.connect(replacement.stop)
    app.aboutToQuit.connect(dock.shutdown_icons)
    app.aboutToQuit.connect(widgets["notes"].save)
    app.aboutToQuit.connect(save_cfg)
    tray = QSystemTrayIcon(make_tray_icon(), app)
    menu = QMenu()
    menu.addAction("Settings…", show_settings)
    if IS_WIN:
        menu.addAction("Restore Windows taskbar", restore_windows)
    menu.addSeparator()
    menu.addAction("Quit KnightDesk", app.quit)
    tray.setContextMenu(menu)
    tray.activated.connect(lambda reason: show_settings() if reason in (
        QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick) else None)
    tray.setToolTip("KnightDesk · click for settings")
    tray.show()

    def relayout():
        primary = app.primaryScreen()
        bounds = primary.availableGeometry()
        placements = {}
        fixed = {}
        areas = {}
        renderer = theme_art.active_renderer()
        for key, widget in widgets.items():
            size = renderer.sizes.get(key, widget.base_size) if renderer else widget.base_size
            if key == "photos" and CFG["photo_square"]:
                size = (184, 184)
            widget.design_size = size
            placement = stored_position("placements", key)
            if placement:
                placements[key] = placement
            else:
                position = stored_position("positions", key)
                if position:
                    fixed[key] = position
            display = screen_for(placement[0]) if placement else primary
            area = areas[key] = display.availableGeometry()
            w, h = widget.design_size
            factor = monitor_scale(area) * CFG["widget_scale"] * CFG["widget_scales"].get(key, 1.0)
            factor = min(factor, area.width() / w, area.height() / h)
            widget.fit_factor = 1.0
            target = QSize(max(1, round(w * factor)), max(1, round(h * factor)))
            if widget.size() != target:
                widget.setFixedSize(target)
        automatic = set(widgets) - set(CFG["hidden"]) - placements.keys() - fixed.keys()
        if CFG["widget_layout"] == "graphite":
            fit, positions = graphite_layout(widgets, bounds, automatic)
        else:
            fit, positions = fit_flow(widgets, bounds, automatic, getattr(renderer, "clock_row", False))
        if fit < 1:
            for key in automatic:
                widget = widgets[key]
                widget.fit_factor = fit
                widget.setFixedSize(max(1, round(widget.width() * fit)), max(1, round(widget.height() * fit)))
        for key, widget in widgets.items():
            area = areas[key]
            max_x = max(0, area.width() - widget.width())
            max_y = max(0, area.height() - widget.height())
            if key in placements:
                _, xf, yf = placements[key]
                x, y = area.left() + round(max_x * xf), area.top() + round(max_y * yf)
            else:
                x, y = fixed.get(key, positions.get(key, (area.left(), area.top())))
            widget.move(max(area.left(), min(int(x), area.left() + max_x)),
                        max(area.top(), min(int(y), area.top() + max_y)))
            widget.update_if_visible()

    def apply_visibility():
        shown = set(widgets) - set(CFG["hidden"])
        for key, widget in widgets.items():
            widget.setVisible(key in shown)
        hub.configure(shown)
        svc.configure(bool(shown & {"weather", "forecast", "weather_board"}))

    def update_settings(key):
        if key == "widget_scale":
            request_relayout()
            return
        if key in {"dock_size", "dock_icon_scale"}:
            dock.size_dock()
            return
        if key == "hidden":
            relayout()
            apply_visibility()
        elif key == "locked":
            for widget in widgets.values():
                widget.apply_lock()
        elif key == "theme":
            if CFG["widget_layout"] == "graphite" and CFG["theme"] != "graphite":
                exit_graphite(CFG["theme"])
                return
            apply_theme(CFG["theme"])
            relayout()
            widgets["notes"].restyle()
            widgets["tasks"].restyle()
            settings.theme_preview.update()
        elif key in {"style", "jalali_clock"}:
            settings.theme_preview.update()
        elif key in {"dock_surface", "dock_opacity"}:
            dock.update()
        elif key in {"show_dock", "replace_taskbar", "keep_windows_tray", "pinned"} or key.startswith("dock_") or key == "sync_taskbar":
            if key in {"show_dock", "replace_taskbar"} and not (CFG["show_dock"] and CFG["replace_taskbar"]):
                apply_taskbar()
            dock.configure()
            if CFG["show_dock"] and CFG["replace_taskbar"]:
                apply_taskbar()
        elif key == "weather_location":
            svc.configure(svc.active, refresh=True)
        elif key == "sample_seconds":
            hub.configure(hub.visible)
        elif key == "gpu_enabled" and not CFG["gpu_enabled"]:
            hub.gpu_val = None
        elif key == "ping_enabled" and not CFG["ping_enabled"]:
            hub.ping_ms = None
        for widget in widgets.values():
            widget.update_if_visible()

    relayout_timer = QTimer(settings)
    relayout_timer.setSingleShot(True)
    relayout_timer.setInterval(24)
    relayout_timer.timeout.connect(relayout)

    def request_relayout():
        if not relayout_timer.isActive():
            relayout_timer.start()

    def set_widget_size(key, value):
        CFG["widget_scales"][key] = value / 100
        settings.widget_sliders[key].sync(value)
        settings.save_timer.start()
        request_relayout()

    def layout_changed():
        save_cfg()
        settings.sync_widget_controls()
        settings.sync_sizes()
        update_settings("theme")
        apply_visibility()

    def apply_graphite():
        if CFG["widget_layout"] == "graphite":
            return
        CFG["graphite_previous"] = {key: copy.deepcopy(CFG[key]) for key in
                                    ("theme", "widget_layout", "hidden", "positions", "placements",
                                     "widget_scales", "widget_scale")}
        CFG["theme"] = "graphite"
        CFG["widget_layout"] = "graphite"
        CFG["hidden"] = [key for key in ORDER if key not in GRAPHITE_PRESET]
        for name in ("positions", "placements"):
            for key in GRAPHITE_PRESET:
                CFG[name].pop(f"{key}@graphite", None)
        layout_changed()

    def exit_graphite(theme=None):
        if CFG["widget_layout"] != "graphite":
            return
        previous = CFG["graphite_previous"]
        if previous:
            CFG.update(previous)
        else:
            CFG["widget_layout"] = "classic"
            CFG["theme"] = "nocturne"
            CFG["hidden"] = sorted(set(DEFAULTS["hidden"]) | set(BENTO_WIDGETS))
        if theme is not None:
            CFG["theme"] = theme
        CFG["graphite_previous"] = None
        layout_changed()

    def reset_positions():
        CFG["positions"].clear()
        CFG["placements"].clear()
        save_cfg()
        relayout()

    def reset_sizes():
        CFG["widget_scale"] = 1.0
        CFG["widget_scales"].clear()
        settings.sync_sizes()
        save_cfg()
        relayout()

    def placement_changed(key):
        settings.widget_sliders[key].sync(widget_percent(key))
        relayout()

    def screen_updated():
        settings.refresh_displays()
        relayout()
        dock.configure()

    def connect_screen(screen):
        screen.geometryChanged.connect(screen_updated)
        screen.availableGeometryChanged.connect(screen_updated)
        screen.logicalDotsPerInchChanged.connect(screen_updated)

    def new_screen(screen):
        connect_screen(screen)
        QTimer.singleShot(0, screen_updated)

    def resize_widget(key):
        widget = widgets[key]
        dialog = QDialog(settings)
        dialog.setWindowTitle(f"{widget.label} size")
        dialog.setMinimumWidth(340)
        dialog.setStyleSheet(settings.styleSheet())
        layout = QVBoxLayout(dialog)
        slider = ScaleSlider(f"{widget.label} size", widget_percent(key), 55, 220)
        slider.changed.connect(lambda value: set_widget_size(key, value))
        layout.addWidget(slider)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    for key, widget in widgets.items():
        def widget_menu(position, k=key):
            popup = QMenu()
            popup.addAction("KnightDesk Settings…", show_settings)
            popup.addAction("Resize widget…", lambda: resize_widget(k))
            displays = popup.addMenu("Move to display")
            for display in app.screens():
                def move_to(_, target=display):
                    CFG["placements"][pos_id(k)] = [screen_id(target), .06, .07]
                    save_cfg()
                    relayout()
                displays.addAction(display.name(), move_to)
            actions = getattr(widgets[k], "menu_actions", None)
            if actions:
                popup.addSeparator()
                actions(popup)
                popup.addSeparator()
            if k == "focus":
                popup.addAction("Start focus session", widgets[k].start_focus)
                popup.addAction("Reset timer", widgets[k].reset_focus)
            popup.addAction("Hide this widget", lambda: settings.widget_controls[k].setChecked(False))
            popup.exec(widgets[k].mapToGlobal(position))
        widget.placement_changed.connect(lambda k=key: placement_changed(k))
        widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        widget.customContextMenuRequested.connect(widget_menu)

    settings.changed.connect(update_settings)
    settings.reset_layout.connect(reset_positions)
    settings.reset_sizes.connect(reset_sizes)
    settings.graphite_requested.connect(apply_graphite)
    settings.graphite_ended.connect(exit_graphite)
    settings.widget_scale_changed.connect(set_widget_size)
    dock.pins_changed.connect(settings.reload_pins)
    app.primaryScreenChanged.connect(screen_updated)
    app.screenAdded.connect(new_screen)
    app.screenRemoved.connect(lambda _: QTimer.singleShot(0, screen_updated))
    for screen in app.screens():
        connect_screen(screen)
    screen_updated()
    apply_visibility()
    apply_taskbar()

    if IS_WIN and getattr(sys, "frozen", False):
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.CreateEventW.restype = wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        event = kernel32.CreateEventW(None, False, False, r"Local\KnightDesk.ShowSettings")
        if event:
            activation = QTimer(settings)
            activation.timeout.connect(lambda: show_settings() if kernel32.WaitForSingleObject(event, 0) == 0 else None)
            activation.start(600)
            app.aboutToQuit.connect(activation.stop)
            app.aboutToQuit.connect(lambda: kernel32.CloseHandle(event))
    if "--background" not in sys.argv:
        QTimer.singleShot(100, show_settings)
    return app.exec()


if __name__ == "__main__":
    if IS_WIN and sys.argv[1:2] == ["--taskbar-guard"]:
        run_guard(sys.argv[2:])
    else:
        sys.exit(main())
