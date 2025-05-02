import pytest
from unittest.mock import MagicMock, patch, mock_open
import json
import os
import pandas as pd
from mesofield.config import ExperimentConfig  # Replace with the actual import path
import useq


from pymmcore_plus import CMMCorePlus
from mesofield.config import ExperimentConfig
from mesofield.engines import MesoEngine, PupilEngine


# PARAMETERS = {
#     'mmc1_path': 'C:/Program Files/Micro-Manager-2.0gamma',
#     'mmc2_path': 'C:/Program Files/Micro-Manager-thor',
#     'mmc1_configuration_path': 'C:/Program Files/Micro-Manager-2.0/mm-sipefield.cfg',
#     'mmc2_configuration_path': 'C:/Program Files/Micro-Manager-2.0/ThorCam.cfg',
#     'memory_buffer_size': 10000,
#     'dhyana_fps': 49,
#     'thorcam_fps': 30,
#     'encoder': {
#         'type': 'dev',
#         'port': 'COM4',
#         'baudrate': '57600',
#         'CPR': '2400',
#         'diameter_cm': '0.1',
#         'sample_interval_ms': '20'
#     }
#     }

@pytest.fixture
def core_parameters():
    return {
        "mmc1_path": "/path/to/mm1",
        "mmc2_path": "/path/to/mm2",
        "mmc1_configuration_path": "/path/to/mmc1_config",
        "mmc2_configuration_path": "/path/to/mmc2_config",
        'dhyana_fps': 49,
        'thorcam_fps': 30,
    }

@pytest.fixture
def core_object():
    return MagicMock(spec=CMMCorePlus)

@pytest.fixture
def config(tmp_path, monkeypatch):
    # Monkey-patch HardwareManager to avoid external dependencies
    monkeypatch.setattr('mesofield.config.HardwareManager', lambda path: type('HM', (), {'devices': {}, 'cameras': []})())
    # Instantiate ExperimentConfig with dummy path
    cfg = ExperimentConfig(str(tmp_path))
    return cfg

@pytest.fixture
def mock_json():
    return {
        "protocol": "TestProtocol",
        "subject": "001",
        "session": "01",
        "task": "TestTask",
        "num_meso_frames": 10,
        "num_pupil_frames": 5,
        "save_dir": "./test_data"
    }

@pytest.fixture
def mock_json_str(mock_json):
    return json.dumps(mock_json)

@patch("builtins.open", new_callable=mock_open)
def test_experiment_config(mock_file, config, mock_json, mock_json_str):
    mock_file.return_value.read.return_value = mock_json_str
    # Load the config from the mocked JSON file
    config.load_json("config.json")

    # All loaded JSON parameters should be in the registry
    assert config._parameters == mock_json
    # Generated sequences use useq
    assert isinstance(config.meso_sequence, useq.MDASequence)
    assert isinstance(config.pupil_sequence, useq.MDASequence)