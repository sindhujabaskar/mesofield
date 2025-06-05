import queue
import time
import threading
import asyncio
import os
import csv
from pathlib import Path
from typing import Dict, List, Any, Optional, TypeVar, Generic, Type, Callable, Set, Union
from dataclasses import dataclass, field
import numpy as np

from mesofield.protocols import DataProducer, DataConsumer, HardwareDevice

T = TypeVar('T')


@dataclass
class DataPoint(Generic[T]):
    """Class representing a single data point with timestamp and metadata."""
    
    data: T
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


class DataBuffer(Generic[T]):
    """Buffer for storing data points with thread-safe access."""
    
    def __init__(self, maxsize: int = 1000):
        self.maxsize = maxsize
        self.buffer: List[DataPoint[T]] = []
        self.lock = threading.Lock()
    
    def add(self, data_point: DataPoint[T]) -> None:
        """Add a data point to the buffer, ensuring size limits."""
        with self.lock:
            self.buffer.append(data_point)
            if len(self.buffer) > self.maxsize:
                self.buffer = self.buffer[-self.maxsize:]
    
    def get_all(self) -> List[DataPoint[T]]:
        """Get all data points in the buffer."""
        with self.lock:
            return self.buffer.copy()
    
    def get_latest(self) -> Optional[DataPoint[T]]:
        """Get the most recent data point."""
        with self.lock:
            if not self.buffer:
                return None
            return self.buffer[-1]
    
    def get_range(self, start_idx: int, end_idx: Optional[int] = None) -> List[DataPoint[T]]:
        """Get a range of data points."""
        with self.lock:
            if end_idx is None:
                return self.buffer[start_idx:].copy()
            return self.buffer[start_idx:end_idx].copy()
    
    def clear(self) -> None:
        """Clear all data points from the buffer."""
        with self.lock:
            self.buffer.clear()
    
    def __len__(self) -> int:
        """Get the number of data points in the buffer."""
        with self.lock:
            return len(self.buffer)


class DataStream:
    """Class representing a data stream from a data producer."""

    def __init__(
        self,
        producer: DataProducer,
        buffer_size: int = 1000,
        time_provider: Optional[Callable[[], float]] = None,
    ) -> None:
        self.producer = producer
        self.buffer = DataBuffer(maxsize=buffer_size)
        self.consumers: List[DataConsumer] = []
        self.active = False
        self.thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        # Function that provides timestamps for collected data
        self.time_provider = time_provider or time.time
    
    def start(self) -> bool:
        """Start the data stream."""
        if self.active:
            return True
        
        if not self.producer.start():
            return False
        
        self.active = True
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._collection_loop)
        self.thread.daemon = True
        self.thread.start()
        return True
    
    def stop(self) -> bool:
        """Stop the data stream."""
        if not self.active:
            return True
        
        self.stop_event.set()
        success = self.producer.stop()
        self.active = False
        
        if self.thread is not None:
            self.thread.join(timeout=1.0)
            self.thread = None
        
        return success
    
    def add_consumer(self, consumer: DataConsumer) -> bool:
        """Add a data consumer to this stream."""
        if consumer in self.consumers:
            return False
        
        # Check if this consumer accepts our data type
        if self.producer.producer_type not in consumer.accepted_data_types:
            return False
        
        self.consumers.append(consumer)
        return True
    
    def remove_consumer(self, consumer: DataConsumer) -> bool:
        """Remove a data consumer from this stream."""
        if consumer not in self.consumers:
            return False
        
        self.consumers.remove(consumer)
        return True
    
    def _collection_loop(self):
        """Main loop for collecting data from the producer."""
        while not self.stop_event.is_set() and self.active:
            data = self.producer.get_data()
            if data is not None:
                # Create data point with metadata
                ts = self.time_provider()
                metadata = {
                    "source": self.producer.name,
                    "type": self.producer.producer_type,
                    "timestamp": ts,
                    **self.producer.metadata,
                }
                data_point = DataPoint(data=data, timestamp=ts, metadata=metadata)
                
                # Add to buffer
                self.buffer.add(data_point)
                
                # Process with consumers
                for consumer in self.consumers:
                    consumer.process_data(data, metadata)
            
            # Small sleep to prevent CPU hogging
            time.sleep(0.001)
    
    def get_data(self) -> List[DataPoint]:
        """Get all data points in the buffer."""
        return self.buffer.get_all()
    
    def get_latest_data(self) -> Optional[DataPoint]:
        """Get the latest data point."""
        return self.buffer.get_latest()
    
    def get_data_range(self, start_idx: int, end_idx: Optional[int] = None) -> List[DataPoint]:
        """Get a range of data points."""
        return self.buffer.get_range(start_idx, end_idx)
    
    def clear_buffer(self) -> None:
        """Clear the data buffer."""
        self.buffer.clear()


class DataManager:
    """Class for managing multiple data streams from different producers."""
    
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(DataManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, loop: Optional[asyncio.AbstractEventLoop] = None):
        if not getattr(self, '_initialized', False):
            self.loop = loop or asyncio.get_event_loop()
            self.streams: Dict[str, DataStream] = {}
            self.lock = threading.Lock()
            self.consumers: Dict[str, DataConsumer] = {}
            # Legacy queue support for backward compatibility
            self._queue = queue.Queue()
            # Global reference start time for timestamp synchronization
            self.start_time: Optional[float] = None
            self._initialized = True

    # ------------------------------------------------------------------
    # Timestamp Management
    # ------------------------------------------------------------------
    def _timestamp(self) -> float:
        """Return a timestamp relative to the manager start time."""
        if self.start_time is None:
            # Lazily set the reference if it hasn't been set explicitly
            self.start_time = time.time()
        return time.time() - self.start_time

    
    def register_producer(self, producer: DataProducer, buffer_size: int = 1000) -> bool:
        """Register a data producer with the manager.
        
        Args:
            producer: The data producer to register.
            buffer_size: Size of the buffer for this producer's data.
            
        Returns:
            bool: True if registration successful, False otherwise.
        """
        with self.lock:
            if producer.name in self.streams:
                return False
            
            stream = DataStream(
                producer=producer,
                buffer_size=buffer_size,
                time_provider=self._timestamp,
            )
            self.streams[producer.name] = stream
            
            # Add all compatible consumers to this stream
            for consumer in self.consumers.values():
                if producer.producer_type in consumer.accepted_data_types:
                    stream.add_consumer(consumer)
            
            return True
    
    def unregister_producer(self, producer_name: str) -> bool:
        """Unregister a data producer from the manager.
        
        Args:
            producer_name: Name of the producer to unregister.
            
        Returns:
            bool: True if unregistration successful, False otherwise.
        """
        with self.lock:
            if producer_name not in self.streams:
                return False
            
            if self.streams[producer_name].active:
                self.streams[producer_name].stop()
            
            del self.streams[producer_name]
            return True
    
    def register_consumer(self, consumer: DataConsumer) -> bool:
        """Register a data consumer with the manager.
        
        Args:
            consumer: The data consumer to register.
            
        Returns:
            bool: True if registration successful, False otherwise.
        """
        with self.lock:
            if consumer.name in self.consumers:
                return False
            
            self.consumers[consumer.name] = consumer
            
            # Add this consumer to compatible streams
            for stream in self.streams.values():
                if stream.producer.producer_type in consumer.accepted_data_types:
                    stream.add_consumer(consumer)
            
            return True
    
    def unregister_consumer(self, consumer_name: str) -> bool:
        """Unregister a data consumer from the manager.
        
        Args:
            consumer_name: Name of the consumer to unregister.
            
        Returns:
            bool: True if unregistration successful, False otherwise.
        """
        with self.lock:
            if consumer_name not in self.consumers:
                return False
            
            consumer = self.consumers[consumer_name]
            
            # Remove this consumer from all streams
            for stream in self.streams.values():
                stream.remove_consumer(consumer)
            
            del self.consumers[consumer_name]
            return True
    
    def start_all(self) -> bool:
        """Start all data streams.
        
        Returns:
            bool: True if all streams started successfully, False otherwise.
        """
        success = True

        with self.lock:
            if self.start_time is None:
                self.start_time = time.time()
            for stream in self.streams.values():
                if not stream.start():
                    success = False
        
        return success
    
    def stop_all(self) -> bool:
        """Stop all data streams.
        
        Returns:
            bool: True if all streams stopped successfully, False otherwise.
        """
        success = True
        
        with self.lock:
            for stream in self.streams.values():
                if not stream.stop():
                    success = False
        
        return success
    
    def start_stream(self, producer_name: str) -> bool:
        """Start a specific data stream.
        
        Args:
            producer_name: Name of the producer whose stream to start.
            
        Returns:
            bool: True if stream started successfully, False otherwise.
        """
        with self.lock:
            if producer_name not in self.streams:
                return False
            if self.start_time is None:
                self.start_time = time.time()
            return self.streams[producer_name].start()
    
    def stop_stream(self, producer_name: str) -> bool:
        """Stop a specific data stream.
        
        Args:
            producer_name: Name of the producer whose stream to stop.
            
        Returns:
            bool: True if stream stopped successfully, False otherwise.
        """
        with self.lock:
            if producer_name not in self.streams:
                return False
            
            return self.streams[producer_name].stop()
    
    def get_data(self, producer_name: str) -> Optional[List[DataPoint]]:
        """Get all data from a specific producer.
        
        Args:
            producer_name: Name of the producer to get data from.
            
        Returns:
            Optional[List[DataPoint]]: List of data points if producer exists, None otherwise.
        """
        with self.lock:
            if producer_name not in self.streams:
                return None
            
            return self.streams[producer_name].get_data()
    
    def get_latest_data(self, producer_name: str) -> Optional[DataPoint]:
        """Get the latest data point from a specific producer.
        
        Args:
            producer_name: Name of the producer to get data from.
            
        Returns:
            Optional[DataPoint]: The latest data point if producer exists and has data,
                               None otherwise.
        """
        with self.lock:
            if producer_name not in self.streams:
                return None
            
            return self.streams[producer_name].get_latest_data()
    
    def get_all_latest_data(self) -> Dict[str, Optional[DataPoint]]:
        """Get the latest data point from all producers.
        
        Returns:
            Dict[str, Optional[DataPoint]]: Dictionary mapping producer names to their latest data points.
        """
        result = {}
        
        with self.lock:
            for name, stream in self.streams.items():
                result[name] = stream.get_latest_data()
        
        return result
    
    def get_data_by_type(self, data_type: str) -> Dict[str, List[DataPoint]]:
        """Get all data of a specific type from all producers.
        
        Args:
            data_type: Type of data to retrieve.
            
        Returns:
            Dict[str, List[DataPoint]]: Dictionary mapping producer names to their data of the specified type.
        """
        result = {}
        
        with self.lock:
            for name, stream in self.streams.items():
                if stream.producer.producer_type == data_type:
                    result[name] = stream.get_data()
        
        return result
    
    def get_latest_data_by_type(self, data_type: str) -> Dict[str, Optional[DataPoint]]:
        """Get the latest data of a specific type from all producers.
        
        Args:
            data_type: Type of data to retrieve.
            
        Returns:
            Dict[str, Optional[DataPoint]]: Dictionary mapping producer names to their latest data of the specified type.
        """
        result = {}
        
        with self.lock:
            for name, stream in self.streams.items():
                if stream.producer.producer_type == data_type:
                    result[name] = stream.get_latest_data()
        
        return result
    
    @property
    def active_streams(self) -> List[str]:
        """Get a list of active stream names.
        
        Returns:
            List[str]: List of names of active streams.
        """
        result = []
        
        with self.lock:
            for name, stream in self.streams.items():
                if stream.active:
                    result.append(name)
        
        return result
    
    @property
    def available_data_types(self) -> List[str]:
        """Get a list of available data types from all producers.
        
        Returns:
            List[str]: List of available data types.
        """
        result = set()
        
        with self.lock:
            for stream in self.streams.values():
                result.add(stream.producer.producer_type)

        return list(result)

    # ------------------------------------------------------------------
    # Data Export Utilities
    # ------------------------------------------------------------------
    def export_all_to_directory(self, directory: str) -> None:
        """Export buffered data from all streams to CSV files."""
        Path(directory).mkdir(parents=True, exist_ok=True)

        with self.lock:
            for name, stream in self.streams.items():
                data = stream.get_data()
                if not data:
                    continue
                csv_path = Path(directory) / f"{name}_stream.csv"
                with open(csv_path, "w", newline="") as f:
                    writer = None
                    for dp in data:
                        row = {"timestamp": dp.timestamp, **dp.metadata, "data": dp.data}
                        if writer is None:
                            writer = csv.DictWriter(f, fieldnames=list(row.keys()))
                            writer.writeheader()
                        writer.writerow(row)

    def close_consumers(self) -> None:
        """Close any consumers that expose a close() method."""
        with self.lock:
            for consumer in self.consumers.values():
                if hasattr(consumer, "close"):
                    try:
                        consumer.close()
                    except Exception:
                        pass
    
    
    # Compatibility with HardwareDevice protocol devices
    def register_hardware_device(self, device) -> bool:
        """Register a HardwareDevice as a data producer if it implements the required methods.
        
        Args:
            device: A device that implements the necessary methods for data production
            
        Returns:
            bool: True if registration successful, False otherwise
        """
        from mesofield.protocols import is_data_acquisition_device
        
        # Check if device implements the necessary interfaces
        if not is_data_acquisition_device(device):
            return False
            
        # Create an adapter that bridges HardwareDevice to DataProducer
        adapter = HardwareDeviceAdapter(device)
        return self.register_producer(adapter)


class HardwareDeviceAdapter(DataProducer):
    """Adapter class to bridge HardwareDevice to DataProducer protocol."""
    
    def __init__(self, device: 'HardwareDevice'):
        self.device = device
        self._active = False
        
    @property
    def name(self) -> str:
        return self.device.device_id
        
    @property
    def producer_type(self) -> str:
        return self.device.device_type
        
    @property
    def is_active(self) -> bool:
        return self._active
        
    def start(self) -> bool:
        try:
            self.device.start()
            self._active = True
            return True
        except Exception as e:
            print(f"Error starting device {self.name}: {e}")
            return False
            
    def stop(self) -> bool:
        try:
            self.device.stop()
            self._active = False
            return True
        except Exception as e:
            print(f"Error stopping device {self.name}: {e}")
            return False
            
    def get_data(self) -> Optional[Any]:
        if hasattr(self.device, 'get_data'):
            return self.device.get_data()
        return None
        
    @property
    def metadata(self) -> Dict[str, Any]:
        if hasattr(self.device, 'get_status'):
            return self.device.get_status()
        return {}


class CSVConsumer:
    """Simple data consumer that writes incoming data to a CSV file."""

    def __init__(self, file_path: str, accepted_data_types: Optional[List[str]] = None) -> None:
        self._path = Path(file_path)
        self._file = open(self._path, "w", newline="")
        self._writer: Optional[csv.DictWriter] = None
        self.accepted_data_types = accepted_data_types or ["*"]

    @property
    def name(self) -> str:  # type: ignore[override]
        return self._path.stem

    def process_data(self, data: Any, metadata: Dict[str, Any]) -> bool:  # type: ignore[override]
        row = {"timestamp": metadata.get("timestamp", time.time()), **metadata, "data": data}
        if self._writer is None:
            self._writer = csv.DictWriter(self._file, fieldnames=list(row.keys()))
            self._writer.writeheader()
        self._writer.writerow(row)
        self._file.flush()
        return True

    def close(self) -> None:
        if not self._file.closed:
            self._file.close()
