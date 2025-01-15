import os

from pymmcore_plus import CMMCorePlus

# Necessary modules for the IPython console
from qtconsole.rich_jupyter_widget import RichJupyterWidget
from qtconsole.inprocess import QtInProcessKernelManager

from PyQt6.QtWidgets import (
    QMainWindow, 
    QWidget, 
    QHBoxLayout, 
    QVBoxLayout,
)

from PyQt6.QtGui import QIcon

from mesofield.gui.widgets import MDA, ConfigController, EncoderWidget
from mesofield.config import ExperimentConfig

class MainWindow(QMainWindow):
    def __init__(self, cfg: ExperimentConfig):
        super().__init__()
        self.setWindowTitle("Mesofield")
        self.config: ExperimentConfig = cfg

        window_icon = QIcon(os.path.join(os.path.dirname(__file__), "Mesofield_icon.png"))
        self.setWindowIcon(window_icon)
        #============================== Widgets =============================#
        self.acquisition_gui = MDA(self.config)
        self.config_controller = ConfigController(self.config)
        self.encoder_widget = EncoderWidget(self.config)
        self.initialize_console(cfg) # Initialize the IPython console
        #--------------------------------------------------------------------#

        #============================== Layout ==============================#
        toggle_console_action = self.menuBar().addAction("Toggle Console")

        central_widget = QWidget()
        main_layout = QHBoxLayout(central_widget)
        mda_layout = QVBoxLayout()
        self.setCentralWidget(central_widget)

        mda_layout.addWidget(self.acquisition_gui)
        main_layout.addLayout(mda_layout)
        main_layout.addWidget(self.config_controller)
        mda_layout.addWidget(self.encoder_widget)
        #--------------------------------------------------------------------#

        #============================== Signals =============================#
        toggle_console_action.triggered.connect(self.toggle_console)
        self.config_controller.configUpdated.connect(self._update_config)
        self.config_controller.recordStarted.connect(self.record)
        #self.config_controller._mmc1.events.sequenceAcquisitionStopped.connect(self._on_end)
        #--------------------------------------------------------------------#


    #============================== Methods =================================#    
    def record(self):
        print('recording')
        
    def toggle_console(self):
        """Show or hide the IPython console."""
        if self.console_widget and self.console_widget.isVisible():
            self.console_widget.hide()
        else:
            if not self.console_widget:
                self.initialize_console()
            else:
                self.console_widget.show()
    
    def plots(self):
        import mesofield.processing.plot as data
        dh_md_df, th_md_df = data.load_metadata(self.config_controller.config.bids_dir)
        data.plot_encoder_csv(data.load_wheel_data(self.config_controller.config.bids_dir), data.load_psychopy_data(self.config_controller.config.bids_dir))
        data.plot_stim_times(data.load_psychopy_data(self.config_controller.config.bids_dir))
        data.plot_camera_intervals(dh_md_df, th_md_df)
    
    def metrics(self):
        import mesofield.processing.plot as data
        from mesofield.processing.metrics import calculate_metrics
        wheel_df = data.load_wheel_data(self.config_controller.config.bids_dir)
        stim_df = data.load_psychopy_data(self.config_controller.config.bids_dir)
        metrics_df = calculate_metrics(wheel_df, stim_df)
        print(metrics_df)   
                
    def initialize_console(self, cfg: ExperimentConfig):
        """Initialize the IPython console and embed it into the application."""
        # Create an in-process kernel
        self.kernel_manager = QtInProcessKernelManager()
        self.kernel_manager.start_kernel()
        self.kernel = self.kernel_manager.kernel
        self.kernel.gui = 'qt'

        # Create a kernel client and start channels
        self.kernel_client = self.kernel_manager.client()
        self.kernel_client.start_channels()

        # Create the console widget
        self.console_widget = RichJupyterWidget()
        self.console_widget.kernel_manager = self.kernel_manager
        self.console_widget.kernel_client = self.kernel_client

        # Expose variables to the console's namespace
        self.kernel.shell.push({
            #'mda': self.acquisition_gui.mda,
            'self': self,
            'config': cfg,
            # Optional, so you can use 'self' directly in the console
        })
    #----------------------------------------------------------------------------#

    def closeEvent(self, event):
        if self.config.hardware.cameras[0].backend == "opencv":
            self.config.hardware.cameras[0].thread.stop()
            event.accept()

    #============================== Private Methods =============================#
    def _on_end(self) -> None:
        """Called when the MDA is finished."""
        #self.config_controller.save_config()
        self.plots()

    def _update_config(self, config):
        self.config: ExperimentConfig = config
        self._refresh_mda_gui()
        self._refresh_save_gui()
        
    def _refresh_mda_gui(self):
        self.acquisition_gui.mda.setValue(self.config.meso_sequence)
        
    def _refresh_save_gui(self):
        self.acquisition_gui.mda.save_info.setValue({'save_dir': str(self.config.bids_dir),  'save_name': str(self.config.meso_file_path), 'format': 'ome-tiff', 'should_save': True})
                
    def _on_pause(self, state: bool) -> None:
        """Called when the MDA is paused."""


