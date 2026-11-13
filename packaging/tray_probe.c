#define UNICODE
#define _UNICODE
#define COBJMACROS
#include <windows.h>
#include <uiautomation.h>
#include <oleauto.h>
#include <stdio.h>
#include <stdint.h>
#include <wchar.h>

static int is_tray_id(const wchar_t *id) {
    return wcscmp(id, L"SystemTrayFrame") == 0 ||
           wcscmp(id, L"SystemTrayFrameGrid") == 0 ||
           wcscmp(id, L"SystemTrayIcon") == 0 ||
           wcscmp(id, L"NotifyItemIcon") == 0 ||
           wcscmp(id, L"NotificationAreaIcons") == 0 ||
           wcscmp(id, L"ControlCenterButton") == 0 ||
           wcscmp(id, L"NotificationCenterButton") == 0 ||
           wcscmp(id, L"SystemTray.ShowDesktop") == 0;
}

static int tray_rectangle(HWND hwnd, RECT *out) {
    IUIAutomation *uia = NULL;
    IUIAutomationElement *root = NULL;
    IUIAutomationCondition *condition = NULL;
    IUIAutomationCacheRequest *cache = NULL;
    IUIAutomationElementArray *items = NULL;
    RECT outer;
    int found = 0;
    if (!GetWindowRect(hwnd, &outer)) {
        return 0;
    }
    if (FAILED(CoCreateInstance(&CLSID_CUIAutomation, NULL, CLSCTX_INPROC_SERVER,
                                &IID_IUIAutomation, (void **)&uia))) {
        goto done;
    }
    if (FAILED(IUIAutomation_ElementFromHandle(uia, hwnd, &root)) ||
        FAILED(IUIAutomation_CreateTrueCondition(uia, &condition)) ||
        FAILED(IUIAutomation_CreateCacheRequest(uia, &cache)) ||
        FAILED(IUIAutomationCacheRequest_put_TreeScope(cache, TreeScope_Element)) ||
        FAILED(IUIAutomationCacheRequest_put_AutomationElementMode(cache, AutomationElementMode_None))) {
        goto done;
    }
    const PROPERTYID properties[] = {UIA_AutomationIdPropertyId, UIA_ClassNamePropertyId,
                                     UIA_IsOffscreenPropertyId, UIA_BoundingRectanglePropertyId};
    for (size_t i = 0; i < ARRAYSIZE(properties); ++i) {
        if (FAILED(IUIAutomationCacheRequest_AddProperty(cache, properties[i]))) {
            goto done;
        }
    }
    if (FAILED(IUIAutomationElement_FindAllBuildCache(root, TreeScope_Descendants, condition, cache, &items))) {
        goto done;
    }
    int count = 0;
    if (FAILED(IUIAutomationElementArray_get_Length(items, &count))) {
        goto done;
    }
    for (int index = 0; index < count && index < 1200; ++index) {
        IUIAutomationElement *element = NULL;
        if (FAILED(IUIAutomationElementArray_GetElement(items, index, &element))) {
            continue;
        }
        BSTR id = NULL;
        BSTR type = NULL;
        IUIAutomationElement_get_CachedAutomationId(element, &id);
        IUIAutomationElement_get_CachedClassName(element, &type);
        int tray = (id && is_tray_id(id)) ||
                   (type && (wcsncmp(type, L"SystemTray.", 11) == 0 || wcscmp(type, L"TrayNotifyWnd") == 0));
        BOOL offscreen = FALSE;
        if (tray) {
            IUIAutomationElement_get_CachedIsOffscreen(element, &offscreen);
        }
        if (tray && !offscreen) {
            RECT bounds;
            if (SUCCEEDED(IUIAutomationElement_get_CachedBoundingRectangle(element, &bounds)) &&
                bounds.right > bounds.left && bounds.bottom > bounds.top &&
                bounds.right - bounds.left < (outer.right - outer.left) * .65 &&
                bounds.bottom >= outer.top && bounds.top <= outer.bottom) {
                if (found) {
                    UnionRect(out, out, &bounds);
                } else {
                    *out = bounds;
                    found = 1;
                }
            }
        }
        SysFreeString(id);
        SysFreeString(type);
        IUIAutomationElement_Release(element);
    }

done:
    if (items) IUIAutomationElementArray_Release(items);
    if (cache) IUIAutomationCacheRequest_Release(cache);
    if (condition) IUIAutomationCondition_Release(condition);
    if (root) IUIAutomationElement_Release(root);
    if (uia) IUIAutomation_Release(uia);
    return found;
}

int main(int argc, char **argv) {
    if (argc != 2) {
        return 2;
    }
    HWND hwnd = (HWND)(uintptr_t)_strtoui64(argv[1], NULL, 10);
    SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
    if (!IsWindow(hwnd) || FAILED(CoInitializeEx(NULL, COINIT_MULTITHREADED))) {
        return 1;
    }
    RECT bounds;
    int found = tray_rectangle(hwnd, &bounds);
    if (found) {
        printf("%ld %ld %ld %ld\n", bounds.left, bounds.top, bounds.right, bounds.bottom);
    }
    CoUninitialize();
    return found ? 0 : 1;
}
