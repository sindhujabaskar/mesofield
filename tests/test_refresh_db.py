import pandas as pd
from pathlib import Path
from mesofield.io.h5db import H5Database


def test_refresh_database(tmp_path):
    root = tmp_path / "exp"
    (root / "sub-SUBJ1" / "ses-01").mkdir(parents=True, exist_ok=True)
    tiff = root / "sub-SUBJ1" / "ses-01" / "mesoscope.ome.tiff"
    tiff.write_text("data")
    enc = root / "sub-SUBJ1" / "ses-01" / "treadmill.csv"
    enc.write_text("x\n1")
    db_path = tmp_path / "db.h5"

    db = H5Database(db_path)
    df = db.refresh(str(root))

    assert isinstance(df, pd.DataFrame)
    stored = db.read("datapaths")
    assert stored is not None
    assert stored.equals(df)
    assert stored.index.nlevels == 3
    assert stored.index.names == ["Subject", "Session", "Task"]
    assert "SUBJ1" in stored.index.get_level_values("Subject")
    assert not isinstance(stored.columns, pd.MultiIndex)
    assert "meso_tiff" in stored.columns
