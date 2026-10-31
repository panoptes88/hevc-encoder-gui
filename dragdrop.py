# -*- coding: utf-8 -*-
"""Windows 原生文件拖放支持（ctypes + DragAcceptFiles/WM_DROPFILES）

tkinter 没有内置的文件拖放，参考项目 VideoCaptioner 用的是 Qt 的
dragEnterEvent/dropEvent，那套 API 只存在于 Qt。这里改用 Win32 老式拖放协议：
DragAcceptFiles 注册窗口 + 子类化窗口过程接收 WM_DROPFILES，
再用 DragQueryFileW 取出文件路径。

选择它而不是 windnd/tkinterdnd2 的原因：零第三方依赖，PyInstaller 单文件打包
不需要额外收集 tcl/tk 动态库；代价是仅支持 Windows，且拿不到 drag-over 事件
（因此无法做到「拖拽悬停时高亮」）。
"""

import ctypes
import os
from ctypes import wintypes
from typing import Callable, List, Optional

WM_DROPFILES = 0x0233
GWL_WNDPROC = -4
_DRAG_QUERY_ALL = 0xFFFFFFFF

_WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t,          # LRESULT
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
)


class _Api:
    def __init__(self):
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)

        self.DragAcceptFiles = shell32.DragAcceptFiles
        self.DragAcceptFiles.argtypes = [wintypes.HWND, wintypes.BOOL]
        self.DragAcceptFiles.restype = None

        self.DragFinish = shell32.DragFinish
        self.DragFinish.argtypes = [wintypes.HANDLE]
        self.DragFinish.restype = None

        self.DragQueryFileW = shell32.DragQueryFileW
        self.DragQueryFileW.argtypes = [wintypes.HANDLE, wintypes.UINT,
                                        wintypes.LPWSTR, wintypes.UINT]
        self.DragQueryFileW.restype = wintypes.UINT

        # 32 位 Python 没有 Get/SetWindowLongPtrW，退回 Get/SetWindowLongW
        if hasattr(user32, "SetWindowLongPtrW"):
            self.GetWindowLong = user32.GetWindowLongPtrW
            self.SetWindowLong = user32.SetWindowLongPtrW
        else:
            self.GetWindowLong = user32.GetWindowLongW
            self.SetWindowLong = user32.SetWindowLongW
        self.GetWindowLong.argtypes = [wintypes.HWND, ctypes.c_int]
        self.GetWindowLong.restype = ctypes.c_void_p
        self.SetWindowLong.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
        self.SetWindowLong.restype = ctypes.c_void_p

        self.CallWindowProc = user32.CallWindowProcW
        self.CallWindowProc.argtypes = [ctypes.c_void_p, wintypes.HWND,
                                        wintypes.UINT, wintypes.WPARAM,
                                        wintypes.LPARAM]
        self.CallWindowProc.restype = ctypes.c_ssize_t


_api: Optional[_Api] = None
_api_failed = False
# 子类化后必须持有回调与上级的窗口过程，否则会被 GC 掉导致野指针
_registry: dict = {}


def _query_paths(hdrop) -> List[str]:
    paths: List[str] = []
    count = _api.DragQueryFileW(hdrop, _DRAG_QUERY_ALL, None, 0)
    for i in range(count):
        # 先取所需字符数，再按长度分配缓冲区，超过 MAX_PATH 的长路径也能拿到
        length = _api.DragQueryFileW(hdrop, i, None, 0)
        if length <= 0:
            continue
        buf = ctypes.create_unicode_buffer(length + 1)
        if _api.DragQueryFileW(hdrop, i, buf, length + 1) > 0:
            paths.append(buf.value)
    return paths


def enable_drop(widget, on_drop: Callable[[List[str]], None]) -> bool:
    """让 widget 所在的原生窗口接收拖放。

    on_drop 在 Windows 消息循环里被调用（属于主线程，但处于窗口过程内部），
    所以应当只做入队之类的轻量操作，界面刷新交给 after 轮询。
    """
    global _api, _api_failed
    if os.name != "nt" or _api_failed:
        return False

    hwnd = _native_hwnd(widget)
    if hwnd is None or hwnd in _registry:
        return hwnd in _registry

    try:
        if _api is None:
            _api = _Api()
        _api.DragAcceptFiles(hwnd, True)

        prev = _api.GetWindowLong(hwnd, GWL_WNDPROC)
        if not prev:
            return False

        def wnd_proc(h, msg, wparam, lparam):
            if msg == WM_DROPFILES:
                try:
                    paths = _query_paths(wparam)
                except Exception:
                    paths = []
                finally:
                    try:
                        _api.DragFinish(wparam)
                    except Exception:
                        pass
                if paths:
                    try:
                        on_drop(paths)
                    except Exception:
                        pass
                return 0
            return _api.CallWindowProc(prev, h, msg, wparam, lparam)

        proc = _WNDPROC(wnd_proc)
        if not _api.SetWindowLong(hwnd, GWL_WNDPROC, ctypes.cast(proc, ctypes.c_void_p)):
            return False
        # wnd_proc 闭包引用 prev/proc，两者一起保住
        _registry[hwnd] = (proc, prev, widget)
        return True
    except Exception:
        _api_failed = True
        return False


def _native_hwnd(widget) -> Optional[int]:
    """Tk 在 Windows 下为每个控件建独立 HWND，winfo_id() 即该 HWND。"""
    try:
        widget.update_idletasks()
        hwnd = int(widget.winfo_id())
    except Exception:
        return None
    return hwnd or None
