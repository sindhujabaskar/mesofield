import os
from datetime import datetime
import threading
import time
import numpy as np

from qtpy.QtCore import Qt
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
    QLineEdit,
    QPushButton,
    QComboBox,
    QFileDialog,
    QMessageBox,
    QInputDialog,
    QDialog,
    QStyle,
    QFormLayout, 
    QLineEdit, 
    QSpinBox, 
    QCheckBox
)
from PyQt6.QtGui import QIcon

from typing import TYPE_CHECKING, Optional
if TYPE_CHECKING:
    from mesofield.config import ExperimentConfig
    from pymmcore_plus import CMMCorePlus
    from mesofield.protocols import Procedure

from mesofield.subprocesses.psychopy import PsychoPyProcess
from mesofield.io import CustomWriter
from mesofield.gui import ConfigTableModel
from .dynamic_controller import DynamicController

class ConfigFormWidget(QWidget):
    """Map each config key to an appropriate editor in a form layout."""
    def __init__(self, registry):
        super().__init__()
        self._registry = registry
        form = QFormLayout(self)
        # create editor per config key with initial values and two-way binding
        for key in self._registry.keys():
            type_hint = self._registry.get_metadata(key).get("type")
            value = self._registry.get(key)
            if type_hint is int:
                editor = QSpinBox()
                editor.setRange(-1_000_000, 1_000_000)
                editor.setValue(int(value or 0))
                editor.valueChanged.connect(lambda val, k=key: self._registry.set(k, val))
            elif type_hint is bool:
                editor = QCheckBox()
                editor.setChecked(bool(value))
                editor.toggled.connect(lambda checked, k=key: self._registry.set(k, checked))
            else:
                editor = QLineEdit()
                editor.setText(str(value))
                editor.textChanged.connect(lambda text, k=key: self._registry.set(k, text))
            form.addRow(key, editor)


class ConfigController(QWidget):
    """AcquisitionEngine object for the napari-mesofield plugin.
    The object connects to the Micro-Manager Core object instances and the Config object.

    The ConfigController widget is a QWidget that allows the user to select a save directory,
    load a JSON configuration file, and edit the configuration parameters in a table.
    The user can also trigger the MDA sequence with the current configuration parameters.
    
    The ConfigController widget emits signals to notify other widgets when the configuration is updated
    and when the record button is pressed.
    
    Public Methods:
    ----------------
    save_config(): 
        saves the current configuration to a JSON file
    
    record(): 
        triggers the MDA sequence with the configuration parameters
    
    launch_psychopy(): 
        launches the PsychoPy experiment as a subprocess with ExperimentConfig parameters
    
    show_popup(): 
        shows a popup message to the user
    
    Private Methods:
    ----------------
    _select_directory(): 
        opens a dialog to select a directory and update the GUI accordingly
    _get_json_file_choices(): 
        returns a list of JSON files in the current directory
    _update_config(): 
        updates the experiment configuration from a new JSON file
    _test_led(): 
        tests the LED pattern by sending a test sequence to the Arduino-Switch device
    _stop_led(): 
        stops the LED pattern by sending a stop sequence to the Arduino-Switch device
    _add_note(): 
        opens a dialog to get a note from the user and save it to the ExperimentConfig.notes list
    
    """
    # ==================================== Signals ===================================== #
    configUpdated = pyqtSignal(object)
    recordStarted = pyqtSignal(str)
    # ------------------------------------------------------------------------------------- #
    def __init__(self, cfg: 'ExperimentConfig', procedure: Optional['Procedure'] = None):
        super().__init__()
        self.mmcores = cfg._cores
        # TODO: Add a check for the number of cores, and adjust rest of controller accordingly

        self.config = cfg
        self.procedure = procedure
        # Sync registry changes to legacy parameters dict
        for key in self.config.keys():
            self.config.register_callback(key, self._on_registry_updated)
        if len(self.mmcores) == 1:
            self._mmc: CMMCorePlus = self.mmcores[0]
        elif len(self.mmcores) == 2:
            self._mmc1: CMMCorePlus = self.mmcores[0]
            self._mmc2: CMMCorePlus = self.mmcores[1]

        self.psychopy_process = None

        # Create main layout
        layout = QVBoxLayout(self)
        self.setFixedWidth(500)

        # ==================================== GUI Widgets ===================================== #

        # 1. Selecting a save directory
        self.directory_label = QLabel('Select Save Directory:')
        self.directory_line_edit = QLineEdit()
        self.directory_line_edit.setReadOnly(True)
        self.directory_button = QPushButton('Browse')

        dir_layout = QHBoxLayout()
        dir_layout.addWidget(self.directory_label)
        dir_layout.addWidget(self.directory_line_edit)
        dir_layout.addWidget(self.directory_button)

        layout.addLayout(dir_layout)

        # 2. Dropdown Widget for JSON configuration files
        self.json_dropdown_label = QLabel('Select JSON Config:')
        self.json_dropdown = QComboBox()

        json_layout = QHBoxLayout()
        json_layout.addWidget(self.json_dropdown_label)
        json_layout.addWidget(self.json_dropdown)

        layout.addLayout(json_layout)

        # 3. Table view to display the configuration parameters loaded from the JSON
        self.config_model = ConfigFormWidget(self.config)
        layout.addWidget(self.config_model)

        # 4. Record button to start the MDA sequence
        self.record_button = QPushButton("Record")

        # Tint the standard play icon red
        play_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
        pix = play_icon.pixmap(24, 24)
        mask = pix.createMaskFromColor(Qt.transparent)
        pix.fill(Qt.GlobalColor.red)
        pix.setMask(mask)
        self.record_button.setIcon(QIcon(pix))

        # Use default background, no custom color
        self.record_button.setStyleSheet("""
            QPushButton {
            background-color: #424242; /* Dark Grey */
            border: none;
            padding: 6px 12px;
            border-radius: 4px;
            }
            QPushButton:hover {
            background-color: #616161;
            }
            QPushButton:pressed {
            background-color: #212121;
            }
        """)        
        layout.addWidget(self.record_button)

        # Procedure-specific controls (only shown when procedure is available)
        if self.procedure is not None:
            # Add procedure info label
            procedure_name = self.procedure.__class__.__name__
            self.procedure_label = QLabel(f"Procedure: {procedure_name}")
            self.procedure_label.setStyleSheet("QLabel { font-weight: bold; color: #2196F3; }")
            layout.addWidget(self.procedure_label)
            
            # Add procedure configuration button
            self.configure_procedure_button = QPushButton("Configure Procedure")
            self.configure_procedure_button.setStyleSheet("""
                QPushButton {
                background-color: #2196F3; /* Blue */
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                color: white;
                }
                QPushButton:hover {
                background-color: #1976D2;
                }
                QPushButton:pressed {
                background-color: #0D47A1;
                }
            """)
            layout.addWidget(self.configure_procedure_button)
            
            # Connect procedure configuration button
            self.configure_procedure_button.clicked.connect(self._configure_procedure)

        # 5. Add Note button to add a note to the configuration
        self.add_note_button = QPushButton("Add Note")
        layout.addWidget(self.add_note_button)

        # Dynamic hardware-specific controls
        self.dynamic_controller = DynamicController(cfg, parent=self)
        layout.addWidget(self.dynamic_controller)
        # ------------------------------------------------------------------------------------- #

        # ============ Callback connections between widget values and functions ================ #

        self.directory_button.clicked.connect(self._select_directory)
        self.json_dropdown.currentIndexChanged.connect(self._update_config)
        self.record_button.clicked.connect(self.record)
        self.add_note_button.clicked.connect(self._add_note)
        
        # Connect dynamic controls using constants defined in DynamicController
        dynamic_buttons = [
            (DynamicController.LED_TEST_BTN, self._test_led),
            (DynamicController.STOP_BTN, self._stop_led),
            (DynamicController.SNAP_BTN, lambda: self._save_snapshot(self._mmc1.snap())),
            (DynamicController.PSYCHOPY_BTN, self.launch_psychopy),
        ]
        for btn_attr, handler in dynamic_buttons:
            if hasattr(self.dynamic_controller, btn_attr):
                getattr(self.dynamic_controller, btn_attr).clicked.connect(handler)

        # ------------------------------------------------------------------------------------- #

    # ============================== Public Class Methods ============================================ #

    def _save_snapshot(self, image: np.ndarray):
        """Creates a PyQt popup window for saving the snapped image."""
        from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
        from matplotlib.figure import Figure

        dialog = QDialog(self)
        dialog.setWindowTitle("Save Snapped Image")
        layout = QVBoxLayout(dialog)

        fig = Figure()
        canvas = FigureCanvas(fig)
        ax = fig.add_subplot(111)
        ax.imshow(image, cmap='gray')
        layout.addWidget(canvas)
        
        # Save button
        save_button = QPushButton("Save", dialog)
        layout.addWidget(save_button)

        save_button.clicked.connect(lambda: self._save_image(image, dialog))

        dialog.exec()

    def _save_image(self, image: np.ndarray, dialog: QDialog):
        """Save the snapped image to the specified directory with a unique filename."""

        # Generate a unique filename with a timestamp
        file_path = self.config.make_path(suffix="snapped", extension="png", bids_type="func")

        # Save the image as a PNG file using matplotlib
        import matplotlib.pyplot as plt

        plt.imsave(file_path, image, cmap='gray')

        # Close the dialog
        dialog.accept()    
    
    def record(self):
        """Run the experimental procedure or fallback to legacy MDA sequence."""
        
        # If a procedure is available, use it for the experimental workflow
        if self.procedure is not None:
            try:
                # Run the procedure in a separate thread to avoid blocking the GUI
                self.procedure_thread = threading.Thread(target=self.procedure.run())
                self.procedure_thread.start()
                
                # Signal that recording has started
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                self.recordStarted.emit(timestamp)
                return
            except Exception as e:
                QMessageBox.critical(self, "Procedure Error", f"Failed to run procedure: {str(e)}")
                return

    def launch_psychopy(self):
        """Launches a PsychoPy experiment as a subprocess with the current ExperimentConfig parameters."""
        # use PsychoPyProcess to manage handshake and subprocess
        self.psychopy_process = PsychoPyProcess(self.config, parent=self)
        self.psychopy_process.error.connect(self._on_psychopy_error)
        self.psychopy_process.start()

    def _on_psychopy_error(self, message):
        """Handle PsychoPyProcess error signal (e.g. handshake timeout)."""
        QMessageBox.critical(self, "PsychoPy Error", message)
    
    def _run_procedure(self):
        """Run the procedure in a separate thread."""
        try:
            self.procedure.run()
        except Exception as e:
            # Handle errors in the procedure execution
            # Since this runs in a thread, we need to emit a signal or use Qt's invokeMethod
            # For now, we'll print the error (in a real implementation, you'd want proper error handling)
            print(f"Procedure execution error: {e}")
            import traceback
            traceback.print_exc()
    
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space:
            self.event_loop.quit()
    
    def show_popup(self):
        msg_box = QMessageBox()
        msg_box.setText("PsychoPy is Ready:\n Press spacebar to start recording.")
        #msg_box.setStandardButtons(QMessageBox.Ok)
        msg_box.exec_()
    
    def save_config(self):
        """ Save the current configuration to a JSON file """
        self.config.save_parameters()
        
    #TODO: add breakdown method

    #-----------------------------------------------------------------------------------------------#
    
    #============================== Private Class Methods ==========================================#

    def _select_directory(self):
        """Open a dialog to select a directory and update the GUI accordingly."""
        directory = QFileDialog.getExistingDirectory(self, "Select Save Directory")
        if directory:
            self.directory_line_edit.setText(directory)
            self._get_json_file_choices(directory)

    def _get_json_file_choices(self, path):
        """Return a list of JSON files in the current directory."""
        import glob
        self.config.save_dir = path
        try:
            json_files = glob.glob(os.path.join(path, "*.json"))
            self.json_dropdown.clear()
            self.json_dropdown.addItems(json_files)
        except Exception as e:
            print(f"Error getting JSON files from directory: {path}\n{e}")

    def _update_config(self, index):
        """Update the experiment configuration from a new JSON file."""
        json_path_input = self.json_dropdown.currentText()

        if json_path_input and os.path.isfile(json_path_input):
            try:
                self.procedure.setup_configuration(json_path_input)
                # Rebuild table model to reflect new parameters
                self.config_table_model = ConfigTableModel(self.config)
                old_form = getattr(self, 'config_model', None)
                new_form = ConfigFormWidget(self.config)
                self.config_model = new_form
                if old_form:
                    layout = self.layout()
                    idx = layout.indexOf(old_form)
                    layout.insertWidget(idx, new_form)
                    layout.removeWidget(old_form)
                    old_form.deleteLater()
            except Exception as e:
                print(f"Trouble updating ExperimentConfig from AcquisitionEngine:\n{json_path_input}\nConfiguration not updated.")
                print(e) 

    def _test_led(self):
        """
        Test the LED pattern by sending a test sequence to the Arduino-Switch device.
        """
        try:
            led_pattern = self.config.led_pattern
            self.config.hardware.Dhyana.core.getPropertyObject('Arduino-Switch', 'State').loadSequence(led_pattern)
            self._mmc1.getPropertyObject('Arduino-Switch', 'State').loadSequence(led_pattern)
            self._mmc1.getPropertyObject('Arduino-Switch', 'State').setValue(4) # seems essential to initiate serial communication
            self._mmc1.getPropertyObject('Arduino-Switch', 'State').startSequence()
            print("LED test pattern sent successfully.")
        except Exception as e:
            print(f"Error testing LED pattern: {e}")
            
    def _stop_led(self):
        """
        Stop the LED pattern by sending a stop sequence to the Arduino-Switch device.
        """
        try:
            self._mmc1.getPropertyObject('Arduino-Switch', 'State').stopSequence()
            print("LED test pattern stopped successfully.")
        except Exception as e:
            print(f"Error stopping LED pattern: {e}")
    
    def _add_note(self):
        """
        Open a dialog to get a note from the user and save it to the ExperimentConfig.notes list.
        """
        time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        text, ok = QInputDialog.getText(self, 'Add Note', 'Enter your note:')
        if ok and text:
            note_with_timestamp = f"{time}: {text}"
            self.config.notes.append(note_with_timestamp)

    def _configure_procedure(self):
        """
        Open a dialog to configure procedure parameters.
        """
        if self.procedure is None:
            return
            
        # Create a simple configuration dialog
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QDialogButtonBox
        
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Configure {self.procedure.__class__.__name__}")
        dialog.setModal(True)
        
        layout = QVBoxLayout(dialog)
        
        # Add procedure configuration form if the procedure has a config
        if hasattr(self.procedure, 'config') and self.procedure.config:
            config_form = ConfigFormWidget(self.procedure.config)
            layout.addWidget(config_form)
        else:
            # Show a simple message if no configuration is available
            info_label = QLabel("This procedure has no configurable parameters.")
            layout.addWidget(info_label)
        
        # Add OK/Cancel buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        # Show the dialog
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Configuration changes are automatically applied through the form widget
            QMessageBox.information(self, "Configuration", "Procedure configuration updated.")

    def _on_registry_updated(self, key, value):
        """Callback to sync registry changes into ExperimentConfig._parameters."""
        try:
            self.config._parameters[key] = value
        except Exception:
            pass
        self.configUpdated.emit(self.config)

    # ----------------------------------------------------------------------------------------------- #




