# KnightDesk 1.8

Run the source with Python 3.12 and `pip install -r requirements.txt` from
the knightdesk folder, then `python app.py`. The existing Windows build.bat
produces a standalone PyInstaller executable.

To reproduce the release installer, place the CPython 3.12.10 Windows x64
embeddable distribution and the contents of these Windows x64 wheels into
`packaging/release`:

- PySide6-Essentials 6.8.3
- shiboken6 6.8.3
- psutil 7.2.2
- tzdata 2026.6 (universal wheel)
- winrt-runtime 4.1.0, winrt-Windows.Media.Control 4!10.0.28000.2957, winrt-Windows.Storage.Streams 4!10.0.28000.2957, their Foundation wheels, and typing-extensions 4.16.0

From the packaging directory, run the following with Zig and NSIS installed.
Use a clean dist directory for each release.

```sh
mkdir -p dist ../out
zig rc resources.rc resources.res
zig cc -target x86_64-windows-gnu -municode -Wl,--subsystem,windows -O2 -s launcher.c resources.res -lshell32 -o dist/KnightDesk.exe
zig cc -target x86_64-windows-gnu -O2 -s tray_probe.c -o dist/KnightDeskTray.exe -lole32 -loleaut32 -luuid
python stage.py
makensis setup.nsi
```

The installer is written to out/KnightDesk-Setup-x64.exe. Quit any running
installed copy before upgrading. Settings live in %APPDATA%\KnightDesk.

Open Settings → Widgets → Apply Graphite Bento layout to turn on the eight
new cards, or enable them individually in the same page. Photo gallery,
Reminders and Quick launch have additional right-click actions. Agenda uses
the due dates from local reminders. Now playing uses Windows media sessions
when a compatible player publishes one.

Settings → Widgets has a global size slider, one slider for each widget,
and controls to apply or exit Graphite Bento. Applying the preset snapshots
the previous theme, visibility, positions, and sizes. Tasks are saved locally
and may be entered inline and completed by clicking the checkbox or pressing
Space with a task selected. Settings → Taskbar has separate sliders for
the dock and app icons.

Taskbar → Keep the Windows system tray preserves Explorer's own notification
area while KnightDesk replaces its app strip. If that area cannot be located,
the native taskbar remains visible. Drag app buttons to reorder them, or use
Move left / Move right from a button's context menu. This order is stored
locally by KnightDesk.
