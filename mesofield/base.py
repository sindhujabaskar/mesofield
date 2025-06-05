"""
Base procedure classes for implementing experimental workflows in Mesofield.

This module provides base classes that implement the Procedure protocol and integrate
with the Mesofield configuration and hardware management systems.
"""

import os
import abc
from datetime import datetime

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Type, List

from mesofield.config import ExperimentConfig
from mesofield.hardware import HardwareManager
from mesofield.io.manager import DataManager, CSVConsumer
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



class BaseProcedure(abc.ABC):
    """
    Base implementation of the Procedure protocol that integrates with Mesofield.
    
    This class provides a foundation for creating custom experimental procedures
    that work seamlessly with Mesofield's hardware management and GUI systems.
    """
    
    def __init__(self, procedure_config: ProcedureConfig):
        self.events = ProcedureSignals()
        
        self.experiment_id = procedure_config.experiment_id
        self.experimentor = procedure_config.experimentor
        self.hardware_yaml = procedure_config.hardware_yaml
        self.data_dir = procedure_config.data_dir
        
        # Initialize the ExperimentConfig with hardware
        self._config = ExperimentConfig(self.hardware_yaml)
        # Add custom parameters to the registry
        for key, value in procedure_config.custom_parameters.items():
            self.config.set(key, value)
        
        # Add procedure-specific parameters
        self.config.set("experiment_id", self.experiment_id)
        self.config.set("experimentor", self.experimentor)
        self.config.set("data_dir", self.data_dir)
        
        # Load JSON configuration if provided 
        if procedure_config.json_config:
            self.setup_configuration(procedure_config.json_config)
        
        # Set data directory 
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir, exist_ok=True)
        self.config.save_dir = self.data_dir
        self.logger = get_logger(f"PROCEDURE.{self.experiment_id}")
        self.logger.info(f"Initialized procedure: {self.experiment_id}")
    
    @property
    def config(self) -> ExperimentConfig:
        """Access to the underlying ExperimentConfig instance."""
        return self._config
    
    @property
    def hardware(self) -> HardwareManager:
        """Access to the hardware manager."""
        return self._config.hardware
        
    def initialize_hardware(self):
        """Setup the experiment procedure hardware.
        
        Returns:
            bool: True if setup was successful, False otherwise.
        """
        try:
            # Initialize all hardware devices
            self.config.hardware.initialize_all()
            
            # Configure engines if using micromanager cameras
            self.config.hardware._configure_engines(self.config)
            
            # Initialize data manager
            self.data_manager = DataManager()
            
            # Register hardware devices with data manager
            registered_count = 0
            for device_id, device in self.config.hardware.devices.items():
                if hasattr(device, 'device_type') and hasattr(device, 'get_data'):
                    self.data_manager.register_hardware_device(device)
                    csv_path = self.config.make_path(device_id, 'csv', 'beh')
                    consumer = CSVConsumer(csv_path, [getattr(device, 'device_type', '*')])
                    self.data_manager.register_consumer(consumer)
                    registered_count += 1
            
            self.logger.info("Hardware initialized successfully")
            self.events.hardware_initialized.emit(True)
        except Exception as e:
            self.logger.error(f"Failed to initialize hardware: {e}")
            self.events.hardware_initialized.emit(False)

    
    def setup_configuration(self, json_config: Optional[str]) -> None:
        """Set up the configuration for the experiment procedure."""

    
    def save_data(self) -> None:
        """Save data from the experiment."""

    
    def cleanup(self) -> None:
        """Clean up after the experiment procedure."""
        try:
            # Stop and cleanup all hardware
            self.config.hardware.close_all()
            self.logger.info("Cleanup completed successfully")
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
    
    @abc.abstractmethod
    def run(self) -> None:
        """Run the experiment procedure. Must be implemented by subclasses."""
        pass
    



class MesofieldProcedure(BaseProcedure):
    """
    Default Mesofield procedure that provides standard experimental workflow.
    
    This procedure implements a typical neuroscience experiment workflow:
    1. Initialize hardware
    2. Start data acquisition (cameras, encoder)
    3. Optionally launch PsychoPy stimulus
    4. Record for specified duration
    5. Stop acquisition and save data
    """
    
    def __init__(self, procedure_config: ProcedureConfig):
        # Add default parameters for standard Mesofield experiments
        default_params = {
            "duration": 60,  # seconds
            "start_on_trigger": False,
        }
        
        # Merge with any custom parameters
        procedure_config.custom_parameters = {**default_params, **procedure_config.custom_parameters}
        
        super().__init__(procedure_config)
    
    def setup_configuration(self, json_config: Optional[str]):
        try:
            self.config.load_json(json_config)
            self.logger.info(f"Loaded configuration from: {json_config}")
            self.logger.info(f"Sending configuration to MMCore engines: {self.config.__dict__}")
            self.config.hardware._configure_engines(self.config)
        except Exception as e:
            self.logger.error(f"Failed to load configuration from {json_config}: {e}")
            raise
    
    def run(self) -> None:
        """Run the standard Mesofield experiment procedure."""
        self.logger.info("Starting Mesofield experiment procedure")
        
        try:
            recorders = [
                (
                    cam.core,
                    self.config.build_sequence(cam),
                    CustomWriter(
                        self.config.make_path(cam.name, "ome.tiff", bids_type="func")
                    )
                )
                for cam in self.hardware.cameras
            ]
            self.hardware.cameras[0].core.mda.events.sequenceFinished.connect(self._cleanup_procedure)
            
            # Optionally launch PsychoPy trigger
            if self.config.get("start_on_trigger", False):
                self.psychopy_process = self._launch_psychopy()
                self.psychopy_process.start()
            self.start_time = datetime.now()

            # Start all registered data streams
            self.data_manager.start_all()

            # Start cameras via MDA sequences
            for mmc, sequence, writer in recorders:
                mmc.run_mda(sequence, output=writer, block=False)

            
        except Exception as e:
            self.logger.error(f"Error during experiment: {e}")
            raise
        
    def save_data(self) -> None:
        import csv

        try:
            # Save configuration parameters
            self.config.save_configuration()
            timestamps_path = os.path.join(self.config.bids_dir, "timestamps.csv")
            with open(timestamps_path, "w", newline="") as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(["device_id", "started", "stopped"])
                writer.writerow(["experiment_id", self.start_time, self.stopped_time])
                for device_id, device in self.hardware.devices.items():
                    started = getattr(device, "_started", "")
                    stopped = getattr(device, "_stopped", "")
                    writer.writerow([device_id, started, stopped])
                    
            # Save any notes
            if self.config.notes:
                notes_path = os.path.join(self.data_dir, "experiment_notes.txt")
                with open(notes_path, 'w') as f:
                    for note in self.config.notes:
                        f.write(f"{note}\n")

            # Export buffered stream data to CSV files
            self.data_manager.export_all_to_directory(self.config.bids_dir)

            self.logger.info("Data saved successfully")
        except Exception as e:
            self.logger.error(f"Failed to save data: {e}")
            
            raise
        
    def _launch_psychopy(self):
        """Launch PsychoPy subprocess if configured."""
        from mesofield.subprocesses.psychopy import PsychoPyProcess
        proc = PsychoPyProcess(self.config)
        return proc

    
    def _wait_for_trigger(self):
        """Wait for external trigger to start recording."""
        self.logger.info("Waiting for trigger...")

        input("Press Enter to start recording...")
    
    def _cleanup_procedure(self):
        """Cleanup after the procedure."""
        self.logger.info("Cleanup Procedure")

        try:
            if hasattr(self, "psychopy_process"):
                del(self.psychopy_process)
            self.stop_cameras()
            self.data_manager.stop_all()
            self.stop_encoder()
            self.stopped_time = datetime.now()
            self.save_data()
            self.data_manager.close_consumers()
            self.cleanup()
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
    
    def start_cameras(self) -> bool:
        """Start all camera devices."""
        try:
            for camera in self.config.hardware.cameras:
                if hasattr(camera, 'start'):
                    camera.start()
            return True
        except Exception as e:
            self.logger.error(f"Failed to start cameras: {e}")
            return False
    
    def stop_cameras(self) -> bool:
        """Stop all camera devices."""
        try:
            for camera in self.config.hardware.cameras:
                if hasattr(camera, 'stop'):
                    camera.stop()
            return True
        except Exception as e:
            self.logger.error(f"Failed to stop cameras: {e}")
            return False
    
    def start_encoder(self) -> bool:
        """Start the encoder device if available."""
        try:
            encoder = self.config.hardware.get_encoder()
            if encoder:
                return self.data_manager.start_stream(encoder.device_id)
            return False
        except Exception as e:
            self.logger.error(f"Failed to start encoder: {e}")
            return False
    
    def stop_encoder(self) -> bool:
        """Stop the encoder device if available."""
        try:
            encoder = self.config.hardware.get_encoder()
            if encoder:
                return self.data_manager.stop_stream(encoder.device_id)
            return False
        except Exception as e:
            self.logger.error(f"Failed to stop encoder: {e}")
            return False
    
    def add_note(self, note: str) -> None:
        """Add a timestamped note to the experiment."""
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        timestamped_note = f"{timestamp}: {note}"
        self.config.notes.append(timestamped_note)
        self.logger.info(f"Added note: {note}")

# Factory function for creating procedures
def create_procedure(procedure_class: Type[BaseProcedure], 
                    experiment_id: str = "default",
                    experimentor: str = "researcher",
                    hardware_yaml: str = "hardware.yaml",
                    data_dir: str = "./data",
                    json_config: Optional[str] = None,
                    **custom_parameters) -> BaseProcedure:
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
