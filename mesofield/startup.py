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

import serial
import yaml
import logging
from pathlib import Path
from IPython import embed
from pymmcore_plus import CMMCorePlus

from mesofield.engines import DevEngine, MesoEngine, PupilEngine
from mesofield.io.encoder import SerialWorker
from mesofield.io.arducam import VideoThread

# Disable pymmcore-plus logger
package_logger = logging.getLogger('pymmcore-plus')

# Set the logging level to CRITICAL to suppress lower-level logs
package_logger.setLevel(logging.CRITICAL)

VALID_BACKENDS = {"micromanager", "opencv"}

class ParameterManager:
    """
    Loads and stores parameters from a YAML configuration file.
    Provides easy access to camera/encoder configs.
    """

    def __init__(self, config_file_path: str):
        self.config_file_path = Path(config_file_path)
        self.params = {}
        self._load_params()

    def _load_params(self):
        if not self.config_file_path.exists():
            raise FileNotFoundError(f"Cannot find config file at: {self.config_file_path}")

        with open(self.config_file_path, "r", encoding="utf-8") as file:
            self.params = yaml.safe_load(file) or {}

    def get_param(self, key, default=None):
        return self.params.get(key, default)

    def get_cameras(self):
        return self.params.get("cameras", [])

    def get_encoder_config(self):
        return self.params.get("encoder", {})

    def __repr__(self):
        return (
            f"<ParameterManager config_file_path='{self.config_file_path}' "
            f"loaded_keys={list(self.params.keys())}>"
        ) 

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
            if self.id == 'thorcam':
                self.engine = PupilEngine(self.core, use_hardware_sequencing=True)
                self.core.mda.set_engine(self.engine)
                print (f"{self.__class__.__module__}.{self.__class__.__name__}.engine: {self.engine}")
            elif self.id == 'dhyana':
                self.engine = MesoEngine(self.core, use_hardware_sequencing=True)
                self.core.mda.set_engine(self.engine)
                print (f"{self.__class__.__module__}.{self.__class__.__name__}.engine: {self.engine}")
            else:
                self.engine = DevEngine(self.core, use_hardware_sequencing=True)
                self.core.mda.set_engine(self.engine)
                print (f"{self.__class__.__module__}.{self.__class__.__name__}.engine: {self.engine}")
        elif self.backend == "opencv":
            pass
        
        self.load_properties()

    def __repr__(self):
        return (
            f"<Camera id='{self.id}' name='{self.name}' "
            f"config_path='{self.config.get('configuration_path', 'N/A')}'>"
        )
        
    #IF the camera_config has properties, load them into the core
    def load_properties(self):
        for prop, value in self.config.get('properties', {}).items():
            if isinstance(value, str) and value.isdigit():
                value = int(value)
            if prop == 'Exposure':
                self.core.setExposure(value)
            if prop == 'roi':
                self.core.setROI(*value)
            if prop == 'trigger_port':
                self.core.setProperty(self.id.capitalize(), 'Output Trigger Port', str(value))
            if prop == 'Arduino-Shutter' and value == 'True':
                self.core.setProperty('Arduino-Switch', 'Sequence', 'On')
                self.core.setProperty('Arduino-Shutter', 'OnOff', '1')
                self.core.setProperty('Core', 'Shutter', 'Arduino-Shutter')
                self.core.setChannelGroup('Channel')


class Encoder:
    """
    Represents an abstracted encoder device (e.g., Arduino).
    Could be extended for NI-DAQ or other devices in the future.
    """

    def __init__(self, config: dict):
        self.config = config
        self.type: str = config.get("type", "dev")
        self.port: str = config.get("port")
        self.baudrate: int = config.get("baud_rate", 57600)
        self.sample_interval_ms: int = config.get("sample_interval_ms", 20)
        self.diameter_mm: int = config.get("wheel_diameter_mm", 80)
        self.cpr: int = config.get("cpr", 2400)
        self.worker: SerialWorker = None
        self.development_mode: bool = config.get("development_mode", True)
        
        self._create_worker()

    def __repr__(self):
        return (
            f"<Encoder type='{self.type}' port='{self.port}' "
            f"config={self.config}>"
        )
    
    def _create_worker(self):
        
        self.worker = SerialWorker(
            serial_port=self.port,
            baud_rate=self.baudrate,
            sample_interval=self.sample_interval_ms,
            wheel_diameter=self.diameter_mm,
            cpr=self.cpr,
            development_mode=self.development_mode
        )
        print(self.worker)
        
    def get_data(self):
        return self.worker.get_data()
        

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
        # 1) Load YAML params
        self.pm = ParameterManager(config_file)

        # 2) Build cameras and engines
        self._initialize_cameras()

        # 3) Build encoder device (abstract enough for other device types)
        self.encoder = self._initialize_encoder()

    def _initialize_cameras(self):
        """
        For each camera in the config, instantiate a `Camera` object.
        Store them in a tuple.
        """
        try:
            camera_configs = self.pm.get_cameras()
        except KeyError:
            print("No camera configurations found in the YAML file.")
            return

        cameras = []
        for cfg in camera_configs:
            cam = Camera(cfg)
            cameras.append(cam)
            setattr(self, cam.id, cam)
        self.cameras = tuple(cameras)

    def configure_engines(self, cfg):
        """
        If using micromanager cameras, configure the engines <camera.core.mda.engine.set_config(cfg)>
        """
        for cam in self.cameras:
            if cam.backend == "micromanager":
                cam.engine.set_config(cfg)

    def cam_backends(self, backend):
        """
        Generator to iterate through cameras with a specific backend.
        """
        for cam in self.cameras:
            if cam.backend == backend:
                yield cam

    def test_camera_backends(self):
        """
        Test if the backend values of cameras are either 'micromanager' or 'opencv'.
        """
        for cam in self.cam_backends("micromanager"):
            assert cam.backend in VALID_BACKENDS, f"Invalid backend {cam.backend} for camera {cam.id}"
        for cam in self.cam_backends("opencv"):
            assert cam.backend in VALID_BACKENDS, f"Invalid backend {cam.backend} for camera {cam.id}"

    def _initialize_encoder(self):
        """
        Optionally create an Encoder object if the config includes encoder info.
        In the future, could handle 'nidaq' or other hardware as well.
        """
        encoder_config = self.pm.get_encoder_config()
        if encoder_config:
            return Encoder(encoder_config)
        return None

    def __repr__(self):
        return (
            "<HardwareManager>\n"
            f"  Cameras: {[cam.id for cam in self.cameras]}\n"
            f"  Encoder: {self.encoder}\n"
            f"  Config: {self.pm}\n"
            "</HardwareManager>"
        )


def main():
    # Example usage: load from a YAML file (e.g. 'params.yaml')
    config_path = "hardware.yaml"
    hardware = HardwareManager(config_path)

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