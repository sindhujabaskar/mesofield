import useq
import logging


from dataclasses import dataclass, field
from typing import Optional, Dict, List
import json

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda import MDAEngine

from mesofield.engines import DevEngine, MesoEngine, PupilEngine
from mesofield.io.encoder import SerialWorker

# Disable pymmcore-plus logger
package_logger = logging.getLogger('pymmcore-plus')

# Set the logging level to CRITICAL to suppress lower-level logs
package_logger.setLevel(logging.CRITICAL)

@dataclass
class Encoder:
    type: str = 'dev'
    port: str = 'COM4'
    baudrate: int = 57600
    cpr: int = 2400
    diameter_mm: float = 80
    sample_interval_ms: int = 20
    reverse: int = -1
    encoder: Optional[SerialWorker] = None

    def __post_init__(self):
        # Create a SerialWorkerData instance with Encoder configurations
        self.encoder = SerialWorker(
            serial_port=self.port,
            baud_rate=self.baudrate,
            sample_interval=self.sample_interval_ms,
            wheel_diameter=self.diameter_mm,
            cpr=self.cpr,
            development_mode=True if self.type == 'dev' else False,
        )

    def __repr__(self):
        return (
            f"Encoder(\n"
            f"  encoder={repr(self.encoder)}"
        )
    
    def get_data(self):
        return self.encoder.get_data()
    
@dataclass
class Engine:
    ''' Engine dataclass to create different engine types for MDA '''
    name: str
    use_hardware_sequencing: bool = True

    def create_engine(self, mmcore: CMMCorePlus):
        # Create an appropriate engine based on the given name
        if self.name == 'DevEngine':
            return DevEngine(mmcore, use_hardware_sequencing=self.use_hardware_sequencing)
        elif self.name == 'MesoEngine':
            return MesoEngine(mmcore, use_hardware_sequencing=self.use_hardware_sequencing)
        elif self.name == 'PupilEngine':
            return PupilEngine(mmcore, use_hardware_sequencing=self.use_hardware_sequencing)
        else:
            raise ValueError(f"Unknown engine type: {self.name}")     

@dataclass
class Core:
    ''' MicroManager Core dataclass to manage MicroManager properties, configurations, and MDA engines
    '''
    name: str
    configuration_path: Optional[str] = None
    memory_buffer_size: int = 2000
    use_hardware_sequencing: bool = True
    roi: Optional[List[int]] = None  # (x, y, width, height)
    trigger_port: Optional[int] = None
    properties: Dict[str, str] = field(default_factory=dict)
    core: Optional[CMMCorePlus] = field(default=None, init=False)
    engine: Optional[MDAEngine] = None

    def __repr__(self):
        return (
            f"Core:\n"
            f"  name='{self.name}',\n"
            f"  core={repr(self.core)},\n"
            f"  engine={repr(self.engine)}\n"
            f"  configuration_path='{self.configuration_path}',\n"
            f"  memory_buffer_size={self.memory_buffer_size},\n"
            f"  properties={self.properties}\n\n"
        )

    def _load_core(self):
        ''' Load the core with specified configurations '''
        self.core = CMMCorePlus()
        if self.configuration_path:
            print(f"Loading {self.name} MicroManager configuration from {self.configuration_path}...")
            self.core.loadSystemConfiguration(self.configuration_path)
        else:
            print(f"Loading {self.name} MicroManager DEMO configuration...")
            self.core.loadSystemConfiguration()
        # Set memory buffer size
        self.core.setCircularBufferMemoryFootprint(self.memory_buffer_size)
        # Load additional properties and parameters for the core
        #self.load_properties()
        if self.configuration_path:
            self._load_additional_params()
        # Attach the specified engine to the core if available
        if self.engine:
            self._load_engine()
        
    def _load_engine(self):
        ''' Load the engine for the core '''
        self.engine = self.engine.create_engine(self.core)
        self.core.mda.set_engine(self.engine)
        logging.info(f"Core loaded for {self.name} from {self.configuration_path} with memory footprint: {self.core.getCircularBufferMemoryFootprint()} MB and engine {self.engine}")

    def load_properties(self):
        # Load specific properties into the core
        for prop, value in self.properties.items():
            self.core.setProperty('Core', prop, value)
        logging.info(f"Properties loaded for core {self.name}")

    def _load_additional_params(self):
        ''' Load additional parameters that are specific to certain cores '''
        # ========================== ThorCam Parameters ========================== #
        if self.name == 'ThorCam':
            # Specific settings for ThorCam
            if self.roi:
                self.core.setROI(self.name, *self.roi)
            self.core.setExposure(20)  # Set default exposure
            self.core.mda.engine.use_hardware_sequencing = self.use_hardware_sequencing
            logging.info(f"Additional parameters loaded for {self.name}")
            
        # ========================== Dhyana Parameters ========================== #
        elif self.name == 'Dhyana':
            if self.trigger_port is not None:
                self.core.setProperty('Dhyana', 'Output Trigger Port', str(self.trigger_port))
            # Configure Arduino switches and shutters for Dhyana setup
            self.core.setProperty('Arduino-Switch', 'Sequence', 'On')
            self.core.setProperty('Arduino-Shutter', 'OnOff', '1')
            self.core.setProperty('Core', 'Shutter', 'Arduino-Shutter')
            # Set channel group for Dhyana
            self.core.setChannelGroup('Channel')
            self.core.mda.engine.use_hardware_sequencing = self.use_hardware_sequencing
            logging.info(f"Additional parameters loaded for {self.name}")

@dataclass
class Startup:
    ''' Startup dataclass for managing the initial configuration of cores and other components '''
        
    _widefield_micromanager_path: str = 'C:/Program Files/Micro-Manager-2.0gamma'
    _thorcam_micromanager_path: str = 'C:/Program Files/Micro-Manager-thor'
    _memory_buffer_size: int = 10000
    _dhyana_fps: int = 49
    _thorcam_fps: int = 30
    
    encoder: Encoder = field(default_factory=lambda: Encoder())
    
    widefield: Core = field(default_factory=lambda: Core(
        name='DevCam',
        memory_buffer_size=10000,
        use_hardware_sequencing=True,
        engine=Engine(name='DevEngine', use_hardware_sequencing=True)
    ))
    
    thorcam: Core = field(default_factory=lambda: Core(
        name='DevCam',
        memory_buffer_size=10000,
        use_hardware_sequencing=True,
        engine=Engine(name='DevEngine', use_hardware_sequencing=True)
    ))

    def __repr__(self):
        return (
            f"HARDWARE:\n"
            f"====================\n"
            f"encoder={repr(self.encoder)}\n"
            f'\nCORES:\n'
            f"====================\n"
            f"MMCORE 1={repr(self.widefield)}"
            f"  dhyana_fps={self._dhyana_fps}\n\n"
            f"MMCORE 2={repr(self.thorcam)}"
            f"  thorcam_fps={self._thorcam_fps} \n"
        )

    @classmethod
    def _from_json(cls, file_path: str):
        ''' Load configuration parameters from a JSON file '''
        
        with open(file_path, 'r') as file:
            json_data = json.load(file)
        
        if 'encoder' in json_data:
            json_data['encoder'] = Encoder(**json_data['encoder'])
        
        if 'widefield' in json_data:
            # Create Core instance without engine
            core_data = json_data['widefield']
            core_instance = Core(**core_data)
            # Manually set the engine
            core_instance.engine = Engine(name='MesoEngine', use_hardware_sequencing=core_data.get('use_hardware_sequencing', True))
            json_data['widefield'] = core_instance
        
        if 'thorcam' in json_data:
            core_data = json_data['thorcam']
            core_instance = Core(**core_data)
            # Manually set the engine
            core_instance.engine = Engine(name='PupilEngine', use_hardware_sequencing=core_data.get('use_hardware_sequencing', True))
            json_data['thorcam'] = core_instance
        
        return cls(**json_data)
    
    def initialize_cores(self, cfg):
        # Initialize widefield and thorcam cores
        self.widefield._load_core()
        self.thorcam._load_core()
        self.widefield.engine.set_config(cfg)
        self.thorcam.engine.set_config(cfg)
        logging.info("Cores initialized")




''' Example Default widefield and thorcam Core dataclass instances 

```python

    widefield: Core = field(default_factory=lambda: Core(
        name='Dhyana',
        configuration_path='C:/Program Files/Micro-Manager-2.0/mm-sipefield.cfg',
        memory_buffer_size=10000,
        use_hardware_sequencing=True,
        trigger_port=2,
        properties={
            'Arduino-Switch': 'Sequence',
            'Arduino-Shutter': 'OnOff',
            'Core': 'Shutter'
        },
        engine=Engine(name='MesoEngine', use_hardware_sequencing=True)
    ))
    
    thorcam: Core = field(default_factory=lambda: Core(
        name='ThorCam',
        configuration_path='C:/Program Files/Micro-Manager-2.0/ThorCam.cfg',
        memory_buffer_size=10000,
        use_hardware_sequencing=True,
        roi=[440, 305, 509, 509],
        properties={
            'Exposure': '20'
        },
        engine=Engine(name='PupilEngine', use_hardware_sequencing=True)
    ))
    
```
    
'''
