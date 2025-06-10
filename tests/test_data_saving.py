import os
import pandas as pd
from pathlib import Path
import json

import pytest

from mesofield.config import ExperimentConfig
from mesofield.base import Procedure, ProcedureConfig
from mesofield.io.manager import DataManager

@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.setattr('mesofield.config.HardwareManager', lambda path: type('HM', (), {'devices': {}, 'cameras': []})())
    cfg = ExperimentConfig('dummy')
    cfg.save_dir = str(tmp_path)
    return cfg

@pytest.fixture
def procedure(config):
    pcfg = ProcedureConfig(data_dir=config.save_dir)
    proc = Procedure(pcfg)
    proc._config = config
    proc.data_manager = DataManager()
    proc.data_manager.set_config(config)
    return proc


def test_data_saver_files(tmp_path, config):
    dm = DataManager()
    dm.set_config(config)
    config.notes.append('note1')
    df = pd.DataFrame({'a':[1]})
    dm.saver.save_encoder_data(df)
    dm.saver.save_config()
    dm.saver.save_notes()

    bids = Path(config.bids_dir)
    assert list(bids.glob('*configuration.csv'))
    assert list(bids.glob('*notes.txt'))
    assert list((bids/'beh').glob('*encoder-data.csv'))


def test_procedure_save_data(procedure):
    procedure._config.notes.append('proc note')
    procedure.start_time = procedure.stopped_time = 0
    procedure.save_data()
    bids = Path(procedure._config.bids_dir)
    assert list(bids.glob('*configuration.csv'))
    assert list(bids.glob('*notes.txt'))
    assert (bids/'timestamps.csv').exists()
