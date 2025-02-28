import numpy as np
import tifffile
import sys

import pyqtgraph as pg
import threading
from PyQt6.QtWidgets import QProgressBar
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QFileDialog
)

def create_tiff_viewer():

    app = QApplication([])
    window = QWidget()
    layout = QVBoxLayout(window)
    button_select = QPushButton("Select Tiff File")
    button_mean = QPushButton("Extract Mean Intensity")
    widget_zstack = pg.ImageView()
    widget_zstack.widthMM = 7
    widget_plot = pg.PlotWidget()
    data_stack = None

    def select_file():
        nonlocal data_stack
        fname, _ = QFileDialog.getOpenFileName(None, "Open Tiff", "", "Tiff Files (*.tif *.tiff)")
        if fname:
            data_stack = tifffile.memmap(fname)
            widget_zstack.setImage(data_stack)

    def show_mean():
        if data_stack is None:
            return

        progress_bar = QProgressBar(window)
        layout.addWidget(progress_bar)
        progress_bar.setValue(0)

        def compute_means():
            n_frames = data_stack.shape[0]
            result = []
            for i in range(n_frames):
                result.append(np.mean(data_stack[i]))
                progress_bar.setValue(int((i + 1) * 100 / n_frames))
            return result

        def run_thread():
            means = compute_means()
            widget_plot.plot(means, clear=True)

        thread = threading.Thread(target=run_thread)
        thread.start()

    button_select.clicked.connect(select_file)
    button_mean.clicked.connect(show_mean)
    layout.addWidget(button_select)
    layout.addWidget(button_mean)
    layout.addWidget(widget_zstack)
    layout.addWidget(widget_plot)
    window.show()
    sys.exit(app.exec())
    
if __name__ == "__main__":
    create_tiff_viewer()