from pymmcore_plus import CMMCorePlus

from PyQt6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)

from pymmcore_widgets import (
    MDAWidget,
    ExposureWidget,
    LiveButton,
    SnapButton,
)

from mesofield.config import ExperimentConfig
from mesofield.io.writer import CustomWriter
from .viewer import ImagePreview

class CustomMDAWidget(MDAWidget):
    def run_mda(self) -> None:
        """Run the MDA sequence experiment."""
        # in case the user does not press enter after editing the save name.
        self.save_info.save_name.editingFinished.emit()

        sequence = self.value()

        # technically, this is in the metadata as well, but isChecked is more direct
        if self.save_info.isChecked():
            save_path = self._update_save_path_from_metadata(
                sequence, update_metadata=True
            )
        else:
            save_path = None

        # run the MDA experiment asynchronously
        self._mmc.run_mda(sequence, output=CustomWriter(save_path))

class MDA(QWidget):
    """
    The `MDAWidget` provides a GUI to construct a `useq.MDASequence` object.
    This object describes a full multi-dimensional acquisition;
    In this example, we set the `MDAWidget` parameter `include_run_button` to `True`,
    meaning that a `run` button is added to the GUI. When pressed, a `useq.MDASequence`
    is first built depending on the GUI values and is then passed to the
    `CMMCorePlus.run_mda` to actually execute the acquisition.
    For details of the corresponding schema and methods, see
    https://github.com/pymmcore-plus/useq-schema and
    https://github.com/pymmcore-plus/pymmcore-plus.

    """

    def __init__(self, config: ExperimentConfig) -> None:
        """

        The layout adapts the viewer based on the number of cores:

        Single Core Layout:

            +-------------------+------------------------------------------------+
            |                   |  Live Viewer                                   |
            |                   |  +-----------------+------------------------+  |
            |                   |  | [Snap Button]   |    [Live Button]       |  |
            |        MDA        |  +-----------------+------------------------+  |
            |                   |  |                                          |  |
            |                   |  |            Image Preview                 |  |
            |                   |  |                                          |  |
            |                   |  +------------------------------------------+  |
            +-------------------+------------------------------------------------+
                
        Dual Core Layout:

            +-------------------+-------------------------------------------------+
            |                   |   Live Viewer                                   |
            |                   |  +-----------------------+-------------------+  |
            |                   |  |       Core 1          |       Core 2      |  |
            |                   |  +-----------------------+-------------------+  |
            |                   |  |     [Buttons]         |     [Buttons]     |  |
            |        MDA        |  +-----------------------+-------------------+  |
            |                   |  |                       |                   |  |
            |                   |  |    Image Preview 1    |   Image Preview 2 |  |
            |                   |  |                       |                   |  |
            |                   |  +-----------------------+-------------------+  |
            +-------------------+-------------------------------------------------+

        """
        super().__init__()
        # get the CMMCore instance and load the default config
        self.mmcores: tuple[CMMCorePlus, CMMCorePlus] = config._cores

        # instantiate the MDAWidget
        self.mda = CustomMDAWidget(mmcore=self.mmcores[0])
        # ----------------------------------Auto-set MDASequence and save_info----------------------------------#
        self.mda.setValue(config.pupil_sequence)
        self.mda.save_info.setValue({'save_dir': r'C:/dev', 'save_name': 'file', 'format': 'ome-tiff', 'should_save': True})
        # -------------------------------------------------------------------------------------------------------#
        self.setLayout(QHBoxLayout())

        live_viewer = QGroupBox()
        live_viewer.setLayout(QVBoxLayout())
        buttons = QGroupBox()
        buttons.setLayout(QHBoxLayout())

        if len(self.mmcores) == 1:
            '''Single Core Layout'''

            self.mmc = self.mmcores[0]
            self.preview = ImagePreview(mmcore=self.mmc, parent=self.mda)
            self.snap_button = SnapButton(mmcore=self.mmc)
            self.live_button = LiveButton(mmcore=self.mmc)
            self.exposure = ExposureWidget(mmcore=self.mmc)

            buttons.layout().addWidget(self.snap_button)
            buttons.layout().addWidget(self.live_button)
            live_viewer.layout().addWidget(self.preview)

            self.layout().addWidget(self.mda)
            self.layout().addWidget(live_viewer)

        elif len(self.mmcores) == 2:
            '''Dual Core Layout'''
            
            self.preview1 = ImagePreview(mmcore=self.mmcores[0], parent=self.mda)
            self.preview2 = ImagePreview(mmcore=self.mmcores[1], parent=self.mda)
            snap_button1 = SnapButton(mmcore=self.mmcores[0])
            live_button1 = LiveButton(mmcore=self.mmcores[0])
            snap_button2 = SnapButton(mmcore=self.mmcores[1])
            live_button2 = LiveButton(mmcore=self.mmcores[1])

            #==================== 2 Viewer Layout ===================#
            cores_groupbox = QGroupBox("Live Viewer")
            cores_groupbox.setLayout(QHBoxLayout())

            #-------------------- Core 1 Viewer ---------------------#
            core1_layout = QVBoxLayout()

            buttons1 = QGroupBox("Core 1")
            buttons1.setLayout(QHBoxLayout())
            buttons1.layout().addWidget(snap_button1)
            buttons1.layout().addWidget(live_button1)
            core1_layout.addWidget(buttons1)
            core1_layout.addWidget(self.preview1)

            #-------------------- Core 2 Viewer ---------------------#
            core2_layout = QVBoxLayout()

            buttons2 = QGroupBox("Core 2")
            buttons2.setLayout(QHBoxLayout())
            buttons2.layout().addWidget(snap_button2)
            buttons2.layout().addWidget(live_button2)
            core2_layout.addWidget(buttons2)
            core2_layout.addWidget(self.preview2)

            #================ Add Widgets to Layout =================#
            cores_groupbox.layout().addLayout(core1_layout)
            cores_groupbox.layout().addLayout(core2_layout)

            self.layout().addWidget(self.mda)
            self.layout().addWidget(cores_groupbox)
        
