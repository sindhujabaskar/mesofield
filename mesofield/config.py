import os
import json
import pathlib
import pandas as pd
import os
import useq
import warnings
from pymmcore_plus import CMMCorePlus

from typing import TYPE_CHECKING

from mesofield.io import SerialWorker
    
from mesofield.startup import HardwareManager

class ExperimentConfig:
    """## Generate and store parameters loaded from a JSON file. 
    
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

    def __init__(self, path: str = None, development_mode: bool = False):
        self._parameters = {}
        self._json_file_path = ''
        self._output_path = ''
        self._save_dir = ''

        self.hardware = HardwareManager(path)
        
        self.notes: list = []

    @property
    def _cores(self) -> tuple[CMMCorePlus, ...]:
        """Return the tuple of CMMCorePlus instances from the hardware cameras."""
        return tuple(cam.core for cam in self.hardware.cameras if cam.backend == "micromanager")

    @property
    def encoder(self) -> SerialWorker:
        return self.hardware.encoder

    @property
    def save_dir(self) -> str:
        return os.path.join(self._save_dir, 'data')

    @save_dir.setter
    def save_dir(self, path: str):
        if isinstance(path, str):
            self._save_dir = os.path.abspath(path)
        else:
            print(f"ExperimentConfig: \n Invalid save directory path: {path}")

    @property
    def subject(self) -> str:
        return self._parameters.get('subject', 'sub')

    @property
    def session(self) -> str:
        return self._parameters.get('session', 'ses')

    @property
    def task(self) -> str:
        return self._parameters.get('task', 'task')

    @property
    def start_on_trigger(self) -> bool:
        return self._parameters.get('start_on_trigger', False)
    
    @property
    def sequence_duration(self) -> int:
        return int(self._parameters.get('duration', 60))
    
    @property
    def trial_duration(self) -> int:
        return int(self._parameters.get('trial_duration', None))
    
    @property
    def num_meso_frames(self) -> int:
        return int(self.hardware.dhyana.fps * self.sequence_duration) 
    
    @property
    def num_pupil_frames(self) -> int:
        return int((self.hardware.thorcam.fps * self.sequence_duration)) + 100 
    
    @property
    def num_trials(self) -> int:
        return int(self.sequence_duration / self.trial_duration)  
    
    @property
    def parameters(self) -> dict:
        return self._parameters
    
    @property
    def meso_sequence(self) -> useq.MDASequence:
        return useq.MDASequence(time_plan={"interval": 0, "loops": self.num_meso_frames})
    
    @property
    def pupil_sequence(self) -> useq.MDASequence:
        return useq.MDASequence(time_plan={"interval": 0, "loops": self.num_pupil_frames})
    
    @property
    def bids_dir(self) -> str:
        """ Dynamic construct of BIDS directory path """
        bids = os.path.join(
            f"sub-{self.subject}",
            f"ses-{self.session}",
        )
        return os.path.abspath(os.path.join(self.save_dir, bids))

    # Property to compute the full file path, handling existing files
    @property
    def meso_file_path(self):
        file = f"sub-{self.subject}_ses-{self.session}_task-{self.task}_meso.ome.tiff"
        return self._generate_unique_file_path(file, 'func')

    # Property for pupil file path, if needed
    @property
    def pupil_file_path(self):
        file = f"sub-{self.subject}_ses-{self.session}_task-{self.task}_pupil.ome.tiff"
        return self._generate_unique_file_path(file, 'func')

    @property
    def dataframe(self):
        data = {'Parameter': list(self._parameters.keys()),
                'Value': list(self._parameters.values())}
        return pd.DataFrame(data)
    
    @property
    def json_path(self):
        return self._json_file_path
    
    @property
    def psychopy_filename(self) -> str:
        py_files = list(pathlib.Path(self._save_dir).glob('*.py'))
        if py_files:
            return py_files[0].name
        else:
            warnings.warn(f'No Psychopy experiment file found in directory {pathlib.Path(self.save_dir).parent}.')
        return self._parameters.get('psychopy_filename', 'experiment.py')
    
    @psychopy_filename.setter
    def psychopy_filename(self, value: str) -> None:
        self._parameters['psychopy_filename'] = value

    @property
    def psychopy_path(self) -> str:
        return os.path.join(self._save_dir, self.psychopy_filename)
    
    @property
    def led_pattern(self) -> list[str]:
        return self._parameters.get('led_pattern', ['4', '4', '2', '2'])
    
    @led_pattern.setter
    def led_pattern(self, value: list) -> None:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                raise ValueError("led_pattern string must be a valid JSON list")
        if isinstance(value, list):
            self._parameters['led_pattern'] = [str(item) for item in value]
        else:
            raise ValueError("led_pattern must be a list or a JSON string representing a list")
    
    # Helper method to generate a unique file path
    def _generate_unique_file_path(self, file: str, bids_type: str = None):
        """
        Example:
        
        ```py
            unique_path = _generate_unique_file_path("example.txt", "func")
        ```
            
        """
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
    
    def filename(self, suffix: str = None) -> str:
        """Generate a unique filename as timestamp_subject_session_task_{suffix}."""
        import datetime
        return f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_sub-{self.subject}_ses-{self.session}_task-{self.task}_{suffix}"
    
    def load_parameters(self, json_file_path) -> None:
        """ Load parameters from a JSON file path into the config object. 
        """
        try:
            with open(json_file_path, 'r') as f: 
                self._parameters = json.load(f)
        except FileNotFoundError:
            print(f"File not found: {json_file_path}")
            return
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON: {e}")
            return

    def update_parameter(self, key, value) -> None:
        """ Update a parameter in the config object """
        self._parameters[key] = value
        
    def list_parameters(self) -> pd.DataFrame:
        """ Create a DataFrame from the ExperimentConfig properties """
        properties = [prop for prop in dir(self.__class__) if isinstance(getattr(self.__class__, prop), property)]
        exclude_properties = {'dataframe', 'parameters', 'json_path'}
        data = {prop: getattr(self, prop) for prop in properties if prop not in exclude_properties}
        return pd.DataFrame(data.items(), columns=['Parameter', 'Value'])
                
    def save_wheel_encoder_data(self, data):
        """ Save the wheel encoder data to a CSV file """
        
        if isinstance(data, list):
            data = pd.DataFrame(data)
            
        encoder_file = f'{self.subject}_ses-{self.session}_encoder-data.csv'
        file = self.filename('encoder-data.csv')
        encoder_path = self._generate_unique_file_path(encoder_file, 'beh')

        params_file = f'{self.subject}_ses-{self.session}_configuration.csv'
        params_path = self._generate_unique_file_path(params_file)

        try:
            params = self.list_parameters()
            params.to_csv(params_path, index=False)
            data.to_csv(encoder_path, index=False)
            print(f"Encoder data saved to {encoder_path}")
        except Exception as e:
            print(f"Error saving encoder data: {e}")
        
            

class ConfigLoader:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.parameters = self.load_parameters(file_path)
        self.set_attributes()

    def load_parameters(self, file_path: str) -> dict:
        if file_path.endswith('.json'):
            with open(file_path, 'r') as f:
                return json.load(f)
        elif file_path.endswith(('.yaml', '.yml')):
            with open(file_path, 'r') as f:
                return yaml.safe_load(f)
        else:
            raise ValueError("Unsupported file format")

    def set_attributes(self):
        for key, value in self.parameters.items():
            setattr(self, key, value)

"""
startup.py

Example refactoring of a startup script using YAML for configuration.
Preserves:
- Per-camera instantiation of CMMCorePlus
- Camera-Engine pairing
- Accessible hardware references
- Friendly __repr__ for debugging
- Extensible for new hardware types (e.g., NI-DAQ)

Requires:
  - pyyaml (pip install pyyaml)
  - pymmcore-plus (pip install pymmcore-plus)
  
  {self.__class__.__module__}.{self.__class__.__name__}
"""

import yaml
from pymmcore_plus import CMMCorePlus

from mesofield.engines import DevEngine, MesoEngine, PupilEngine
from mesofield.io.encoder import SerialWorker
from mesofield.io.arducam import VideoThread


VALID_BACKENDS = {"micromanager", "opencv"}


class Camera:
    """
    Represents one camera device dynamically loaded based on backend
    """

    def __init__(self, camera_config: dict):
        self.config = camera_config
        self.id = camera_config.get("id", "devcam")
        self.name = camera_config.get("name", "DevCam")
        self.backend = camera_config.get("backend", "micromanager")
        self.fps = camera_config.get("fps", 30)

        if self.backend == "micromanager":
            # Instantiate a dedicated CMMCorePlus for this camera
            self.micromanager_path = camera_config.get("micromanager_path", None)
            self.core = CMMCorePlus(self.micromanager_path)

            # Load and initialize the Micro-Manager configuration file, if specified
            if "configuration_path" in camera_config:
                self.core.loadSystemConfiguration(camera_config["configuration_path"])
            else:
                print(f"{self.__class__.__module__}.{self.__class__.__name__} loading {self.core.getDeviceAdapterSearchPaths()}")
                self.core.loadSystemConfiguration()

            # Create an Engine and associate it with this camera
            if self.id == 'pupil':
                self.engine = PupilEngine(self.core, use_hardware_sequencing=True)
                self.core.mda.set_engine(self.engine)
                print (f"{self.__class__.__module__}.{self.__class__.__name__}.engine: {self.engine}")
            elif self.id == 'meso':
                self.engine = MesoEngine(self.core, use_hardware_sequencing=True)
                self.core.mda.set_engine(self.engine)
                print (f"{self.__class__.__module__}.{self.__class__.__name__}.engine: {self.engine}")
            else:
                self.engine = DevEngine(self.core, use_hardware_sequencing=True)
                self.core.mda.set_engine(self.engine)
                print (f"{self.__class__.__module__}.{self.__class__.__name__}.engine: {self.engine}")
                
        elif self.backend == "opencv":
            self.thread = VideoThread()
            pass

    def __repr__(self):
        return (
            f"<Camera id='{self.id}' name='{self.name}' "
            f"config_path='{self.config.get('configuration_path', 'N/A')}'>"
        )
        
    #IF the camera_config has properties, load them into the core
    def load_properties(self):
        for prop, value in self.config.get('properties', {}).items():
            self.core.setProperty('Core', prop, value)     

class Daq:
    """
    Represents an abstracted NI-DAQ device.
    """

    def __init__(self, config: dict):
        self.config = config
        self.type = config.get("type", "unknown")
        self.port = config.get("port")


    def __repr__(self):
        return (
            f"<Daq type='{self.type}' port='{self.port}' "
            f"config={self.config}>"
        )

class HardwareManager:
    """
    High-level class that initializes all hardware (cameras, encoder, etc.)
    using the ParameterManager. Keeps references easily accessible.
    """

    def __init__(self, config_file: str):
        self.yaml = self._load_hardware_from_yaml(config_file)
        self.cameras: tuple[Camera, ...] = ()
        self._initialize_cameras()
        self._test_camera_backends()
        self._initialize_encoder()

    def __repr__(self):
        return (
            "<HardwareManager>\n"
            f"  Cameras: {[cam.id for cam in self.cameras]}\n"
            f"  Encoder: {self.encoder}\n"
            f"  Config: {self.yaml}\n"
            f"  loaded_keys={list(self.params.keys())}\n"
            "</HardwareManager>"
        )
        
        
    def _load_hardware_from_yaml(self, path):
        params = {}

        if not path:
            raise FileNotFoundError(f"Cannot find config file at: {path}")

        with open(path, "r", encoding="utf-8") as file:
            params = yaml.safe_load(file) or {}
            
        return params
            
            
    def _initialize_encoder(self):
        if self.yaml.get("encoder"):
            params = self.yaml.get("encoder")
            self.encoder = SerialWorker(
                serial_port=params.get('port'),
                baud_rate=params.get('baudrate'),
                sample_interval=params.get('sample_interval_ms'),
                wheel_diameter=params.get('diameter_mm'),
                cpr=params.get('cpr'),
                development_mode=params.get('development_mode')
            )
        
        
    def _initialize_cameras(self):
        """
        For each camera in the config, instantiate a `Camera` object.
        Store them in a tuple, and set them as attributes on the HardwareManager.
        """
        try:
            camera_configs = self.yaml.get("cameras")
        except KeyError:
            print("No camera configurations found in the YAML file.")
            return

        cams = []
        for cfg in camera_configs:
            cam = Camera(cfg)
            cams.append(cam)
            setattr(self, cam.id, cam)
        self.cameras = tuple(cams)


    def configure_engines(self, cfg):
        """ If using micromanager cameras, configure the engines <camera.core.mda.engine.set_config(cfg)>
        """
        for cam in self.cameras:
            if cam.backend == "micromanager":
                cam.engine.set_config(cfg)


    def cam_backends(self, backend):
        """ Generator to iterate through cameras with a specific backend.
        """
        for cam in self.cameras:
            if cam.backend == backend:
                yield cam


    def _test_camera_backends(self):
        """ Test if the backend values of cameras are either 'micromanager' or 'opencv'.
        """
        for cam in self.cam_backends("micromanager"):
            assert cam.backend in VALID_BACKENDS, f"Invalid backend {cam.backend} for camera {cam.id}"
        for cam in self.cam_backends("opencv"):
            assert cam.backend in VALID_BACKENDS, f"Invalid backend {cam.backend} for camera {cam.id}"



# def main():
#     # Example usage: load from a YAML file (e.g. 'params.yaml')
#     config_path = "hardware.yaml"
#     hardware = HardwareManager(config_path)

    # # Print everything for demonstration (showing __repr__ output):
    # print(hardware)

    # # Access cameras or encoder from hardware
    # if "thorcam" in hardware.cameras:
    #     thorcam = hardware.cameras["thorcam"]
    #     print("\nInspecting ThorCam details:")har
    #     print(thorcam)
    #     print("Engine:", thorcam.engine)
    #     print("core")

    # if hardware.encoder is not None:
    #     print("\nEncoder details:")
    #     print(hardware.encoder)


# if __name__ == "__main__":
#     main()

#embed()