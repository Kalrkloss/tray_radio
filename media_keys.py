import ctypes
import logging
from ctypes import wintypes
from PyQt5.QtCore import QTimer

logger = logging.getLogger(__name__)

WH_KEYBOARD_LL = 13
HC_ACTION = 0
WM_KEYDOWN = 0x0100

VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3

_KEY_ACTIONS = {
    VK_MEDIA_PLAY_PAUSE: "play_pause",
    VK_MEDIA_STOP: "stop",
    VK_MEDIA_NEXT_TRACK: "next",
    VK_MEDIA_PREV_TRACK: "prev",
}


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ('vkCode', wintypes.DWORD),
        ('scanCode', wintypes.DWORD),
        ('flags', wintypes.DWORD),
        ('time', wintypes.DWORD),
        ('dwExtraInfo', ctypes.c_void_p),
    ]


_HookProc = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)


class MediaKeyHandler:
    def __init__(self, callback):
        self._callback = callback
        self._hook = None
        self._hook_proc = None

    def install(self):
        if self._hook:
            return
        user32 = ctypes.windll.user32
        callback = self._callback

        @_HookProc
        def hook_proc(nCode, wParam, lParam):
            if nCode == HC_ACTION and wParam == WM_KEYDOWN:
                kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                action = _KEY_ACTIONS.get(kb.vkCode)
                if action:
                    logger.debug("Media key: %s", action)
                    # WH_KEYBOARD_LL runs in a system thread, not the main Qt
                    # thread — dispatch to main thread via the event loop.
                    QTimer.singleShot(0, lambda a=action: callback(a))
                    return 1
            return user32.CallNextHookEx(None, nCode, wParam, lParam)

        user32.CallNextHookEx.argtypes = [
            ctypes.c_void_p, ctypes.c_int,
            ctypes.c_void_p, ctypes.c_void_p,
        ]
        self._hook_proc = hook_proc
        self._hook = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL,
            hook_proc,
            0,
            0,
        )
        if self._hook:
            logger.info("Media key hook installed")
        else:
            logger.warning("Failed to install media key hook")

    def unregister(self):
        if self._hook:
            ctypes.windll.user32.UnhookWindowsHookEx(self._hook)
            self._hook = None
            self._hook_proc = None
            logger.info("Media key hook removed")
