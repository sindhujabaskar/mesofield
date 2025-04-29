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

from PyQt6.QtCore import pyqtSignal, QThread


@dataclass
class EncoderData:
    distance: float
    speed: float
    timestamp: Optional[int] = None

    def __repr__(self):
        return (f"EncoderData(timestamp={self.timestamp}, "
                f"distance={self.distance:.3f} mm, speed={self.speed:.3f} mm/s)")

class EncoderSerialInterface(QThread):
    
    serialDataReceived = pyqtSignal(object)  # Emits the parsed EncoderData
    serialStreamStarted = pyqtSignal()         # Emits when streaming starts
    serialStreamStopped = pyqtSignal()         # Emits when streaming stops
    serialSpeedUpdated = pyqtSignal(float, float)  # Emits elapsed time and current speed

    def __init__(self, port: str, baudrate: int = 192000, data_callback=None):
        super().__init__()
        self.logger = logging.getLogger("EncoderSerialInterface")
        self.serial_port = port
        self.baud_rate = baudrate
        self.data_callback = data_callback
        
        self._recording = False
        self._recording_file = None
        self._recorded_data = []
        try:
            self.ser = serial.Serial(port, baudrate, timeout=1)
        except serial.SerialException as e:
            self.logger.error(f"Failed to open serial port {port}: {e}")
            raise

        self.data_saver = None
        self.logger.info(f"EncoderSerialInterface initialized on port {port} with baudrate {baudrate}")

    def start_recording(self, file_path: str):
        if not self.isRunning():
            self.start()
        if self.isRunning():
            # Flush the input buffer to discard any backlog of serial data.
            self.ser.reset_input_buffer()
            self._recording = True
            self._recording_file = file_path
            self._recorded_data = []
            self.logger.info(f"Recording started. Data will be stored to {file_path}")
        else:
            self.logger.warning("Cannot start recording: Serial interface is not running.")

    def stop_recording(self):
        if self._recording:
            self._recording = False
            try:
                with open(self._recording_file, 'w', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=['timestamp', 'distance', 'speed'])
                    writer.writeheader()
                    for d in self._recorded_data:
                        writer.writerow({'timestamp': d.timestamp, 'distance': d.distance, 'speed': d.speed})
                self.logger.info(f"Recording stopped. Data saved to {self._recording_file}")
            except Exception as e:
                self.logger.error(f"Failed to save recorded data: {e}")
        else:
            self.logger.warning(f"Recording not active; nothing to stop.")

    def start(self):
        self.serialStreamStarted.emit()
        super().start()

    def stop(self):
        self.requestInterruption()
        self.wait()
        if self.ser.is_open:
            self.ser.close()
        self.serialStreamStopped.emit()
        self.logger.info(f"Serial interface stopped and port closed.")

    def run(self):
        self.logger.info(f"Serial read thread started.")
        while not self.isInterruptionRequested():
            try:
                raw_line = self.ser.readline()
                if not raw_line:
                    continue
                line = raw_line.decode('utf-8', errors='replace').strip()
                if line:
                    data = self._parse_line(line)
                    if data:
                        if self.data_callback:
                            self.data_callback(data)
                        # Emit signals
                        self.serialDataReceived.emit(data)
                        self.serialSpeedUpdated.emit(data.timestamp or 0, data.speed)
                        # Record data if recording is active.
                        if self._recording:
                            self._recorded_data.append(data)
            except serial.SerialException as e:
                self.logger.error(f"Serial error: {e}")
                break
            except Exception as ex:
                self.logger.error(f"Unexpected error: {ex}")
        self.logger.info(f"Exiting serial read loop.")

    def _parse_line(self, line: str) -> Optional[EncoderData]:
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
                self.logger.debug(f"Ignored non-data line: {line}")
                return None
        except ValueError:
            self.logger.debug(f"Failed to parse line: {line}")
            return None

    def send_command(self, command: str):
        if self.ser.is_open:
            self.ser.write(command.encode('utf-8'))
            self.logger.info(f"Sent command: {command}")
        else:
            self.logger.warning(f"Serial port not open; command not sent.")

    def shutdown(self):
        self.stop()

def main():
    """
    Demonstration of how to use the EncoderSerialInterface.
    """
    def process_encoder_data(data: EncoderData):
        print(data)
    
    port = 'COM6'
    encoder_interface = EncoderSerialInterface(port)
    encoder_interface.start()

    try:
        encoder_interface.send_command('?')
        while True:
            time.sleep(1)
    finally:
        encoder_interface.stop()


if __name__ == '__main__':
    main()
