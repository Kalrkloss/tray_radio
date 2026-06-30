from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QComboBox,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QLabel, QGroupBox, QProgressDialog,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from catalog import RadioBrowserClient
from playlist_manager import PlaylistManager, Stream
from scanner import scan_streams
from proxy import ProxyConfig


class SearchWorker(QThread):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, client: RadioBrowserClient, params: dict):
        super().__init__()
        self._client = client
        self._params = params

    def run(self):
        try:
            results = self._client.search_stations(**self._params)
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))


class ScanWorker(QThread):
    finished = pyqtSignal(list)
    progress = pyqtSignal(int, int)
    station_found = pyqtSignal(dict)

    def __init__(self, stations: list, workers: int, proxies: dict):
        super().__init__()
        self._stations = stations
        self._workers = workers
        self._proxies = proxies

    def run(self):
        self.progress.emit(0, len(self._stations))
        results = scan_streams(
            self._stations,
            max_workers=self._workers,
            proxies=self._proxies or None,
            progress_cb=lambda c, t: self.progress.emit(c, t),
            responsive_cb=lambda r: self.station_found.emit(r),
        )
        self.finished.emit(results)


class StationBrowserDialog(QDialog):
    def __init__(self, client: RadioBrowserClient, playlist_manager: PlaylistManager,
                 proxy_config: ProxyConfig = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Browse Radio Stations")
        self.setMinimumSize(700, 500)
        self._client = client
        self._pm = playlist_manager
        self._proxy_config = proxy_config or ProxyConfig()
        self._results = []
        self._worker = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        search_group = QGroupBox("Search")
        search_layout = QHBoxLayout(search_group)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Station name...")
        self._search_input.returnPressed.connect(self._search)

        self._tag_combo = QComboBox()
        self._tag_combo.setEditable(True)
        self._tag_combo.setPlaceholderText("Tag (e.g. jazz)")

        self._country_combo = QComboBox()
        self._country_combo.setEditable(True)
        self._country_combo.setPlaceholderText("Country")

        self._search_btn = QPushButton("Search")
        self._search_btn.clicked.connect(self._search)

        search_layout.addWidget(QLabel("Name:"))
        search_layout.addWidget(self._search_input)
        search_layout.addWidget(QLabel("Tag:"))
        search_layout.addWidget(self._tag_combo)
        search_layout.addWidget(QLabel("Country:"))
        search_layout.addWidget(self._country_combo)
        search_layout.addWidget(self._search_btn)
        layout.addWidget(search_group)

        self._table = QTableWidget()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels(["Name", "Tags", "Country", "Codec", "Bitrate", "Language"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setSelectionMode(QTableWidget.SingleSelection)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.doubleClicked.connect(self._preview)
        layout.addWidget(self._table)

        btn_layout = QHBoxLayout()
        self._playlist_combo = QComboBox()
        self._refresh_playlist_combo()
        self._add_btn = QPushButton("Add to Playlist")
        self._add_btn.clicked.connect(self._add_to_playlist)
        self._preview_btn = QPushButton("Preview")
        self._preview_btn.clicked.connect(self._preview)

        btn_layout.addWidget(QLabel("Add to:"))
        btn_layout.addWidget(self._playlist_combo, 1)
        btn_layout.addWidget(self._add_btn)
        btn_layout.addWidget(self._preview_btn)
        btn_layout.addStretch()

        status_layout = QHBoxLayout()
        self._status_label = QLabel("")
        status_layout.addWidget(self._status_label)
        status_layout.addStretch()
        self._close_btn = QPushButton("Close")
        self._close_btn.clicked.connect(self.accept)
        status_layout.addWidget(self._close_btn)

        layout.addLayout(btn_layout)
        layout.addLayout(status_layout)

    def _refresh_playlist_combo(self):
        self._playlist_combo.clear()
        for pl in self._pm.playlists:
            self._playlist_combo.addItem(pl.name)

    def _search(self):
        name = self._search_input.text().strip()
        tag = self._tag_combo.currentText().strip()
        country = self._country_combo.currentText().strip()
        params = {"limit": 100}

        if name:
            params["name"] = name
        if tag:
            params["tag"] = tag
        if country:
            params["country"] = country

        self._search_btn.setEnabled(False)
        self._search_btn.setText("Searching...")
        self._status_label.setText("Searching...")

        self._worker = SearchWorker(self._client, params)
        self._worker.finished.connect(self._on_results)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_results(self, results):
        self._results = []
        self._status_label.setText(f"Scanning {len(results)} streams...")
        self._search_btn.setEnabled(False)
        self._search_btn.setText("Scanning...")
        self._table.setRowCount(0)

        session = self._proxy_config.create_session()
        proxies = session.proxies if session.proxies else None

        self._scan_worker = ScanWorker(
            results,
            workers=self._proxy_config.workers,
            proxies=proxies,
        )
        self._scan_worker.finished.connect(self._on_scan_done)
        self._scan_worker.progress.connect(self._on_scan_progress)
        self._scan_worker.station_found.connect(self._on_station_found)
        self._scan_worker.start()

    def _on_scan_progress(self, checked: int, total: int):
        self._status_label.setText(f"Scanning {checked}/{total}...")

    def _on_station_found(self, station: dict):
        self._results.append(station)
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setItem(row, 0, QTableWidgetItem(station.get("name", "")))
        self._table.setItem(row, 1, QTableWidgetItem(station.get("tags", "")))
        self._table.setItem(row, 2, QTableWidgetItem(station.get("country", "")))
        self._table.setItem(row, 3, QTableWidgetItem(station.get("codec", "")))
        self._table.setItem(row, 4, QTableWidgetItem(str(station.get("bitrate", ""))))
        self._table.setItem(row, 5, QTableWidgetItem(station.get("language", "")))

    def _on_scan_done(self, _responsive):
        self._search_btn.setEnabled(True)
        self._search_btn.setText("Search")
        self._status_label.setText(
            f"Found {len(self._results)} responsive"
        )

    def _on_error(self, msg):
        self._search_btn.setEnabled(True)
        self._search_btn.setText("Search")
        self._status_label.setText("Search failed")
        QMessageBox.warning(self, "Search Error", f"Search failed: {msg}")

    def _add_to_playlist(self):
        row = self._table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Add Station", "Select a station first.")
            return

        pl_idx = self._playlist_combo.currentIndex()
        if pl_idx < 0 or pl_idx >= len(self._pm.playlists):
            QMessageBox.information(self, "Add Station", "Select a target playlist.")
            return

        r = self._results[row]
        stream = Stream(**RadioBrowserClient.station_to_stream(r))
        self._pm.add_stream(pl_idx, stream)
        self._client.click_station(r.get("stationuuid", ""))
        self._status_label.setText(f'Added "{stream.name}" to "{self._pm.playlists[pl_idx].name}"')

    def _preview(self):
        row = self._table.currentRow()
        if row < 0:
            return
        r = self._results[row]
        stream_data = RadioBrowserClient.station_to_stream(r)
        url = stream_data.get("url_resolved") or stream_data.get("url", "")
        name = stream_data.get("name", "") or r.get("name", "")
        if url:
            preview_cb = getattr(self, "open_preview", None)
            if preview_cb:
                preview_cb(name, url)
