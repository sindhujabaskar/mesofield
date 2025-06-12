from __future__ import annotations
"""
DataManager & DataSaver Workflow Overview
1. Initialization
    ├─ dm = DataManager()
    ├─ dm.set_config(config)      # attaches ExperimentConfig instance -> DataSaver(config)
    └─ dm.set_database(path)      # attaches H5Database(path) instance
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

from dataclasses import dataclass
from typing import Optional, List, Any

import os

import pandas as pd

from mesofield.config import ExperimentConfig
from mesofield.io.writer import CustomWriter
from mesofield.io.h5db import H5Database
from mesofield.io import sessiondb


@dataclass
class DataSaver:
    """Helper to persist experiment metadata and outputs."""

    config: ExperimentConfig

    def save_config(self) -> None:
        """Persist the configuration to disk."""
        self.config.save_configuration()

    def save_encoder_data(self, df: Any) -> None:
        """Write wheel encoder values as CSV."""
        if isinstance(df, list):
            df = pd.DataFrame(df)
        path = self.config.make_path("encoder-data", "csv", "beh")
        df.to_csv(path, index=False)
        enc = self.config.hardware.get_encoder() if hasattr(self.config.hardware, "get_encoder") else None
        if enc:
            enc.output_path = path

    def save_notes(self) -> None:
        """Persist user notes if present."""
        if not self.config.notes:
            return
        path = self.config.make_path("notes", "txt")
        with open(path, "w") as fh:
            fh.write("\n".join(self.config.notes))

    def writer_for(self, camera) -> CustomWriter:
        """Create an image writer for ``camera`` and store the output path."""
        writer = CustomWriter(self.config.make_path(camera.name, "ome.tiff", "func"))
        camera.output_path = writer._filename
        camera.metadata_path = writer._frame_metadata_filename
        return writer


class DataManager:
    """Very small wrapper providing optional :class:`DataSaver`."""

    def __init__(self) -> None:
        self.saver: Optional[DataSaver] = None
        self.database: Optional[H5Database] = None
        self.devices: List[Any] = []

    def set_config(self, config: ExperimentConfig) -> None:
        """Attach configuration so data can be saved."""
        self.saver = DataSaver(config)

    def set_database(self, path: str) -> None:
        """Attach an :class:`H5Database` for appending session data."""
        self.database = H5Database(path)

    def append_to_database(self, df: pd.DataFrame, key: str = "data") -> None:
        """Append ``df`` to the database if configured."""
        if self.database:
            self.database.update(df, key)

    def read_database(self, key: str = "data") -> Optional[pd.DataFrame]:
        """Return a DataFrame from the database if configured."""
        if self.database:
            return self.database.read(key)
        return None

    def register_hardware_device(self, device: Any) -> None:  # pragma: no cover - convenience
        """Track a hardware device (no streaming management)."""
        self.devices.append(device)

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
        if not (self.database and self.saver):
            return

        cfg = self.saver.config
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
            cfg_df = sessiondb.config_dataframe(cfg)
            if not cfg_df.empty:
                self.append_to_database(cfg_df, key="config")
        except Exception as e:  # pragma: no cover - optional
            cfg.logger.error(f"Database update failed while storing config: {e}")
