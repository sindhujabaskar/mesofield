import pytest
from unittest.mock import MagicMock, patch, mock_open
import json
import os
import pandas as pd
from mesofield.config import ExperimentConfig  # Replace with the actual import path
import useq


from pymmcore_plus import CMMCorePlus
from mesofield.mmcore import MMConfigurator
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
def mm_configurator():
    # Instantiate MMConfigurator
    mm_config = MMConfigurator(core_parameters, dev=False)
    return mm_config

def test_initialize(mm_configurator):
    with patch.object(CMMCorePlus, 'loadSystemConfiguration') as mock_load_config:
        mmcore1, mmcore2 = mm_configurator.initialize()
        assert mmcore1 is not None
        assert mmcore2 is not None
        assert isinstance(mmcore1, CMMCorePlus)
        assert isinstance(mmcore2, CMMCorePlus)
        assert mock_load_config.called

def test_register_engines(mm_configurator):
    mm_configurator.mmcore1 = MagicMock()
    mm_configurator.mmcore2 = MagicMock()
    mm_configurator.register_engines()
    assert isinstance(mm_configurator.meso_engine, MesoEngine)
    assert isinstance(mm_configurator.pupil_engine, PupilEngine)
    mm_configurator.mmcore1.register_mda_engine.assert_called_with(mm_configurator.meso_engine)
    mm_configurator.mmcore2.register_mda_engine.assert_called_with(mm_configurator.pupil_engine)

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
def test_experiment_config(mock_file, mock_json, mock_json_str):
    mock_file.return_value.read.return_value = mock_json_str

    # Load the config from the mocked JSON file
    config = ExperimentConfig(mm_configurator)
    config.load_parameters(json_file_path="config.json")

    # Test parameters
    assert config.protocol == mock_json["protocol"]
    assert config.subject == mock_json["subject"]
    assert config.session == mock_json["session"]
    assert config.task == mock_json["task"]
    assert config.num_meso_frames == mock_json["num_meso_frames"]
    assert config.num_pupil_frames == mock_json["num_pupil_frames"]
    assert config.save_dir == os.path.abspath(mock_json["save_dir"])

    # Test methods
    assert isinstance(config.meso_sequence, useq.MDASequence)
    assert isinstance(config.pupil_sequence, useq.MDASequence)