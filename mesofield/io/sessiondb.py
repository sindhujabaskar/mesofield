from __future__ import annotations

import json
import os
from typing import Any, List

import pandas as pd
import tifffile


def camera_dataframe_tiffs(cameras: List[Any], subject: str, session: str, *, parse_metadata: bool = True) -> pd.DataFrame:
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


def camera_dataframe(
    cameras: List[Any],
    subject: str,
    session: str,
    *,
    include_metadata: bool = True
) -> pd.DataFrame:
    """
    Return a DataFrame of camera file-paths (TIFF and optional metadata).
    Index is a MultiIndex: (Subject, Session), with columns tiff_path and meta_path.
    """
    rows: list[dict[str, str | None]] = []
    for cam in cameras:
        tiff_path = getattr(cam, "output_path", None)
        meta_path = getattr(cam, "metadata_path", None)
        if include_metadata and not meta_path and tiff_path:
            if tiff_path.endswith(".ome.tiff"):
                meta_path = tiff_path.replace(".ome.tiff", ".ome.tiff_frame_metadata.json")
            elif tiff_path.endswith(".ome.tif"):
                meta_path = tiff_path.replace(".ome.tif", ".ome.tif_frame_metadata.json")
        rows.append({"tiff_path": tiff_path, "meta_path": meta_path})

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df.index = pd.MultiIndex.from_arrays(
        [[subject] * len(df), [session] * len(df)],
        names=["Subject", "Session"]
    )
    return df


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


def queue_dataframe(queue_path: Any, subject: str, session: str) -> pd.DataFrame:
    """Return a DataFrame of queued data if the CSV exists."""
    if not queue_path or not os.path.exists(queue_path):
        return pd.DataFrame()

    df = pd.read_csv(queue_path)
    if df.empty:
        return pd.DataFrame()

    idx = pd.MultiIndex.from_arrays(
        [[subject] * len(df), [session] * len(df)],
        names=["Subject", "Session"],
    )
    df.index = idx
    return df
