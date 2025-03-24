#!/usr/bin/env python3
"""
encoder_interface.py

This module provides a serial interface to a Teensy board running the EncoderInterfaceT4 firmware.
It abstracts the serial communication and encoder data parsing to allow easy integration into larger systems.

Firmware Data Format:
  - With SHOW_MICROS defined:
      "micros,distance (mm),speed (mm/s)"
  - Without SHOW_MICROS defined:
      "distance (mm),speed (mm/s)"
      
Supported Commands:
  | Command | Description                                  |
  |---------|----------------------------------------------|
  | '?'     | Print version and header info                |
  | 'c'     | Initiate speed output calibration            |

Usage Example:
    def process_encoder_data(data):
        print(data)

    encoder_interface = EncoderSerialInterface('/dev/ttyACM0', data_callback=process_encoder_data)
    encoder_interface.start()
    
    # Send a command to get header information.
    encoder_interface.send_command('?')
    
    # Run until interrupted...
"""
import os
import serial
import time
import threading
import logging
import csv
from typing import Optional
from dataclasses import dataclass

# Configure logging for demonstration purposes.
logging.basicConfig(level=logging.INFO)

@dataclass
class EncoderData:
    distance: float
    speed: float
    timestamp: Optional[int] = None

    def __repr__(self):
        return (f"EncoderData(timestamp={self.timestamp}, "
                f"distance={self.distance:.3f} mm, speed={self.speed:.3f} mm/s)")

class DataLogger:
    """
    Logs movement data to a CSV file.
    """
    def __init__(self, filename):
        """
        Initialize the data logger.
        
        Args:
            filename (str): Path to the CSV file.
        """
        self.filename = filename
        self.fieldnames = ['timestamp', 'distance', 'speed']
        file_exists = os.path.isfile(self.filename)
        self.file = open(self.filename, 'a', newline='')
        self.writer = csv.DictWriter(self.file, fieldnames=self.fieldnames)
        if not file_exists:
            self.writer.writeheader()

    def log(self, data: EncoderData):
        self.writer.writerow({'timestamp': data.timestamp, 'distance': data.distance, 'speed': data.speed})
        self.file.flush()

    def close(self):
        self.file.close()



from PyQt6.QtCore import pyqtSignal, QThread

class EncoderSerialInterface(QThread):
    # QThread signals similar to SerialWorker
    serialDataReceived = pyqtSignal(object)  # Emits the parsed EncoderData
    serialStreamStarted = pyqtSignal()         # Emits when streaming starts
    serialStreamStopped = pyqtSignal()         # Emits when streaming stops
    serialSpeedUpdated = pyqtSignal(float, float)  # Emits elapsed time and current speed

    def __init__(self, port: str, baudrate: int = 192000, data_callback=None):
        super().__init__()
        self.serial_port = port
        self.baud_rate = baudrate
        self.data_callback = data_callback

        try:
            self.ser = serial.Serial(port, baudrate, timeout=1)
        except serial.SerialException as e:
            logging.error("Failed to open serial port %s: %s", port, e)
            raise

        # Optional: holds a DataLogger instance if set_save_dir is used.
        self.data_saver = None
        logging.info("EncoderSerialInterface initialized on port %s with baudrate %d",
                     port, baudrate)

    def set_save_dir(self, save_path: str):
        self.save_dir = save_path
        self.data_saver = DataLogger(save_path)
        self.data_callback = self.data_saver.log

    def start(self):
        """Override start to emit the stream started signal."""
        self.serialStreamStarted.emit()
        super().start()

    def stop(self):
        """Stop reading serial data and close the connection."""
        self.requestInterruption()
        self.wait()
        if self.ser.is_open:
            self.ser.close()
        self.serialStreamStopped.emit()
        logging.info("Serial interface stopped and port closed.")

    def run(self):
        """QThread run method; continuously reads lines from the serial port."""
        logging.info("Serial read thread started.")
        while not self.isInterruptionRequested():
            try:
                raw_line = self.ser.readline()
                if not raw_line:
                    continue

                # Decode and strip newline characters
                line = raw_line.decode('utf-8', errors='replace').strip()
                if line:
                    data = self._parse_line(line)
                    if data:
                        if self.data_callback:
                            self.data_callback(data)
                        self.serialSpeedUpdated.emit(data.timestamp or 0, data.speed)
            except serial.SerialException as e:
                logging.error("Serial error: %s", e)
                break
            except Exception as ex:
                logging.error("Unexpected error: %s", ex)
        logging.info("Exiting serial read loop.")

    def _parse_line(self, line: str) -> Optional[EncoderData]:
        """
        Parse a line of serial output.
        
        Expected line formats:
          - "timestamp,distance,speed"  or
          - "distance,speed"
        
        Returns an EncoderData instance or None if parsing fails.
        """
        parts = line.split(',')
        try:
            if len(parts) == 3:
                timestamp = int(parts[0].strip())
                distance = float(parts[1].strip())
                speed = float(parts[2].strip())
                return EncoderData(distance=distance, speed=speed, timestamp=timestamp)
            elif len(parts) == 2:
                distance = float(parts[0].strip())
                speed = float(parts[1].strip())
                return EncoderData(distance=distance, speed=speed)
            else:
                logging.debug("Ignored non-data line: %s", line)
                return None
        except ValueError:
            logging.debug("Failed to parse line: %s", line)
            return None

    def send_command(self, command: str):
        """
        Send a command to the Teensy board.
        """
        if self.ser.is_open:
            self.ser.write(command.encode('utf-8'))
            logging.info("Sent command: %s", command)
        else:
            logging.warning("Serial port not open; command not sent.")

    def shutdown(self):
        """Close the serial port and clean up resources."""
        self.stop()
        if self.data_saver:
            self.data_saver.close()

def main():
    """
    Demonstration of how to use the EncoderSerialInterface.
    """
    def process_encoder_data(data: EncoderData):
        print(data)
    
    port = 'COM6'
    encoder_interface = EncoderSerialInterface(port)
    encoder_interface.set_save_dir('encoder_data.csv')
    encoder_interface.start()

    try:
        encoder_interface.send_command('?')
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Interrupt received, stopping.")
    finally:
        encoder_interface.stop()


if __name__ == '__main__':
    main()
