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

import serial
import time
import threading
import logging
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


class EncoderSerialInterface:
    """
    Abstraction for the Teensy serial interface running the EncoderInterfaceT4 firmware.

    This class encapsulates the serial communication and parsing logic, enabling easy
    integration with other modules that need encoder data.

    Attributes:
        port (str): The serial port (e.g., '/dev/ttyACM0' or 'COM3').
        baudrate (int): Serial communication speed (must match firmware, e.g., 192000).
        ser (serial.Serial): The underlying PySerial instance.
        data_callback (Optional[callable]): Callback function for new EncoderData.
    """

    def __init__(self, port: str, baudrate: int = 192000, data_callback=None):
        """
        Initialize the serial interface.

        Args:
            port (str): Serial port where the Teensy is connected.
            baudrate (int): Communication speed.
            data_callback (callable, optional): Function to call with each EncoderData.
        """
        self.port = port
        self.baudrate = baudrate
        self.data_callback = data_callback
        try:
            self.ser = serial.Serial(port, baudrate, timeout=1)
        except serial.SerialException as e:
            logging.error("Failed to open serial port %s: %s", port, e)
            raise
        self.running = False
        self.read_thread = None
        logging.info("EncoderSerialInterface initialized on port %s with baudrate %d",
                     port, baudrate)

    def start(self):
        """Start the background thread to read serial data."""
        self.running = True
        self.read_thread = threading.Thread(target=self._read_loop, daemon=True)
        self.read_thread.start()
        logging.info("Serial read thread started.")

    def stop(self):
        """Stop reading serial data and close the connection."""
        self.running = False
        if self.read_thread:
            self.read_thread.join()
        if self.ser.is_open:
            self.ser.close()
        logging.info("Serial interface stopped and port closed.")

    def _read_loop(self):
        """Internal loop for continuously reading lines from the serial port."""
        while self.running:
            try:
                # Read a line from the Teensy board
                raw_line = self.ser.readline()
                if not raw_line:
                    continue

                # Decode and strip newline characters
                line = raw_line.decode('utf-8', errors='replace').strip()
                if line:
                    data = self._parse_line(line)
                    if data and self.data_callback:
                        self.data_callback(data)
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

        Args:
            line (str): A single line from the serial port.

        Returns:
            EncoderData: An instance with parsed values, or None if parsing fails.
        """
        parts = line.split(',')
        try:
            if len(parts) == 3:
                # Format: timestamp, distance, speed
                timestamp = int(parts[0].strip())
                distance = float(parts[1].strip())
                speed = float(parts[2].strip())
                return EncoderData(distance=distance, speed=speed, timestamp=timestamp)
            elif len(parts) == 2:
                # Format: distance, speed
                distance = float(parts[0].strip())
                speed = float(parts[1].strip())
                return EncoderData(distance=distance, speed=speed)
            else:
                # Likely a header or message line (non-data)
                logging.debug("Ignored non-data line: %s", line)
                return None
        except ValueError:
            # Non-numeric data (e.g., header info)
            logging.debug("Failed to parse line: %s", line)
            return None

    def send_command(self, command: str):
        """
        Send a command to the Teensy board.

        The firmware recognizes commands such as:
          - '?' for version and header information.
          - 'c' for speed output calibration.

        Args:
            command (str): A single-character command.
        """
        if self.ser.is_open:
            self.ser.write(command.encode('utf-8'))
            logging.info("Sent command: %s", command)
        else:
            logging.warning("Serial port not open; command not sent.")


def main():
    """
    Demonstration of how to use the EncoderSerialInterface.
    
    This example:
      1. Sets up a callback to print each encoder reading.
      2. Starts the serial reading thread.
      3. Sends a '?' command to request header information.
      4. Runs until interrupted by the user.
    """

    def process_encoder_data(data: EncoderData):
        # Process or log the data; here we simply print it.
        print(data)

    # Adjust the port as necessary (e.g., 'COM3' on Windows or '/dev/ttyACM0' on Unix)
    port = 'COM6'
    encoder_interface = EncoderSerialInterface(port, data_callback=process_encoder_data)
    encoder_interface.start()

    try:
        # Send a command to display firmware header/version info
        encoder_interface.send_command('?')
        # Main loop; in a larger system, replace this with your event loop or integration code.
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Interrupt received, stopping.")
    finally:
        encoder_interface.stop()


if __name__ == '__main__':
    main()
