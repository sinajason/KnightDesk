"""Read Explorer shortcuts and retrieve native, high-resolution shell images."""
import ctypes as c
from ctypes import wintypes as w
from dataclasses import dataclass
import json
from functools import lru_cache
import os
from pathlib import Path
import subprocess
import struct
from uuid import UUID
from xml.etree import ElementTree

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QImageReader


def taskbar_pins():
    # WScript resolves shortcut targets and preserves arguments by launching the link itself.
    script = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$dir = Join-Path $env:APPDATA 'Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar'
$shell = New-Object -ComObject WScript.Shell
$folder = (New-Object -ComObject Shell.Application).NameSpace($dir)
$result = @(Get-ChildItem -LiteralPath $dir -Filter '*.lnk' -ErrorAction SilentlyContinue | ForEach-Object {
    $shortcut = $shell.CreateShortcut($_.FullName)
    $target = [Environment]::ExpandEnvironmentVariables($shortcut.TargetPath)
    $appid = $null
    if ($folder) {
        try { $appid = $folder.ParseName($_.Name).ExtendedProperty('System.AppUserModel.ID') } catch {}
    }
    if ($appid -match '^[^\\/!]+![^\\/!]+$') {
        $target = 'shell:AppsFolder\' + $appid
    } elseif (-not $target -or -not [IO.File]::Exists($target)) {
        $target = $_.FullName
    }
    @{ name = $_.BaseName; path = $target; shortcut = $_.FullName; icon = $shortcut.IconLocation }
})
# Explorer stores some packaged pins as IDs instead of .lnk files.
try {
    $band = Get-ItemProperty -LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Taskband'
    $record = @('Favorites', 'FavoritesResolve') | ForEach-Object {
        if ($band.$_ -is [byte[]] -and $band.$_.Length -gt 1) {
            [Text.Encoding]::Unicode.GetString($band.$_)
            [Text.Encoding]::Unicode.GetString($band.$_, 1, $band.$_.Length - 1)
        }
    }
    foreach ($app in (Get-StartApps -ErrorAction Stop)) {
        if ($app.AppID -notmatch '^[^\\/!]+![^\\/!]+$') { continue }
        $pattern = '(?i)(?<![\p{L}\p{N}_.!\-])' + [regex]::Escape($app.AppID) + '(?![\p{L}\p{N}_.!\-])'
        if ($record | Where-Object { $_ -match $pattern }) {
            $result += @{ name = $app.Name; path = 'shell:AppsFolder\' + $app.AppID }
        }
    }
} catch {}
ConvertTo-Json -InputObject $result -Compress
"""
    exe = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    try:
        raw = subprocess.check_output(
            [str(exe), "-NoProfile", "-NonInteractive", "-Command", script],
            timeout=12, creationflags=0x08000000, encoding="utf-8-sig",
        )
        return json.loads(raw)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


class BitmapHeader(c.Structure):
    _fields_ = [("size", w.DWORD), ("width", w.LONG), ("height", w.LONG),
                ("planes", w.WORD), ("bits", w.WORD), ("compression", w.DWORD),
                ("image_size", w.DWORD), ("x", w.LONG), ("y", w.LONG),
                ("used", w.DWORD), ("important", w.DWORD)]


class Bitmap(c.Structure):
    _fields_ = [("kind", w.LONG), ("width", w.LONG), ("height", w.LONG),
                ("stride", w.LONG), ("planes", w.WORD), ("bits", w.WORD),
                ("data", c.c_void_p)]


@lru_cache(maxsize=192)
def shell_icon(path, pixels):
    ole = c.windll.ole32
    ole.CoInitializeEx.argtypes = [c.c_void_p, w.DWORD]
    ole.CoInitializeEx.restype = c.c_long
    result = ole.CoInitializeEx(None, 2)
    if result < 0 and result != -2147417850:  # RPC_E_CHANGED_MODE: COM is already initialized.
        return QImage()
    try:
        return _read_shell_icon(path, pixels)
    finally:
        if result >= 0:
            ole.CoUninitialize()


def _read_shell_icon(path, pixels):
    shell, gdi = c.windll.shell32, c.windll.gdi32
    create = shell.SHCreateItemFromParsingName
    create.argtypes = [w.LPCWSTR, c.c_void_p, c.c_void_p, c.POINTER(c.c_void_p)]
    create.restype = c.c_long
    iid = (c.c_ubyte * 16).from_buffer_copy(UUID("bcc18b79-ba16-442f-80c4-8a59c30c463b").bytes_le)
    factory = c.c_void_p()
    if create(path, None, iid, c.byref(factory)) < 0 or not factory:
        if not path.casefold().startswith("shell:appsfolder\\"):
            return QImage()
        namespace = "::{4234d49b-0245-4df3-b780-3893943456e1}\\" + path.split("\\", 1)[1]
        if create(namespace, None, iid, c.byref(factory)) < 0 or not factory:
            return QImage()
    methods = c.cast(factory, c.POINTER(c.POINTER(c.c_void_p))).contents
    release = c.WINFUNCTYPE(w.ULONG, c.c_void_p)(methods[2])
    get_image = c.WINFUNCTYPE(c.c_long, c.c_void_p, w.SIZE, c.c_int, c.POINTER(w.HBITMAP))(methods[3])
    bitmap = w.HBITMAP()
    try:
        if get_image(factory, w.SIZE(pixels, pixels), 0x5, c.byref(bitmap)) < 0 or not bitmap:
            return QImage()
        create_dc = gdi.CreateCompatibleDC
        create_dc.argtypes, create_dc.restype = [w.HDC], w.HDC
        delete_dc = gdi.DeleteDC
        delete_dc.argtypes = [w.HDC]
        get_bits = gdi.GetDIBits
        get_bits.argtypes = [w.HDC, w.HBITMAP, w.UINT, w.UINT, c.c_void_p, c.c_void_p, w.UINT]
        dc = create_dc(None)
        if not dc:
            return QImage()
        try:
            get_object = gdi.GetObjectW
            get_object.argtypes = [w.HGDIOBJ, c.c_int, c.c_void_p]
            details = Bitmap()
            if not get_object(bitmap, c.sizeof(details), c.byref(details)):
                return QImage()
            width, height = details.width, abs(details.height)
            if not (0 < width <= 512 and 0 < height <= 512):
                return QImage()
            header = BitmapHeader(size=c.sizeof(BitmapHeader), width=width, height=-height,
                                  planes=1, bits=32)
            buffer = bytearray(width * height * 4)
            data = (c.c_ubyte * len(buffer)).from_buffer(buffer)
            if get_bits(dc, bitmap, 0, height, data, c.byref(header), 0) != height:
                return QImage()
            if not any(buffer[3::4]):
                return QImage()
            return QImage(buffer, width, height, width * 4, QImage.Format.Format_ARGB32_Premultiplied).copy()
        finally:
            delete_dc(dc)
    finally:
        if bitmap:
            gdi.DeleteObject.argtypes = [w.HGDIOBJ]
            gdi.DeleteObject(bitmap)
        release(factory)


@lru_cache(maxsize=64)
def installed_package_paths(family):
    kernel = c.windll.kernel32
    names_fn = kernel.GetPackagesByPackageFamily
    names_fn.argtypes = [w.LPCWSTR, c.POINTER(w.UINT), c.POINTER(w.LPWSTR), c.POINTER(w.UINT), w.LPWSTR]
    names_fn.restype = w.LONG
    count, length = w.UINT(), w.UINT()
    if names_fn(family, c.byref(count), None, c.byref(length), None) != 122:
        return ()
    if not 0 < count.value <= 128 or not 0 < length.value <= 65536:
        return ()
    names = (w.LPWSTR * count.value)()
    name_buffer = c.create_unicode_buffer(length.value)
    if names_fn(family, c.byref(count), names, c.byref(length), name_buffer) != 0:
        return ()

    path_fn = kernel.GetPackagePathByFullName
    path_fn.argtypes = [w.LPCWSTR, c.POINTER(w.UINT), w.LPWSTR]
    path_fn.restype = w.LONG
    paths = []
    for full_name in names:
        length = w.UINT()
        if path_fn(full_name, c.byref(length), None) == 122 and 0 < length.value <= 32768:
            buffer = c.create_unicode_buffer(length.value)
            if path_fn(full_name, c.byref(length), buffer) == 0:
                paths.append(Path(buffer.value))
    return tuple(paths)


def package_logo_paths(root, application_id):
    try:
        manifest = root / "AppxManifest.xml"
        if manifest.stat().st_size > 2 * 1024 * 1024:
            return ()
        xml = ElementTree.parse(manifest)
    except (OSError, ElementTree.ParseError):
        return ()
    app = next((entry for entry in xml.findall("./{*}Applications/{*}Application")
                if entry.get("Id") == application_id), None)
    if app is None:
        return ()
    visuals = app.find("./{*}VisualElements")
    if visuals is None:
        return ()
    variants = []
    for name in ("Square44x44Logo", "Square30x30Logo", "SmallLogo", "Square150x150Logo", "Logo"):
        value = visuals.get(name)
        if not value or value.lower().startswith("ms-resource:"):
            continue
        path = root / value.replace("\\", "/")
        if path.is_absolute() and not path.is_relative_to(root):
            continue
        if ".." in path.parts:
            continue
        try:
            variants.extend(candidate for candidate in path.parent.glob(path.stem + ".*")
                            if candidate.suffix.lower() in {".png", ".webp", ".ico"}
                            and candidate.is_file())
        except OSError:
            continue
    return tuple(dict.fromkeys(variants))


def app_logo_variant(paths, pixels):
    """Prefer the closest full-color, unplated asset at or above the target."""
    scored = []
    for path in paths:
        name = path.stem.casefold()
        if "contrast-" in name and "contrast-standard" not in name:
            continue
        if "altform-lightunplated" in name:  # Designed for a light surface.
            continue
        reader = QImageReader(str(path))
        size = reader.size()
        edge = min(size.width(), size.height())
        if edge <= 0 or max(size.width(), size.height()) > 2048:
            continue
        unplated = "altform-unplated" in name or "altform-darkunplated" in name
        rank = (edge < pixels, not unplated, abs(edge - pixels), "targetsize-" not in name)
        scored.append((rank, path))
    for _, path in sorted(scored):
        image = QImageReader(str(path)).read()
        if not image.isNull():
            return image
    return QImage()


@lru_cache(maxsize=96)
def packaged_icon(path, pixels):
    prefix, separator, app_id = path.rpartition("\\")
    family, bang, application = app_id.partition("!")
    if not (separator and bang and prefix.casefold() == "shell:appsfolder" and family and application):
        return QImage()
    paths = []
    for root in installed_package_paths(family):
        paths.extend(package_logo_paths(root, application))
    return app_logo_variant(paths, pixels)


def packaged_path(pid):
    """Use the process's registered application identity when it has one."""
    kernel = c.windll.kernel32
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    kernel.OpenProcess.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return None
    try:
        get_id = kernel.GetApplicationUserModelId
        get_id.argtypes = [w.HANDLE, c.POINTER(w.UINT), w.LPWSTR]
        length = w.UINT(512)
        appid = c.create_unicode_buffer(length.value)
        if get_id(handle, c.byref(length), appid) == 0 and "!" in appid.value:
            return "shell:AppsFolder\\" + appid.value
        return None
    finally:
        kernel.CloseHandle(handle)


def hosted_app_path(hwnd):
    """Find the packaged app hosted by an ApplicationFrameHost window."""
    user = c.windll.user32
    callback = c.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    user.EnumChildWindows.argtypes = [w.HWND, callback, w.LPARAM]
    result = None

    @callback
    def check(child, _):
        nonlocal result
        pid = w.DWORD()
        user.GetWindowThreadProcessId(child, c.byref(pid))
        result = packaged_path(pid.value)
        return not result

    user.EnumChildWindows(hwnd, check, 0)
    return result


@dataclass(frozen=True)
class IconFrame:
    width: int
    height: int
    depth: int
    length: int
    location: int


def icon_frames(directory, *, group=False):
    """Decode an ICO directory or a PE RT_GROUP_ICON table."""
    if len(directory) < 6:
        return []
    reserved, kind, count = struct.unpack_from("<HHH", directory)
    entry_size = 14 if group else 16
    if reserved or kind != 1 or not 0 < count <= 512 or len(directory) < 6 + entry_size * count:
        return []
    frames = []
    for offset in range(6, 6 + entry_size * count, entry_size):
        width, height, _, _, _, depth, length, location = struct.unpack_from(
            "<BBBBHHI" + ("H" if group else "I"), directory, offset)
        if length and (group or location + length <= len(directory)):
            frames.append(IconFrame(width or 256, height or 256, depth, length, location))
    return frames


def choose_frame(frames, pixels):
    def rank(frame):
        edge = min(frame.width, frame.height)
        return edge < pixels, frame.depth < 24 and frame.depth != 0, abs(edge - pixels), -frame.depth
    return min(frames, key=rank, default=None)


class ResourceFile:
    """Read resources from a PE file without executing it."""
    def __init__(self, path):
        self.kernel = kernel = c.windll.kernel32
        kernel.LoadLibraryExW.argtypes = [w.LPCWSTR, w.HANDLE, w.DWORD]
        kernel.LoadLibraryExW.restype = w.HMODULE
        kernel.FreeLibrary.argtypes = [w.HMODULE]
        kernel.FindResourceW.argtypes = [w.HMODULE, c.c_void_p, c.c_void_p]
        kernel.FindResourceW.restype = w.HRSRC
        kernel.SizeofResource.argtypes = [w.HMODULE, w.HRSRC]
        kernel.SizeofResource.restype = w.DWORD
        kernel.LoadResource.argtypes = [w.HMODULE, w.HRSRC]
        kernel.LoadResource.restype = w.HGLOBAL
        kernel.LockResource.argtypes = [w.HGLOBAL]
        kernel.LockResource.restype = c.c_void_p
        self.module = kernel.LoadLibraryExW(path, None, 0x22)  # Data file + image resources.

    def __enter__(self):
        return self

    def __exit__(self, *_):
        if self.module:
            self.kernel.FreeLibrary(self.module)

    def name_at(self, kind, index):
        callback = c.WINFUNCTYPE(w.BOOL, w.HMODULE, c.c_void_p, c.c_void_p, w.LPARAM)
        enum = self.kernel.EnumResourceNamesW
        enum.argtypes = [w.HMODULE, c.c_void_p, callback, w.LPARAM]
        names = []

        @callback
        def collect(_, __, name, ___):
            names.append(name if name <= 0xFFFF else c.wstring_at(name))
            return len(names) <= index

        enum(self.module, kind, collect, 0)
        return names[index] if index < len(names) else None

    def read(self, kind, name):
        label = c.c_wchar_p(name) if isinstance(name, str) else None
        name_pointer = c.cast(label, c.c_void_p) if label else name
        resource = self.kernel.FindResourceW(self.module, name_pointer, kind)
        if not resource:
            return b""
        size = self.kernel.SizeofResource(self.module, resource)
        if not 0 < size <= 8 * 1024 * 1024:
            return b""
        data = self.kernel.LoadResource(self.module, resource)
        bits = self.kernel.LockResource(data) if data else None
        return c.string_at(bits, size) if bits else b""


@lru_cache(maxsize=96)
def resource_icon(path, pixels, index=0):
    """Return the best available original icon frame, at its stored size."""
    path = os.path.abspath(path)
    extension = Path(path).suffix.lower()
    if extension == ".ico":
        try:
            with open(path, "rb") as file:
                directory = file.read(8 * 1024 * 1024 + 1)
            if len(directory) > 8 * 1024 * 1024:
                return QImage()
        except OSError:
            return QImage()
        frame = choose_frame(icon_frames(directory), pixels)
        bits = directory[frame.location:frame.location + frame.length] if frame else b""
    elif extension in {".exe", ".dll", ".icl", ".cpl"}:
        with ResourceFile(path) as source:
            if not source.module:
                return QImage()
            name = -index if index < 0 else source.name_at(14, index)
            if name is None:
                return QImage()
            frame = choose_frame(icon_frames(source.read(14, name), group=True), pixels)
            bits = source.read(3, frame.location) if frame else b""
    else:
        return QImage()
    if not frame or not bits:
        return QImage()
    if bits.startswith(b"\x89PNG\r\n\x1a\n"):
        return QImage.fromData(bits, "PNG")
    user = c.windll.user32
    create = user.CreateIconFromResourceEx
    create.argtypes = [c.c_void_p, w.DWORD, w.BOOL, w.DWORD, c.c_int, c.c_int, w.UINT]
    create.restype = w.HICON
    user.DestroyIcon.argtypes = [w.HICON]
    buffer = c.create_string_buffer(bits)
    icon = create(buffer, len(bits), True, 0x00030000, frame.width, frame.height, 0)
    if not icon:
        return QImage()
    try:
        return _render_hicon(icon, frame.width, frame.height)
    finally:
        user.DestroyIcon(icon)


class IconInfo(c.Structure):
    _fields_ = [("icon", w.BOOL), ("x", w.DWORD), ("y", w.DWORD),
                ("mask", w.HBITMAP), ("color", w.HBITMAP)]


def native_icon_size(icon):
    user, gdi = c.windll.user32, c.windll.gdi32
    user.GetIconInfo.argtypes = [w.HICON, c.POINTER(IconInfo)]
    gdi.GetObjectW.argtypes = [w.HGDIOBJ, c.c_int, c.c_void_p]
    gdi.DeleteObject.argtypes = [w.HGDIOBJ]
    info = IconInfo()
    if not user.GetIconInfo(icon, c.byref(info)):
        return None
    try:
        bitmap = Bitmap()
        if gdi.GetObjectW(info.color or info.mask, c.sizeof(bitmap), c.byref(bitmap)):
            width = bitmap.width
            height = abs(bitmap.height) // (1 if info.color else 2)
            if 0 < width <= 512 and 0 < height <= 512:
                return width, height
        return None
    finally:
        for bitmap in (info.mask, info.color):
            if bitmap:
                gdi.DeleteObject(bitmap)


def _render_hicon(icon, width, height):
    gdi, user = c.windll.gdi32, c.windll.user32
    gdi.CreateCompatibleDC.argtypes, gdi.CreateCompatibleDC.restype = [w.HDC], w.HDC
    gdi.CreateDIBSection.argtypes = [w.HDC, c.c_void_p, w.UINT, c.POINTER(c.c_void_p), w.HANDLE, w.DWORD]
    gdi.CreateDIBSection.restype = w.HBITMAP
    gdi.SelectObject.argtypes, gdi.SelectObject.restype = [w.HDC, w.HGDIOBJ], w.HGDIOBJ
    gdi.DeleteObject.argtypes = [w.HGDIOBJ]
    gdi.DeleteDC.argtypes = [w.HDC]
    user.DrawIconEx.argtypes = [w.HDC, c.c_int, c.c_int, w.HICON, c.c_int, c.c_int, w.UINT, w.HBRUSH, w.UINT]
    dc = gdi.CreateCompatibleDC(None)
    if not dc:
        return QImage()
    bitmap = None
    previous = None
    try:
        bits = c.c_void_p()
        header = BitmapHeader(size=c.sizeof(BitmapHeader), width=width, height=-height, planes=1, bits=32)
        bitmap = gdi.CreateDIBSection(dc, c.byref(header), 0, c.byref(bits), None, 0)
        if not bitmap or not bits:
            return QImage()
        previous = gdi.SelectObject(dc, bitmap)
        if not previous:
            return QImage()
        length = width * height * 4
        c.memset(bits, 0, length)
        if not user.DrawIconEx(dc, 0, 0, icon, width, height, 0, None, 3):
            return QImage()
        gdi.GdiFlush()
        dark = bytearray(c.string_at(bits, length))
        c.memset(bits, 255, length)
        if not user.DrawIconEx(dc, 0, 0, icon, width, height, 0, None, 3):
            return QImage()
        gdi.GdiFlush()
        light = c.string_at(bits, length)
        for offset in range(0, length, 4):
            alpha = 255 - max(0, *(light[offset + i] - dark[offset + i] for i in range(3)))
            dark[offset + 3] = max(alpha, dark[offset], dark[offset + 1], dark[offset + 2])
        return QImage(dark, width, height, width * 4, QImage.Format.Format_ARGB32_Premultiplied).copy()
    finally:
        if previous:
            gdi.SelectObject(dc, previous)
        if bitmap:
            gdi.DeleteObject(bitmap)
        gdi.DeleteDC(dc)


def window_icon(hwnd):
    """Use a live window's icon when there is no readable executable icon."""
    user = c.windll.user32
    user.GetClassLongPtrW.argtypes = [w.HWND, c.c_int]
    user.GetClassLongPtrW.restype = c.c_size_t
    user.SendMessageTimeoutW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM, w.UINT,
                                         w.UINT, c.POINTER(c.c_size_t)]
    user.SendMessageTimeoutW.restype = w.LPARAM
    result = c.c_size_t()
    user.SendMessageTimeoutW(hwnd, 0x7F, 1, 0, 2, 50, c.byref(result))
    icon = result.value or user.GetClassLongPtrW(hwnd, -14)
    size = native_icon_size(icon) if icon else None
    return _render_hicon(icon, *size) if size else QImage()
class PropertyKey(c.Structure):
    _fields_ = [("format", c.c_ubyte * 16), ("id", w.DWORD)]


class PropertyValue(c.Structure):
    # The supported installer is x64. PROPVARIANT has a 16-byte payload on x64.
    _fields_ = [("type", w.WORD), ("reserved", w.WORD * 3), ("pointer", c.c_void_p),
                ("extra", c.c_void_p)]


def window_identity(hwnd):
    shell, ole = c.windll.shell32, c.windll.ole32
    ole.CoInitializeEx.argtypes = [c.c_void_p, w.DWORD]
    ole.CoInitializeEx.restype = w.LONG
    initialized = ole.CoInitializeEx(None, 2)
    if initialized < 0 and initialized != -2147417850:
        return "", ""
    try:
        get_store = shell.SHGetPropertyStoreForWindow
        get_store.argtypes = [w.HWND, c.c_void_p, c.POINTER(c.c_void_p)]
        get_store.restype = w.LONG
        iid = (c.c_ubyte * 16).from_buffer_copy(UUID("886d8eeb-8cf2-4446-8d02-cdba1dbdcf99").bytes_le)
        store = c.c_void_p()
        if get_store(hwnd, iid, c.byref(store)) < 0 or not store:
            return "", ""
        methods = c.cast(store, c.POINTER(c.POINTER(c.c_void_p))).contents
        release = c.WINFUNCTYPE(w.ULONG, c.c_void_p)(methods[2])
        get_value = c.WINFUNCTYPE(w.LONG, c.c_void_p, c.POINTER(PropertyKey), c.POINTER(PropertyValue))(methods[5])
        ole.PropVariantClear.argtypes = [c.POINTER(PropertyValue)]
        key_format = (c.c_ubyte * 16).from_buffer_copy(UUID("9f4c2855-9f79-4b39-a8d0-e1d42de1d5f3").bytes_le)
        values = []
        try:
            for number in (5, 3):  # AppUserModel.ID and AppUserModel.RelaunchIconResource.
                key = PropertyKey(key_format, number)
                value = PropertyValue()
                try:
                    found = get_value(store, c.byref(key), c.byref(value)) >= 0
                    values.append(c.wstring_at(value.pointer) if found and value.type == 31 and value.pointer else "")
                finally:
                    ole.PropVariantClear(c.byref(value))
            return tuple(values)
        finally:
            release(store)
    finally:
        if initialized >= 0:
            ole.CoUninitialize()


def prepare_dock_image(image, pixels):
    """Resize once from original pixels with alpha-aware area averaging."""
    if image.isNull():
        return image
    width, height = image.width(), image.height()
    extent = max(width, height)
    if extent <= pixels:
        return image
    # Qt's native area filter is applied to premultiplied channels, so the
    # transparent colors around line art do not create light or dark fringes.
    image = image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    return image.scaled(pixels, pixels, Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation)


