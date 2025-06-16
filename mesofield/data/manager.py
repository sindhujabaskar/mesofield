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
from mesofield.data.writer import CustomWriter
from mesofield.io.h5db import H5Database
from mesofield.io import sessiondb
from mesofield.utils._logger import get_logger, log_this_fr


@dataclass
class DataPacket:
    """Entry in :class:`DataQueue`."""

    device_id: str
    timestamp: float
    payload: Any
    device_ts: float | None = None
    meta: Dict[str, Any] = field(default_factory=dict)


class DataQueue:
    """Thread-safe queue for data streaming between devices and consumers."""

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
class DataSaver:
    """Helper to persist experiment metadata and outputs."""

    cfg: ExperimentConfig
    logger: Logger = field(default_factory=lambda: get_logger("DataSaver"))

    def configuration(self, suffix: str = "configuration") -> None:
        """Save the ExperimentConfig registry to a CSV file."""
        
        self.params_path = self.cfg.make_path(suffix="configuration", extension="csv")
        try:
            # Get all parameters from the registry
            registry_items = self.cfg.items()
            params_df = pd.DataFrame(list(registry_items.items()), columns=['Parameter', 'Value'])
            params_df.to_csv(self.params_path, index=False)
            self.logger.info(f"Configuration saved to {self.params_path}")
        except Exception as e:
            self.logger.error(f"Error saving configuration: {e}")

    def hardware(self) -> None:
        """Call `save_data()` method for all hardware devices registered to the HardwareManager."""
        #TODO: fetch all output and metadata path attributes from devices and store them in a dict attr of DataSaver
        #self.device_output_paths = {}
        for device in self.cfg.hardware.devices.values():
            try:
                device.save_data()
            except Exception as e:
                self.logger.error(f"Error saving device {device} state: {e}")

    def notes(self) -> None:
        """Persist user notes if present."""
        if not self.cfg.notes:
            return
        self.notes_path = self.cfg.make_path("notes", "txt")
        try:
            with open(self.notes_path, 'w') as f:
                f.write('\n'.join(self.cfg.notes))
                self.logger.info(f"Notes saved to {self.notes_path}")
        except Exception as e:
            self.logger.error(f"Error saving notes: {e}")

    #TODO: move this logic to the MMCamera class itself
    def writer_for(self, camera) -> CustomWriter:
        """Create an image writer for ``camera`` and store the output path."""
        writer = CustomWriter(self.cfg.make_path(camera.name, "ome.tiff", "func"))
        camera.output_path = writer._filename
        camera.metadata_path = writer._frame_metadata_filename
        return writer


class DataManager:
    """Very small wrapper providing optional :class:`DataSaver`."""

    def __init__(self) -> None:
        self.save: DataSaver
        self.database: Optional[H5Database] = None
        self.queue = DataQueue()
        
        self.devices: List[Any] = []
        
        self.queue_log_path: Optional[str] = None
        self.queue_packets: list[list[Any]] = []
        
        self._queue_thread: Optional[threading.Thread] = None
        self._stop_queue: bool = False
        self._stream: bool = False
        self._writer: Optional[csv.writer] = None
        self._file: Optional[Any] = None

    @log_this_fr
    def setup(self, config: ExperimentConfig, path: str, devices: Iterable[Any]) -> None:
        """Attach configuration, database, and register devices."""
        self.save = DataSaver(config)
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
    def start_queue_logger(self, path: str | None = None, *, stream: bool = True) -> None:
        """Begin capturing :class:`DataQueue` contents."""
        if path is None and self.save:
            path = self.save.cfg.make_path("dataqueue", "csv", "beh")
        if path is None:
            return

        self.queue_log_path = path
        self.queue_packets = []
        self._stream = stream
        self._stop_queue = False

        if self._stream:
            self._file = open(path, "w", newline="")
            self._writer = csv.writer(self._file)
            self._writer.writerow([
                "datetime",
                "timestamp",
                "device_ts",
                "device_id",
                "payload",
            ])
        else:
            self._file = None
            self._writer = None

        self._queue_thread = threading.Thread(target=self._queue_writer_loop, daemon=True)
        self._queue_thread.start()

    def stop_queue_logger(self) -> None:
        """Stop the queue logging thread and flush data to disk."""
        self._stop_queue = True
        if self._queue_thread:
            self._queue_thread.join(timeout=1)

        if not self._stream and self.queue_log_path:
            with open(self.queue_log_path, "w", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow([
                    "datetime",
                    "timestamp",
                    "device_ts",
                    "device_id",
                    "payload",
                ])
                writer.writerows(self.queue_packets)

        if self._file:
            try:
                self._file.close()
            except Exception:
                pass
        self._file = None
        self._writer = None

    def _queue_writer_loop(self) -> None:

        while not self._stop_queue or not self.queue.empty():
            try:
                pkt = self.queue.pop(timeout=0.1)
            except queue.Empty:
                continue

            now = datetime.now().isoformat()
            row = [now, pkt.timestamp, pkt.device_ts, pkt.device_id, pkt.payload]
            self.queue_packets.append(row)

            if self._stream and self._writer:
                self._writer.writerow(row)
                assert self._file is not None
                self._file.flush()

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
        except Exception as e:  # pragma: no cover - optional
            cfg.logger.error(f"Database update failed while storing camera data: {e}")

        try:
            encoder = cfg.hardware.get_encoder()
            enc_df = sessiondb.encoder_dataframe(encoder, subject, session)
            if not enc_df.empty:
                self.append_to_database(enc_df, key="encoder")
        except Exception as e:  # pragma: no cover - optional
            cfg.logger.error(f"Database update failed while storing encoder data: {e}")

        try:
            dev_df = self.get_device_outputs(subject, session)
            if not dev_df.empty:
                self.append_to_database(dev_df, key="device_files")
        except Exception as e:  # pragma: no cover - optional
            cfg.logger.error(f"Database update failed while storing device outputs: {e}")

        try:
            notes_df = sessiondb.notes_dataframe(cfg.notes, subject, session)
            if not notes_df.empty:
                self.append_to_database(notes_df, key="notes")
        except Exception as e:  # pragma: no cover - optional
            cfg.logger.error(f"Database update failed while storing notes: {e}")

        try:
            ts_df = sessiondb.timestamps_dataframe(cfg.bids_dir, subject, session)
            if not ts_df.empty:
                self.append_to_database(ts_df, key="timestamps")
        except Exception as e:  # pragma: no cover - optional
            cfg.logger.error(f"Database update failed while storing timestamps: {e}")

        try:
            if self.queue_log_path:
                q_df = sessiondb.queue_dataframe(self.queue_log_path, subject, session)
                if not q_df.empty:
                    self.append_to_database(q_df, key="queue_stream")
        except Exception as e:  # pragma: no cover - optional
            cfg.logger.error(f"Database update failed while storing queue data: {e}")

        try:
            cfg_df = sessiondb.config_dataframe(cfg)
            if not cfg_df.empty:
                self.append_to_database(cfg_df, key="config")
        except Exception as e:  # pragma: no cover - optional
            cfg.logger.error(f"Database update failed while storing config: {e}")
