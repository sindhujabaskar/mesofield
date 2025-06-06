from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List, Any

import pandas as pd

from mesofield.config import ExperimentConfig
from mesofield.io.writer import CustomWriter


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

    def save_notes(self) -> None:
        """Persist user notes if present."""
        if not self.config.notes:
            return
        path = self.config.make_path("notes", "txt")
        with open(path, "w") as fh:
            fh.write("\n".join(self.config.notes))

    def writer_for(self, camera) -> CustomWriter:
        """Create an image writer for ``camera``."""
        return CustomWriter(self.config.make_path(camera.name, "ome.tiff", "func"))


@dataclass
class DataSaver:
    """Helper class for saving experiment data using an ExperimentConfig."""

    config: ExperimentConfig

    def save_config(self) -> None:
        """Save configuration parameters using ExperimentConfig."""
        self.config.save_configuration()

    def save_encoder_data(self, df) -> None:
        """Save wheel encoder dataframe to disk."""
        if isinstance(df, list):
            df = pd.DataFrame(df)
        path = self.config.make_path("encoder-data", "csv", "beh")
        df.to_csv(path, index=False)

    def save_notes(self) -> None:
        """Write experiment notes to file."""
        if not self.config.notes:
            return
        path = self.config.make_path("notes", "txt")
        with open(path, "w") as f:
            f.write("\n".join(self.config.notes))

    def writer_for(self, camera) -> CustomWriter:
        """Return a :class:`CustomWriter` for the given camera."""
        return CustomWriter(self.config.make_path(camera.name, "ome.tiff", "func"))


class DataManager:
    """Very small wrapper providing optional :class:`DataSaver`."""

    def __init__(self) -> None:
        self.saver: Optional[DataSaver] = None
        self.devices: List[Any] = []

    def set_config(self, config: ExperimentConfig) -> None:
        """Attach configuration so data can be saved."""
        self.saver = DataSaver(config)

    def register_hardware_device(self, device: Any) -> None:  # pragma: no cover - convenience
        """Track a hardware device (no streaming management)."""
        self.devices.append(device)
