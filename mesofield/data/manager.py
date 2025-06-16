from __future__ import annotations
"""
DataManager & DataSaver Workflow Overview
1. Initialization
    ├─ dm = DataManager()
    └─ dm.setup(config, path, devices)
2. Optional data persistence via DataSaver
    ├─ dm.saver.save_config()         # writes experiment config to disk
    ├─ dm.saver.save_encoder_data(df) # writes encoder CSV + updates encoder.output_path
    ├─ dm.saver.save_notes()          # writes notes.txt if any
    └─ dm.saver.writer_for(camera)    # returns `CustomWriter`, sets camera.output_path & metadata_path
3. Final database update: dm.update_database()
    update_database()
    ├─ camera data
    │   └─ sessiondb.camera_dataframe(cameras, subject, session)
    │       └─ dm.append_to_database(df, key="camera_data")
    ├─ encoder data
    │   └─ sessiondb.encoder_dataframe(encoder, subject, session)
    │       └─ dm.append_to_database(df, key="encoder")
    ├─ device files
    │   └─ dm.get_device_outputs(subject, session)
    │       └─ dm.append_to_database(df, key="device_files")
    ├─ notes
    │   └─ sessiondb.notes_dataframe(notes, subject, session)
    │       └─ dm.append_to_database(df, key="notes")
    ├─ timestamps
    │   └─ sessiondb.timestamps_dataframe(bids_dir, subject, session)
    │       └─ dm.append_to_database(df, key="timestamps")
    └─ config snapshot
         └─ sessiondb.config_dataframe(config)
              └─ dm.append_to_database(df, key="config")
              
• Each block is wrapped in try/except to log errors and continue remaining steps.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Any, Dict, Iterable
from logging import Logger

import os
import queue
import csv
import threading
import time
from datetime import datetime

import pandas as pd

from mesofield.config import ExperimentConfig
from mesofield.data.writer import CustomWriter, CV2Writer
from mesofield.io.h5db import H5Database
from mesofield.io import sessiondb
from mesofield.utils._logger import get_logger, log_this_fr
from typing import Dict
from mesofield.utils._logger import get_logger


@dataclass
class DataPacket:
    """Entry in :class:`DataQueue`."""

    device_id: str
    timestamp: float
    payload: Any
    device_ts: float | None = None
    meta: Dict[str, Any] = field(default_factory=dict)


class DataQueue:
    """Thread-safe queue for data streaming between devices and consumers.
    
    Registered DataProducer (the :class:`DataManager`) devices can push data packets to this queue,
    which can then be consumed by other parts of the system.
    """

    def __init__(self, maxsize: int = 0) -> None:
        self._queue: queue.Queue[DataPacket] = queue.Queue(maxsize)

    def push(
        self,
        device_id: str,
        payload: Any,
        *,
        timestamp: float | None = None,
        device_ts: float | None = None,
        **meta: Any,
    ) -> None:
        """Add a new data packet to the queue."""
        if timestamp is None:
            timestamp = time.time()
        self._queue.put(DataPacket(device_id, timestamp, payload, device_ts, meta))

    def pop(self, block: bool = True, timeout: float | None = None) -> DataPacket:
        """Return the next :class:`DataPacket` from the queue."""
        return self._queue.get(block=block, timeout=timeout)

    def empty(self) -> bool:
        return self._queue.empty()


@dataclass
class DataPaths:
    """Structured storage for all output paths used by the :class:`DataSaver`.
    
    Relies on the :class:`ExperimentConfig` to generate paths based on the
    experiment's BIDS directory using the `make_path` method, which relies
    on HardwareDevices implementing a file_type, bids_type.
    
    These paths can then be passed to HardwareDevice.save_data(path)  
    """
    configuration: str
    notes: str
    timestamps: str
    hardware: Dict[str, str] = field(default_factory=dict)
    writers: Dict[str, str] = field(default_factory=dict)
    queue: str = ""

    @classmethod
    def build(cls, cfg: ExperimentConfig) -> DataPaths:
        cfg_paths = {
            "configuration": cfg.make_path("configuration", "csv"),
            "notes": cfg.make_path("notes", "txt"),
            "timestamps": cfg.make_path("timestamps", "csv"),
        }
        hw_paths: Dict[str, str] = {}
        for dev_id, device in cfg.hardware.devices.items():
            args = getattr(device, "path_args", {})
            suffix = args.get("suffix", dev_id)
            ext = args.get("extension", getattr(device, "file_type", "dat"))
            bids_type = args.get("bids_type", getattr(device, "bids_type"))
            hw_paths[dev_id] = cfg.make_path(suffix, ext, bids_type)
        return cls(
            configuration=cfg_paths["configuration"],
            notes=cfg_paths["notes"],
            timestamps=cfg_paths["timestamps"],
            hardware=hw_paths,
            writers={},
            queue=cfg.make_path("dataqueue", "csv", "beh"),
        )

@dataclass
class DataSaver:
    """Helper class for saving experiment data to disk.
    
    This class handles saving configuration, hardware data, notes, timestamps,
    and camera data to disk.
    
    Takes paths generated from :class:`DataPaths` instance and calls `Device.save_data(path)`
    on all hardware devices that implement this method.
    
    (NOTE: If a device does not implement `save_data`, it will be skipped.)
    
    Takes an :class:`ExperimentConfig` to save configuration.
    """
    
    cfg: ExperimentConfig
    paths: DataPaths = field(init=False)
    logger: Logger = field(default_factory=lambda: get_logger("DataSaver"))

    def __post_init__(self) -> None:
        self.paths = DataPaths.build(self.cfg)
        self.logger.info(f"Prepared output paths: {self.paths}")

    def configuration(self) -> None:
        path = self.paths.configuration
        try:
            params = self.cfg.items()
            df = pd.DataFrame(params.items(), columns=["Parameter", "Value"])
            os.makedirs(os.path.dirname(path), exist_ok=True)
            df.to_csv(path, index=False)
            self.logger.info(f"Configuration saved to {path}")
        except Exception as e:
            self.logger.error(f"Error saving configuration: {e}")

    def all_hardware(self) -> None:
        for dev_id, path in self.paths.hardware.items():
            device = self.cfg.hardware.devices.get(dev_id)
            if not device:
                continue
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                device.output_path = path
                if hasattr(device, "save_data"):
                    device.save_data(path)
                self.logger.info(f"Device {dev_id} data saved to {path}")
            except Exception as e:
                self.logger.error(f"Error saving device {dev_id}: {e}")

    def all_notes(self) -> None:
        if not self.cfg.notes:
            return
        path = self.paths.notes
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write("\n".join(self.cfg.notes))
            self.logger.info(f"Notes saved to {path}")
        except Exception as e:
            self.logger.error(f"Error saving notes: {e}")

    def save_timestamps(self, id, start_time, stop_time) -> None:
        path = self.paths.timestamps
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", newline="") as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(["device_id", "started", "stopped"])
                writer.writerow([id, start_time, stop_time])
                for dev_id, device in self.cfg.hardware.devices.items():
                    started = getattr(device, "_started", "")
                    stopped = getattr(device, "_stopped", "")
                    writer.writerow([dev_id, started, stopped])
            self.logger.info(f"Timestamps saved to {path}")
        except Exception as e:
            self.logger.error(f"Error saving timestamps: {e}")

    def writer_for(self, camera) -> Any:
        # choose writer based on camera.file_type
        file_type = getattr(camera, "file_type", None)
        if file_type == "ome.tiff":
            path = self.cfg.make_path(camera.name, "ome.tiff", "func")
            writer = CustomWriter(path)
            camera.output_path = writer._filename
            camera.metadata_path = writer._frame_metadata_filename
        elif file_type == "mp4":
            path = self.cfg.make_path(camera.name, "mp4", "func")
            # assume camera.fps exists or default to 30
            fps = getattr(camera, "fps", 30)
            writer = CV2Writer(path, fps=fps)
            camera.output_path = path
        else:
            raise ValueError(f"Unsupported camera file_type: {file_type}")

        self.paths.writers[camera.name] = path
        self.logger.info(f"Writer for {camera.name} set to {path}")
        return writer
    
    def save_queue(self, rows: list[list[Any]], path: str | None = None) -> None:
        """Save queued data rows to CSV file specified in DataPaths or override path."""
        if path is None:
            path = self.paths.queue
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", newline="") as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow([
                    "datetime",
                    "timestamp",
                    "device_ts",
                    "device_id",
                    "payload",
                ])
                writer.writerows(rows)
            self.logger.info(f"Queue log saved to {path}")
        except Exception as e:
            self.logger.error(f"Error saving queue log: {e}")


class DataManager:
    """Very small wrapper providing optional :class:`DataSaver`."""

    def __init__(self) -> None:
        self.save: DataSaver
        self.database: Optional[H5Database] = None
        self.queue = DataQueue()

        # backwards compatibility
        self.data_queue = self.queue
        self.saver = None

        self.devices: List[Any] = []
        
        self.queue_log_path: Optional[str] = None
        self.queue_packets: list[list[Any]] = []
        
        self._queue_thread: Optional[threading.Thread] = None
        self._stop_queue: bool = False

    # backwards compatibility for tests
    def set_config(self, config: ExperimentConfig) -> None:
        self.save = DataSaver(config)
        self.saver = self.save
        self.database = None


    @log_this_fr
    def setup(self, config: ExperimentConfig, path: str, devices: Iterable[Any]) -> None:
        """Attach configuration, database, and register devices."""
        self.save = DataSaver(config)
        self.saver = self.save
        self.database = H5Database(path)
        self.register_devices(devices)

    def register_devices(self, devices: Iterable[Any]) -> None:
        """Register a list of hardware devices with the manager."""
        for dev in devices:
            if hasattr(dev, "device_type") and hasattr(dev, "get_data"):
                self.register_hardware_device(dev)

    def append_to_database(self, df: pd.DataFrame, key: str = "data") -> None:
        """Append ``df`` to the database if configured."""
        if self.database:
            self.database.update(df, key)

    # ------------------------------------------------------------------
    def start_queue_logger(self, path: str | None = None) -> None:
        """Begin capturing :class:`DataQueue` contents."""
        # determine log path, default to DataPaths.queue
        if path is None and self.save:
            path = self.save.paths.queue
        if path is None:
            return

        self.queue_log_path = path
        # in-memory storage for log rows
        self.queue_packets = []
        self._stop_queue = False

        # start background thread to record queue packets
        self._queue_thread = threading.Thread(
            target=self._queue_writer_loop,
            daemon=True,
        )
        self._queue_thread.start()

    def stop_queue_logger(self) -> None:
        """Stop the queue logging thread and flush data to disk."""
        self._stop_queue = True
        if self._queue_thread:
            self._queue_thread.join(timeout=1)

        # save recorded packets via DataSaver
        if self.save and self.queue_log_path:
            # use the configured log path for writing
            self.save.save_queue(self.queue_packets, self.queue_log_path)

    def _queue_writer_loop(self) -> None:

        while not self._stop_queue or not self.queue.empty():
            try:
                pkt = self.queue.pop(timeout=0.1)
            except queue.Empty:
                continue

            now = datetime.now().isoformat()
            row = [now, pkt.timestamp, pkt.device_ts, pkt.device_id, pkt.payload]
            self.queue_packets.append(row)

            # if self._stream and self._writer:
            #     self._writer.writerow(row)
            #     assert self._file is not None
            #     self._file.flush()

    def register_hardware_device(self, device: Any) -> None:  # pragma: no cover - convenience
        """Track a hardware device and connect its data stream to the queue."""
        self.devices.append(device)

        # Try to connect various callback styles to push data to our queue
        def _push(payload: Any, device_ts: Any = None, *, dev=device) -> None:
            dev_id = getattr(dev, "device_id", getattr(dev, "id", "unknown"))
            #print(f"DataManager: Pushing data from {dev_id} to queue: {payload}")
            self.queue.push(dev_id, payload, device_ts=device_ts)

        # Connect using a standard data_event if present
        evt = getattr(device, "data_event", None)
        if evt is not None and hasattr(evt, "connect"):
            try:
                evt.connect(_push)
            except Exception:
                pass
            
        sig = getattr(device, "serialDataReceived", None)
        if sig is not None and hasattr(sig, "connect"):
            try:
                sig.connect(_push)
            except Exception:
                pass

        if sig is None and hasattr(device, "core"):
            # connect metadata-only from core.mda.events.frameReady
            sig = getattr(device.core.mda.events, "frameReady", None)
            if sig is not None and hasattr(sig, "connect"):
                try:
                    # frameReady callback signature: (image, metadata)
                    sig.connect(lambda _img, event, metadata: _push(metadata['camera_metadata']['TimeReceivedByCore']))
                except Exception:
                    pass
                
    #TODO: move this logic to DataSaver
    def get_device_outputs(self, subject: str, session: str) -> pd.DataFrame:
        """Return a DataFrame of output file paths for registered devices."""
        records = {}
        for dev in self.devices:
            dev_id = getattr(dev, "device_id", getattr(dev, "id", "unknown"))
            out = getattr(dev, "output_path", None)
            if out:
                key = (dev.device_type, dev_id, "file")
                records[key] = out

                # derive metadata path if attribute not set
                meta = getattr(dev, "metadata_path", None)
                if not meta:
                    if out.endswith("ome.tiff"):
                        meta = out.replace("ome.tiff", "ome.tiff_frame_metadata.json")
                    elif out.endswith("ome.tif"):
                        meta = out.replace("ome.tif", "ome.tif_frame_metadata.json")
                if meta and os.path.exists(meta):
                    key = (dev.device_type, dev_id, "metadata")
                    records[key] = meta
        if not records:
            return pd.DataFrame()
        idx = pd.MultiIndex.from_arrays([[subject], [session]], names=["Subject", "Session"])
        return pd.DataFrame(records, index=idx)

    # ------------------------------------------------------------------
    def update_database(self) -> None:
        """Gather session outputs and append them to the HDF5 database."""
        if not (self.database and self.save):
            return

        cfg = self.save.cfg
        subject, session = cfg.subject, cfg.session

        try:
            cam_df = sessiondb.camera_dataframe(cfg.hardware.cameras, subject, session)
            if not cam_df.empty:
                self.append_to_database(cam_df, key="camera_data")
        except Exception:  # pragma: no cover - optional
            cfg.logger.exception("Database update failed while storing camera data")

        try:
            encoder = cfg.hardware.get_encoder()
            enc_df = sessiondb.encoder_dataframe(encoder, subject, session)
            if not enc_df.empty:
                self.append_to_database(enc_df, key="encoder")
        except Exception:  # pragma: no cover - optional
            cfg.logger.exception("Database update failed while storing encoder data")

        try:
            dev_df = self.get_device_outputs(subject, session)
            if not dev_df.empty:
                self.append_to_database(dev_df, key="device_files")
        except Exception:  # pragma: no cover - optional
            cfg.logger.exception("Database update failed while storing device outputs")

        try:
            notes_df = sessiondb.notes_dataframe(cfg.notes, subject, session)
            if not notes_df.empty:
                self.append_to_database(notes_df, key="notes")
        except Exception:  # pragma: no cover - optional
            cfg.logger.exception("Database update failed while storing notes")

        try:
            ts_df = sessiondb.timestamps_dataframe(cfg.bids_dir, subject, session)
            if not ts_df.empty:
                self.append_to_database(ts_df, key="timestamps")
        except Exception:  # pragma: no cover - optional
            cfg.logger.exception("Database update failed while storing timestamps")

        try:
            if self.queue_log_path:
                q_df = sessiondb.queue_dataframe(self.queue_log_path, subject, session)
                if not q_df.empty:
                    self.append_to_database(q_df, key="queue_stream")
        except Exception:  # pragma: no cover - optional
            cfg.logger.exception("Database update failed while storing queue data")

        try:
            cfg_df = sessiondb.config_dataframe(cfg)
            if not cfg_df.empty:
                self.append_to_database(cfg_df, key="config")
        except Exception:  # pragma: no cover - optional
            cfg.logger.exception("Database update failed while storing config")
