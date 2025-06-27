# Mesofield

Mesofield is a small framework for managing neuroscience hardware.  It controls
cameras, encoders and other instruments through serial connections and
[MicroManager](https://micro-manager.org/) using
[pymmcore-plus]().  The project is aimed at laboratory use and is not a
full production package.


## Overview

Experiments are driven by :class:`mesofield.base.Procedure`.  Each procedure
owns a configuration object, :class:`~mesofield.config.ExperimentConfig`, which
loads the ``hardware.yaml`` via :class:`mesofield.hardware.HardwareManager`.
This registry stores parameters such as ``subject``, ``session`` and user-definable 
parameters stored and loaded via JSON.  GUI widgets like
:class:`mesofield.gui.controller.ConfigController` expose these values for
interactive editing.

Main components:

- **ExperimentConfig** – configuration registry with methods such as
  `load_json`, `build_sequence` and `make_path`.
- **HardwareManager** – creates devices from the YAML configuration and
  exposes them via attributes like `cameras`, `encoder` and `nidaq`.
- **DataManager** – collects device output using a thread safe
  `DataQueue` and can log entries with `start_queue_logger`. Owns
  a `DataSaver` and `DataPaths` for managing data saving and pathing, respectively.
- **Procedure** – high level experiment runner defined in
  `mesofield.base`.  It coordinates the configuration, hardware and data
  manager.  Use `create_procedure` to build a procedure instance.

Mesofield uses PyQt6 and has only been tested on various Windows 10/11.
Multi-camera setups prodcuing large experimental files require modern
computing hardware. I reccommend having at least 32gb RAM and a 12th
generation i7 core or equivalent.

An attemp tat universal logging and exception handling has been made;
all logs and uncaught exceptions are written to `logs/mesofield.log`
using a standardized logger.

## Custom Hardware

Hardware classes implement the protocols defined in
`mesofield.protocols`.  A minimal data producing device looks like this:

```python
import serial
from mesofield.protocols import DataAcquisitionDevice

class SerialSensor(DataAcquisitionDevice):
    device_type = "arduino"
    device_id = "temp"

    def initialize(self):
        self.ser = serial.Serial("COM3", 9600)

    def start(self) -> bool:
        return True

    def stop(self) -> bool:
        self.ser.close()
        return True

    def get_data(self):
        return float(self.ser.readline())
```

Register the class with `mesofield.DeviceRegistry.register("sensor")` and add an
entry to your `hardware.yaml` so that `HardwareManager` can instantiate it.

## Threading Models

Devices can run in different concurrency models:

```python
from PyQt6.QtCore import QThread
from mesofield.mixins import ThreadingHardwareDeviceMixin

class QtDevice(QThread):
    device_type = "qt_device"
    device_id = "qdev"
    def run(self):
        ...  # Qt loop

class ThreadedDevice(ThreadingHardwareDeviceMixin):
    device_type = "thread_device"
    device_id = "tdev"
    def _run(self):
        ...  # standard thread
```

Asynchronous devices can be implemented with `asyncio` while still
providing the protocol methods.

## Development Setup

```bash
conda create -n mesofield python=3.13
conda activate mesofield
pip install -r requirements.txt
```

Launch the GUI with simulated hardware:

```bash
python -m mesofield launch --dev True
```

## Using the Console

Press **Toggle Console** to open the embedded IPython terminal.  The names
inserted by :func:`MainWindow.initialize_console` include:

- ``self`` – the application window
- ``procedure`` – the running :class:`mesofield.base.Procedure`
- ``data`` – the :mod:`mesofield.data` package

Access the configuration as ``procedure.config``.  Type
``procedure.config.hardware`` to inspect loaded devices and use tab completion
on ``procedure.config.`` to discover parameters.
