from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QComboBox,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QLabel, QGroupBox, QCheckBox,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from catalog import CatalogBase
from playlist_manager import PlaylistManager, Stream
from scanner import scan_streams
from proxy import ProxyConfig
from lms.models import LmsPlayer


class SearchWorker(QThread):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, catalog: CatalogBase, params: dict):
        super().__init__()
        self._catalog = catalog
        self._params = params

    def run(self):
        try:
            results = self._catalog.search(**self._params)
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))


class ScanWorker(QThread):
    finished = pyqtSignal(list)
    progress = pyqtSignal(int, int)
    station_found = pyqtSignal(dict)

    def __init__(self, stations: list, workers: int, proxies: dict, commercials: bool = False):
        super().__init__()
        self._stations = stations
        self._workers = workers
        self._proxies = proxies
        self._commercials = commercials

    def run(self):
        self.progress.emit(0, len(self._stations))
        results = scan_streams(
            self._stations,
            max_workers=self._workers,
            proxies=self._proxies or None,
            progress_cb=lambda c, t: self.progress.emit(c, t),
            responsive_cb=lambda r: self.station_found.emit(r),
            commercials=self._commercials,
        )
        self.finished.emit(results)


class StationBrowserDialog(QDialog):
    def __init__(self, catalogs: list[CatalogBase], playlist_manager: PlaylistManager,
                 proxy_config: ProxyConfig = None, lms_service=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Browse Radio Stations")
        self.setMinimumSize(700, 500)
        self._catalogs = catalogs
        self._pm = playlist_manager
        self._proxy_config = proxy_config or ProxyConfig()
        self._lms_service = lms_service
        self._results = []
        self._worker = None
        self._scan_worker = None
        self._old_workers = []
        self._search_seq = 0
        self._search_offset = 0
        self._last_params = None
        self._last_results_full = False
        self._build_ui()
        self._update_lms_button()

    def _get_catalog(self) -> CatalogBase:
        idx = self._catalog_combo.currentIndex()
        if 0 <= idx < len(self._catalogs):
            return self._catalogs[idx]
        return self._catalogs[0] if self._catalogs else None

    def _build_ui(self):
        layout = QVBoxLayout(self)

        search_group = QGroupBox("Search")
        search_vbox = QVBoxLayout(search_group)
        search_row = QHBoxLayout()

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Station name...")
        self._search_input.returnPressed.connect(self._search)

        self._tag_combo = QComboBox()
        self._tag_combo.setEditable(True)
        self._tag_combo.setPlaceholderText("Tag (e.g. jazz)")

        self._country_combo = QComboBox()
        self._country_combo.setEditable(True)
        self._country_combo.setPlaceholderText("Country")

        self._catalog_combo = QComboBox()
        for c in self._catalogs:
            self._catalog_combo.addItem(c.name, c.id)

        self._search_btn = QPushButton("Search")
        self._search_btn.clicked.connect(self._search)

        self._scan_cb = QCheckBox("Scan streams")
        self._scan_cb.setChecked(True)
        self._scan_cb.setToolTip("Test each stream before listing (slower but shows only reachable stations)")

        self._commercial_cb = QCheckBox("Check for commercials")
        self._commercial_cb.setChecked(False)
        self._commercial_cb.setToolTip("Detect possible commercial insertion via redirect analysis and audio transition heuristics")

        search_row.addWidget(QLabel("Name:"))
        search_row.addWidget(self._search_input)
        search_row.addWidget(QLabel("Tag:"))
        search_row.addWidget(self._tag_combo)
        search_row.addWidget(QLabel("Country:"))
        search_row.addWidget(self._country_combo)
        search_row.addWidget(QLabel("Catalog:"))
        search_row.addWidget(self._catalog_combo)
        search_row.addWidget(self._search_btn)
        search_vbox.addLayout(search_row)
        search_vbox.addLayout(self._make_checkbox_row())
        layout.addWidget(search_group)

        self._table = QTableWidget()
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels(["Name", "Tags", "Country", "Codec", "Bitrate", "Language", "Commercial"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setSelectionMode(QTableWidget.SingleSelection)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSortingEnabled(True)
        self._table.doubleClicked.connect(self._preview)
        layout.addWidget(self._table)

        btn_layout = QHBoxLayout()
        self._playlist_combo = QComboBox()
        self.refresh_playlist_combo()
        self._add_btn = QPushButton("Add to Playlist")
        self._add_btn.clicked.connect(self._add_to_playlist)
        self._preview_btn = QPushButton("Preview")
        self._preview_btn.clicked.connect(self._preview)
        self._lms_btn = QPushButton("Add to LMS")
        self._lms_btn.setToolTip("Add stream to an LMS player\u2019s playlist")
        self._lms_btn.clicked.connect(self._add_to_lms_playlist)
        self._lms_btn.setEnabled(False)

        btn_layout.addWidget(QLabel("Add to:"))
        btn_layout.addWidget(self._playlist_combo, 1)
        btn_layout.addWidget(self._add_btn)
        btn_layout.addWidget(self._lms_btn)
        btn_layout.addWidget(self._preview_btn)
        btn_layout.addStretch()

        status_layout = QHBoxLayout()
        self._status_label = QLabel("")
        status_layout.addWidget(self._status_label)
        status_layout.addStretch()
        self._load_more_btn = QPushButton("Load more\u2026")
        self._load_more_btn.clicked.connect(self._load_more)
        self._load_more_btn.setVisible(False)
        status_layout.addWidget(self._load_more_btn)
        self._close_btn = QPushButton("Close")
        self._close_btn.clicked.connect(self.accept)
        status_layout.addWidget(self._close_btn)

        layout.addLayout(btn_layout)
        layout.addLayout(status_layout)

    def _make_checkbox_row(self):
        row = QHBoxLayout()
        row.addWidget(self._scan_cb)
        row.addWidget(self._commercial_cb)
        row.addStretch()
        return row

    def _add_table_row(self, station: dict):
        idx = len(self._results)
        self._results.append(station)
        self._table.setSortingEnabled(False)
        row = self._table.rowCount()
        self._table.insertRow(row)
        item0 = QTableWidgetItem()
        item0.setData(Qt.DisplayRole, station.get("name", ""))
        item0.setData(Qt.UserRole, idx)
        self._table.setItem(row, 0, item0)
        self._set_cell(row, 1, station.get("tags", ""))
        self._set_cell(row, 2, station.get("country", ""))
        self._set_cell(row, 3, station.get("codec", ""))
        self._set_cell(row, 4, str(station.get("bitrate", "")), numeric=True)
        self._set_cell(row, 5, station.get("language", ""))
        com = station.get("has_commercial")
        if com is True:
            self._set_cell(row, 6, "Yes")
        elif com is False:
            self._set_cell(row, 6, "No")
        else:
            self._set_cell(row, 6, "\u2014")
        self._table.setSortingEnabled(True)

    def _current_result_index(self) -> int:
        row = self._table.currentRow()
        if row < 0:
            return -1
        item = self._table.item(row, 0)
        if item is None:
            return -1
        return item.data(Qt.UserRole)

    def _set_cell(self, row: int, col: int, text: str, numeric: bool = False):
        item = QTableWidgetItem()
        if numeric and text:
            try:
                item.setData(Qt.DisplayRole, int(text))
            except ValueError:
                item.setData(Qt.DisplayRole, text)
        else:
            item.setData(Qt.DisplayRole, text)
        self._table.setItem(row, col, item)

    def refresh_playlist_combo(self):
        self._playlist_combo.clear()
        for pl in self._pm.playlists:
            self._playlist_combo.addItem(pl.name)

    def _search(self):
        self._search_seq += 1
        seq = self._search_seq
        catalog = self._get_catalog()
        if not catalog:
            self._status_label.setText("No catalog selected")
            return

        name = self._search_input.text().strip()
        tag = self._tag_combo.currentText().strip()
        country = self._country_combo.currentText().strip()
        self._search_offset = 0
        self._last_results_full = False
        params = {"limit": 100, "offset": 0}

        if name:
            params["name"] = name
        if tag:
            params["tag"] = tag
        if country:
            params["country"] = country
        self._last_params = params

        self._search_btn.setEnabled(False)
        self._search_btn.setText("Searching...")
        self._status_label.setText("Searching...")
        self._load_more_btn.setVisible(False)

        self._stash_worker(self._worker)
        self._worker = SearchWorker(catalog, params)
        self._worker.finished.connect(lambda r: self._on_results(r, seq, append=False))
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _load_more(self):
        if not self._last_params:
            return
        catalog = self._get_catalog()
        if not catalog:
            return

        params = dict(self._last_params)
        params["offset"] = self._search_offset
        seq = self._search_seq

        self._load_more_btn.setEnabled(False)
        self._load_more_btn.setText("Loading\u2026")
        self._status_label.setText(f"Loading more (from #{self._search_offset + 1})\u2026")

        self._stash_worker(self._worker)
        self._worker = SearchWorker(catalog, params)
        self._worker.finished.connect(lambda r: self._on_results(r, seq, append=True))
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _stash_worker(self, w):
        if w is None:
            return
        self._old_workers.append(w)
        w.finished.connect(lambda: self._release_worker(w))
        if hasattr(w, "error"):
            w.error.connect(lambda: self._release_worker(w))

    def _release_worker(self, w):
        try:
            self._old_workers.remove(w)
        except ValueError:
            pass

    def _on_results(self, results, seq, append=False):
        if seq != self._search_seq:
            return
        if not append:
            self._results = []
            self._table.setSortingEnabled(False)
            self._table.setRowCount(0)

        self._search_offset += len(results)
        self._last_results_full = len(results) >= 100

        if self._scan_cb.isChecked():
            if not append:
                self._search_btn.setEnabled(False)
                self._search_btn.setText("Scanning...")
            self._status_label.setText(f"Scanning {len(results)} streams...")

            session = self._proxy_config.create_session()
            proxies = session.proxies if session.proxies else None

            self._stash_worker(self._scan_worker)
            self._scan_worker = ScanWorker(
                results,
                workers=self._proxy_config.workers,
                proxies=proxies,
                commercials=self._commercial_cb.isChecked(),
            )
            self._scan_worker.finished.connect(lambda r: self._on_scan_done(r, seq, append=append))
            self._scan_worker.progress.connect(self._on_scan_progress)
            self._scan_worker.station_found.connect(lambda r: self._on_station_found(r, seq))
            self._scan_worker.start()
        else:
            for r in results:
                self._add_table_row(r)
            self._refresh_after_results(append)

    def _on_scan_progress(self, checked: int, total: int):
        self._status_label.setText(f"Scanning {checked}/{total}...")

    def _on_station_found(self, station: dict, seq: int):
        if seq != self._search_seq:
            return
        self._add_table_row(station)

    def _refresh_after_results(self, append: bool = False):
        if not append:
            self._search_btn.setEnabled(True)
            self._search_btn.setText("Search")
        self._load_more_btn.setEnabled(True)
        self._load_more_btn.setText("Load more\u2026")
        self._load_more_btn.setVisible(self._last_results_full)
        total_shown = len(self._results)
        self._status_label.setText(
            f"Found {total_shown} stations"
        )
        self._update_lms_button()

    def _on_scan_done(self, _responsive, seq: int, append: bool = False):
        if seq != self._search_seq:
            return
        self._refresh_after_results(append=append)
        self._status_label.setText(
            f"Found {len(self._results)} responsive"
        )

    def _on_error(self, msg):
        self._search_btn.setEnabled(True)
        self._search_btn.setText("Search")
        self._status_label.setText("Search failed")
        QMessageBox.warning(self, "Search Error", f"Search failed: {msg}")

    def _add_to_playlist(self):
        idx = self._current_result_index()
        if idx < 0:
            QMessageBox.information(self, "Add Station", "Select a station first.")
            return

        pl_idx = self._playlist_combo.currentIndex()
        if pl_idx < 0 or pl_idx >= len(self._pm.playlists):
            QMessageBox.information(self, "Add Station", "Select a target playlist.")
            return

        catalog = self._get_catalog()
        if not catalog:
            return
        r = self._results[idx]
        stream = Stream(**catalog.station_to_stream(r))
        if self._pm.add_stream(pl_idx, stream):
            catalog.click_station(r.get("stationuuid", ""))
            self._status_label.setText(f'Added "{stream.name}" to "{self._pm.playlists[pl_idx].name}"')
        else:
            self._status_label.setText(f'"{stream.name}" already in "{self._pm.playlists[pl_idx].name}"')

    def _add_to_lms_playlist(self):
        idx = self._current_result_index()
        if idx < 0:
            QMessageBox.information(self, "Add to LMS", "Select a station first.")
            return
        if not self._lms_service or not self._lms_service.cli or not self._lms_service.cli.is_connected:
            QMessageBox.information(self, "Add to LMS", "LMS is not connected.\nConfigure it in Settings first.")
            return

        catalog = self._get_catalog()
        if not catalog:
            return
        r = self._results[idx]
        stream_data = catalog.station_to_stream(r)
        url = stream_data.get("url_resolved") or stream_data.get("url", "")
        name = stream_data.get("name", "") or r.get("name", "")

        players = self._lms_service.get_players()
        if not players:
            QMessageBox.information(self, "Add to LMS", "No LMS players found.")
            return

        if len(players) == 1:
            target = players[0]
        else:
            items = [f"{p.name}  ({p.model})" for p in players]
            from PyQt5.QtWidgets import QInputDialog
            selected, ok = QInputDialog.getItem(
                self, "Select LMS Player", "Target player:", items, 0, False,
            )
            if not ok:
                return
            target = players[items.index(selected)]

        self._lms_service.cli.playlist_add_url(target.playerid, url, name)
        self._status_label.setText(f'Sent "{name}" to {target.name}')

    def _update_lms_button(self):
        connected = bool(self._lms_service and self._lms_service.cli and self._lms_service.cli.is_connected)
        self._lms_btn.setEnabled(connected)
        if connected:
            self._lms_btn.setToolTip("Add stream to an LMS player\u2019s playlist")
        else:
            self._lms_btn.setToolTip("LMS not connected \u2014 configure in Settings")

    def _preview(self):
        idx = self._current_result_index()
        if idx < 0:
            return
        catalog = self._get_catalog()
        if not catalog:
            return
        r = self._results[idx]
        stream_data = catalog.station_to_stream(r)
        url = stream_data.get("url_resolved") or stream_data.get("url", "")
        name = stream_data.get("name", "") or r.get("name", "")
        codec = stream_data.get("codec", "") or r.get("codec", "")
        if url:
            preview_cb = getattr(self, "open_preview", None)
            if preview_cb:
                preview_cb(name, url, codec)
