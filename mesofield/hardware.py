VALID_BACKENDS = {"micromanager", "opencv"}
import time
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Protocol, Type, ClassVar, runtime_checkable
import importlib
import yaml
import nidaqmx.system
import nidaqmx
from pymmcore_plus import CMMCorePlus

from mesofield.engines import DevEngine, MesoEngine, PupilEngine
from mesofield.io.arducam import VideoThread
from mesofield.io.encoder import SerialWorker


@runtime_checkable
class HardwareDevice(Protocol):
    """Protocol defining the interface for hardware devices."""
    
    device_type: str
    device_id: str
    config: Dict[str, Any]
    
    def initialize(self) -> None:
        """Initialize the hardware device."""
        ...
    
    def start(self) -> None:
        """Start data acquisition or operation."""
        ...
    
    def stop(self) -> None:
        """Stop data acquisition or operation."""
        ...
    
    def close(self) -> None:
        """Close and clean up resources."""
        ...
    
    def get_status(self) -> Dict[str, Any]:
        """Get the current status of the device."""
        ...


@runtime_checkable
class DataAcquisitionDevice(HardwareDevice, Protocol):
    """Protocol for devices that acquire data."""
    
    data_rate: float  # in Hz
    
    def get_data(self) -> Dict[str, Any]:
        """Get the latest data from the device."""
        ...


@runtime_checkable
class ControlDevice(HardwareDevice, Protocol):
    """Protocol for devices that control something."""
    
    def set_parameter(self, parameter: str, value: Any) -> None:
        """Set a parameter on the device."""
        ...
    
    def get_parameter(self, parameter: str) -> Any:
        """Get a parameter from the device."""
        ...


@dataclass
class Nidaq:
    device_name: str
    lines: str
    io_type: str
    device_type: ClassVar[str] = "nidaq"
    device_id: str = "nidaq"
    config: Dict[str, Any] = None

    def __post_init__(self):
        if self.config is None:
            self.config = {
                "device_name": self.device_name,
                "lines": self.lines,
                "io_type": self.io_type
            }

    def initialize(self) -> None:
        """Initialize the device."""
        pass

    def test_connection(self):
        print(f"Testing connection to NI-DAQ device: {self.device_name}")
        try:
            with nidaqmx.Task() as task:
                task.do_channels.add_do_chan(f'{self.device_name}/{self.lines}')
                task.write(True)
                time.sleep(3)
                task.write(False)
            print("Connection successful.")
        except nidaqmx.DaqError as e:
            print(f"NI-DAQ connection error: {e}")

    def reset(self):
        print(f"Resetting NI-DAQ device: {self.device_name}")
        nidaqmx.system.Device(self.device_name).reset_device()

    def start(self) -> None:
        """Start the device."""
        pass
    
    def stop(self) -> None:
        """Stop the device."""
        pass
    
    def close(self) -> None:
        """Close the device."""
        pass
    
    def get_status(self) -> Dict[str, Any]:
        """Get the status of the device."""
        return {"status": "ok"}


class DeviceRegistry:
    """Registry for device classes."""
    
    _registry: Dict[str, Type[Any]] = {}
    
    @classmethod
    def register(cls, device_type: str) -> callable:
        """Register a device class for a specific device type."""
        def decorator(device_class: Type[Any]) -> Type[Any]:
            cls._registry[device_type] = device_class
            return device_class
        return decorator
    
    @classmethod
    def get_class(cls, device_type: str) -> Optional[Type[Any]]:
        """Get the device class for a specific device type."""
        return cls._registry.get(device_type)


class HardwareManager:
    """
    High-level class that initializes all hardware (cameras, encoder, etc.)
    using the ParameterManager. Keeps references easily accessible.
    """

    def __init__(self, config_file: str):
        self.config_file = config_file
        self.devices: Dict[str, HardwareDevice] = {}
        self.yaml = self._load_hardware_from_yaml(config_file)
        self.cameras: tuple = ()
        self._viewer = self.yaml.get('viewer_type', 'static')
        self._initialize_devices()

    def __repr__(self):
        return (
            "<HardwareManager>\n"
            f"  Cameras: {[cam for cam in self.cameras]}\n"
            f"  Devices: {list(self.devices.keys())}\n"
            f"  Config: {self.yaml}\n"
            "</HardwareManager>"
        )
        
        
    def shutdown(self):
        """Shutdown all devices."""
        for device in self.devices.values():
            try:
                device.stop()
                device.close()
            except Exception as e:
                print(f"Error shutting down device: {e}")
        
        # Legacy support
        if hasattr(self, 'encoder') and self.encoder:
            self.encoder.stop()
    
    def _load_hardware_from_yaml(self, path):
        """Load hardware configuration from a YAML file."""
        params = {}

        if not path:
            raise FileNotFoundError(f"Cannot find config file at: {path}")

        with open(path, "r", encoding="utf-8") as file:
            params = yaml.safe_load(file) or {}
            
        return params
            
    def _initialize_devices(self):
        """Initialize hardware devices from YAML configuration."""
        self._initialize_cameras()
        self._initialize_encoder()
        self._initialize_daq()

    def _initialize_daq(self):
        """Initialize NI-DAQ device from YAML configuration."""
        if self.yaml.get("nidaq"):
            params = self.yaml.get("nidaq")
            self.nidaq = Nidaq(
                device_name=params.get('device_name'),
                lines=params.get('lines'),
                io_type=params.get('io_type')
            )
            self.devices["nidaq"] = self.nidaq
        else:
            self.nidaq = None

            
    def _initialize_encoder(self):
        """Initialize encoder device from YAML configuration."""
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
            self.devices["encoder"] = self.encoder
         
         
    def _initialize_cameras(self):
        """
        Initialize and configure camera objects based on YAML settings.
        This method reads the "cameras" section of a YAML configuration file,
        iterating over each camera definition. Depending on the specified backend
        (micromanager or opencv), it initializes and returns corresponding camera
        objects while applying any device-specific properties (e.g., ROI, fps, and
        other hardware settings).
        
        For Micro-Manager backends:
            - Creates an engine instance based on the camera ID (ThorCam, Dhyana, or a
                generic DevEngine).
            - Loads the Micro-Manager core, optionally setting hardware sequencing.
            - Applies properties from the configuration file, including ROI and fps.
        
        For OpenCV backends:
            - Creates a simple VideoThread instance.
            
        All resulting camera objects are placed into a tuple stored in the 'cameras'
        attribute of the object, and instance attributes are created for each by
        camera id enabling their access elsewhere:
        
        ```python
        HardwareManager.ThorCam
        HardwareManager.Dhyana
        HardwareManager.cameras[0]
        ```
        
        """

        cams = []
        for camera_config in self.yaml.get("cameras", []):
            camera_id = camera_config.get("id")
            backend = camera_config.get("backend")
            if backend == "micromanager":
                core = self._get_core_object(
                    camera_config.get("micromanager_path"),
                    camera_config.get("configuration_path", None),
                )
                camera_object = core.getDeviceObject(camera_id)
                for device_id, props in camera_config.get("properties", {}).items():
                    if isinstance(props, dict):
                        for property_id, value in props.items():
                            if property_id == 'ROI':
                                print(f"<{__class__.__name__}>: Setting {device_id} {property_id} to {value}")
                                core.setROI(device_id, *value) # * operator used to unpack the {type(value)=list}: [x, y, width, height]
                            elif property_id == 'fps':
                                print(f"<{__class__.__name__}>: Setting {device_id} {property_id} to {value}")
                                setattr(camera_object, 'fps', value)
                            elif property_id == 'viewer_type':
                                setattr(self, 'viewer', value)
                            else:
                                print(f"<{__class__.__name__}>: Setting {device_id} {property_id} to {value}")
                                core.setProperty(device_id, property_id, value)
                    else:
                        pass
                if camera_id == 'ThorCam':
                    engine = PupilEngine(core, use_hardware_sequencing=True)
                    core.mda.set_engine(engine)
                    print (f"{self.__class__.__module__}.{self.__class__.__name__}.engine: {engine}")
                elif camera_id == 'Dhyana':
                    engine = MesoEngine(core, use_hardware_sequencing=True)
                    core.mda.set_engine(engine)
                    print (f"{self.__class__.__module__}.{self.__class__.__name__}.engine: {engine}")
                else:
                    engine = DevEngine(core, use_hardware_sequencing=True)
                    core.mda.set_engine(engine)
                    print (f"{self.__class__.__module__}.{self.__class__.__name__}.engine: {engine}")
                
            elif backend == 'opencv':
                camera_object = VideoThread()
                
            cams.append(camera_object)
            setattr(self, camera_id, camera_object)
            self.devices[camera_id] = camera_object
            
        self.cameras = tuple(cams)
                
    
    def _get_core_object(self, mm_path, mm_cfg_path):
        core = CMMCorePlus(mm_path)
        if mm_path and mm_cfg_path is not None:
            core.loadSystemConfiguration(mm_cfg_path)
        elif mm_cfg_path is None and mm_path:
            core.loadSystemConfiguration()
        return core


    @staticmethod
    def get_property_object(core : CMMCorePlus, device_id: str, property_id: str):
        return core.getPropertyObject(device_id, property_id)
    
    
    def _configure_engines(self, cfg):
        """ If using micromanager cameras, configure the engines <camera.core.mda.engine.set_config(cfg)>
        """
        for cam in self.cameras:
            if isinstance(cam.core, CMMCorePlus):
                cam.core.mda.engine.set_config(cfg)


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
            
    # Interface methods
    def get_device(self, device_id: str) -> Optional[HardwareDevice]:
        """Get a device by its ID."""
        return self.devices.get(device_id)
    
    def get_devices_by_type(self, device_type: str) -> List[HardwareDevice]:
        """Get all devices of a specific type."""
        return [dev for dev in self.devices.values() if getattr(dev, 'device_type', None) == device_type]
    
    def has_device(self, device_id: str) -> bool:
        """Check if a device with the given ID exists."""
        return device_id in self.devices
    
    def initialize_all(self) -> None:
        """Initialize all devices."""
        for device in self.devices.values():
            if hasattr(device, 'initialize'):
                device.initialize()
    
    def close_all(self) -> None:
        """Close all devices."""
        for device in self.devices.values():
            if hasattr(device, 'close'):
                device.close()
    
    # Backward compatibility methods
    def get_camera(self, camera_id: str) -> Optional[Any]:
        """Get a camera device by its ID."""
        return self.get_device(camera_id)
    
    def get_encoder(self) -> Optional[SerialWorker]:
        """Get the encoder device."""
        return self.encoder
    
    def has_camera(self) -> bool:
        """Check if at least one camera device exists."""
        return len(self.cameras) > 0
    
    def has_encoder(self) -> bool:
        """Check if the encoder device exists."""
        return hasattr(self, 'encoder') and self.encoder is not None