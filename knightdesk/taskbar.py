"""Windows taskbar visibility, work-area reservation, and crash recovery."""
import ctypes as c
from ctypes import wintypes as w
from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

from PySide6.QtCore import QObject, QTimer, Signal


class AppBarData(c.Structure):
    _fields_ = [("size", w.DWORD), ("window", w.HWND), ("callback", w.UINT),
                ("edge", w.UINT), ("rect", w.RECT), ("parameter", w.LPARAM)]


class MonitorInfo(c.Structure):
    # MONITORINFOEXW adds the display device name needed for fullscreen detection.
    _fields_ = [("size", w.DWORD), ("monitor", w.RECT), ("work", w.RECT),
                ("flags", w.DWORD), ("device", w.WCHAR * 32)]


def read_monitor_info(user, monitor):
    get_info = user.GetMonitorInfoW
    get_info.argtypes = [w.HMONITOR, c.POINTER(MonitorInfo)]
    get_info.restype = w.BOOL
    info = MonitorInfo(size=c.sizeof(MonitorInfo))
    return info if get_info(monitor, c.byref(info)) else None


TRAY_REGION_PROPERTY = "KnightDesk.TrayRegion"


@dataclass(frozen=True)
class TrayArea:
    bar: int
    monitor: int
    outer: tuple
    region: tuple
    left_edge: bool
    top: bool

    @property
    def bounds(self):
        x, y, _, _ = self.outer
        left, top, right, bottom = self.region
        return x + left, y + top, x + right, y + bottom


def measure_tray(bar, monitor, outer, tray, monitor_rect):
    """Accept a measured horizontal notification area touching an outer edge."""
    left, top, right, bottom = outer
    x1, y1, x2, y2 = tray
    width, height = right - left, bottom - top
    if width < 240 or height < 15 or width < height * 4:
        return None
    if not 20 <= x2 - x1 <= width * .60 or min(bottom, y2) - max(top, y1) < height * .4:
        return None
    if x1 < left - 6 or x2 > right + 6:
        return None
    gap_left, gap_right = x1 - left, right - x2
    left_edge = gap_left < gap_right
    if min(gap_left, gap_right) > min(96, width // 12):
        return None
    padding = max(4, height // 9)
    region = (0 if left_edge else max(0, x1 - left - padding), 0,
              min(width, x2 - left + padding) if left_edge else width, height)
    _, mtop, _, mbottom = monitor_rect
    edge_top = abs(top - mtop) < abs(bottom - mbottom)
    return TrayArea(bar, monitor, outer, region, left_edge, edge_top)


class WindowsTaskbar:
    def __init__(self):
        self.user = c.windll.user32
        self.kernel = c.windll.kernel32
        self.message = c.windll.shell32.SHAppBarMessage
        self.message.argtypes = [w.DWORD, c.POINTER(AppBarData)]
        self.message.restype = c.c_size_t
        self.user.FindWindowW.argtypes = [w.LPCWSTR, w.LPCWSTR]
        self.user.FindWindowW.restype = w.HWND
        self.user.FindWindowExW.argtypes = [w.HWND, w.HWND, w.LPCWSTR, w.LPCWSTR]
        self.user.FindWindowExW.restype = w.HWND
        self.user.IsWindowVisible.argtypes = [w.HWND]
        self.user.GetWindowLongW.argtypes = [w.HWND, c.c_int]
        self.user.ShowWindowAsync.argtypes = [w.HWND, c.c_int]
        self.user.MonitorFromWindow.argtypes = [w.HWND, w.DWORD]
        self.user.MonitorFromWindow.restype = w.HMONITOR
        self.user.RegisterWindowMessageW.argtypes = [w.LPCWSTR]
        self.user.RegisterWindowMessageW.restype = w.UINT
        self.user.GetWindowRect.argtypes = [w.HWND, c.POINTER(w.RECT)]
        self.user.SetWindowRgn.argtypes = [w.HWND, w.HRGN, w.BOOL]
        self.user.GetWindowRgn.argtypes = [w.HWND, w.HRGN]
        self.user.GetPropW.argtypes, self.user.GetPropW.restype = [w.HWND, w.LPCWSTR], w.HANDLE
        self.user.RemovePropW.argtypes, self.user.RemovePropW.restype = [w.HWND, w.LPCWSTR], w.HANDLE
        self.user.SetPropW.argtypes = [w.HWND, w.LPCWSTR, w.HANDLE]
        self.gdi = c.windll.gdi32
        self.gdi.CreateRectRgn.argtypes = [c.c_int] * 4
        self.gdi.CreateRectRgn.restype = w.HRGN
        self.gdi.GetRgnBox.argtypes = [w.HRGN, c.POINTER(w.RECT)]
        self.gdi.DeleteObject.argtypes = [w.HGDIOBJ]
        self.kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        self.kernel.OpenProcess.restype = w.HANDLE
        self.kernel.CreateEventW.argtypes = [c.c_void_p, w.BOOL, w.BOOL, w.LPCWSTR]
        self.kernel.CreateEventW.restype = w.HANDLE
        for fn in (self.kernel.SetEvent, self.kernel.ResetEvent, self.kernel.CloseHandle):
            fn.argtypes = [w.HANDLE]
        self.kernel.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
        self.kernel.WaitForSingleObject.restype = w.DWORD
        self.user.RegisterHotKey.argtypes = [w.HWND, c.c_int, w.UINT, w.UINT]
        self.user.UnregisterHotKey.argtypes = [w.HWND, c.c_int]

    def window_rect(self, hwnd):
        box = w.RECT()
        if hwnd and self.user.GetWindowRect(hwnd, c.byref(box)):
            return box.left, box.top, box.right, box.bottom
        return None

    def tray_area(self, bar, xaml_bounds=None):
        outer = self.window_rect(bar)
        if not outer:
            return None
        monitor = self.user.MonitorFromWindow(bar, 2)
        info = read_monitor_info(self.user, monitor)
        if info is None:
            return None
        child = self.user.FindWindowExW(bar, None, "TrayNotifyWnd", None)
        tray = self.window_rect(child)
        bounds = info.monitor
        monitor_rect = bounds.left, bounds.top, bounds.right, bounds.bottom
        if tray and self.user.IsWindowVisible(child):
            area = measure_tray(bar, monitor, outer, tray, monitor_rect)
            if area:
                return area
        if xaml_bounds:
            return measure_tray(bar, monitor, outer, xaml_bounds, monitor_rect)
        return None

    def region_box(self, bar):
        region = self.gdi.CreateRectRgn(0, 0, 0, 0)
        if not region:
            return None
        try:
            if not self.user.GetWindowRgn(bar, region):
                return None
            box = w.RECT()
            kind = self.gdi.GetRgnBox(region, c.byref(box))
            return kind, (box.left, box.top, box.right, box.bottom)
        finally:
            self.gdi.DeleteObject(region)

    def query_xaml_tray(self, bar):
        paths = (Path(sys.executable).with_name("KnightDeskTray.exe"),
                 Path(__file__).with_name("KnightDeskTray.exe"))
        helper = next((path for path in paths if path.is_file()), None)
        if helper is None:
            return None
        try:
            result = subprocess.run([str(helper), str(bar)], capture_output=True, text=True,
                                    timeout=2.5, creationflags=subprocess.CREATE_NO_WINDOW, check=True)
            bounds = tuple(map(int, result.stdout.split()))
            return bounds if len(bounds) == 4 else None
        except (OSError, subprocess.SubprocessError, ValueError):
            return None

    def keep_tray(self, area):
        bar = area.bar
        region_box = area.region
        if self.user.GetWindowLongW(bar, -20) & 0x00400000:  # WS_EX_LAYOUTRTL
            width = area.outer[2] - area.outer[0]
            left, top, right, bottom = region_box
            region_box = width - right, top, width - left, bottom
        owned = self.user.GetPropW(bar, TRAY_REGION_PROPERTY)
        previous = self.region_box(bar)
        if owned and previous == (2, region_box):
            return True
        if not owned and previous is not None:
            return False  # A separate taskbar customizer already owns its region.
        region = self.gdi.CreateRectRgn(*region_box)
        if not region:
            return False
        if not owned and not self.user.SetPropW(bar, TRAY_REGION_PROPERTY, 1):
            self.gdi.DeleteObject(region)
            return False
        if self.user.SetWindowRgn(bar, region, True):
            return True  # Windows owns the successful region.
        self.gdi.DeleteObject(region)
        if not owned:
            self.user.RemovePropW(bar, TRAY_REGION_PROPERTY)
        return False

    def unclip(self, bar):
        if self.user.GetPropW(bar, TRAY_REGION_PROPERTY):
            if self.user.SetWindowRgn(bar, None, True):
                self.user.RemovePropW(bar, TRAY_REGION_PROPERTY)


    def native_bars(self):
        primary = self.user.FindWindowW("Shell_TrayWnd", None)
        if primary:
            yield primary
        secondary = None
        while True:
            secondary = self.user.FindWindowExW(None, secondary, "Shell_SecondaryTrayWnd", None)
            if not secondary:
                break
            yield secondary

    def state(self):
        return self.message(4, c.byref(AppBarData(size=c.sizeof(AppBarData))))

    def set_state(self, state):
        taskbar = self.user.FindWindowW("Shell_TrayWnd", None)
        self.message(10, c.byref(AppBarData(size=c.sizeof(AppBarData), window=taskbar, parameter=state)))

    def restore(self, state):
        self.set_state(state)
        for bar in self.native_bars():
            self.unclip(bar)
            self.user.ShowWindowAsync(bar, 8)  # SW_SHOWNA
        # Explorer may update the taskbar asynchronously after the show request.
        self.set_state(state)

    def launch_guard(self, original_state):
        # The child inherits an actual process handle, so recovery works even if
        # KnightDesk exits before the child finishes starting.
        parent = self.kernel.OpenProcess(0x100000, True, os.getpid())
        event = self.kernel.CreateEventW(None, True, False, None)
        if not parent or not event:
            for handle in (parent, event):
                if handle:
                    self.kernel.CloseHandle(handle)
            raise OSError("Could not create the taskbar recovery handles.")
        try:
            os.set_handle_inheritable(event, True)
            info = subprocess.STARTUPINFO(lpAttributeList={"handle_list": [parent, event]})
            args = [sys.executable]
            if not getattr(sys, "frozen", False):
                args.append(sys.argv[0])
            args += ["--taskbar-guard", str(parent), str(event), str(original_state)]
            child = subprocess.Popen(args, startupinfo=info, close_fds=True,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
        except (OSError, ValueError):
            self.kernel.CloseHandle(event)
            raise
        finally:
            self.kernel.CloseHandle(parent)
        return event, child


def run_guard(args):
    api = WindowsTaskbar()
    parent, event, state = map(int, args)
    try:
        if api.kernel.WaitForSingleObject(parent, 0xFFFFFFFF) == 0:
            if api.kernel.WaitForSingleObject(event, 0) == 0:
                api.restore(state)
    finally:
        api.kernel.CloseHandle(event)
        api.kernel.CloseHandle(parent)


class TaskbarReplacement(QObject):
    changed = Signal()
    restore_requested = Signal()
    tray_ready = Signal(object, object)
    HOTKEY_ID = 4712

    def __init__(self, dock):
        super().__init__(dock)
        self.dock = dock
        self.api = WindowsTaskbar()
        self.callback = self.api.user.RegisterWindowMessageW("KnightDesk.AppBar")
        self.shell_created = self.api.user.RegisterWindowMessageW("TaskbarCreated")
        self.timer = QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.keep_hidden)
        self.window = None
        self.guard = None
        self.registered = False
        self.position = None
        self.reserved_rect = None
        self.hotkey_registered = False
        self.original_state = None
        self.preserve_tray = False
        self.tray = None
        self.tray_fallback = False
        self.probe_bar = None
        self.probe_bounds = None
        self.probe_at = 0.0
        self.probing = False
        self.tray_ready.connect(self.receive_tray_probe)
        self.error = ""

    @property
    def active(self):
        return self.window is not None

    def data(self):
        return AppBarData(size=c.sizeof(AppBarData), window=self.window, callback=self.callback)

    def start(self, keep_tray=False):
        if self.active:
            if self.preserve_tray == keep_tray:
                self.keep_hidden()
                return self.active
            self.stop()
        self.preserve_tray = keep_tray
        self.probe_bar = self.probe_bounds = None
        self.probe_at = 0.0
        self.error = ""
        if not self.callback or not list(self.api.native_bars()):
            self.error = "Explorer taskbar is unavailable."
            return False
        state = self.api.state()
        try:
            if not self.guard or self.guard[1].poll() is not None or self.original_state != state:
                if self.guard:
                    self.api.kernel.CloseHandle(self.guard[0])
                self.guard = None
                self.guard = self.api.launch_guard(state)
            self.original_state = state
        except (OSError, ValueError):
            self.error = "Could not start taskbar recovery."
            return False
        self.window = int(self.dock.winId())
        self.registered = bool(self.api.message(0, c.byref(self.data())))
        if not self.registered:
            self.window = None
            self.error = "Windows could not reserve the taskbar edge."
            return False
        if not self.api.kernel.SetEvent(self.guard[0]):
            self.api.message(1, c.byref(self.data()))
            self.window = None
            self.registered = False
            self.error = "Could not arm taskbar recovery."
            return False
        self.hotkey_registered = bool(self.api.user.RegisterHotKey(self.window, self.HOTKEY_ID, 0x4007, 0x7B))
        self.set_native_state()
        self.keep_hidden()
        if self.active:
            self.timer.start()
        return self.active

    def set_native_state(self):
        state = self.original_state & ~1 if self.preserve_tray else self.original_state | 1
        self.api.set_state(state)

    def keep_hidden(self):
        if not self.active:
            return
        if self.guard[1].poll() is not None:
            self.stop()
            self.error = "Taskbar recovery stopped. Windows taskbar restored."
            self.changed.emit()
            return
        api = self.api
        if self.preserve_tray:
            monitor = api.user.MonitorFromWindow(self.window, 2)
            tray, fallback = None, False
            for bar in api.native_bars():
                if api.user.MonitorFromWindow(bar, 2) != monitor:
                    api.unclip(bar)
                    if not api.user.IsWindowVisible(bar):
                        api.user.ShowWindowAsync(bar, 8)
                    continue
                if not api.user.IsWindowVisible(bar):
                    api.user.ShowWindowAsync(bar, 8)
                xaml = self.probe_bounds if self.probe_bar == bar else None
                area = api.tray_area(bar, xaml)
                if not area or xaml is not None:
                    self.schedule_tray_probe(bar)
                if area and api.keep_tray(area):
                    tray = area
                else:
                    api.unclip(bar)
                    fallback = True
            if (tray, fallback) != (self.tray, self.tray_fallback):
                self.tray, self.tray_fallback = tray, fallback
                self.position = None
                QTimer.singleShot(0, self.changed.emit)
            return
        for bar in api.native_bars():
            if api.user.IsWindowVisible(bar):
                api.user.ShowWindowAsync(bar, 0)

    def schedule_tray_probe(self, bar):
        now = time.monotonic()
        if self.probing or (self.probe_bar == bar and now < self.probe_at):
            return
        if self.probe_bar != bar:
            self.probe_bar, self.probe_bounds = bar, None
        self.probe_at = now + 6
        self.probing = True

        def read():
            bounds = self.api.query_xaml_tray(bar)
            try:
                self.tray_ready.emit(bar, bounds)
            except RuntimeError:
                pass

        threading.Thread(target=read, daemon=True).start()

    def receive_tray_probe(self, bar, bounds):
        self.probing = False
        if self.active and self.preserve_tray and self.probe_bar == bar and bounds and bounds != self.probe_bounds:
            self.probe_bounds = bounds
            self.keep_hidden()

    def lane(self, screen, top):
        geometry = screen.geometry()
        area = self.tray
        if not area or area.top != top or self.tray_fallback:
            return geometry.left(), geometry.right() + 1
        info = read_monitor_info(self.api.user, area.monitor)
        if not info or info.device.casefold() != screen.name().casefold():
            return geometry.left(), geometry.right() + 1
        physical = max(1, info.monitor.right - info.monitor.left)
        left, _, right, _ = area.bounds
        def logical(x):
            return geometry.left() + round((x - info.monitor.left) * geometry.width() / physical)
        if area.left_edge:
            return min(geometry.right(), logical(right) + 8), geometry.right() + 1
        return geometry.left(), max(geometry.left() + 1, logical(left) - 8)

    def reserve(self, screen, thickness, top, *, compact=False):
        if not self.active or not self.registered:
            return None
        api = self.api
        monitor = api.user.MonitorFromWindow(self.window, 2)
        info = read_monitor_info(api.user, monitor)
        if info is None:
            return None
        geometry = screen.geometry()
        scale = (info.monitor.bottom - info.monitor.top) / max(1, geometry.height())
        physical_height = round(thickness * scale)
        key = (monitor, physical_height, top, compact)
        if self.position and self.position[0] == key:
            return self.position[1]
        data = self.data()
        data.edge = 1 if top else 3
        data.rect = info.monitor
        if top:
            data.rect.bottom = data.rect.top + physical_height
        else:
            data.rect.top = data.rect.bottom - physical_height
        api.message(2, c.byref(data))
        shared = None
        area = self.tray
        if area and area.top == top and area.monitor == monitor and not self.tray_fallback and not compact:
            _, y1, _, y2 = area.outer
            if top and abs(data.rect.top - y2) <= 2:
                shared = y1
                physical_height = max(1, physical_height - (y2 - y1))
            elif not top and abs(data.rect.bottom - y1) <= 2:
                shared = y2
                physical_height = max(1, physical_height - (y2 - y1))
        if top:
            data.rect.bottom = data.rect.top + physical_height
        else:
            data.rect.top = data.rect.bottom - physical_height
        rect = data.rect
        requested = rect.left, rect.top, rect.right, rect.bottom, data.edge
        if requested != self.reserved_rect:
            if not api.message(3, c.byref(data)):
                return None
            rect = data.rect
            self.reserved_rect = rect.left, rect.top, rect.right, rect.bottom, data.edge
        edge = data.rect.top if top else data.rect.bottom
        if shared is not None:
            edge = shared
        y = geometry.top() + round((edge - info.monitor.top) / scale)
        self.position = key, y
        return y

    def notify(self, message, parameter):
        if not self.active:
            return False
        if message == self.shell_created:
            self.probe_bar = self.probe_bounds = None
            self.probe_at = 0.0
            self.registered = bool(self.api.message(0, c.byref(self.data())))
            self.set_native_state()
            self.keep_hidden()
            self.position = None
            self.reserved_rect = None
            if not self.registered:
                QTimer.singleShot(0, self.reservation_failed)
            else:
                QTimer.singleShot(0, self.changed.emit)
        elif message == self.callback and parameter == 1:  # ABN_POSCHANGED
            self.position = None
            QTimer.singleShot(0, self.changed.emit)
        elif message == 0x0312 and parameter == self.HOTKEY_ID:  # WM_HOTKEY
            QTimer.singleShot(0, self.restore_requested.emit)
            return True
        return False

    def reservation_failed(self):
        if self.active:
            self.stop()
            self.error = "Could not reserve desktop space. Windows taskbar restored."
            self.changed.emit()

    def stop(self):
        if not self.active:
            return
        self.timer.stop()
        self.hotkey_registered = False
        self.api.user.UnregisterHotKey(self.window, self.HOTKEY_ID)
        if self.registered:
            self.api.message(1, c.byref(self.data()))
        self.window = None
        self.position = None
        self.reserved_rect = None
        self.registered = False
        self.tray = None
        self.tray_fallback = False
        self.api.restore(self.original_state)
        self.api.kernel.ResetEvent(self.guard[0])
        self.error = ""
