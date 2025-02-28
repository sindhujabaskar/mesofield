VALID_BACKENDS = {"micromanager", "opencv"}
import time
from dataclasses import dataclass
import nidaqmx.system
import yaml

import nidaqmx
from pymmcore_plus import CMMCorePlus


from mesofield.engines import DevEngine, MesoEngine, PupilEngine
from mesofield.io.arducam import VideoThread
from mesofield.io.encoder import SerialWorker

from typing import TYPE_CHECKING
#if TYPE_CHECKING:


@dataclass
class Nidaq:
    device_name: str
    lines: str
    io_type: str

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




class HardwareManager:
    """
    High-level class that initializes all hardware (cameras, encoder, etc.)
    using the ParameterManager. Keeps references easily accessible.
    """

    def __init__(self, config_file: str):
        self.yaml = self._load_hardware_from_yaml(config_file)
        self.cameras: tuple = ()
        self._viewer = self.yaml['viewer_type']
        self._initialize_cameras()
        self._initialize_encoder()
        self._initialize_daq()

    def __repr__(self):
        return (
            "<HardwareManager>\n"
            f"  Cameras: {[cam for cam in self.cameras]}\n"
            f"  Encoder: {self.encoder}\n"
            f"  Config: {self.yaml}\n"
            f"  loaded_keys={list(self.params.keys())}\n"
            "</HardwareManager>"
        )
        
        
    def shutdown(self):
        self.encoder.stop()
    
    def _load_hardware_from_yaml(self, path):
        params = {}

        if not path:
            raise FileNotFoundError(f"Cannot find config file at: {path}")

        with open(path, "r", encoding="utf-8") as file:
            params = yaml.safe_load(file) or {}
            
        return params
            

    def _initialize_daq(self):
        if self.yaml.get("nidaq"):
            params = self.yaml.get("nidaq")
            self.nidaq = Nidaq(
                device_name=params.get('device_name'),
                lines=params.get('lines'),
                io_type=params.get('io_type')
            )
        else:
            self.nidaq = None

            
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
        for camera_config in self.yaml.get("cameras"):
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