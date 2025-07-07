import sys
import json
import logging
from typing import List, Tuple, Optional

import numpy as np
import tifffile
import pyqtgraph as pg

from PyQt6.QtCore import QObject, pyqtSignal, QRunnable, QThreadPool, Qt, QPointF
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QComboBox,
    QFileDialog,
    QSlider,
    QProgressBar,
    QCheckBox,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s:%(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("TiffViewer")

# Optimize pyqtgraph settings
pg.setConfigOptions(useOpenGL=True, antialias=False)

# Shared thread pool for background tasks
thread_pool = QThreadPool.globalInstance()


class ROIWorkerSignals(QObject):
    """
    Signals for ROIWorker.
    finished: emits (index, time_series)
    progress: emits (index, percent_complete)
    """
    finished = pyqtSignal(int, np.ndarray)
    progress = pyqtSignal(int, int)


class ROIWorker(QRunnable):
    """
    Worker that computes the mean intensity over time for a given ROI.
    """
    def __init__(
        self,
        index: int,
        filepath: str,
        dtype_str: str,
        shape: Tuple[int, int, int],
        x0: int,
        y0: int,
        mask: np.ndarray,
        chunk: int = 1000,
    ):
        super().__init__()
        self.index = index
        self.filepath = filepath
        self.dtype_str = dtype_str
        self.shape = shape  # (frames, height, width)
        self.x0 = x0
        self.y0 = y0
        self.mask = mask.astype(bool)
        self.chunk = chunk
        self.signals = ROIWorkerSignals()

    def run(self) -> None:
        """
        Perform memory-mapped IO and compute mean intensity per frame.
        Emits `progress` and `finished` signals.
        """
        mmap = np.memmap(
            self.filepath,
            mode='r',
            dtype=np.dtype(self.dtype_str),
            shape=self.shape,
        )
        total_frames = self.shape[0] - 1  # skip first frame
        mask_sum = self.mask.sum()
        result = np.empty(total_frames, dtype=float)

        for start in range(1, self.shape[0], self.chunk):
            end = min(self.shape[0], start + self.chunk)
            block = mmap[start:end, self.y0 : self.y0 + self.mask.shape[0],
                         self.x0 : self.x0 + self.mask.shape[1]]
            sums = (block * self.mask).sum(axis=(1, 2))
            idx0 = start - 1
            length = end - start
            result[idx0 : idx0 + length] = sums / mask_sum

            percent = int((idx0 + length) * 100 / total_frames)
            self.signals.progress.emit(self.index, percent)

        self.signals.finished.emit(self.index, result)


class AlignmentWorkerSignals(QObject):
    """Signals for AlignmentWorker: result(lags, correlation_values)"""
    result = pyqtSignal(np.ndarray, np.ndarray)


class AlignmentWorker(QRunnable):
    """
    Worker that computes normalized cross-correlation between two time series.
    """
    def __init__(self, series_list: List[np.ndarray]) -> None:
        super().__init__()
        self.series_list = series_list
        self.signals = AlignmentWorkerSignals()

    def run(self) -> None:
        s0, s1 = self.series_list[0], self.series_list[1]
        a = (s0 - s0.mean()) / s0.std()
        b = (s1 - s1.mean()) / s1.std()
        corr = np.correlate(a, b, mode='full')
        lags = np.arange(-len(a) + 1, len(a))
        self.signals.result.emit(lags, corr)


class TiffViewer(QWidget):
    """
    Main application widget for interactive TIFF viewing and ROI analysis.
    """
    def __init__(self):
        super().__init__()
        self.filepath: Optional[str] = None
        self.mmap: Optional[np.memmap] = None
        self.rois: List[Tuple[str, pg.ROI]] = []
        self.results: dict = {}
        self.colors = ['r', 'g', 'b', 'c', 'm']

        self._setup_ui()
        self._connect_signals()
        self.setWindowTitle("TIFF ROI Viewer")

    def _setup_ui(self) -> None:
        """Initialize and arrange all UI components."""
        main_layout = QVBoxLayout(self)

        # --- Control panel ---
        ctrl_panel = QWidget()
        ctrl_layout = QHBoxLayout(ctrl_panel)
        self.btn_open = QPushButton("Open TIFF…")
        self.combo_shape = QComboBox()
        self.combo_shape.addItems(["Rect", "Ellipse", "Polygon"])
        self.btn_add_roi = QPushButton("Add ROI")
        self.btn_clear_roi = QPushButton("Clear ROIs")
        self.btn_save_roi = QPushButton("Save ROIs…")
        self.btn_load_roi = QPushButton("Load ROIs…")
        self.btn_compute = QPushButton("Compute ROIs")
        self.chk_corr = QCheckBox("Compute Correlation")
        self.chk_corr.setChecked(True)
        self.lbl_align = QLabel("")

        for widget in [
            self.btn_open,
            self.combo_shape,
            self.btn_add_roi,
            self.btn_clear_roi,
            self.btn_save_roi,
            self.btn_load_roi,
            self.btn_compute,
            self.chk_corr,
            self.lbl_align,
        ]:
            ctrl_layout.addWidget(widget)
        main_layout.addWidget(ctrl_panel)

        # --- Image display and LUT ---
        img_panel = QWidget()
        img_layout = QHBoxLayout(img_panel)
        self.img_view = pg.GraphicsLayoutWidget()
        self.view_box = self.img_view.addViewBox()
        self.view_box.setAspectLocked(True)
        self.img_item = pg.ImageItem()
        self.view_box.addItem(self.img_item)
        img_layout.addWidget(self.img_view)

        self.lut_widget = pg.HistogramLUTWidget()
        self.lut_widget.setImageItem(self.img_item)
        img_layout.addWidget(self.lut_widget)
        main_layout.addWidget(img_panel)

        # --- Slider and progress bar ---
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setEnabled(False)
        main_layout.addWidget(self.slider)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        main_layout.addWidget(self.progress)

        # --- Time-series plot ---
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.addLegend()
        self.plot_widget.setVisible(False)
        main_layout.addWidget(self.plot_widget)

        # --- Correlation plot ---
        self.corr_widget = pg.PlotWidget(title="Cross-Correlation")
        self.corr_widget.setVisible(False)
        main_layout.addWidget(self.corr_widget)

    def _connect_signals(self) -> None:
        """Wire UI events to their handlers."""
        self.btn_open.clicked.connect(self.open_file)
        self.slider.valueChanged.connect(self.display_frame)
        self.btn_add_roi.clicked.connect(self.add_roi)
        self.btn_clear_roi.clicked.connect(self.clear_rois)
        self.btn_save_roi.clicked.connect(self.save_rois)
        self.btn_load_roi.clicked.connect(self.load_rois)
        self.btn_compute.clicked.connect(self.compute_rois)

    def open_file(self) -> None:
        """Open a TIFF file and memory-map it for fast access."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select TIFF", "", "*.tif *.tiff"
        )
        if not path:
            return
        self.filepath = path
        self.mmap = tifffile.memmap(path)
        total_frames = self.mmap.shape[0]
        self.slider.setRange(1, total_frames - 1)
        self.slider.setValue(1)
        self.slider.setEnabled(True)
        self.display_frame(1)

    def display_frame(self, index: int) -> None:
        """Display a single frame from the TIFF stack."""
        if self.mmap is None:
            return
        image = np.asarray(self.mmap[index])
        self.img_item.setImage(image, autoLevels=(index == 1))
        self.view_box.autoRange()

    def add_roi(self) -> None:
        """Add a new ROI of the selected shape to the image view."""
        shape_type = self.combo_shape.currentText()
        idx = len(self.rois)
        color = self.colors[idx % len(self.colors)]

        if shape_type == "Rect":
            roi = pg.RectROI([20, 20], [100, 100], pen=color)
        elif shape_type == "Ellipse":
            roi = pg.EllipseROI([20, 20], [100, 100], pen=color)
        else:
            pts = [[20, 20], [120, 20], [120, 120], [20, 120]]
            roi = pg.PolyLineROI(pts, closed=True, pen=color)

        self.view_box.addItem(roi)
        self.rois.append((shape_type, roi))

    def clear_rois(self) -> None:
        """Remove all ROIs and reset plots/labels."""
        for _, roi in self.rois:
            self.view_box.removeItem(roi)
        self.rois.clear()
        self.plot_widget.clear()
        self.plot_widget.setVisible(False)
        self.corr_widget.clear()
        self.corr_widget.setVisible(False)
        self.results.clear()
        self.lbl_align.clear()
        self.progress.setVisible(False)

    def save_rois(self) -> None:
        """Export ROI definitions to a JSON file."""
        if not self.rois:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save ROIs", "rois.json", "JSON Files (*.json)"
        )
        if not path:
            return

        export_data = []
        for shape_type, roi in self.rois:
            info = {'type': shape_type}
            if shape_type in ("Rect", "Ellipse"):
                pos = roi.pos()
                size = roi.size()
                info['pos'] = [pos.x(), pos.y()]
                info['size'] = [size.x(), size.y()]
            else:
                info['points'] = roi.getState()['points']
            export_data.append(info)

        with open(path, 'w') as f:
            json.dump(export_data, f, indent=2)

        logger.info(f"Saved {len(export_data)} ROIs to {path}")

    def load_rois(self) -> None:
        """Import ROI definitions from a JSON file and render them."""
        if self.mmap is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Load ROIs", "", "JSON Files (*.json)"
        )
        if not path:
            return
        self.clear_rois()

        with open(path) as f:
            roi_list = json.load(f)

        for entry in roi_list:
            shape_type = entry['type']
            idx = len(self.rois)
            color = self.colors[idx % len(self.colors)]

            if shape_type in ("Rect", "Ellipse"):
                x, y = entry['pos']
                w, h = entry['size']
                if shape_type == "Rect":
                    roi = pg.RectROI([x, y], [w, h], pen=color)
                else:
                    roi = pg.EllipseROI([x, y], [w, h], pen=color)
            else:
                pts = entry['points']
                roi = pg.PolyLineROI(pts, closed=True, pen=color)

            self.view_box.addItem(roi)
            self.rois.append((shape_type, roi))

        logger.info(f"Loaded {len(self.rois)} ROIs from {path}")

    def compute_rois(self) -> None:
        """Run ROI mean-series calculations and optional correlation."""
        if self.mmap is None or not self.rois:
            return
        self.progress.setVisible(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)

        self.plot_widget.clear()
        self.plot_widget.setVisible(True)
        self.results.clear()

        for idx, (_, roi) in enumerate(self.rois):
            h, w = self.mmap.shape[1], self.mmap.shape[2]
            ones = np.ones((h, w), dtype=np.uint8)
            mask = roi.getArrayRegion(
                ones, self.img_item, returnMappedCoords=False
            ).astype(bool)
            x0 = int(roi.pos().x())
            y0 = int(roi.pos().y())

            worker = ROIWorker(
                idx, self.filepath, self.mmap.dtype.str,
                self.mmap.shape, x0, y0, mask
            )
            worker.signals.progress.connect(
                lambda _, pct: self.progress.setValue(pct)
            )
            worker.signals.finished.connect(self._on_roi_finished)
            thread_pool.start(worker)

    def _on_roi_finished(self, idx: int, series: np.ndarray) -> None:
        """Handle completion of a ROIWorker."""
        self.plot_widget.plot(
            series, pen=self.colors[idx % len(self.colors)],
            name=f"ROI {idx+1}"
        )
        self.results[idx] = series

        all_done = len(self.results) == len(self.rois)
        if all_done and self.chk_corr.isChecked() and len(self.rois) > 1:
            self.progress.setRange(0, 0)
            align_worker = AlignmentWorker(
                [self.results[0], self.results[1]]
            )
            align_worker.signals.result.connect(self._on_aligned)
            thread_pool.start(align_worker)
        elif all_done:
            self.progress.setVisible(False)

    def _on_aligned(self, lags: np.ndarray, corr: np.ndarray) -> None:
        """Plot correlation results and display peak lag."""
        self.corr_widget.clear()
        self.corr_widget.plot(lags, corr, pen='y')
        peak = lags[corr.argmax()]
        self.lbl_align.setText(f"Lag = {peak} frames")
        self.progress.setRange(0, 100)
        self.progress.setValue(100)


def main() -> None:
    app = QApplication(sys.argv)
    viewer = TiffViewer()
    viewer.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
