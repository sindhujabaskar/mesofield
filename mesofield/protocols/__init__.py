"""
Protocol definitions for hardware instruments and data management.

This module defines the core interfaces that standardize behavior across
the mesofield project, allowing for interoperability between different
hardware instruments, data producers, and data consumers.

Protocol Implementation Notes
----------------------------
When implementing these protocols, there are two approaches:

1. Direct inheritance (for regular classes without metaclass conflicts):
   ```python
   class MySensor(DataAcquisitionDevice):
       # Implement required methods and attributes
   ```

2. Duck typing (for classes with existing inheritance or metaclass conflicts, e.g., QThread):
   ```python
   class MyQThreadSensor(QThread):  # Cannot inherit from Protocol due to metaclass conflict
       # Implement all required methods and attributes
       device_type = "sensor"
       device_id = "my_sensor"
       # etc.
   ```

The second approach is necessary for Qt classes (QObject, QThread, QWidget) or 
any class that already uses a metaclass. Protocol checking uses duck typing 
internally, so both approaches will work with our system.
"""

from typing import Dict, List, Any, Optional, Protocol, TypeVar, Generic, runtime_checkable

T = TypeVar('T')

# These are the Protocol definitions - they are useful for static type checking
# and documentation, but should not be used for inheritance with classes that
# already have a metaclass (like QThread)

@runtime_checkable
class HardwareDevice(Protocol):
    """Protocol defining the standard interface for all hardware devices."""
    
    device_type: str
    device_id: str
    config: Dict[str, Any]
    
    def initialize(self) -> None:
        """Initialize the hardware device."""
        ...
    
    def start(self) -> bool:
        """Start data acquisition or operation.
        
        Returns:
            bool: True if started successfully, False otherwise.
        """
        ...
    
    def stop(self) -> bool:
        """Stop data acquisition or operation.
        
        Returns:
            bool: True if stopped successfully, False otherwise.
        """
        ...
    
    def close(self) -> None:
        """Close and clean up resources."""
        ...
    
    def get_status(self) -> Dict[str, Any]:
        """Get the current status of the device.
        
        Returns:
            Dict[str, Any]: Dictionary containing device status information.
        """
        ...


@runtime_checkable
class DataAcquisitionDevice(HardwareDevice, Protocol):
    """Protocol for devices that acquire data."""
    
    data_rate: float  # in Hz
    
    def get_data(self) -> Any:
        """Get the latest data from the device.
        
        Returns:
            Any: The latest data from the device.
        """
        ...


@runtime_checkable
class ControlDevice(HardwareDevice, Protocol):
    """Protocol for devices that control something."""
    
    def set_parameter(self, parameter: str, value: Any) -> bool:
        """Set a parameter on the device.
        
        Args:
            parameter: Name of the parameter to set.
            value: Value to set the parameter to.
            
        Returns:
            bool: True if parameter was set successfully, False otherwise.
        """
        ...
    
    def get_parameter(self, parameter: str) -> Any:
        """Get a parameter from the device.
        
        Args:
            parameter: Name of the parameter to get.
            
        Returns:
            Any: Value of the parameter.
        """
        ...

# Helper functions for protocol checking

def is_hardware_device(obj) -> bool:
    """Check if an object implements the HardwareDevice interface."""
    required_attrs = ['device_id', 'device_type', 'config', 'initialize', 
                     'start', 'stop', 'close', 'get_status']
    return all(hasattr(obj, attr) for attr in required_attrs)

def is_data_acquisition_device(obj) -> bool:
    """Check if an object implements the DataAcquisitionDevice interface."""
    if not is_hardware_device(obj):
        return False
    return hasattr(obj, 'data_rate') and hasattr(obj, 'get_data')

def is_control_device(obj) -> bool:
    """Check if an object implements the ControlDevice interface."""
    if not is_hardware_device(obj):
        return False
    return hasattr(obj, 'set_parameter') and hasattr(obj, 'get_parameter')


@runtime_checkable
class DataProducer(Protocol):
    """Protocol defining the interface for data-producing components."""
    
    @property
    def name(self) -> str:
        """Return the name of the data producer."""
        ...
    
    @property
    def producer_type(self) -> str:
        """Return the type of data this producer generates."""
        ...
    
    @property
    def is_active(self) -> bool:
        """Return whether the data producer is actively producing data."""
        ...
    
    def start(self) -> bool:
        """Start data production.
        
        Returns:
            bool: True if production started successfully, False otherwise.
        """
        ...
    
    def stop(self) -> bool:
        """Stop data production.
        
        Returns:
            bool: True if production stopped successfully, False otherwise.
        """
        ...
    
    def get_data(self) -> Optional[Any]:
        """Get the latest data from the producer.
        
        Returns:
            Optional[Any]: The latest data, or None if no data available.
        """
        ...
    
    @property
    def metadata(self) -> Dict[str, Any]:
        """Return metadata about the data producer and its output."""
        ...


@runtime_checkable
class DataConsumer(Protocol):
    """Protocol defining the interface for data-consuming components."""
    
    @property
    def name(self) -> str:
        """Return the name of the data consumer."""
        ...
    
    @property
    def accepted_data_types(self) -> List[str]:
        """Return the types of data this consumer can process."""
        ...
    
    def process_data(self, data: Any, metadata: Dict[str, Any]) -> bool:
        """Process data with metadata.
        
        Args:
            data: The data to process.
            metadata: Metadata about the data, including source, timestamp, etc.
            
        Returns:
            bool: True if data was processed successfully, False otherwise.
        """
        ...