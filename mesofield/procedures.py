"""
Base procedure classes for implementing experimental workflows in Mesofield.

This module provides base classes that implement the Procedure protocol and integrate
with the Mesofield configuration and hardware management systems.
"""

import os
import json
import abc
import logging
from typing import Dict, Any, Optional, Type, List
from dataclasses import dataclass, field

from mesofield.protocols import Procedure, Configurator
from mesofield.config import ExperimentConfig, ConfigRegister


logger = logging.getLogger(__name__)


@dataclass 
class ProcedureConfig:
    """Configuration container for procedures."""
    experiment_id: str = "default_experiment"
    experimentor: str = "researcher"
    hardware_yaml: str = "hardware.yaml"
    data_dir: str = "./data"
    json_config: Optional[str] = None
    custom_parameters: Dict[str, Any] = field(default_factory=dict)


class ConfiguratorAdapter:
    """Adapter to make ExperimentConfig._registry compatible with Configurator protocol."""
    
    def __init__(self, registry: ConfigRegister):
        self._registry = registry
    
    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a configuration value for the given key."""
        try:
            return self._registry.get_value(key)
        except KeyError:
            return default
    
    def set(self, key: str, value: Any) -> None:
        """Set a configuration value for the given key."""
        # Get the current parameter info to preserve type and category
        try:
            current_info = self._registry._parameters[key]
            param_type = current_info['type']
            category = current_info['category']
            description = current_info['description']
        except KeyError:
            # If key doesn't exist, use defaults
            param_type = type(value)
            category = "custom"
            description = f"Custom parameter: {key}"
        
        self._registry.register(key, value, param_type, description, category)
    
    def has(self, key: str) -> bool:
        """Check if the configuration contains the given key."""
        return key in self._registry._parameters
    
    def keys(self) -> List[str]:
        """Get all configuration keys."""
        return list(self._registry._parameters.keys())
    
    def items(self) -> Dict[str, Any]:
        """Get all configuration key-value pairs."""
        return {key: self._registry.get_value(key) for key in self._registry._parameters.keys()}


class BaseProcedure(abc.ABC):
    """
    Base implementation of the Procedure protocol that integrates with Mesofield.
    
    This class provides a foundation for creating custom experimental procedures
    that work seamlessly with Mesofield's hardware management and GUI systems.
    """
    
    def __init__(self, procedure_config: ProcedureConfig):
        self.experiment_id = procedure_config.experiment_id
        self.experimentor = procedure_config.experimentor
        self.hardware_yaml = procedure_config.hardware_yaml
        self.data_dir = procedure_config.data_dir
        
        # Initialize the ExperimentConfig with hardware
        self._experiment_config = ExperimentConfig(self.hardware_yaml)
        
        # Create a configurator adapter
        self.config = ConfiguratorAdapter(self._experiment_config._registry)
        
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
        self._experiment_config.save_dir = self.data_dir
        
        logger.info(f"Initialized procedure: {self.experiment_id}")
    
    @property
    def experiment_config(self) -> ExperimentConfig:
        """Access to the underlying ExperimentConfig instance."""
        return self._experiment_config
    
    def initialize_hardware(self) -> bool:
        """Setup the experiment procedure hardware.
        
        Returns:
            bool: True if setup was successful, False otherwise.
        """
        try:
            # Initialize all hardware devices
            self._experiment_config.hardware.initialize_all()
            
            # Configure engines if using micromanager cameras
            self._experiment_config.hardware._configure_engines(self._experiment_config)
            
            logger.info("Hardware initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize hardware: {e}")
            return False
    
    def setup_configuration(self, json_config: str) -> None:
        """Set up the configuration for the experiment procedure.
        
        Args:
            json_config: Path to a JSON configuration file (.json)
        """
        try:
            self._experiment_config.load_json(json_config)
            logger.info(f"Loaded configuration from: {json_config}")
        except Exception as e:
            logger.error(f"Failed to load configuration from {json_config}: {e}")
            raise
    
    def save_data(self) -> None:
        """Save data from the experiment."""
        try:
            # Save configuration parameters
            self._experiment_config.save_configuration()
            
            # Save any notes
            if self._experiment_config.notes:
                notes_path = os.path.join(self.data_dir, "experiment_notes.txt")
                with open(notes_path, 'w') as f:
                    for note in self._experiment_config.notes:
                        f.write(f"{note}\n")
            
            logger.info("Data saved successfully")
        except Exception as e:
            logger.error(f"Failed to save data: {e}")
            raise
    
    def cleanup(self) -> None:
        """Clean up after the experiment procedure."""
        try:
            # Stop and cleanup all hardware
            self._experiment_config.hardware.close_all()
            logger.info("Cleanup completed successfully")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
    @abc.abstractmethod
    def run(self) -> None:
        """Run the experiment procedure. Must be implemented by subclasses."""
        pass
    
    # Additional helper methods for common experimental tasks
    
    def start_cameras(self) -> bool:
        """Start all camera devices."""
        try:
            for camera in self._experiment_config.hardware.cameras:
                if hasattr(camera, 'start'):
                    camera.start()
            return True
        except Exception as e:
            logger.error(f"Failed to start cameras: {e}")
            return False
    
    def stop_cameras(self) -> bool:
        """Stop all camera devices."""
        try:
            for camera in self._experiment_config.hardware.cameras:
                if hasattr(camera, 'stop'):
                    camera.stop()
            return True
        except Exception as e:
            logger.error(f"Failed to stop cameras: {e}")
            return False
    
    def start_encoder(self) -> bool:
        """Start the encoder device if available."""
        try:
            encoder = self._experiment_config.hardware.get_encoder()
            if encoder and hasattr(encoder, 'start_recording'):
                encoder.start_recording(self._experiment_config.make_path('treadmill_data', 'csv', 'beh'))
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to start encoder: {e}")
            return False
    
    def stop_encoder(self) -> bool:
        """Stop the encoder device if available."""
        try:
            encoder = self._experiment_config.hardware.get_encoder()
            if encoder and hasattr(encoder, 'stop'):
                encoder.stop()
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to stop encoder: {e}")
            return False
    
    def add_note(self, note: str) -> None:
        """Add a timestamped note to the experiment."""
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        timestamped_note = f"{timestamp}: {note}"
        self._experiment_config.notes.append(timestamped_note)
        logger.info(f"Added note: {note}")


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
            "use_psychopy": False,
            "auto_start_cameras": True,
            "auto_start_encoder": True,
        }
        
        # Merge with any custom parameters
        procedure_config.custom_parameters = {**default_params, **procedure_config.custom_parameters}
        
        super().__init__(procedure_config)
    
    def run(self) -> None:
        """Run the standard Mesofield experiment procedure."""
        logger.info("Starting Mesofield experiment procedure")
        
        try:
            # Initialize hardware
            if not self.initialize_hardware():
                raise RuntimeError("Failed to initialize hardware")
            
            # Start data acquisition
            if self.config.get("auto_start_cameras", True):
                self.start_cameras()
            
            if self.config.get("auto_start_encoder", True):
                self.start_encoder()
            
            # Launch PsychoPy if enabled
            psychopy_process = None
            if self.config.get("use_psychopy", False):
                psychopy_process = self._launch_psychopy()
            
            # Wait for trigger if enabled
            if self.config.get("start_on_trigger", False):
                self._wait_for_trigger()
            
            # Record for specified duration
            duration = self.config.get("duration", 60)
            logger.info(f"Recording for {duration} seconds")
            
            # TODO: Implement actual recording logic here
            # This would involve starting MDA sequences, monitoring data acquisition, etc.
            import time
            time.sleep(duration)
            
            logger.info("Recording completed")
            
        except Exception as e:
            logger.error(f"Error during experiment: {e}")
            raise
        
        finally:
            # Cleanup
            self._cleanup_procedure()
    
    def _launch_psychopy(self):
        """Launch PsychoPy subprocess if configured."""
        try:
            from mesofield.subprocesses.psychopy import PsychoPyProcess
            psychopy_process = PsychoPyProcess(self._experiment_config)
            psychopy_process.start()
            return psychopy_process
        except Exception as e:
            logger.error(f"Failed to launch PsychoPy: {e}")
            return None
    
    def _wait_for_trigger(self):
        """Wait for external trigger to start recording."""
        logger.info("Waiting for trigger...")
        # TODO: Implement trigger waiting logic
        # This could be spacebar press, external signal, etc.
        input("Press Enter to start recording...")
    
    def _cleanup_procedure(self):
        """Cleanup after the procedure."""
        try:
            self.stop_cameras()
            self.stop_encoder()
            self.save_data()
            self.cleanup()
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")


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
