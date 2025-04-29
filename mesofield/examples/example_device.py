"""
Example implementation of a custom hardware device for mesofield.

This module shows how to create a custom hardware device that conforms to the
HardwareDevice protocol and can be registered with both the HardwareManager
and DataManager.
"""

import time
import random
from typing import Dict, Any, ClassVar, Optional, List
from dataclasses import dataclass

from mesofield.protocols import DataAcquisitionDevice


@dataclass
class TemperatureSensor:
    """Example temperature sensor hardware device.
    
    This is a simulated temperature sensor that generates random temperature
    readings at a specified rate.
    
    Implementation notes:
    This class implements the DataAcquisitionDevice protocol through duck typing,
    providing all the required attributes and methods without inheritance.
    This approach allows for compatibility with different threading models (QThread, 
    Python threading, asyncio) without metaclass conflicts.
    """
    
    # Required properties for HardwareDevice protocol
    device_type: ClassVar[str] = "temperature_sensor"
    device_id: str
    config: Dict[str, Any]
    
    # Required property for DataAcquisitionDevice protocol
    data_rate: float = 1.0  # Hz
    
    # Additional properties specific to this device
    min_temp: float = 20.0
    max_temp: float = 30.0
    noise_level: float = 0.5
    
    # Internal state
    _active: bool = False
    _last_temp: float = 25.0
    _last_reading_time: float = 0.0
    _readings: List[Dict[str, Any]] = None
    
    def __post_init__(self):
        """Initialize the device after dataclass initialization."""
        if self._readings is None:
            self._readings = []
        
        # Set default config if not provided
        if not self.config:
            self.config = {
                "min_temp": self.min_temp,
                "max_temp": self.max_temp,
                "noise_level": self.noise_level,
                "data_rate": self.data_rate
            }
        
        # Update instance attributes from config
        for key, value in self.config.items():
            if hasattr(self, key):
                setattr(self, key, value)
    
    def initialize(self) -> None:
        """Initialize the device."""
        self._active = False
        self._last_temp = (self.min_temp + self.max_temp) / 2
        self._last_reading_time = time.time()
        self._readings = []
        print(f"Temperature sensor {self.device_id} initialized")
    
    def start(self) -> bool:
        """Start data acquisition."""
        self._active = True
        self._last_reading_time = time.time()
        print(f"Temperature sensor {self.device_id} started")
        return True
    
    def stop(self) -> bool:
        """Stop data acquisition."""
        self._active = False
        print(f"Temperature sensor {self.device_id} stopped")
        return True
    
    def close(self) -> None:
        """Close and clean up resources."""
        self._active = False
        print(f"Temperature sensor {self.device_id} closed")
    
    def get_status(self) -> Dict[str, Any]:
        """Get the current status of the device."""
        return {
            "active": self._active,
            "last_reading_time": self._last_reading_time,
            "readings_count": len(self._readings),
            "data_rate": self.data_rate
        }
    
    def get_data(self) -> Dict[str, Any]:
        """Get the latest data from the device.
        
        In a real device, this would read from hardware.
        In this simulation, we generate random temperature values.
        """
        current_time = time.time()
        
        # If not active or if not enough time has passed since last reading, return None
        if not self._active or (current_time - self._last_reading_time) < (1.0 / self.data_rate):
            return None
        
        # Generate a random temperature with some correlation to the previous reading
        drift = random.uniform(-self.noise_level, self.noise_level)
        new_temp = self._last_temp + drift
        
        # Keep temperature within bounds
        new_temp = max(self.min_temp, min(self.max_temp, new_temp))
        
        # Update state
        self._last_temp = new_temp
        self._last_reading_time = current_time
        
        # Create reading data
        reading = {
            "temperature": new_temp,
            "timestamp": current_time,
            "unit": "celsius"
        }
        
        # Store in readings history
        self._readings.append(reading)
        
        # Keep only the last 1000 readings
        if len(self._readings) > 1000:
            self._readings = self._readings[-1000:]
        
        return reading


# Example usage:
# Create a temperature sensor
def create_temperature_sensor(sensor_id: str = "temp1", config: Optional[Dict[str, Any]] = None) -> TemperatureSensor:
    """Create a temperature sensor with the given ID and configuration."""
    if config is None:
        config = {
            "min_temp": 18.0,
            "max_temp": 32.0,
            "noise_level": 0.2,
            "data_rate": 2.0  # 2 Hz
        }
    
    sensor = TemperatureSensor(device_id=sensor_id, config=config)
    sensor.initialize()
    return sensor