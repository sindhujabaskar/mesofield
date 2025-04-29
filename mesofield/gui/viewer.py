from contextlib import suppress
from typing import Tuple, Union, Literal
import numpy as np
from pymmcore_plus import CMMCorePlus
from qtpy.QtCore import Qt, QTimer
from qtpy.QtGui import QImage, QPixmap
from qtpy.QtWidgets import QHBoxLayout, QLabel, QWidget, QSizePolicy
from threading import Lock

class ImagePreview(QWidget):
    """
    A PyQt widget that displays images from a `CMMCorePlus` instance (mmcore).

    This widget displays images from a single `CMMCorePlus` instance,
    updating the display in real-time as new images are captured.

    The image is displayed using PyQt's `QLabel` and `QPixmap`, allowing for efficient
    rendering without external dependencies like VisPy.

    **Parameters**
    ----------
    parent : QWidget, optional
        The parent widget. Defaults to `None`.
    mmcore : CMMCorePlus
        The `CMMCorePlus` instance from which images will be displayed.
        Represents the microscope control core.
    use_with_mda : bool, optional
        If `True`, the widget will update during Multi-Dimensional Acquisitions (MDA).
        If `False`, the widget will not update during MDA. Defaults to `True`.

    **Attributes**
    ----------
    clims : Union[Tuple[float, float], Literal["auto"]]
        The contrast limits for the image display. If set to `"auto"`, the widget will
        automatically adjust the contrast limits based on the image data.
    cmap : str
        The colormap to use for the image display. Currently set to `"grayscale"`.

    **Notes**
    -----
    - **Image Display**: Uses a `QLabel` widget to display the image.
      The image is set to scale to fit the label size (`setScaledContents(True)`).

    - **Image Conversion**: Converts images from the `CMMCorePlus` instance to `uint8`
      and scales them appropriately for display using `QImage` and `QPixmap`.

    - **Event Handling**: Connects to various events emitted by the `CMMCorePlus` instance:
        - `imageSnapped`: Emitted when a new image is snapped.
        - `continuousSequenceAcquisitionStarted` and `sequenceAcquisitionStarted`: Emitted when
          a sequence acquisition starts.
        - `sequenceAcquisitionStopped`: Emitted when a sequence acquisition stops.
        - `exposureChanged`: Emitted when the exposure time changes.
        - `frameReady` (MDA): Emitted when a new frame is ready during MDA.

    - **Thread Safety**: Uses a threading lock (`Lock`) to ensure thread-safe access to
      shared resources, such as the current frame. UI updates are performed in the main
      thread using Qt's signals and slots mechanism, ensuring thread safety.

    - **Timer for Updates**: A `QTimer` is used to periodically update the image
      from the core. The timer interval can be adjusted based on the exposure time,
      ensuring that updates occur at appropriate intervals.

    - **Contrast Limits and Colormap**: Allows setting contrast limits (`clims`) and
      colormap (`cmap`) for the image. Currently, only grayscale images are supported.
      The `clims` can be set to a tuple `(min, max)` or `"auto"` for automatic adjustment.

    - **Usage with MDA**: The `use_with_mda` parameter determines whether the widget updates
      during Multi-Dimensional Acquisitions. If set to `False`, the widget will not update
      during MDA runs.

    **Examples**
    --------
    ```python
    from pymmcore_plus import CMMCorePlus
    from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget

    # Initialize a CMMCorePlus instance
    mmc = CMMCorePlus()

    # Set up the application and main window
    app = QApplication([])
    window = QWidget()
    layout = QVBoxLayout(window)

    # Create the ImagePreview widget
    image_preview = ImagePreview(mmcore=mmc)

    # Add the widget to the layout
    layout.addWidget(image_preview)
    window.show()

    # Start the Qt event loop
    app.exec()
    ```

    **Methods**
    -------
    - `clims`: Property to get or set the contrast limits of the image.
    - `cmap`: Property to get or set the colormap of the image.

    **Initialization Parameters**
    ----------
    parent : QWidget, optional
        The parent widget for this widget.
    mmcore : CMMCorePlus
        The `CMMCorePlus` instance to be used for image acquisition.
    use_with_mda : bool, optional
        Flag to determine if the widget should update during MDA sequences.

    **Raises**
    ------
    ValueError
        If `mmcore` is not provided.

    **Private Methods**
    ----------------
    These methods handle internal functionality:

    - `_disconnect()`: Disconnects all connected signals from the `CMMCorePlus` instance.
    - `_on_streaming_start()`: Starts the streaming timer when a sequence acquisition starts.
    - `_on_streaming_stop()`: Stops the streaming timer when the sequence acquisition stops.
    - `_on_exposure_changed(device, value)`: Adjusts the timer interval when the exposure changes.
    - `_on_streaming_timeout()`: Called periodically by the timer to fetch and display new images.
    - `_on_image_snapped(img)`: Handles new images snapped outside of sequences.
    - `_on_frame_ready(event)`: Handles new frames ready during MDA.
    - `_display_image(img)`: Converts and displays the image in the label.
    - `_adjust_image_data(img)`: Scales image data to `uint8` for display.
    - `_convert_to_qimage(img)`: Converts a NumPy array to a `QImage` for display.

    **Usage Notes**
    ------------
    - **Initialization**: Provide an initialized and configured `CMMCorePlus` instance.
    - **Thread Safety**: UI updates are performed in the main thread. Ensure that heavy computations are offloaded to avoid blocking the UI.
    - **Customization**: You can adjust the `clims` and `cmap` properties to customize the image display.

    **Performance Considerations**
    --------------------------
    - **Frame Rate**: The default timer interval is set to 10 milliseconds. Adjust the interval based on your performance needs.
    - **Resource Management**: Disconnect signals properly by ensuring the `_disconnect()` method is called when the widget is destroyed.

    """

    def __init__(self, parent: QWidget = None, *, 
                 mmcore: CMMCorePlus, 
                 use_with_mda: bool = True):
        super().__init__(parent=parent)
        if mmcore is None:
            raise ValueError("A CMMCorePlus instance must be provided.")
        self._mmcore = mmcore
        self._use_with_mda = use_with_mda
        self._clims: Union[Tuple[float, float], Literal["auto"]] = "auto"
        self._cmap: str = "grayscale"
        self._current_frame = None
        self._frame_lock = Lock()

        # Set up image label
        self.image_label = QLabel()
        self.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(512, 512)
        self.image_label.setScaledContents(False)  # Keep aspect ratio

        # Set up layout
        self.setLayout(QHBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(self.image_label)
        self.layout().setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Set up timer
        self.streaming_timer = QTimer(parent=self)
        self.streaming_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.streaming_timer.setInterval(10)  # Default interval; adjust as needed
        self.streaming_timer.timeout.connect(self._on_streaming_timeout)

        # Connect events for the mmcore
        ev = self._mmcore.events
        #ev.imageSnapped.connect(self._on_image_snapped)
        ev.continuousSequenceAcquisitionStarted.connect(self._on_streaming_start)
        ev.sequenceAcquisitionStarted.connect(self._on_streaming_start)
        ev.sequenceAcquisitionStopped.connect(self._on_streaming_stop)
        ev.exposureChanged.connect(self._on_exposure_changed)

        enev = self._mmcore.mda.events
        enev.frameReady.connect(self._on_frame_ready)

        self.destroyed.connect(self._disconnect)

    def _disconnect(self) -> None:
        # Disconnect events for the mmcore
        ev = self._mmcore.events
        with suppress(TypeError):
            ev.imageSnapped.disconnect()
            ev.continuousSequenceAcquisitionStarted.disconnect()
            ev.sequenceAcquisitionStarted.disconnect()
            ev.sequenceAcquisitionStopped.disconnect()
            ev.exposureChanged.disconnect()

        enev = self._mmcore.mda.events
        with suppress(TypeError):
            enev.frameReady.disconnect()

    def _on_streaming_start(self) -> None:
        if not self.streaming_timer.isActive():
            self.streaming_timer.start()

    def _on_streaming_stop(self) -> None:
        # Stop the streaming timer
        if not self._mmcore.isSequenceRunning():
            self.streaming_timer.stop()

    def _on_exposure_changed(self, device: str, value: str) -> None:
        # Adjust timer interval if needed
        exposure = self._mmcore.getExposure() or 10
        interval = int(exposure) or 10
        self.streaming_timer.setInterval(interval)

    def _on_streaming_timeout(self) -> None:
        frame = None
        if not self._mmcore.mda.is_running():
            with suppress(RuntimeError, IndexError):
                frame = self._mmcore.getLastImage()
        else:
            with self._frame_lock:
                if self._current_frame is not None:
                    frame = self._current_frame
                    self._current_frame = None
        # Update the image if a frame is available
        if frame is not None:
            self._display_image(frame)

    def _on_image_snapped(self, img: np.ndarray) -> None:
        self._update_image(img)

    def _on_frame_ready(self, img: np.ndarray) -> None:
        frame = img 
        with self._frame_lock:
            self._current_frame = frame

    def _display_image(self, img: np.ndarray) -> None:
        if img is None:
            return
        qimage = self._convert_to_qimage(img)
        if qimage is not None:
            pixmap = QPixmap.fromImage(qimage)
            pixmap = pixmap.scaled(self.image_label.width(), self.image_label.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.image_label.setPixmap(pixmap)

    def _update_image(self, img: np.ndarray) -> None:
        # Update the current frame
        with self._frame_lock:
            self._current_frame = img

    def _adjust_image_data(self, img: np.ndarray) -> np.ndarray:
        # NOTE: This is the default implementation for grayscale images
        # NOTE: This is the most processor-intensive part of this widget
        
        # Ensure the image is in float format for scaling
        img = img.astype(np.float32, copy=False)

        # Apply contrast limits
        if self._clims == "auto":
            min_val, max_val = np.min(img), np.max(img)
        else:
            min_val, max_val = self._clims

        # Avoid division by zero
        scale = 255.0 / (max_val - min_val) if max_val != min_val else 255.0

        # Scale to 0-255
        img = np.clip((img - min_val) * scale, 0, 255).astype(np.uint8, copy=False)
        return img

    def _convert_to_qimage(self, img: np.ndarray) -> QImage:
        """Convert a NumPy array to QImage."""
        if img is None:
            return None
        img = self._adjust_image_data(img)
        img = np.ascontiguousarray(img)
        height, width = img.shape[:2]

        if img.ndim == 2:
            # Grayscale image
            bytes_per_line = width
            qimage = QImage(img.data, width, height, bytes_per_line, QImage.Format.Format_Grayscale8)
        else:
            # Handle other image formats if needed
            return None

        return qimage

    @property
    def clims(self) -> Union[Tuple[float, float], Literal["auto"]]:
        """Get the contrast limits of the image."""
        return self._clims

    @clims.setter
    def clims(self, clims: Union[Tuple[float, float], Literal["auto"]] = "auto") -> None:
        """Set the contrast limits of the image.

        Parameters
        ----------
        clims : tuple[float, float], or "auto"
            The contrast limits to set.
        """
        self._clims = clims

    @property
    def cmap(self) -> str:
        """Get the colormap (lookup table) of the image."""
        return self._cmap

    @cmap.setter
    def cmap(self, cmap: str = "grayscale") -> None:
        """Set the colormap (lookup table) of the image.

        Parameters
        ----------
        cmap : str
            The colormap to use.
        """
        self._cmap = cmap


import pyqtgraph as pg
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt, QTimer
import numpy as np
from threading import Lock
from contextlib import suppress
from typing import Tuple, Union, Literal
from pymmcore_plus import CMMCorePlus

pg.setConfigOptions(imageAxisOrder='row-major', useOpenGL=True)

class InteractivePreview(pg.ImageView):
    def __init__(self, parent=None, mmcore=None, use_with_mda=True, image_payload=None):
        super().__init__(parent=parent)
        self._mmcore: CMMCorePlus = mmcore
        self._use_with_mda = use_with_mda
        self._clims: Union[Tuple[float, float], Literal["auto"]] = "auto"
        self._current_frame = np.zeros((512, 512), dtype=np.uint8)
        self._display_image(self._current_frame)
        self._cmap: str = "grayscale"
        self._current_frame = None
        self._frame_lock = Lock()

        if image_payload is not None:
            image_payload.connect(self._on_image_payload)

        if self._mmcore is not None:
            self._mmcore.events.imageSnapped.connect(self._on_image_snapped)
            self._mmcore.events.continuousSequenceAcquisitionStarted.connect(self._on_streaming_start)
            self._mmcore.events.sequenceAcquisitionStarted.connect(self._on_streaming_start)
            self._mmcore.events.sequenceAcquisitionStopped.connect(self._on_streaming_stop)
            self._mmcore.events.exposureChanged.connect(self._on_exposure_changed)

            enev = self._mmcore.mda.events
            enev.frameReady.connect(self._on_image_payload, type=Qt.ConnectionType.QueuedConnection)
            if self._use_with_mda:
                self._mmcore.mda.events.frameReady.connect(self._on_frame_ready)

            self.streaming_timer = QTimer(parent=self)
            self.streaming_timer.setTimerType(Qt.TimerType.PreciseTimer)
            self.streaming_timer.setInterval(10)
            self.streaming_timer.timeout.connect(self._on_streaming_timeout)

        self.destroyed.connect(self._disconnect)

    def _disconnect(self) -> None:
        if self._mmcore:
            ev = self._mmcore.events
            with suppress(TypeError):
                ev.imageSnapped.disconnect()
                ev.continuousSequenceAcquisitionStarted.disconnect()
                ev.sequenceAcquisitionStarted.disconnect()
                ev.sequenceAcquisitionStopped.disconnect()
                ev.exposureChanged.disconnect()
            enev = self._mmcore.mda.events
            with suppress(TypeError):
                enev.frameReady.disconnect()

    def _on_streaming_start(self) -> None:
        if not self.streaming_timer.isActive():
            self.streaming_timer.start()

    def _on_streaming_stop(self) -> None:
        if not self._mmcore.isSequenceRunning():
            self.streaming_timer.stop()

    def _on_exposure_changed(self, device: str, value: str) -> None:
        exposure = self._mmcore.getExposure() or 10
        self.streaming_timer.setInterval(int(exposure) or 10)

    def _on_frame_ready(self, img: np.ndarray) -> None:
        with self._frame_lock:
            self._current_frame = img

    def _on_streaming_timeout(self) -> None:
        frame = None
        if not self._mmcore.mda.is_running():
            with suppress(RuntimeError, IndexError):
                frame = self._mmcore.getLastImage()
        else:
            with self._frame_lock:
                if self._current_frame is not None:
                    frame = self._current_frame
                    self._current_frame = None
        if frame is not None:
            self._display_image(frame)

    def _on_image_snapped(self, img: np.ndarray) -> None:
        with self._frame_lock:
            self._current_frame = img
        self._display_image(img)

    def _on_image_payload(self, img: np.ndarray) -> None:
        #img = self._adjust_image_data(img)
        self.setImage(img.T, 
                      autoHistogramRange=False, 
                      autoRange=False, 
                      levelMode='mono', 
                      autoLevels=(self._clims == "auto"),
                      )

    def _display_image(self, img: np.ndarray) -> None:
        if img is None:
            return
        img = self._adjust_image_data(img)
        self.setImage(img.T, 
                      autoHistogramRange=False, 
                      autoRange=False, 
                      levelMode='mono', 
                      autoLevels=(self._clims == "auto"),
                      )

    def _adjust_image_data(self, img: np.ndarray) -> np.ndarray:
        img = img.astype(np.float32, copy=False)
        if self._clims == "auto":
            min_val, max_val = np.min(img), np.max(img)
        else:
            min_val, max_val = self._clims
        scale = 255.0 / (max_val - min_val) if max_val != min_val else 255.0
        img = np.clip((img - min_val) * scale, 0, 255).astype(np.uint8, copy=False)
        return img

    # @property
    # def clims(self) -> Union[Tuple[float, float], Literal["auto"]]:
    #     return self._clims

    # @clims.setter
    # def clims(self, clims: Union[Tuple[float, float], Literal["auto"]] = "auto") -> None:
    #     self._clims = clims
    #     if self._current_frame is not None:
    #         self._display_image(self._current_frame)

    # @property
    # def cmap(self) -> str:
    #     return self._cmap

    # @cmap.setter
    # def cmap(self, cmap: str = "grayscale") -> None:
    #     self._cmap = cmap