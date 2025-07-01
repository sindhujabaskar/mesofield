import os
import json
import datetime
from typing import Dict, Any, List, Optional, Type, TypeVar, Callable

import pandas as pd
import useq
from useq import TIntervalLoops

from mesofield.hardware import HardwareManager
from mesofield.protocols import DataProducer
from mesofield.utils._logger import get_logger

T = TypeVar('T')

# Configuration Registry pattern
class ConfigRegister:
    """A registry that maintains configuration values with optional type validation."""
    
    def __init__(self):
        self._registry: Dict[str, Any] = {}
        self._metadata: Dict[str, Dict[str, Any]] = {}
        self._callbacks: Dict[str, List[Callable[[str, Any], None]]] = {}
    
    def register(self, key: str, default: Any = None, 
                type_hint: Optional[Type] = None, 
                description: str = "", 
                category: str = "general") -> None:
        """Register a configuration parameter with metadata."""
        self._registry[key] = default
        self._metadata[key] = {
            "type": type_hint,
            "description": description,
            "category": category
        }
        self._callbacks[key] = []
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value."""
        return self._registry.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """Set a configuration value with type validation."""
        # Register the key if it doesn't exist
        if key not in self._registry:
            self.register(key, value)
        
        # Validate type if type hint exists
        type_hint = self._metadata.get(key, {}).get("type")
        if type_hint and not isinstance(value, type_hint):
            try:
                # Attempt type conversion
                value = type_hint(value)
            except (ValueError, TypeError):
                raise TypeError(f"Invalid type for {key}. Expected {type_hint.__name__}, got {type(value).__name__}")
        
        # Update value
        self._registry[key] = value
        
        # Trigger callbacks
        for callback in self._callbacks.get(key, []):
            callback(key, value)
    
    def has(self, key: str) -> bool:
        """Check if a key exists in the registry."""
        return key in self._registry
    
    def keys(self) -> List[str]:
        """Get all registered keys."""
        return list(self._registry.keys())
    
    def items(self) -> Dict[str, Any]:
        """Get all key-value pairs."""
        return self._registry.copy()
    
    def get_metadata(self, key: str) -> Dict[str, Any]:
        """Get metadata for a key."""
        return self._metadata.get(key, {})
    
    def register_callback(self, key: str, callback: Callable[[str, Any], None]) -> None:
        """Register a callback for when a key's value changes."""
        if key not in self._callbacks:
            self._callbacks[key] = []
        self._callbacks[key].append(callback)
    
    
    def clear(self) -> None:
        """Clear all configurations."""
        self._registry.clear()


class ExperimentConfig(ConfigRegister):
    """## Generate and store parameters using a configuration registry. 
    
    #### Example Usage:
    ```python
    config = ExperimentConfig()
    # create dict and pandas DataFrame from JSON file path:
    config.load_parameters('path/to/json_file.json')
        
    config._save_dir = './output'
    config.subject = '001'
    config.task = 'TestTask'
    config.notes.append('This is a test note.')

    # Update a parameter
    config.update_parameter('new_param', 'test_value')

    # Save parameters and notes
    config.save_parameters()
    ```
    """

    def __init__(self, path: str):
        super().__init__()
        # Initialize logging first
        self.logger = get_logger(__name__)
        self.logger.info(f"Initializing ExperimentConfig with hardware path: {path}")
        
        # Initialize the configuration registry
        self._json_file_path = ''
        self._save_dir = ''
        self._parameters: dict = {}  # NOTE: For backward compatibility

        # Register common configuration parameters with defaults and types
        self._register_default_parameters()
        self.logger.debug("Registered default parameters")

        # Initialize hardware
        try:
            self.hardware = HardwareManager(path)
        except Exception as e:
            self.logger.error(f"Failed to initialize hardware: {e}")
            raise
        
        self.notes: list = []

    def _register_default_parameters(self):
        """Register default parameters in the registry."""
        # Core experiment parameters
        self.register("subject", "sub", str, "Subject identifier", "experiment")
        self.register("session", "ses", str, "Session identifier", "experiment")
        self.register("task", "task", str, "Task identifier", "experiment")
        self.register("start_on_trigger", False, bool, "Whether to start acquisition on trigger", "hardware")
        self.register("duration", 60, int, "Sequence duration in seconds", "experiment")
        self.register("trial_duration", None, int, "Trial duration in seconds", "experiment")
        self.register("led_pattern", ['4', '4'], list, "LED pattern sequence", "hardware")
        self.register("psychopy_filename", "experiment.py", str, "PsychoPy experiment filename", "experiment")

    @property
    def _cores(self):# -> tuple[CMMCorePlus, ...]:
        """Return the tuple of CMMCorePlus instances from the hardware cameras."""
        return tuple(cam.core for cam in self.hardware.cameras if hasattr(cam, 'core'))

    @property
    def save_dir(self) -> str:
        """Get the save directory."""
        return os.path.join(self._save_dir, 'data')

    @save_dir.setter
    def save_dir(self, path: str):
        """Set the save directory."""
        if isinstance(path, str):
            self._save_dir = os.path.abspath(path)
        else:
            print(f"ExperimentConfig: \n Invalid save directory path: {path}")

    @property
    def subject(self) -> str:
        """Get the subject ID."""
        return self.get("subject", self._parameters.get('subject', 'sub'))

    @property
    def session(self) -> str:
        """Get the session ID."""
        return self.get("session", self._parameters.get('session', 'ses'))

    @property
    def task(self) -> str:
        """Get the task ID."""
        return self.get("task", self._parameters.get('task', 'task'))

    @property
    def start_on_trigger(self) -> bool:
        """Get whether to start on trigger."""
        return self.get("start_on_trigger", self._parameters.get('start_on_trigger', False))
    
    @property
    def sequence_duration(self) -> int:
        """Get the sequence duration in seconds."""
        return int(self.get("duration", self._parameters.get('duration', 60)))
    
    @property
    def trial_duration(self) -> int:
        """Get the trial duration in seconds."""
        return int(self.get("trial_duration", self._parameters.get('trial_duration', None)))
        
    @property
    def num_trials(self) -> int:
        """Calculate the number of trials."""
        return int(self.get("num_trials", self._parameters.get('num_trials', 1)))
    
    
    def build_sequence(self, camera: DataProducer) -> useq.MDASequence:
        if self.has('num_meso_frames'):
            loops = int(self.get('num_meso_frames'))
        else:
            try:
                loops = int(camera.sampling_rate * self.sequence_duration)
            except Exception:
                loops = 5
            metadata = self.hardware.__dict__

        # convert to a datetime.timedelta and build the time_plan
        time_plan = TIntervalLoops(
            interval=0,
            loops=loops,
            prioritize_duration=False
        )
        return useq.MDASequence(metadata=metadata, time_plan=time_plan)
    
    @property
    def bids_dir(self) -> str:
        """ Dynamic construct of BIDS directory path """
        bids = os.path.join(
            f"sub-{self.subject}",
            f"ses-{self.session}",
        )
        return os.path.abspath(os.path.join(self.save_dir, bids))

    
    @property
    def dataframe(self):
        """Convert parameters to a pandas DataFrame."""
        # Combine registry and legacy parameters
        combined_params = self.items()
        combined_params.update(self._parameters)
        
        data = {'Parameter': list(combined_params.keys()),
                'Value': list(combined_params.values())}
        return pd.DataFrame(data)
    
    @property
    def psychopy_filename(self) -> str:
        """Get the PsychoPy experiment filename."""
        # py_files = list(pathlib.Path(self._save_dir).glob('*.py'))
        # if py_files:
        #     return py_files[0].name
        # else:
        #     warnings.warn(f'No Psychopy experiment file found in directory {pathlib.Path(self.save_dir).parent}.')
        return self.get("psychopy_filename", self._parameters.get('psychopy_filename', 'experiment.py'))

    @property
    def psychopy_path(self) -> str:
        """Get the PsychoPy script path."""
        return os.path.join(self._save_dir, self.psychopy_filename)
    
    @property
    def psychopy_save_path(self) -> str:
        """Get the PsychoPy save path."""
        return os.path.join(self._save_dir, f"data/sub-{self.subject}/ses-{self.session}/beh/{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_sub-{self.subject}_ses-{self.session}_task-{self.task}_psychopy")
    
    @property
    def psychopy_parameters(self) -> dict:
        """Get parameters for PsychoPy."""
        return {
            'subject': self.subject,
            'session': self.session,
            'save_dir': self.save_dir,
            'num_trials': self.num_trials,
            'save_path': self.psychopy_save_path
        }
    
    @property
    def led_pattern(self) -> list[str]:
        """Get the LED pattern."""
        return self.get("led_pattern", self._parameters.get('led_pattern', ['4', '4', '2', '2']))
    
    @led_pattern.setter
    def led_pattern(self, value: list) -> None:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                raise ValueError("led_pattern string must be a valid JSON list")
        if isinstance(value, list):
            value_str = [str(item) for item in value]
            self.set("led_pattern", value_str)
            self._parameters['led_pattern'] = value_str  # For backward compatibility
        else:
            raise ValueError("led_pattern must be a list or a JSON string representing a list")
    
    # Helper method to generate a unique file path
    def make_path(self, suffix: str, extension: str, bids_type: Optional[str] = None, create_dir: bool = False):
        """ Example:
        ```py
            ExperimentConfig._generate_unique_file_path("images", "jpg", "func")
            print(unique_path)
        ```
        Output:
            C:/save_dir/data/sub-id/ses-id/func/20250110_123456_sub-001_ses-01_task-example_images.jpg
        """
        file = f"{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_sub-{self.subject}_ses-{self.session}_task-{self.task}_{suffix}.{extension}"

        if bids_type is None:
            bids_path = self.bids_dir
        else:
            bids_path = os.path.join(self.bids_dir, bids_type)

        if create_dir:
            os.makedirs(bids_path, exist_ok=True)
        base, ext = os.path.splitext(file)
        counter = 1
        file_path = os.path.join(bids_path, file)
        while os.path.exists(file_path):
            file_path = os.path.join(bids_path, f"{base}_{counter}{ext}")
            counter += 1
        return file_path
        
    def load_json(self, file_path) -> None:
        """ Load parameters from a JSON configuration file into the config object. 
        """
        self.logger.info(f"Loading configuration from: {file_path}")
        try:
            with open(file_path, 'r') as f:
                self._parameters = json.load(f)
            self.logger.info(f"Successfully loaded {len(self._parameters)} parameters from JSON")
        except FileNotFoundError:
            self.logger.error(f"Configuration file not found: {file_path}")
            return 
        except json.JSONDecodeError as e:
            self.logger.error(f"Error decoding JSON from {file_path}: {e}")
            return
            
        self._json_file_path = file_path #store the json filepath
        #TODO: set output_paths for all devices using the `make_path` method 

        # Update the registry and legacy parameters
        for key, value in self._parameters.items():
            self.set(key, value)
            self._parameters[key] = value  # NOTE: For backward compatibility
                    
        
    def register_parameter(self, key, default=None, type_hint=None, description="", category="general"):
        """Register a new parameter with metadata.
        
        Args:
            key: Parameter key
            default: Default value
            type_hint: Type of the parameter
            description: Description of the parameter
            category: Category for the parameter
        """
        self.register(key, default, type_hint, description, category)
        if default is not None:
            self._parameters[key] = default  # For backward compatibility

