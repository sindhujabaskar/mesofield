# Mesofield

A hardware management framework for neuroscience instruments that interfaces with scientific hardware through serial connections and [MicroManager](https://micro-manager.org/).

## Overview

The core of the application is the `ExperimentConfig` class (`mesofield.config.ExperimentConfig`) and the corresponding `ConfigController` widget (`mesofield.gui.widgets.ConfigController`). 

Key features:
- Standardized hardware device protocols
- Unified data management system
- Real-time data acquisition and processing
- Integration with MicroManager for camera control
- GUI components for hardware interaction and visualization

`ExperimentConfig` loads hardware configurations via the `HardwareManager` which parses a `hardware.yaml` file. All hardware and GUI components inherit from the `ExperimentConfig`, providing global state access to parameters defining filenames, directories, and experimental settings.

NOTE: This has only been tested on Windows 10/11. Hardware control features rely on pymmcore-plus and an installation of MicroManager with specific device drivers.

## Core Components

### Hardware Devices

All hardware devices implement the `HardwareDevice` protocol which standardizes how devices are initialized, started, stopped, and monitored. Specialized protocols extend this for specific device types:

- `DataAcquisitionDevice`: For devices that acquire data (e.g., cameras, encoders)
- `ControlDevice`: For devices that control external hardware (e.g., NI-DAQ, stimulators)

These protocols can be implemented either through direct inheritance or duck typing (for classes that already have inheritance such as Qt classes), providing flexibility in how hardware integrates with the framework.

### Data Management

The `DataManager` provides a centralized system for:

- Registering data producers and consumers
- Managing data streams from multiple devices
- Real-time data processing
- Buffering and accessing data

The GUI components include live views for cameras (with optional pyqtgraph ImageView), encoder velocity plots, buttons for hardware control, and an iPython terminal for access to the backend.

## Creating Custom Hardware Instruments

To create a custom hardware device for use with Mesofield, implement the appropriate protocol:

```python
from dataclasses import dataclass
from typing import Dict, Any, ClassVar
from mesofield.protocols import DataAcquisitionDevice

@dataclass
class MyCustomSensor(DataAcquisitionDevice):
    # Required properties for HardwareDevice protocol
    device_type: ClassVar[str] = "my_sensor"
    device_id: str
    config: Dict[str, Any]
    
    # Required property for DataAcquisitionDevice protocol
    data_rate: float = 1.0  # Hz
    
    # Your custom properties
    custom_property: str = "default"
    
    def initialize(self) -> None:
        """Initialize your hardware device."""
        pass
    
    def start(self) -> bool:
        """Start data acquisition."""
        return True
    
    def stop(self) -> bool:
        """Stop data acquisition."""
        return True
    
    def close(self) -> None:
        """Clean up resources."""
        pass
    
    def get_status(self) -> Dict[str, Any]:
        """Return device status."""
        return {"status": "ok"}
    
    def get_data(self) -> Any:
        """Get data from your device."""
        return {"data": "your_data_here"}
```

See `example_device.py` for a more complete example.

## Integration

To use your custom device with Mesofield:

1. Create your device class implementing one of the hardware protocols
2. Add your device configuration to your hardware.yaml file
3. Register your device class with the DeviceRegistry
4. The HardwareManager will load and initialize your device
5. The DataManager will automatically register compatible devices for data streaming

## Example Usage

```python
from mesofield.config import ExperimentConfig
from mesofield.example_device import create_temperature_sensor

# Initialize from config file
config = ExperimentConfig("hardware.yaml")

# Access hardware devices
encoder = config.hardware.encoder
camera = config.hardware.Dhyana

# Create and register a custom device
sensor = create_temperature_sensor("temp1")
config.hardware.devices["temp1"] = sensor
config.data_manager.register_hardware_device(sensor)

# Start data acquisition
config.data_manager.start_all()

# Get data from specific device
encoder_data = config.data_manager.get_latest_data("encoder_dev")
temp_data = config.data_manager.get_latest_data("temp1")

# Get all data of a specific type
all_sensor_data = config.data_manager.get_data_by_type("temperature_sensor")

# Stop acquisition
config.data_manager.stop_all()
```

## Threading Models Support

Mesofield supports multiple threading models for hardware devices:

1. **Qt-based (QThread)**: For GUI applications using PyQt
2. **Thread-based**: Using Python's standard threading library
3. **Asyncio-based**: For asynchronous programming

Example implementations for each model are provided to simplify integration with different types of hardware devices and applications:

```python
# QThread-based device implementation (works with GUI applications)
from PyQt6.QtCore import QThread, pyqtSignal

class MyQtSensor(QThread):
    # Implement protocol through duck typing
    device_type = "sensor"
    device_id = "qt_sensor"
    
    # Add device methods
    def get_data(self):
        return {"reading": 42}
    
    # Define QThread methods
    def run(self):
        # QThread implementation
        pass

# Standard threading device implementation
from mesofield.mixins import ThreadingHardwareDeviceMixin

class MyThreadingSensor(ThreadingHardwareDeviceMixin):
    device_type = "sensor"
    device_id = "thread_sensor"
    
    def get_data(self):
        return {"reading": 42}
    
    def _run(self):
        # Threading implementation
        pass
```

See `threading_example.py` for complete examples.

# Setting Up Mesofield in Visual Studio Code

Below is a brief tutorial on how to set up a Python environment in VS Code, install mesofield, and run the [mesofield] CLI.

## 1. Clone and Open in VS Code

1. Clone this repository (or download it) to your local machine.
2. Open the folder in Visual Studio Code.

## 2. Create a Virtual Environment

*You can use a conda environment or a venv*

Open VS Code’s integrated terminal and create a virtual environment:

```
python -m venv .venv
```

Activate it:

- On Windows:

```
.venv\Scripts\activate
```

## 3. Install Dependencies

Install the required dependencies using [requirements.txt]:

```
pip install -r requirements.txt
```

Optionally, you can install directly from [setup.py]:

```
pip install .
```

Notable dependencies include: [pymmcore-plus](https://pymmcore-plus.github.io/pymmcore-plus/), [pymmcore-widgets](https://pymmcore-plus.github.io/pymmcore-widgets/) (for the MDAWidget), [useq](https://pymmcore-plus.github.io/useq-schema/), [PyQt](https://doc.qt.io/qtforpython-6/), [pyqtgraph](https://pyqtgraph.readthedocs.io/en/latest/), [pyserial](https://pyserial.readthedocs.io/en/latest/), pandas, numpy, matplotlib, and OpenCV (if using Arducam or other OpenCV compatible camera)

## 4. Launch Mesofield

Run the mesofield module in development mode from [mesofield.__main__]:

```
python -m mesofield launch --dev True
```

That’s it! This will open the main Mesofield GUI and set it up with simulated hardware for development.

# Using the Console in Mesofield

The IPython terminal can be launched with the `Toggle Console` button in the top-left menu bar. 

The console gives you access to the backend of the application. Type >>locals() into the terminal to see the accesible namespace using dot-notation

`self` provides access to the MainWindow and its attributes
`config` provides you access to the ExperimentConfig
`mda` provides access to the MDAWidget

The `config` command is the most useful outside of development. Type `config.hardware` to see the loaded hardware, for example.
Type `config.` + `tab` to see the available methods and parameters. Test them out, nothing should break in development mode. 
