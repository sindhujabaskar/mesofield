import os
from typing import cast

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
from PyQt6.QtCore import QCoreApplication

from mesofield.gui.mdagui import MDA
from mesofield.gui.controller import ConfigController
from mesofield.gui.speedplotter import EncoderWidget
from mesofield.config import ExperimentConfig
from mesofield.protocols import Procedure

class MainWindow(QMainWindow):
    def __init__(self, procedure: Procedure):
        super().__init__()
        self.config: ExperimentConfig = cast(ExperimentConfig, procedure.config)
        self.procedure = procedure
        window_icon = QIcon(os.path.join(os.path.dirname(__file__), "Mesofield_icon.png"))
        self.setWindowIcon(window_icon)        
        #============================== Widgets =============================#
        self.acquisition_gui = MDA(self.config)
        self.config_controller = ConfigController(self.config, self.procedure)
        self.encoder_widget = EncoderWidget(self.config)
        self.initialize_console(self.config) # Initialize the IPython console
        #--------------------------------------------------------------------#

        #============================== Layout ==============================#
        toggle_console_action = self.menuBar().addAction("Toggle Console")

        central_widget = QWidget()
        main_layout = QHBoxLayout(central_widget)
        self.setCentralWidget(central_widget)

        mda_layout = QVBoxLayout()
        main_layout.addLayout(mda_layout)

        # Horizontal row for acquisition GUI and config controller
        top_row = QHBoxLayout()
        top_row.addWidget(self.acquisition_gui)
        top_row.addWidget(self.config_controller)
        mda_layout.addLayout(top_row)

        # Encoder widget below the top row
        mda_layout.addWidget(self.encoder_widget)
        #--------------------------------------------------------------------#

        #============================== Signals =============================#
        toggle_console_action.triggered.connect(self.toggle_console)
        self.config_controller.configUpdated.connect(self._update_config)
        self.config_controller.recordStarted.connect(self.record)
        #self.config_controller._mmc1.events.sequenceAcquisitionStopped.connect(self._on_end)
        #--------------------------------------------------------------------#


    #============================== Methods =================================#    
    def record(self, timestamp):
        self.config.register_parameter("recording_started", timestamp)


    def toggle_console(self):
        """Show or hide the IPython console."""
        if self.console_widget and self.console_widget.isVisible():
            self.console_widget.hide()
        else:
            if not self.console_widget:
                self.initialize_console()
            else:
                self.console_widget.show()

                
    def initialize_console(self, cfg):
        """Initialize the IPython console and embed it into the application."""
        import mesofield.data as data
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
        self.console_widget.kernel_client = self.kernel_client        # Expose variables to the console's namespace
        console_namespace = {
            #'mda': self.acquisition_gui.mda,
            'self': self,
            'config': cfg,
            'data': data
            # Optional, so you can use 'self' directly in the console
        }
        
        # Add procedure to console namespace if available
        # if self.procedure is not None:
        #     console_namespace['procedure'] = self.procedure
        
        self.kernel.shell.push(console_namespace)
    #----------------------------------------------------------------------------#

    def closeEvent(self, event):
        # 0. Try to shut down the MDA relay threads gracefully
        try:
            self.acquisition_gui.mda.shutdown()
        except Exception:
            pass

        # 1. Stop any remaining relay threads
        for thread_name in ("thread0", "thread1", "thread2"):
            thr = getattr(self.config_controller, thread_name, None)
            if not thr:
                continue

            # If it's a pymmcore_plus relay thread, signal it to stop
            if hasattr(thr, "shutdown"):
                try:
                    thr.shutdown()
                except Exception:
                    pass

            # Wait for it to terminate
            if hasattr(thr, "is_alive") and thr.is_alive():
                thr.join(timeout=2)
            elif hasattr(thr, "isRunning") and thr.isRunning():
                thr.quit()
                thr.wait(2000)

        # # 2. Abort any remaining acquisitions and reset each core
        # for cam in getattr(self.config.hardware, "cameras", []):
        #     core = getattr(cam, "core", None)
        #     if not core:
        #         continue
        #     try:
        #         core.stopSequenceAcquisition()
        #         core.reset()
        #     except Exception:
        #         pass

        # 3. Shut down the IPython console
        if hasattr(self, "kernel_client"):
            self.kernel_client.stop_channels()
        if hasattr(self, "kernel_manager"):
            self.kernel_manager.shutdown_kernel()
        if hasattr(self, "console_widget"):
            self.console_widget.close()

        # 4. Finally shut down all hardware
        try:
            self.config.hardware.shutdown()
        except Exception:
            pass

        event.accept()
        QCoreApplication.quit()

    #============================== Private Methods =============================#
    def _on_end(self) -> None:
        """Called when the MDA is finished."""
        #self.config_controller.save_config()

    def _update_config(self, config):
        self.config = config
                
    def _on_pause(self, state: bool) -> None:
        """Called when the MDA is paused."""


