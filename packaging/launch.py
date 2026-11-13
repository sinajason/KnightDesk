import ctypes
import os
import sys
import traceback
from pathlib import Path

install_dir = Path(__file__).resolve().parent
sys.frozen = True
sys.executable = str(install_dir / "KnightDesk.exe")
os.environ["QT_PLUGIN_PATH"] = str(install_dir / "PySide6" / "plugins")
os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(install_dir / "PySide6" / "plugins" / "platforms")

if sys.argv[1:2] == ["--taskbar-guard"]:
    from taskbar import run_guard
    run_guard(sys.argv[2:])
    raise SystemExit(0)

log_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "KnightDesk"
try:
    log_dir.mkdir(parents=True, exist_ok=True)
    log = (log_dir / "startup.log").open("w", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = log
except OSError:
    log = None

try:
    from app import main
    raise SystemExit(main())
except Exception:
    if log:
        traceback.print_exc(file=log)
    ctypes.windll.user32.MessageBoxW(
        None,
        "KnightDesk could not start." + (f"\n\nSee {log.name}" if log else ""),
        "KnightDesk",
        0x10,
    )
    raise SystemExit(1)
