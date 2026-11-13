#include <windows.h>
#include <wchar.h>
#include <strsafe.h>
#include <shellapi.h>

typedef int (__cdecl *PythonMain)(int, wchar_t **);

static int show_error(const wchar_t *message) {
    MessageBoxW(NULL, message, L"KnightDesk", MB_OK | MB_ICONERROR);
    return 1;
}

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous, PWSTR command, int show) {
    int count = 0;
    wchar_t **args = CommandLineToArgvW(GetCommandLineW(), &count);
    BOOL guard = args && count == 5 && wcscmp(args[1], L"--taskbar-guard") == 0;
    HANDLE single_instance = guard ? NULL : CreateMutexW(NULL, FALSE, L"Local\\KnightDesk.Installed");
    if (!guard && !single_instance) {
        return show_error(L"KnightDesk could not start.");
    }
    if (!guard && GetLastError() == ERROR_ALREADY_EXISTS) {
        if (wcscmp(command, L"--background") != 0) {
            HANDLE activate = OpenEventW(EVENT_MODIFY_STATE, FALSE, L"Local\\KnightDesk.ShowSettings");
            if (activate) {
                SetEvent(activate);
                CloseHandle(activate);
            }
        }
        CloseHandle(single_instance);
        return 0;
    }

    wchar_t executable[32768], runtime[32768], script[32768];
    DWORD length = GetModuleFileNameW(NULL, executable, ARRAYSIZE(executable));
    if (!length || length >= ARRAYSIZE(executable)) {
        return show_error(L"KnightDesk could not find its installation folder.");
    }
    wchar_t *separator = wcsrchr(executable, L'\\');
    if (!separator) {
        return show_error(L"KnightDesk could not find its installation folder.");
    }
    *separator = L'\0';
    if (FAILED(StringCchPrintfW(runtime, ARRAYSIZE(runtime), L"%ls\\python312.dll", executable)) ||
        FAILED(StringCchPrintfW(script, ARRAYSIZE(script), L"%ls\\launch.py", executable))) {
        return show_error(L"The KnightDesk installation path is too long.");
    }

    *separator = L'\\';
    HMODULE library = LoadLibraryExW(runtime, NULL,
        LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_SYSTEM32);
    if (!library) {
        return show_error(L"KnightDesk could not load its bundled runtime. Reinstall KnightDesk to restore its files.");
    }

    PythonMain python_main = (PythonMain)GetProcAddress(library, "Py_Main");
    if (!python_main) {
        return show_error(L"The bundled KnightDesk runtime is invalid. Reinstall KnightDesk.");
    }
    int background = wcscmp(command, L"--background") == 0;
    wchar_t *arguments[] = { executable, script, background ? L"--background" : NULL, NULL };
    wchar_t *guard_arguments[] = { executable, script, NULL, NULL, NULL, NULL, NULL };
    if (guard) {
        for (int index = 1; index < count; ++index) {
            guard_arguments[index + 1] = args[index];
        }
    }
    int result = guard ? python_main(6, guard_arguments) : python_main(2 + background, arguments);
    if (args) {
        LocalFree(args);
    }
    if (single_instance) {
        CloseHandle(single_instance);
    }
    return result;
}
