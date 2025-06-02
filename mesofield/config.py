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
    
    def unregister_callback(self, key: str, callback: Callable[[str, Any], None]) -> None:
        """Unregister a callback."""
        if key in self._callbacks and callback in self._callbacks[key]:
            self._callbacks[key].remove(callback)
    
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
        self._output_path = ''
        self._save_dir = ''
        self._parameters: dict = {}  # NOTE: For backward compatibility

        # Register common configuration parameters with defaults and types
        self._register_default_parameters()
        self.logger.debug("Registered default parameters")

        # Initialize hardware
        try:
            self.hardware = HardwareManager(path)
            self.logger.info(f"Hardware initialized with {len(self.hardware.devices)} devices")
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
        return int(self._parameters.get('num_trials', 1))
    
    @property
    def parameters(self) -> dict:
        """Get all parameters as a dictionary."""
        # Merge registry with legacy parameters for backward compatibility
        params = self.items()
        params.update(self._parameters)
        return params
    
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
    def notes_file_path(self):
        """Get the notes file path."""
        return self.make_path(suffix="notes", extension="txt")
    
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
    def make_path(self, suffix: str, extension: str, bids_type: str = None):
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
        
        # Update the registry and legacy parameters
        for key, value in self._parameters.items():
            self.set(key, value)
            self._parameters[key] = value  # NOTE: For backward compatibility
                
    def update_parameter(self, key, value) -> None:
        """Update a parameter in both registry and legacy dictionary."""
        self.set(key, value)
        self._parameters[key] = value  # NOTE: For backward compatibility
        
    def list_parameters(self) -> pd.DataFrame:
        """ Create a DataFrame from the ExperimentConfig properties """
        properties = [prop for prop in dir(self.__class__) if isinstance(getattr(self.__class__, prop), property)]
        exclude_properties = {'dataframe', 'parameters', 'json_path', "_cores", "meso_sequence", "pupil_sequence", "psychopy_path", "encoder"}
        data = {prop: getattr(self, prop) for prop in properties if prop not in exclude_properties}
        return pd.DataFrame(data.items(), columns=['Parameter', 'Value'])
                
    def save_wheel_encoder_data(self, data):
        """ Save the wheel encoder data to a CSV file """
        if isinstance(data, list):
            data = pd.DataFrame(data)
        encoder_path = self.make_path(suffix="encoder-data", extension="csv", bids_type='beh')
        try:
            data.to_csv(encoder_path, index=False)
            print(f"Encoder data saved to {encoder_path}")        
        except Exception as e:
            print(f"Error saving encoder data: {e}")
            
    def save_configuration(self):
        """ Save the configuration parameters from the registry to a CSV file """
        self.logger.info("Saving configuration and notes")
        params_path = self.make_path(suffix="configuration", extension="csv")
        try:
            # Get all parameters from the registry
            registry_items = self.items()
            params_df = pd.DataFrame(list(registry_items.items()), columns=['Parameter', 'Value'])
            params_df.to_csv(params_path, index=False)
            self.logger.info(f"Configuration saved to {params_path}")
        except Exception as e:
            self.logger.error(f"Error saving configuration: {e}")
        
        notes_path = self.make_path(suffix="notes", extension="txt")
        try:
            with open(notes_path, 'w') as f:
                f.write('\n'.join(self.notes))
                self.logger.info(f"Notes saved to {notes_path}")
        except Exception as e:
            self.logger.error(f"Error saving notes: {e}")
    
    def save_parameters(self, file_path=None):
        """Save parameters to a file (JSON or YAML based on extension)."""
        if file_path is None:
            file_path = self._json_file_path
            
        if not file_path:
            print("No file path specified for saving parameters")
            return
            
        try: #to save combined registry and legacy parameters
            combined_params = self.items()
            combined_params.update(self._parameters)
            with open(file_path, 'w') as f:
                json.dump(combined_params, f, indent=2)
        except Exception as e:
            print(f"Error saving JSON: {e}")
            print(f"Parameters saved to {file_path}")
            
    def get_parameter_metadata(self, key=None):
        """Get metadata for a parameter or all parameters.
        
        Args:
            key: Optional parameter key to get metadata for. If None, returns all metadata.
            
        Returns:
            Dictionary of parameter metadata including type, description, and category.
        """
        if key is not None:
            return self.get_metadata(key)
        else:
            # Return metadata for all parameters
            return {k: self.get_metadata(k) for k in self.keys()}
            
    def get_parameters_by_category(self, category=None):
        """Get parameters grouped by category.
        
        Args:
            category: Optional category to filter by. If None, returns all categories.
            
        Returns:
            Dictionary of parameters grouped by category.
        """
        result = {}
        for key in self.keys():
            meta = self.get_metadata(key)
            cat = meta.get('category', 'general')
            
            if category is not None and cat != category:
                continue
                
            if cat not in result:
                result[cat] = {}
                
            result[cat][key] = {
                'value': self.get(key),
                'metadata': meta
            }
            
        return result
        
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

