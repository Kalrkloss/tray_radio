import queue
import os
import sys
import logging
from typing import Optional, Callable

import pystray
from PIL import Image
from pystray import Menu, MenuItem

from icon_generator import create_tray_icon, create_playing_icon, create_stopped_icon
from playlist_manager import PlaylistManager

logger = logging.getLogger(__name__)


class TrayApp:
    def __init__(self, playlist_manager: PlaylistManager):
        self._pm = playlist_manager
        self._icon: Optional[pystray.Icon] = None
        self._current_song: str = ""
        self._current_station: str = ""
        self._is_playing: bool = False
        self._callbacks: dict[str, Callable] = {}
        self.cmd_queue: queue.Queue = queue.Queue()

    def set_callbacks(self, callbacks: dict[str, Callable]):
        self._callbacks = callbacks

    def start(self):
        self._register_aumid_shortcut()
        placeholder = Menu(MenuItem("Loading...", None, enabled=False))
        icon = pystray.Icon(
            "tray_radio",
            icon=create_tray_icon(),
            title="Tray Radio",
            menu=placeholder,
        )
        self._icon = icon

        def _setup(icon_ref):
            self._icon.menu = self._build_menu()
            icon_ref.visible = True

        icon.run_detached(setup=_setup)

    def stop(self):
        if self._icon:
            self._icon.stop()

    def process_commands(self):
        try:
            while True:
                name, args = self.cmd_queue.get_nowait()
                if name in self._callbacks:
                    self._callbacks[name](*args)
        except queue.Empty:
            pass

    def _build_menu(self) -> Menu:
        items = []

        now_playing_label = "Not playing"
        if self._is_playing and self._current_station:
            now_playing_label = self._trunc(self._current_station, 64)
            if self._current_song:
                now_playing_label += " — " + self._trunc(self._current_song, 64)

        items.append(MenuItem(
            now_playing_label,
            lambda icon, item: self.cmd_queue.put(("show_stream_info", [])),
            enabled=self._is_playing,
            default=True,
        ))

        items.append(Menu.SEPARATOR)

        items.append(MenuItem(
            "Play/Pause",
            lambda icon, item: self.cmd_queue.put(("toggle_play_pause", [])),
            enabled=self._is_playing or bool(self._current_station),
        ))

        items.append(MenuItem(
            "Stop",
            lambda icon, item: self.cmd_queue.put(("stop_playback", [])),
            enabled=self._is_playing,
        ))

        items.append(Menu.SEPARATOR)

        playlists_menu = self._build_playlists_menu()
        if playlists_menu:
            items.append(MenuItem("Playlists", playlists_menu))

        items.append(Menu.SEPARATOR)

        items.append(MenuItem(
            "Browse Stations",
            lambda icon, item: self.cmd_queue.put(("show_station_browser", [])),
        ))

        items.append(MenuItem(
            "Edit Playlists",
            lambda icon, item: self.cmd_queue.put(("show_playlist_editor", [])),
        ))

        items.append(MenuItem(
            "Settings",
            lambda icon, item: self.cmd_queue.put(("show_settings", [])),
        ))

        items.append(Menu.SEPARATOR)

        items.append(MenuItem(
            "Quit",
            lambda icon, item: self.cmd_queue.put(("quit", [])),
        ))

        return Menu(*items)

    def _build_playlists_menu(self) -> Optional[Menu]:
        if not self._pm.playlists:
            return None

        pl_items = []
        for pl_idx, pl in enumerate(self._pm.playlists):
            stream_menu = self._build_stream_menu(pl_idx, pl.name, pl.streams)
            pl_items.append(MenuItem(pl.name, stream_menu))

        return Menu(*pl_items)

    @staticmethod
    def _trunc(s, n=64):
        return s if len(s) <= n else s[:n-1] + "…"

    def _make_stream_action(self, stream):
        def action(icon, item):
            self.cmd_queue.put(("play_stream", [stream]))
        return action

    def _make_checked(self, stream):
        def checked(item):
            return stream.uuid == self._pm.current_stream_uuid
        return checked

    def _build_stream_menu(self, pl_idx: int, pl_name: str, streams: list) -> Menu:
        items = []
        for s in streams:
            is_current = s.uuid == self._pm.current_stream_uuid
            label = self._trunc(s.name, 64)
            if is_current and self._is_playing:
                label = "> " + self._trunc(s.name, 62)

            items.append(MenuItem(
                label,
                self._make_stream_action(s),
                checked=self._make_checked(s),
            ))

        if not items:
            items.append(MenuItem("(empty)", None, enabled=False))

        return Menu(*items)

    def set_icon(self, icon: Image.Image):
        self._refresh(icon)

    def update_playing_state(self, is_playing: bool):
        self._is_playing = is_playing
        if not is_playing:
            self._refresh(create_tray_icon())

    def update_station_info(self, station_name: str, song: str = ""):
        self._current_station = station_name
        self._current_song = song
        self._refresh()

    def update_song(self, song: str):
        self._current_song = song
        self._refresh()

    def _refresh(self, icon_img: Optional[Image.Image] = None):
        if not self._icon:
            return
        title_parts = []
        if self._current_station:
            title_parts.append(self._current_station)
        if self._current_song:
            title_parts.append(self._current_song)
        text = " — ".join(title_parts) if title_parts else "Tray Radio"
        if len(text) > 128:
            text = text[:124] + "..."
        self._icon.title = text
        self._icon.menu = self._build_menu()
        if icon_img:
            self._icon.icon = icon_img

    def _register_aumid_shortcut(self):
        import tempfile
        from win32com.propsys import propsys, pscon
        from win32com.shell import shell, shellcon
        import win32com.client, pythoncom

        startup_folder = os.path.join(
            os.environ.get("APPDATA", ""),
            r"Microsoft\Windows\Start Menu\Programs",
        )
        os.makedirs(startup_folder, exist_ok=True)
        lnk_path = os.path.join(startup_folder, "Tray Radio.lnk")
        if os.path.exists(lnk_path):
            return

        ico_path = os.path.join(tempfile.gettempdir(), "tray_radio_icon.ico")
        if not os.path.exists(ico_path):
            create_playing_icon().save(ico_path, format="ICO", sizes=[(16,16),(32,32),(64,64)])

        try:
            wshell = win32com.client.Dispatch("WScript.Shell")
            s = wshell.CreateShortcut(lnk_path)
            s.TargetPath = sys.executable
            s.Arguments = f'"{os.path.abspath("main.py")}"'
            s.IconLocation = f"{ico_path}, 0"
            s.Save()

            ps = propsys.SHGetPropertyStoreFromParsingName(
                lnk_path, None, shellcon.GPS_READWRITE, propsys.IID_IPropertyStore,
            )
            pv = propsys.PROPVARIANTType("TrayRadio", 8)
            ps.SetValue(pscon.PKEY_AppUserModel_ID, pv)
            ps.Commit()
            logger.info("AUMID shortcut created at %s", lnk_path)
        except Exception:
            logger.warning("Could not create AUMID shortcut", exc_info=True)

    def notify(self, title: str, message: str):
        if not self._icon:
            return
        self.dismiss_notification()
        try:
            self._icon.notify(title, message)
        except Exception:
            pass

    def dismiss_notification(self):
        if not self._icon:
            return
        try:
            self._icon._message(1, 16, szInfo="")
        except Exception:
            pass
