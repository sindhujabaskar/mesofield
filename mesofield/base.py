"""
Base procedure classes for implementing experimental workflows in Mesofield.

This module provides base classes that implement the Procedure protocol and integrate
with the Mesofield configuration and hardware management systems.
"""

import os
from datetime import datetime

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Type

from mesofield.config import ExperimentConfig
from mesofield.hardware import HardwareManager
from mesofield.io.manager import DataManager
from mesofield.utils._logger import get_logger
from mesofield.io.writer import CustomWriter
from PyQt6.QtCore import QObject, pyqtSignal

class ProcedureSignals(QObject):
    """All procedure-level signals that a Qt GUI can connect to."""
    procedure_started      = pyqtSignal()
    hardware_initialized   = pyqtSignal(bool)     # success
    data_saved             = pyqtSignal()
    procedure_error        = pyqtSignal(str)      # emits error message
    procedure_finished     = pyqtSignal()
    
    
@dataclass 
class ProcedureConfig:
    """Configuration container for procedures."""
    experiment_id: str = "default_experiment"
    experimentor: str = "researcher"
    hardware_yaml: str = "hardware.yaml"
    data_dir: str = "./data"
    json_config: Optional[str] = None
    custom_parameters: Dict[str, Any] = field(default_factory=dict)


class Procedure:
    """High level class describing an experiment run in Mesofield."""

    def __init__(self, procedure_config: ProcedureConfig):
        self.events = ProcedureSignals()

        # Default parameters for a typical Mesofield experiment
        defaults = {"duration": 60, "start_on_trigger": False}
        procedure_config.custom_parameters = {
            **defaults,
            **procedure_config.custom_parameters,
        }

        self.experiment_id = procedure_config.experiment_id
        self.experimentor = procedure_config.experimentor
        self.hardware_yaml = procedure_config.hardware_yaml
        self.data_dir = procedure_config.data_dir
        self.h5_path = os.path.join(self.data_dir, f"{self.experiment_id}.h5")

        # Initialize configuration and apply custom parameters
        self._config = ExperimentConfig(self.hardware_yaml)
        for key, value in procedure_config.custom_parameters.items():
            self._config.set(key, value)

        self._config.set("experiment_id", self.experiment_id)
        self._config.set("experimentor", self.experimentor)
        self._config.set("data_dir", self.data_dir)
        self._config.set("h5_path", self.h5_path)

        if procedure_config.json_config:
            self.setup_configuration(procedure_config.json_config)

        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir, exist_ok=True)
        self._config.save_dir = self.data_dir

        self.logger = get_logger(f"PROCEDURE.{self.experiment_id}")
        self.logger.info(f"Initialized procedure: {self.experiment_id}")
        self.initialize_hardware()

    # ------------------------------------------------------------------
    # Convenience accessors
    @property
    def config(self) -> ExperimentConfig:
        return self._config

    @property
    def hardware(self) -> HardwareManager:
        return self._config.hardware

    # ------------------------------------------------------------------
    # Core business logic
    def initialize_hardware(self) -> None:
        """Set up all hardware and prepare data managers."""
        try:
            self._config.hardware.initialize_all()
            self._config.hardware._configure_engines(self._config)
            self.data_manager = DataManager()
            self.data_manager.set_config(self._config)
            self.data_manager.set_database(self.h5_path)
            for device in self._config.hardware.devices.values():
                if hasattr(device, "device_type") and hasattr(device, "get_data"):
                    self.data_manager.register_hardware_device(device)
            self.logger.info("Hardware initialized successfully")
            self.events.hardware_initialized.emit(True)
        except Exception as e:  # pragma: no cover - initialization failures
            self.logger.error(f"Failed to initialize hardware: {e}")
            self.events.hardware_initialized.emit(False)

    # ------------------------------------------------------------------
    def setup_configuration(self, json_config: Optional[str]) -> None:
        if json_config:
            self._config.load_json(json_config)
            self._config.hardware._configure_engines(self._config)

    # ------------------------------------------------------------------
    def run(self) -> None:
        """Run the standard Mesofield workflow."""
        self.logger.info("Starting experiment")
        try:
            recorders = []
            for cam in self.hardware.cameras:
                writer = (
                    self.data_manager.saver.writer_for(cam)
                    if self.data_manager.saver
                    else CustomWriter(self._config.make_path(cam.name, "ome.tiff", bids_type="func"))
                )
                if not hasattr(cam, "output_path"):
                    # ensure path attributes even when writer created directly
                    cam.output_path = writer._filename
                    cam.metadata_path = writer._frame_metadata_filename
                recorders.append((cam.core, self._config.build_sequence(cam), writer))
            self.hardware.cameras[0].core.mda.events.sequenceFinished.connect(self._cleanup_procedure)

            if self._config.get("start_on_trigger", False):
                self.psychopy_process = self._launch_psychopy()
                self.psychopy_process.start()

            self.start_time = datetime.now()
            self.start_encoder()
            for mmc, sequence, writer in recorders:
                mmc.run_mda(sequence, output=writer, block=False)
        except Exception as e:  # pragma: no cover - hardware errors
            self.logger.error(f"Error during experiment: {e}")
            raise

    # ------------------------------------------------------------------
    def save_data(self) -> None:
        import csv

        if hasattr(self, "data_manager") and getattr(self.data_manager, "saver", None):
            self.data_manager.saver.save_config()
            self.data_manager.saver.save_notes()
        else:
            self._config.save_configuration()
        timestamps_path = os.path.join(self._config.bids_dir, "timestamps.csv")
        with open(timestamps_path, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["device_id", "started", "stopped"])
            writer.writerow(["experiment_id", self.start_time, self.stopped_time])
            for device_id, device in self.hardware.devices.items():
                started = getattr(device, "_started", "")
                stopped = getattr(device, "_stopped", "")
                writer.writerow([device_id, started, stopped])

        self.logger.info("Data saved successfully")

    # ------------------------------------------------------------------
    def cleanup(self) -> None:
        try:
            self._config.hardware.close_all()
            self.logger.info("Cleanup completed successfully")
        except Exception as e:  # pragma: no cover - cleanup failures
            self.logger.error(f"Error during cleanup: {e}")

    # ------------------------------------------------------------------
    def _launch_psychopy(self):
        from mesofield.subprocesses.psychopy import PsychoPyProcess
        return PsychoPyProcess(self._config)

    def _wait_for_trigger(self):
        self.logger.info("Waiting for trigger...")
        input("Press Enter to start recording...")

    def _cleanup_procedure(self):
        self.logger.info("Cleanup Procedure")
        try:
            if hasattr(self, "psychopy_process"):
                del self.psychopy_process
            self.stop_cameras()
            self.stop_encoder()
            self.stopped_time = datetime.now()
            self.save_data()
            if hasattr(self, "data_manager"):
                self.data_manager.update_database()
            self.cleanup()
        except Exception as e:  # pragma: no cover - cleanup failure
            self.logger.error(f"Error during cleanup: {e}")

    # ------------------------------------------------------------------
    def start_cameras(self) -> bool:
        try:
            for camera in self.hardware.cameras:
                if hasattr(camera, "start"):
                    camera.start()
            return True
        except Exception as e:
            self.logger.error(f"Failed to start cameras: {e}")
            return False

    def stop_cameras(self) -> bool:
        try:
            for camera in self.hardware.cameras:
                if hasattr(camera, "stop"):
                    camera.stop()
            return True
        except Exception as e:
            self.logger.error(f"Failed to stop cameras: {e}")
            return False

    def start_encoder(self) -> bool:
        try:
            encoder = self.hardware.get_encoder()
            if encoder and hasattr(encoder, "start_recording"):
                path = self._config.make_path(encoder.device_id, "csv", "beh")
                encoder.output_path = path
                encoder.start_recording(path)
                return True
            return False
        except Exception as e:
            self.logger.error(f"Failed to start encoder: {e}")
            return False

    def stop_encoder(self) -> bool:
        try:
            encoder = self.hardware.get_encoder()
            if encoder and hasattr(encoder, "stop"):
                encoder.stop()
                return True
            return False
        except Exception as e:
            self.logger.error(f"Failed to stop encoder: {e}")
            return False

    def add_note(self, note: str) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._config.notes.append(f"{timestamp}: {note}")
        self.logger.info(f"Added note: {note}")



    def load_database(self, key: str = "data"):
        """Return a DataFrame with all sessions stored for this Procedure."""
        if hasattr(self, "data_manager"):
            return self.data_manager.read_database(key)
        return None




# Factory function for creating procedures
def create_procedure(procedure_class: Type[Procedure],
                    experiment_id: str = "default",
                    experimentor: str = "researcher",
                    hardware_yaml: str = "hardware.yaml",
                    data_dir: str = "./data",
                    json_config: Optional[str] = None,
                    **custom_parameters) -> Procedure:
    """
    Factory function to create procedure instances.
    
    Args:
        procedure_class: The procedure class to instantiate
        experiment_id: Unique identifier for the experiment
        experimentor: Name of the person running the experiment
        hardware_yaml: Path to hardware configuration file
        data_dir: Directory for saving data
        json_config: Optional JSON configuration file
        **custom_parameters: Additional custom parameters
    
    Returns:
        Instance of the specified procedure class
    """
    config = ProcedureConfig(
        experiment_id=experiment_id,
        experimentor=experimentor,
        hardware_yaml=hardware_yaml,
        data_dir=data_dir,
        json_config=json_config,
        custom_parameters=custom_parameters
    )
    
    return procedure_class(config)


# Legacy constants for backward compatibility
NAME = "mesofield"
