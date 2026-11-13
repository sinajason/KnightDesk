Unicode true
!include "MUI2.nsh"
!include "WinVer.nsh"
!include "x64.nsh"
!include "LogicLib.nsh"

Name "KnightDesk"
OutFile "../out/KnightDesk-Setup-x64.exe"
InstallDir "$LOCALAPPDATA\Programs\KnightDesk"
RequestExecutionLevel user
SetCompressor /SOLID lzma

!define MUI_ICON "knightdesk.ico"
!define MUI_UNICON "knightdesk.ico"
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\KnightDesk.exe"
!define UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\KnightDesk"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

!macro RequireClosed
    System::Call 'kernel32::OpenMutexW(i 0x100000, i 0, w "Local\KnightDesk.Installed") p.r0'
    ${If} $0 P<> 0
        System::Call 'kernel32::CloseHandle(p r0)'
        MessageBox MB_OK|MB_ICONEXCLAMATION "Quit KnightDesk from its system tray menu, then try again." /SD IDOK
        Abort
    ${EndIf}
!macroend

Function .onInit
    ${IfNot} ${IsNativeAMD64}
    ${OrIfNot} ${AtLeastWin10}
        MessageBox MB_OK|MB_ICONSTOP "KnightDesk requires Windows 10 or 11 on an x64 PC." /SD IDOK
        Abort
    ${EndIf}
    !insertmacro RequireClosed
FunctionEnd

Function un.onInit
    !insertmacro RequireClosed
FunctionEnd

Section "KnightDesk"
    !insertmacro RequireClosed
    SetShellVarContext current
    SetOutPath "$INSTDIR"
    SetOverwrite on
    File /r "dist\*"
    WriteUninstaller "$INSTDIR\Uninstall.exe"
    CreateShortcut "$SMPROGRAMS\KnightDesk.lnk" "$INSTDIR\KnightDesk.exe"

    SetRegView 64
    WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayName" "KnightDesk"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayVersion" "1.8.0"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayIcon" "$INSTDIR\KnightDesk.exe"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
    WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoModify" 1
    WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoRepair" 1
SectionEnd

Section "Uninstall"
    !insertmacro RequireClosed
    SetShellVarContext current
    Delete "$SMPROGRAMS\KnightDesk.lnk"
    SetRegView 64
    DeleteRegKey HKCU "${UNINSTALL_KEY}"
    ReadRegStr $0 HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "KnightDesk"
    ${If} $0 == '$\"$INSTDIR\KnightDesk.exe$\"'
    ${OrIf} $0 == '$\"$INSTDIR\KnightDesk.exe$\" --background'
        DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "KnightDesk"
    ${EndIf}
    !include "uninstall-files.nsh"
    Delete "$INSTDIR\Uninstall.exe"
    RMDir "$INSTDIR"
SectionEnd
