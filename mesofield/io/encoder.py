import random
import time
import math
from queue import Queue
import serial
from PyQt6.QtCore import pyqtSignal, QThread

from mesofield.io import DataManager

class SerialWorker(QThread):
    """
    SerialWorker is a QThread subclass responsible for handling encoder data through two modes:
    development mode (generating simulated data) or serial mode (reading a real serial port).

    Signals:
    
        1. `serialDataReceived` (pyqtSignal(int)): Emits each time a new encoder reading is captured.
        2. `serialStreamStarted` (pyqtSignal()): Emits when the streaming thread starts running.
        3. `serialStreamStopped` (pyqtSignal()): Emits when the streaming thread stops running.
        4. `serialSpeedUpdated` (pyqtSignal(float, float)): Emits the elapsed time and current speed.
    
    Core Methods:
    
        `start()`: Initiates the thread and emits serialStreamStarted.
        `stop()`: Requests the thread interruption, waits for it, and emits serialStreamStopped.
        `get_data()`: Returns a DataFrame containing stored encoder readings, time, and computed speeds.
        `process_data(position_change)`: Updates and stores the computed speed using the encoder clicks.
        `calculate_speed(delta_clicks, delta_time)`: Performs speed calculation in meters/second.
    """
    
    # ===================== PyQt Signals ===================== #
    serialDataReceived = pyqtSignal(int) # Emits each time a new encoder reading is captured
    serialStreamStarted = pyqtSignal() # Emits when the streaming thread starts running
    serialStreamStopped = pyqtSignal() # Emits when the streaming thread stops running
    serialSpeedUpdated = pyqtSignal(float, float) # Emits the elapsed time (float) and current speed (float)
    # ======================================================== #

    def __init__(self, 
                 serial_port: str, 
                 baud_rate: int, 
                 sample_interval: int, 
                 wheel_diameter: float,
                 cpr: int,
                 development_mode: bool = True):
        
        super().__init__()

        self.development_mode = development_mode

        self.serial_port = serial_port
        self.baud_rate = baud_rate
        self.sample_interval_ms = sample_interval
        self.diameter_mm = wheel_diameter
        self.cpr = cpr

        self.init_data()


    def init_data(self):
        self.stored_data = []
        self.times = []
        self.speeds = []
        self.clicks = []
        self.start_time = None


    def start(self):
        self.serialStreamStarted.emit()
        return super().start()
    
    
    def stop(self):
        self.requestInterruption()
        self.wait()
        self.serialStreamStopped.emit()


    def run(self):
        self.init_data()
        self.start_time = time.time()
        try:
            if self.development_mode:
                self.run_development_mode()
            else:
                self.run_serial_mode()
        finally:
            print("Encoder Stream stopped.")
            
            
    def run_development_mode(self):
        while not self.isInterruptionRequested():
            try:
                # Simulate receiving random encoder clicks
                clicks = random.randint(1, 10)  # Simulating random click values
                
                # Emit signals, store data, and push to the queue
                self.stored_data.append(clicks)  # Store data for later retrieval
                self.serialDataReceived.emit(clicks)  # Emit PyQt signal for real-time plotting
                
                # Optionally, simulate processing the data for speed calculation
                self.process_data(clicks)
            except Exception as e:
                print(f"Exception in DevelopmentSerialWorker: {e}")
                self.requestInterruption()
            self.msleep(self.sample_interval_ms)  # Sleep for sample interval to reduce CPU usage


    def run_serial_mode(self):
        """
        Runs a continuous loop to read integer data from the configured serial port. 
        Emits raw encoder clicks and send them to processed_data() method.

        Emits:
        
        - serialDataReceived (pyqtSignal(int)): Emits each time a new encoder reading is captured.
        - serialStreamStopped (pyqtSignal()): Emits when the streaming thread stops running.
    
        Raises:
        
            `serial.SerialException`: If there is an issue opening or reading from the serial port.
            `ValueError`: If non-integer values are encountered while reading data.
        """
        
        try:
            self.arduino = serial.Serial(self.serial_port, self.baud_rate, timeout=0.1)
            print("Serial port opened.")
        except serial.SerialException as e:
            print(f"Serial connection error: {e}")
            return
        
        try:
            while not self.isInterruptionRequested():
                try:
                    data = self.arduino.readline().decode('utf-8').strip()
                    if data:
                        clicks = int(data)
                        self.serialDataReceived.emit(clicks)  # Emit PyQt signal for real-time plotting
                        self.process_data(clicks)
                except ValueError:
                    print(f"Non-integer data received: {data}")
                except serial.SerialException as e:
                    print(f"Serial exception: {e}")
                    self.requestInterruption()
                self.msleep(1)  # Sleep for 1ms to reduce CPU usage
        finally:
            if hasattr(self, 'arduino') and self.arduino is not None:
                try:
                    self.arduino.close()
                    print("Serial port closed.")
                except Exception as e:
                    print(f"Exception while closing serial port: {e}")


    def process_data(self, position_change):
        try:
            # Use fixed delta_time based on sample interval
            delta_time = self.sample_interval_ms / 1000.0  # Convert milliseconds to seconds

            # Calculate speed
            speed = self.calculate_speed(position_change, delta_time)

            # Update data lists
            current_time = time.time()
            self.times.append(current_time - self.start_time)
            self.speeds.append(speed)
            self.clicks.append(position_change)

            # Emit a signal for speed update
            self.serialSpeedUpdated.emit((current_time - self.start_time), speed)
        except Exception as e:
            print(f"Exception in processData: {e}")


    def calculate_speed(self, delta_clicks, delta_time):
        """Calculates speed of a wheel with diameter_mm in meters/second
        """
        
        reverse = 1  # Placeholder for direction configuration
        diameter_m = self.diameter_mm / 1000.0 #convert millimeters to meters
        rotations = delta_clicks / self.cpr
        distance = reverse * rotations * (math.pi * diameter_m)  # Circumference * rotations
        speed = distance / delta_time
        return speed
    
        
    def get_data(self):
        from pandas import DataFrame

        clicks = self.clicks
        times = self.times
        speeds = self.speeds
        data = {
            'Clicks': clicks,
            'Time': times,
            'Speed': speeds
        }
        encoder_df = DataFrame(data)
        return encoder_df
    
    
    def clear_data(self):
        self.stored_data = []
        self.times = []
        self.speeds = []
        self.start_time = time.time()
    

    def __repr__(self):
        class_name = self.__class__.__name__
        module_name = self.__module__
        parent_classes = [cls.__name__ for cls in self.__class__.__bases__]
        return (
            f"<{class_name} {parent_classes} from {module_name}>"
        )

# Usage Example:
# Replace the original SerialWorker instantiation with SerialWorker in development mode
# encoder = SerialWorker(cfg=your_config, development_mode=True)
# encoder.start()
