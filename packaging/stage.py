from pathlib import Path
from shutil import copy2, copytree, ignore_patterns

source = Path("release")
dist = Path("dist")

def copy(name, dest=None):
    target = dist / (dest or name)
    target.parent.mkdir(parents=True, exist_ok=True)
    copy2(source / name, target)

for path in source.iterdir():
    if path.suffix.lower() in {".dll", ".pyd", ".zip", "._pth"}:
        copy(path.name)

for package in ("psutil", "shiboken6"):
    for path in (source / package).iterdir():
        if path.suffix.lower() in {".dll", ".pyd", ".py"}:
            copy(path.relative_to(source))

qt = source / "PySide6"
for path in qt.iterdir():
    if path.suffix == ".py" or path.name in {
        "QtCore.pyd", "QtGui.pyd", "QtWidgets.pyd", "Qt6Core.dll", "Qt6Gui.dll",
        "Qt6Widgets.dll", "Qt6Svg.dll", "pyside6.abi3.dll", "concrt140.dll",
    } or path.name.startswith(("msvcp140", "vcruntime140")) and path.suffix == ".dll":
        copy(path.relative_to(source))

for category, names in {
    "platforms": ["qwindows.dll"],
    "styles": ["qmodernwindowsstyle.dll"],
    "iconengines": ["qsvgicon.dll"],
    "imageformats": ["qgif.dll", "qico.dll", "qjpeg.dll", "qsvg.dll", "qwebp.dll"],
}.items():
    for name in names:
        copy(f"PySide6/plugins/{category}/{name}")

copy("LICENSE.txt", "Licenses/Python.txt")
copy("psutil-7.2.2.dist-info/LICENSE", "Licenses/psutil.txt")
for filename in ("GPL-3.0-only.txt", "LGPL-3.0-only.txt", "Third-party.txt"):
    copy2(filename, dist / "Licenses" / filename)

(dist / "python312._pth").write_bytes(b"python312.zip\r\n.\r\n")
copy2("../knightdesk/app.py", dist / "app.py")
copy2("../knightdesk/design.py", dist / "design.py")
copy2("../knightdesk/theme_art.py", dist / "theme_art.py")
copy2("../knightdesk/windows_shell.py", dist / "windows_shell.py")
copy2("../knightdesk/taskbar.py", dist / "taskbar.py")
copy2("../knightdesk/media_session.py", dist / "media_session.py")
copy("typing_extensions.py")
copytree(source / "winrt", dist / "winrt", dirs_exist_ok=True,
         ignore=ignore_patterns("__pycache__", "__pyinstaller", "*.pyi"))
for metadata in sorted(source.glob("winrt*.dist-info")) + sorted(source.glob("typing_extensions*.dist-info")):
    for license_path in (metadata / "licenses").glob("LICENSE*"):
        copy(license_path.relative_to(source), f"Licenses/{metadata.name.removesuffix('.dist-info')}-{license_path.name}.txt")
copytree(source / "tzdata", dist / "tzdata", dirs_exist_ok=True, ignore=ignore_patterns("__pycache__"))
copy("tzdata-2026.6.dist-info/licenses/LICENSE", "Licenses/tzdata.txt")
copy("tzdata-2026.6.dist-info/licenses/licenses/LICENSE_APACHE", "Licenses/tzdata-Apache.txt")
copy2("launch.py", dist / "launch.py")

files = sorted(path.relative_to(dist) for path in dist.rglob("*") if path.is_file())
dirs = sorted(
    (path.relative_to(dist) for path in dist.rglob("*") if path.is_dir()),
    key=lambda path: (-len(path.parts), str(path)),
)
lines = [f'Delete "$INSTDIR\\{path.as_posix().replace("/", chr(92))}"' for path in files]
lines += [f'RMDir "$INSTDIR\\{path.as_posix().replace("/", chr(92))}"' for path in dirs]
Path("uninstall-files.nsh").write_text("\n".join(lines) + "\n")
