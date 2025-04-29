"""
Example implementation of custom hardware devices using different threading models.

This module demonstrates how to create hardware devices using both Python's
threading library and Qt's QThread, while conforming to the hardware device protocols.
"""

import time
import random
import threading
from dataclasses import dataclass, field
from typing import Dict, Any, ClassVar, List, Optional

from PyQt6.QtCore import QThread, pyqtSignal

from mesofield.protocols.mixins import ThreadedHardwareDevice
from mesofield.protocols import is_data_acquisition_device  # For runtime checking


class ThreadingSensor(ThreadedHardwareDevice):
    """
    Example temperature sensor using Python's threading library.
    
    This class implements the DataAcquisitionDevice protocol through both
    inheritance of the ThreadingHardwareDeviceMixin and providing the
    required additional methods and attributes.
    """
    
    # Required HardwareDevice protocol properties
    device_type: ClassVar[str] = "temperature_sensor"
    device_id: str
    config: Dict[str, Any]
    
    # Required DataAcquisitionDevice protocol property
    data_rate: float
    
    def __init__(self, device_id: str, config: Optional[Dict[str, Any]] = None, 
                 data_rate: float = 1.0):
        """Initialize the sensor with the given parameters."""
        super().__init__()  # Initialize the threading mixin
        
        self.device_id = device_id
        self.config = config or {}
        self.data_rate = data_rate
        
        # Sensor-specific properties
        self.min_temp = self.config.get("min_temp", 20.0)
        self.max_temp = self.config.get("max_temp", 30.0)
        self.noise_level = self.config.get("noise_level", 0.5)
        
        # Internal state
        self._last_temp = (self.min_temp + self.max_temp) / 2
        self._readings = []
    
    def initialize(self) -> None:
        """Initialize the device. Required for HardwareDevice protocol."""
        self._last_temp = (self.min_temp + self.max_temp) / 2
        self._readings = []
        print(f"Threading sensor {self.device_id} initialized")
    
    def get_status(self) -> Dict[str, Any]:
        """Get the current status of the device."""
        return {
            "active": self._active,
            "readings_count": len(self._readings),
            "data_rate": self.data_rate
        }
    
    def get_data(self) -> Optional[Dict[str, Any]]:
        """Get the latest data from the device."""
        if not self._readings:
            return None
        return self._readings[-1]
    
    def _run(self) -> None:
        """Thread main method that generates simulated sensor readings."""
        print(f"Threading sensor {self.device_id} started")
        
        while not self._stop_event.is_set():
            # Generate a random temperature with some correlation to previous reading
            drift = random.uniform(-self.noise_level, self.noise_level)
            new_temp = self._last_temp + drift
            
            # Keep temperature within bounds
            new_temp = max(self.min_temp, min(self.max_temp, new_temp))
            self._last_temp = new_temp
            
            # Create reading data
            reading = {
                "temperature": new_temp,
                "timestamp": time.time(),
                "unit": "celsius"
            }
            
            # Store in readings history
            self._readings.append(reading)
            
            # Keep only the last 1000 readings
            if len(self._readings) > 1000:
                self._readings = self._readings[-1000:]
            
            # Sleep for the appropriate interval
            time.sleep(1.0 / self.data_rate)
        
        print(f"Threading sensor {self.device_id} stopped")


class QtSensor(QThread):
    """
    Example temperature sensor using Qt's QThread.
    
    This class implements the DataAcquisitionDevice protocol through duck typing,
    providing all the required methods and attributes without directly inheriting
    from the protocol (which would cause metaclass conflicts with QThread).
    """
    
    # PyQt signals
    dataReady = pyqtSignal(dict)
    sensorStarted = pyqtSignal()
    sensorStopped = pyqtSignal()
    
    # Required HardwareDevice protocol properties
    device_type: ClassVar[str] = "temperature_sensor"
    device_id: str
    config: Dict[str, Any]
    
    # Required DataAcquisitionDevice protocol property
    data_rate: float
    
    def __init__(self, device_id: str, config: Optional[Dict[str, Any]] = None, 
                 data_rate: float = 1.0):
        """Initialize the Qt sensor with the given parameters."""
        super().__init__()
        
        self.device_id = device_id
        self.config = config or {}
        self.data_rate = data_rate
        
        # Sensor-specific properties
        self.min_temp = self.config.get("min_temp", 20.0)
        self.max_temp = self.config.get("max_temp", 30.0)
        self.noise_level = self.config.get("noise_level", 0.5)
        
        # Internal state
        self._last_temp = (self.min_temp + self.max_temp) / 2
        self._readings = []
        self._active = False
    
    def initialize(self) -> None:
        """Initialize the device. Required for HardwareDevice protocol."""
        self._last_temp = (self.min_temp + self.max_temp) / 2
        self._readings = []
        print(f"Qt sensor {self.device_id} initialized")
    
    def start(self) -> bool:
        """Start data acquisition. Overrides QThread.start() but maintains protocol compatibility."""
        self._active = True
        self.sensorStarted.emit()
        super().start()  # Start the QThread
        return True
    
    def stop(self) -> bool:
        """Stop data acquisition."""
        if not self._active:
            return True
        
        self.requestInterruption()
        self.wait(1000)  # Wait up to 1 second for the thread to finish
        self._active = False
        self.sensorStopped.emit()
        return True
    
    def close(self) -> None:
        """Close and clean up resources."""
        self.stop()
    
    def get_status(self) -> Dict[str, Any]:
        """Get the current status of the device."""
        return {
            "active": self._active,
            "readings_count": len(self._readings),
            "data_rate": self.data_rate
        }
    
    def get_data(self) -> Optional[Dict[str, Any]]:
        """Get the latest data from the device."""
        if not self._readings:
            return None
        return self._readings[-1]
    
    def run(self) -> None:
        """QThread run method that generates simulated sensor readings."""
        print(f"Qt sensor {self.device_id} thread started")
        
        while not self.isInterruptionRequested():
            # Generate a random temperature with some correlation to previous reading
            drift = random.uniform(-self.noise_level, self.noise_level)
            new_temp = self._last_temp + drift
            
            # Keep temperature within bounds
            new_temp = max(self.min_temp, min(self.max_temp, new_temp))
            self._last_temp = new_temp
            
            # Create reading data
            reading = {
                "temperature": new_temp,
                "timestamp": time.time(),
                "unit": "celsius"
            }
            
            # Store in readings history
            self._readings.append(reading)
            
            # Emit the data
            self.dataReady.emit(reading)
            
            # Keep only the last 1000 readings
            if len(self._readings) > 1000:
                self._readings = self._readings[-1000:]
            
            # Sleep for the appropriate interval (using QThread's msleep)
            self.msleep(int(1000 / self.data_rate))
        
        print(f"Qt sensor {self.device_id} thread stopped")


# Test the runtime protocol checking
def test_protocol_compliance():
    """Test that both sensors comply with the DataAcquisitionDevice protocol."""
    threading_sensor = ThreadingSensor("thread_temp", data_rate=2.0)
    qt_sensor = QtSensor("qt_temp", data_rate=2.0)
    
    assert is_data_acquisition_device(threading_sensor), "ThreadingSensor failed protocol check"
    assert is_data_acquisition_device(qt_sensor), "QtSensor failed protocol check"
    
    print("Both sensors comply with the DataAcquisitionDevice protocol!")
    return threading_sensor, qt_sensor


# Example usage
if __name__ == "__main__":
    threading_sensor, qt_sensor = test_protocol_compliance()
    
    # Start both sensors
    threading_sensor.initialize()
    threading_sensor.start()
    
    qt_sensor.initialize()
    qt_sensor.start()
    
    # Let them run for a few seconds
    time.sleep(5)
    
    # Get and print data
    print("\nThreading sensor data:", threading_sensor.get_data())
    print("Qt sensor data:", qt_sensor.get_data())
    
    # Stop both sensors
    threading_sensor.stop()
    qt_sensor.stop()
    
    print("\nDone!")