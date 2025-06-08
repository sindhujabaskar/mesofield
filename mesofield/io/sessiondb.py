from __future__ import annotations

import json
import os
from typing import Any, List

import pandas as pd
import tifffile


def camera_dataframe(cameras: List[Any], subject: str, session: str, *, parse_metadata: bool = True) -> pd.DataFrame:
    """Return a DataFrame describing camera outputs."""
    records = {}
    for cam in cameras:
        cam_id = getattr(cam, "device_id", getattr(cam, "id", "unknown"))
        out_path = getattr(cam, "output_path", None)
        if out_path and os.path.exists(out_path):
            records[(cam.device_type, cam_id, "tiff")] = [tifffile.memmap(out_path)]
            if parse_metadata:
                meta_path = getattr(cam, "metadata_path", None)
                if not meta_path:
                    if out_path.endswith("ome.tiff"):
                        meta_path = out_path.replace("ome.tiff", "ome.tiff_frame_metadata.json")
                    elif out_path.endswith("ome.tif"):
                        meta_path = out_path.replace("ome.tif", "ome.tif_frame_metadata.json")
                if meta_path and os.path.exists(meta_path):
                    with open(meta_path) as fh:
                        records[(cam.device_type, cam_id, "metadata")] = [json.load(fh)]
    if not records:
        return pd.DataFrame()
    idx = pd.MultiIndex.from_arrays([[subject], [session]], names=["Subject", "Session"])
    return pd.DataFrame(records, index=idx)


def encoder_dataframe(encoder: Any, subject: str, session: str) -> pd.DataFrame:
    """Return a DataFrame for encoder outputs."""
    if not encoder or not getattr(encoder, "output_path", None):
        return pd.DataFrame()
    if not os.path.exists(encoder.output_path):
        return pd.DataFrame()
    enc_df = pd.read_csv(encoder.output_path)
    if enc_df.empty:
        return pd.DataFrame()
    idx = pd.MultiIndex.from_arrays(
        [[subject] * len(enc_df), [session] * len(enc_df)],
        names=["Subject", "Session"],
    )
    enc_df.index = idx
    return enc_df


def notes_dataframe(notes: List[str], subject: str, session: str) -> pd.DataFrame:
    """Return a DataFrame of experiment notes."""
    if not notes:
        return pd.DataFrame()
    notes_df = pd.DataFrame({"note": notes})
    idx = pd.MultiIndex.from_arrays(
        [[subject] * len(notes_df), [session] * len(notes_df)],
        names=["Subject", "Session"],
    )
    notes_df.index = idx
    return notes_df


def timestamps_dataframe(bids_dir: str, subject: str, session: str) -> pd.DataFrame:
    """Return a DataFrame of timestamp metadata if present."""
    ts_path = os.path.join(bids_dir, "timestamps.csv")
    if not os.path.exists(ts_path):
        return pd.DataFrame()
    ts_df = pd.read_csv(ts_path)
    idx = pd.MultiIndex.from_arrays(
        [[subject] * len(ts_df), [session] * len(ts_df)],
        names=["Subject", "Session"],
    )
    ts_df.index = idx
    return ts_df


def config_dataframe(cfg) -> pd.DataFrame:
    """Return a DataFrame of configuration parameters."""
    cfg_df = cfg.dataframe
    cfg_df = cfg_df.set_index("Parameter")
    idx = pd.MultiIndex.from_product(
        [[cfg.subject], [cfg.session], cfg_df.index],
        names=["Subject", "Session", "Parameter"],
    )
    cfg_df.index = idx
    return cfg_df
