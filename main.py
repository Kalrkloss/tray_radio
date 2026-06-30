import sys
import os
import json
import logging

from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import QTimer, Qt

from proxy import ProxyConfig, resolve_proxy_for_url, set_auto_start
from playlist_manager import PlaylistManager, Stream
from catalog import CatalogBase, probe_catalogs
from player import Player
from tray import TrayApp
from icon_generator import fetch_logo, create_playing_icon

from ui.settings_dialog import SettingsDialog
from ui.playlist_editor import PlaylistEditorDialog
from ui.station_browser import StationBrowserDialog
from ui.stream_info import StreamInfoDialog
from ui.add_stream_dialog import AddStreamDialog
from media_keys import MediaKeyHandler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")


CONFIG_DIR = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")),
    "tray_radio",
)
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")


class TrayRadioApp:
    def __init__(self):
        self._proxy_config = self._load_proxy_config()
        self._pm = PlaylistManager(CONFIG_DIR)
        self._player = Player()
        self._catalogs: list[CatalogBase] = []
        self._tray: TrayApp = None
        self._current_station: Stream = None
        self._current_song: str = ""
        self._stream_info_dialog: StreamInfoDialog = None
        self._poll_timer: QTimer = None
        self._cached_proxy_url: Optional[str] = None

    def _load_proxy_config(self) -> ProxyConfig:
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r") as f:
                    data = json.load(f)
                return ProxyConfig.from_dict(data.get("proxy", {}))
        except Exception:
            pass
        return ProxyConfig()

    def _save_proxy_config(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        try:
            existing = {}
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r") as f:
                    existing = json.load(f)
            existing["proxy"] = self._proxy_config.to_dict()
            with open(CONFIG_FILE, "w") as f:
                json.dump(existing, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save proxy config: {e}")

    def _apply_proxy_for_url(self, url: str):
        if self._proxy_config.mode == "system":
            if self._cached_proxy_url is None:
                self._cached_proxy_url = resolve_proxy_for_url(url)
        elif self._proxy_config.mode == "manual":
            self._cached_proxy_url = self._proxy_config.get_proxy_url()
        else:
            self._cached_proxy_url = None
        self._player.set_proxy(self._cached_proxy_url)

    def _resolve_proxy(self):
        if self._proxy_config.mode == "system":
            logger.info("Resolving system proxy...")
            self._cached_proxy_url = resolve_proxy_for_url(
                "https://example.com"
            )
            logger.info(f"Proxy: {self._cached_proxy_url}")
        elif self._proxy_config.mode == "manual":
            self._cached_proxy_url = self._proxy_config.get_proxy_url()
            logger.info(f"Manual proxy: {self._cached_proxy_url}")
        else:
            self._cached_proxy_url = None
            logger.info("Proxy disabled")

    def start(self):
        self._resolve_proxy()
        set_auto_start(self._proxy_config.auto_start)

        session = self._proxy_config.create_session()

        self._catalogs = probe_catalogs(session)
        if not self._catalogs:
            logger.warning("No catalogs available")

        self._tray = TrayApp(self._pm)
        self._tray.set_callbacks({
            "toggle_play_pause": self._toggle_play_pause,
            "stop_playback": self._stop_playback,
            "play_stream": self._play_stream,
            "show_settings": self._show_settings,
            "show_station_browser": self._show_station_browser,
            "show_playlist_editor": self._show_playlist_editor,
            "show_stream_info": self._show_stream_info,
            "add_manual_stream": self._add_manual_stream,
            "quit": self._quit,
        })
        self._tray.start()

        self._player.state_changed.connect(self._on_player_state)
        self._player.error_occurred.connect(self._on_player_error)
        self._player.song_changed.connect(self._on_song_change)
        self._player.station_info_changed.connect(self._on_station_info)

        self._media_keys = MediaKeyHandler(self._media_key_callback)
        QTimer.singleShot(0, self._media_keys.install)

        self._poll_timer = QTimer()
        self._poll_timer.timeout.connect(self._tray.process_commands)
        self._poll_timer.start(100)

        self._check_auto_play()

    def _check_auto_play(self):
        if not self._proxy_config.auto_play:
            return
        stream = self._pm.get_current_stream()
        if stream:
            self._play_stream(stream)

    def _dismiss_after_5(self):
        QTimer.singleShot(5000, self._tray.dismiss_notification)

    def _on_player_state(self, state: str):
        is_playing = state == "playing"
        self._tray.update_playing_state(is_playing)
        if is_playing and self._current_station:
            self._tray.notify(self._current_station.name, "Now playing")
            self._dismiss_after_5()

    def _on_player_error(self, msg: str):
        logger.error(f"Player error: {msg}")
        self._tray.notify("Playback Error", msg)
        self._dismiss_after_5()

    def _on_song_change(self, song: str):
        self._current_song = song
        self._tray.update_song(song)
        if self._current_station:
            self._tray.notify(self._current_station.name, song)
            self._dismiss_after_5()
        if self._stream_info_dialog and self._stream_info_dialog.isVisible():
            self._stream_info_dialog.update_song(song)

    def _on_station_info(self, info: dict):
        name = info.get("icy-name", "") or (self._current_station.name if self._current_station else "")
        if name:
            self._tray.update_station_info(name, self._current_song)

    def _toggle_play_pause(self):
        if self._player.is_playing:
            self._player.pause()
        elif self._current_station:
            self._play_stream(self._current_station)

    def _stop_playback(self):
        self._player.stop()
        self._tray.update_playing_state(False)

    def _set_station_icon(self, favicon_url: str):
        logo = fetch_logo(favicon_url) if favicon_url else None
        if logo:
            logo.thumbnail((64, 64))
            self._tray.set_icon(logo)
        else:
            self._tray.set_icon(create_playing_icon())

    def _play_stream(self, stream: Stream):
        self._current_station = stream
        self._pm.set_current_stream(stream.uuid)
        url = stream.url_resolved or stream.url
        self._apply_proxy_for_url(url)
        self._set_station_icon(stream.favicon)
        self._tray.notify(stream.name, "Connecting…")
        self._player.play(url, codec_hint=stream.codec, output_device=self._proxy_config.output_device)
        self._tray.update_station_info(stream.name, "")
        self._tray.update_playing_state(True)

    def open_preview(self, name: str, url: str, codec: str = ""):
        self._current_station = Stream(uuid="", name=name, url=url, codec=codec)
        self._apply_proxy_for_url(url)
        self._tray.notify(name, "Connecting…")
        self._player.play(url, codec_hint=codec, output_device=self._proxy_config.output_device)
        self._tray.update_station_info(name, "")
        self._tray.update_playing_state(True)

    def _show_settings(self):
        dialog = SettingsDialog(self._proxy_config)
        if dialog.exec_() == SettingsDialog.Accepted:
            self._proxy_config = dialog.proxy_config
            self._save_proxy_config()

    def _show_station_browser(self):
        if not self._catalogs:
            session = self._proxy_config.create_session()
            self._catalogs = probe_catalogs(session)
        if not self._catalogs:
            QMessageBox.warning(None, "Catalog Error", "No station catalogs reachable")
            return
        dialog = StationBrowserDialog(
            self._catalogs, self._pm, proxy_config=self._proxy_config
        )
        dialog.open_preview = self.open_preview
        dialog.refresh_playlist_combo()
        dialog.exec_()

    def _show_playlist_editor(self):
        dialog = PlaylistEditorDialog(self._pm)
        dialog.exec_()

    def _add_manual_stream(self):
        dialog = AddStreamDialog(self._pm)
        if dialog.exec_() == AddStreamDialog.Accepted:
            self._tray._refresh()

    def _media_key_callback(self, action: str):
        if action == "play_pause":
            self._toggle_play_pause()
        elif action == "stop":
            self._stop_playback()
        elif action == "next":
            self._play_next()
        elif action == "prev":
            self._play_previous()

    def _play_next(self):
        stream = self._pm.get_next_stream()
        if stream:
            self._play_stream(stream)

    def _play_previous(self):
        stream = self._pm.get_prev_stream()
        if stream:
            self._play_stream(stream)

    def _show_stream_info(self):
        if self._current_station:
            self._stream_info_dialog = StreamInfoDialog(
                self._current_station, self._current_song
            )
            self._stream_info_dialog.show()

    def _quit(self):
        logger.info("Shutting down...")
        self._media_keys.unregister()
        if self._tray:
            self._tray._notifier.shutdown()
        logger.info("Exiting...")
        os._exit(0)


def main():
    sys.argv[0] = "Tray Radio"
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("TrayRadio")
    except Exception:
        pass
    app = QApplication(sys.argv)
    app.setApplicationName("Tray Radio")
    app.setQuitOnLastWindowClosed(False)

    tray_app = TrayRadioApp()
    tray_app.start()
    logger.info("Tray icon ready")

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
