from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd  # type: ignore[import]
import logging
logging.getLogger("tables").setLevel(logging.ERROR)

import warnings
from pandas.io.pytables import PerformanceWarning
warnings.filterwarnings("ignore", category=PerformanceWarning)


class H5Database:
    """Simple helper for storing experiment data in an HDF5 file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def update(self, df: pd.DataFrame, key: str = "data") -> None:
        """Append or update ``df`` at ``key`` inside the HDF5 store."""
        with pd.HDFStore(self.path, mode="a") as store:
            if key in store:
                existing = store[key]
                combined = pd.concat([existing, df])
                combined = combined[~combined.index.duplicated(keep="last")]
            else:
                combined = df

            fmt = "table"
            if combined.index.nlevels > 1 or combined.columns.nlevels > 1:
                fmt = "fixed"

            store.put(key, combined, format=fmt)

    def read(self, key: str = "data") -> Optional[pd.DataFrame | pd.Series]:
        """Read a DataFrame or Series from the store if present."""
        if not self.path.exists():
            return None
        with pd.HDFStore(self.path, mode="r") as store:
            return store.get(key)

    def keys(self) -> list[str]:
        """
        Return all top-level keys in the HDF5 store (without leading '/').
        """
        if not self.path.exists():
            return []
        with pd.HDFStore(self.path, mode="r") as store:
            return [k.lstrip("/") for k in store.keys()]

    def to_dataframe(self) -> pd.DataFrame:
        """
        Read every key in the store into a single pandas DataFrame with a
        MultiIndex: outer level is the HDF5 key, inner level is the original index.
        """
        if not self.path.exists():
            return pd.DataFrame()

        with pd.HDFStore(self.path, mode="r") as store:
            frames: dict[str, pd.DataFrame] = {}
            for raw_key in store.keys():
                key = raw_key.lstrip("/")
                obj = store.get(raw_key)
                # if it's a Series, convert to DataFrame
                if isinstance(obj, pd.Series):
                    obj = obj.to_frame()
                frames[key] = obj

        # keys argument creates an outer index level with names
        return pd.concat(
            frames,
            names=["key", *([] if frames[next(iter(frames))].index.nlevels == 1 else ["lvl" + str(i) for i in range(frames[next(iter(frames))].index.nlevels)])]
        )
