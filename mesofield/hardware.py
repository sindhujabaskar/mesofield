VALID_BACKENDS = {"micromanager", "opencv"}
import time
import inspect
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Type, ClassVar, TypeVar, Callable
import yaml
import threading 

import nidaqmx.system
import nidaqmx
from nidaqmx.constants import Edge
from pymmcore_plus import CMMCorePlus, DeviceType

from mesofield.engines import DevEngine, MesoEngine, PupilEngine
from mesofield.io.arducam import VideoThread
from mesofield.io.encoder import SerialWorker
from mesofield.io.treadmill import EncoderSerialInterface
from mesofield.protocols import HardwareDevice, DataProducer
from mesofield.utils._logger import get_logger, log_this_fr

T = TypeVar("T")

class DeviceRegistry:
    """Registry for device classes."""
    
    _registry: Dict[str, Type[Any]] = {}
    
    @classmethod
    def register(cls, device_type: str) -> Callable[[Type[T]], Type[T]]:
        """Register a device class for a specific device type."""
        def decorator(device_class: Type[T]) -> Type[T]:
            cls._registry[device_type] = device_class
            return device_class
        return decorator
    
    @classmethod
    def get_class(cls, device_type: str) -> Optional[Type[Any]]:
        """Get the device class for a specific device type."""
        return cls._registry.get(device_type)


class HardwareManager():
    """
    High-level class that initializes all hardware (cameras, encoder, etc.)
    using the ParameterManager. Keeps references easily accessible.
    """

    def __init__(self, config_file: str):
        # Initialize logging first
        self.logger = get_logger(f'{__name__}.{self.__class__.__name__}')
        self.logger.info(f"Initializing HardwareManager with config: {config_file}")

        self.config_file = config_file
        self.devices: Dict[str, HardwareDevice] = {}

        try:
            self.yaml = self._load_hardware_from_yaml(config_file)
            self.logger.info("Successfully loaded hardware configuration")
        except Exception as e:
            self.logger.error(f"Failed to load hardware configuration: {e}")
            raise

        # Build canonical widget list from YAML
        self.widgets: List[str] = self._aggregate_widgets()
        self.cameras: tuple[MMCamera, ...] = ()
        self._viewer = self.yaml.get('viewer_type', 'static')

        # Initialize all devices
        self._initialize_devices()
        self.logger.info(f"Hardware initialization complete. {len(self.devices)} devices initialized")

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
                device.shutdown()
            except Exception as e:
                self.logger.error(f"Error shutting down device: {e}")

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

    def _aggregate_widgets(self) -> List[str]:
        """
        Aggregate widget keys from root, camera entries, and encoder into a single list.
        """
        widgets: List[str] = []
        # Global widgets
        for w in self.yaml.get('widgets', []):
            if w not in widgets:
                widgets.append(w)
        # Camera-specific widgets
        for cam in self.yaml.get('cameras', []):
            for w in cam.get('widgets', []):
                if w not in widgets:
                    widgets.append(w)
        # Encoder-specific widgets
        for w in self.yaml.get('encoder', {}).get('widgets', []):
            if w not in widgets:
                widgets.append(w)
        # NIDAQ widgets
        if self.yaml.get('nidaq'):
            for w in self.yaml['nidaq'].get('widgets', []):
                if w not in widgets:
                    widgets.append(w)
        return widgets

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
                io_type=params.get('io_type'),
                ctr=params.get('crt', 'ctr0'),
            )
            self.devices["nidaq"] = self.nidaq
        else:
            self.nidaq = None


    def _initialize_encoder(self):
        """Initialize encoder device from YAML configuration."""
        if self.yaml.get("encoder"):
            params = self.yaml.get("encoder")
            if params.get('type') == 'wheel':
                self.encoder = SerialWorker(
                    serial_port=params.get('port'),
                    baud_rate=params.get('baudrate'),
                    sample_interval=params.get('sample_interval_ms'),
                    wheel_diameter=params.get('diameter_mm'),
                    cpr=params.get('cpr'),
                    development_mode=params.get('development_mode')
                )
            elif params.get('type') == 'treadmill':
                self.encoder = EncoderSerialInterface(
                    port=params.get('port'),
                    baudrate=params.get('baudrate'),
                    data_callback=None
                )
            self.devices["encoder"] = self.encoder


    def _initialize_cameras(self):
        cams = []
        CameraClass = DeviceRegistry.get_class("camera")
        for cfg in self.yaml.get("cameras", []):
            cam = CameraClass(cfg)
            setattr(self, cam.id, cam)
            self.devices[cam.id] = cam
            cams.append(cam)
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
        """If using micromanager cameras, configure the engines."""
        for cam in self.cameras:
            if isinstance(cam.core, CMMCorePlus):
                cam.core.mda.engine.set_config(cfg)


    def cam_backends(self, backend):
        """Generator to iterate through cameras with a specific backend."""
        for cam in self.cameras:
            if cam.backend == backend:
                yield cam


    def _test_camera_backends(self):
        """Test if the backend values of cameras are valid."""
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
            if hasattr(device, 'shutdown'):
                device.shutdown()

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


@dataclass
class Nidaq:
    """
    NIDAQ hardware control device.
    
    This class implements the ControlDevice protocol via duck typing,
    providing all the necessary methods and attributes without inheritance.
    """
    device_name: str
    lines: str
    ctr: str
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
        self.logger = get_logger(f"{__name__}.{self.__class__.__name__}[{self.device_id}]")
        self.pulse_width = 0.001
        self.poll_interval = 0.01
        self._stop_event = threading.Event()
        self._thread = None
        self._lock = threading.Lock()
        self._exposure_times: list[float] = []

    def initialize(self) -> None:
        """Initialize the device."""
        pass

    def test_connection(self):
        self.logger.info(f"Testing connection to NI-DAQ device: {self.device_name}")
        try:
            with nidaqmx.Task() as task:
                task.do_channels.add_do_chan(f'{self.device_name}/{self.lines}')
                task.write(True)
                time.sleep(3)
                task.write(False)
            self.logger.info("NI-DAQ connection successful")
        except nidaqmx.DaqError as e:
            self.logger.error(f"NI-DAQ connection failed: {e}")

    def reset(self):
        self.logger.info(f"Resetting NIDAQ device")
        nidaqmx.system.Device(self.device_name).reset_device()

    def start(self):
        # Configure and start the CI task
        self._ci = nidaqmx.Task()
        self._ci.ci_channels.add_ci_count_edges_chan(
            f"{self.device_name}/{self.ctr}", edge=Edge.RISING, initial_count=0
        )
        self._ci.start()

        # Configure the DO task (camera trigger)
        self._do = nidaqmx.Task()
        self._do.do_channels.add_do_chan(f"{self.device_name}/{self.lines}")

        # Launch background thread
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def _worker(self):
        prev_count = 0
        while not self._stop_event.is_set():
            # 1) Trigger camera
            self._do.write(True)
            time.sleep(self.pulse_width)
            self._do.write(False)

            # 2) Read count & timestamp
            cnt = self._ci.read()
            ts = time.time()

            # 3) For each new edge, record the same timestamp
            if cnt > prev_count:
                with self._lock:
                    self._exposure_times.extend([ts] * (cnt - prev_count))
                prev_count = cnt

            # 4) Wait before next trigger
            time.sleep(self.poll_interval)

        # Cleanup when stopping
        self._ci.stop()
        self._ci.close()
        self._do.close()
    
    def stop(self) -> bool:
        """Signal the background thread to stop and wait for it."""
        self._stop_event.set()
        if self._thread:
            self._thread.join()
    
    def shutdown(self) -> None:
        """Close the device."""
        self.stop()
    
    def get_exposure_times(self) -> list[float]:
        """Retrieve a copy of the host-time exposure timestamps."""
        with self._lock:
            return list(self._exposure_times)
        
    def get_status(self) -> Dict[str, Any]:
        """Get the status of the device."""
        return {"status": "ok"}
        
    def set_parameter(self, parameter: str, value: Any) -> bool:
        """Set a parameter on the device."""
        if parameter in self.config:
            self.config[parameter] = value
            return True
        return False
    
    def get_parameter(self, parameter: str) -> Any:
        """Get a parameter from the device."""
        return self.config.get(parameter)

from pymmcore_plus.core._device import CameraDevice 

@DeviceRegistry.register("camera")
class MMCamera(DataProducer, HardwareDevice):
    
    device_type = "camera"

    def __init__(self, cfg: dict):
        self.camera_device: Optional[CameraDevice | VideoThread] = None
        self.core: Optional[CMMCorePlus | VideoThread] = None
        self.id = cfg["id"]
        self.name = cfg["name"]
        self.backend = cfg.get("backend", "").lower()
        self.properties = cfg.get("properties", {})
        self.viewer = cfg.get("viewer_type", "static")
        self._engine = None
        self.is_active = False
        self.logger = get_logger(f"{__name__}.MMCamera[{self.id}]")

        if self.backend == "micromanager":
            self._setup_micromanager(cfg)
        elif self.backend == "opencv":
            self._setup_opencv()
        else:
            raise ValueError(f"Unknown camera backend '{self.backend}'")

        # automatically apply all YAML properties
        self.initialize()

    def _setup_micromanager(self, cfg):
        core = CMMCorePlus(cfg.get("micromanager_path"))
        cfg_path = cfg.get("configuration_path")
        core.loadSystemConfiguration(cfg_path) if cfg_path else core.loadSystemConfiguration()
        self.camera_device = core.getDeviceObject(core.getCameraDevice(),
                                                  DeviceType.Camera)
        Engine = {"ThorCam": PupilEngine,
                  "Dhyana": MesoEngine}.get(self.id, DevEngine)
        self._engine = Engine(core, use_hardware_sequencing=True)
        core.mda.set_engine(self._engine)
        self.core = core

    def _setup_opencv(self):
        vid = VideoThread()
        self.camera_device = vid
        self.core = vid

    def initialize(self):
        for dev_id, props in self.properties.items():
            if not isinstance(props, dict):
                continue
            for prop, val in props.items():
                self.logger.info(f"Setting {dev_id}.{prop} → {val}")
                if prop == "ROI":
                    roi_setter = getattr(self.core, "setROI", None) if self.backend == "micromanager" else None
                    if roi_setter:
                        roi_setter(dev_id, *val)
                elif prop == "fps":
                    setattr(self, "sampling_rate", val)
                elif prop == "viewer_type":
                    setattr(self, "viewer", val)
                else:
                    if self.backend == "micromanager":
                        setter = getattr(self.core, "setProperty", None)
                    else:
                        setter = getattr(self.camera_device, "setProperty", None)
                    if setter:
                        setter(dev_id, prop, val)

    def start(self) -> bool:
        self.is_active = True
        return True

    def stop(self) -> bool:
        self.is_active = False
        return True

    def get_data(self):
        return getattr(self.camera_device, "get_frame", lambda: None)() if self.is_active else None
    
    def shutdown(self):
        if self.backend == "micromanager" and hasattr(self.core, "reset"):
            self.core.reset()
    
    def __getattr__(self, name: str):
        """
        Any attribute not found on MMCamera will be looked up
        on the wrapped camera_device automatically.
        """
        if self.camera_device is not None and hasattr(self.camera_device, name):
            return getattr(self.camera_device, name)
        raise AttributeError(f"{self.__class__.__name__!r} has no attribute {name!r}")

    def __dir__(self):
        """
        Include camera_device’s public attributes in dir(self) so
        tab‐complete / introspection still works.
        """
        base = set(super().__dir__())
        if self.camera_device is not None:
            base.update(n for n in dir(self.camera_device) if not n.startswith("_"))
        return sorted(base)
    
    def __repr__(self):
        # Module info
        module = inspect.getmodule(self)
        module_name = module.__name__ if module else "<unknown>"
        module_file = getattr(module, "__file__", "<built-in>")
        # Instance attributes (public)
        attributes = {k: v for k, v in vars(self).items() if not k.startswith("_")}
        # Inheritance tree (object → … → MMCamera)
        mro = inspect.getmro(self.__class__)
        inheritance = " → ".join(cls.__name__ for cls in reversed(mro))
        return (
            f"<MMCamera\n"
            f"  id          = {self.id!r}\n"
            f"  name        = {self.name!r}\n"
            f"  backend     = {self.backend!r}\n"
            f"  module      = {module_name!r} ({module_file!r})\n"
            f"  properties  = {self.properties!r}\n"
            f"  attributes  = {attributes!r}\n"
            f"  engine      = {type(self._engine).__name__!r}\n"
            f"  device      = {type(self.camera_device).__name__!r}\n"
            f"  inheritance = {inheritance}\n"
            f">"
        )