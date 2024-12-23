import pytest
from pathlib import Path
from unittest.mock import MagicMock
from pymmcore_plus import CMMCorePlus
from mesofield.config import ExperimentConfig
from mesofield.widgets import MainWidget
import datetime

# mesofield/test_widgets.py


@pytest.fixture
def core_object():
    return CMMCorePlus()

@pytest.fixture
def experiment_config():
    return ExperimentConfig()

@pytest.fixture
def main_widget(core_object, experiment_config):
    return MainWidget(core_object, core_object, experiment_config)

def test_initialization(main_widget):
    assert main_widget.dhyana_gui is not None
    assert main_widget.thor_gui is not None
    assert main_widget.config is not None

def test_dhyana_mda_start(main_widget):
    main_widget._dhyana_mda_start()
    assert main_widget._meso_counter is not None
    assert main_widget._dhyana_metadata == {}

def test_thor_mda_start(main_widget):
    main_widget._thor_mda_start()
    assert main_widget._pupil_counter is not None
    assert main_widget._thor_metadata == {}

def test_dhyana_save_frame_metadata(main_widget):
    frame_metadata = {"key": "value"}
    main_widget._dhyana_save_frame_metadata(None, None, frame_metadata)
    assert main_widget._dhyana_metadata[0] == frame_metadata

def test_thor_save_frame_metadata(main_widget):
    frame_metadata = {"key": "value"}
    main_widget._thor_save_frame_metadata(None, None, frame_metadata)
    assert main_widget._thor_metadata[0] == frame_metadata

def test_save_meso_metadata(main_widget, tmp_path):
    main_widget._dhyana_metadata = {0: {"key": "value"}, 1: {"mda_event": "value"}}
    main_widget.save_meso_metadata()
    save_dir = Path('C:/dev/mesofield/tests')
    assert (save_dir / f'{datetime.datetime.now().strftime("%Y%m%d-%H%M%S")}_dhyana_frame_metadata.json').exists()

def test_save_pupil_metadata(main_widget, tmp_path):
    main_widget._thor_metadata = {0: {"key": "value"}, 1: {"mda_event": "value"}}
    main_widget.save_pupil_metadata()
    save_dir = Path('C:/dev/mesofield/tests')
    assert (save_dir / f'{datetime.datetime.now().strftime("%Y%m%d-%H%M%S")}_thor_frame_metadata.json').exists()

def test_toggle_console(main_widget):
    main_widget.init_console()
    main_widget.toggle_console()
    assert main_widget.console_widget.isVisible() == True
    main_widget.toggle_console()
    assert main_widget.console_widget.isVisible() == False
    
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
import pandas as pd
import numpy as np
from mesofield.widgets import MainWidget, MDA, load_arduino_led, stop_led
from mesofield.config import ExperimentConfig
from pymmcore_plus import CMMCorePlus
from useq import MDAEvent

#mesofield/test_widgets.py


# @pytest.fixture
# def core_object():
#     return MagicMock(spec=CMMCorePlus)

# @pytest.fixture
# def experiment_config():
#     return MagicMock(spec=ExperimentConfig)

@pytest.fixture
def main_widget(core_object, experiment_config):
    return MainWidget(core_object, core_object, experiment_config)

def test_initialization(main_widget):
    assert main_widget.windowTitle() == "Main Widget with Two MDA Widgets"
    assert main_widget.dhyana_gui is not None
    assert main_widget.thor_gui is not None
    assert main_widget.config is not None

def test_dhyana_mda_start(main_widget):
    main_widget._dhyana_mda_start()
    assert main_widget._meso_counter is not None
    assert main_widget._dhyana_metadata == {}

def test_thor_mda_start(main_widget):
    main_widget._thor_mda_start()
    assert main_widget._pupil_counter is not None
    assert main_widget._thor_metadata == {}

def test_dhyana_save_frame_metadata(main_widget):
    image = np.zeros((10, 10))
    event = MagicMock(spec=MDAEvent)
    frame_metadata = {"key": "value"}
    main_widget._dhyana_save_frame_metadata(image, event, frame_metadata)
    assert main_widget._dhyana_metadata[0] == frame_metadata

def test_thor_save_frame_metadata(main_widget):
    image = np.zeros((10, 10))
    event = MagicMock(spec=MDAEvent)
    frame_metadata = {"key": "value"}
    main_widget._thor_save_frame_metadata(image, event, frame_metadata)
    assert main_widget._thor_metadata[0] == frame_metadata

# @patch("pandas.DataFrame.to_json")
# def test_save_meso_metadata(mock_to_json, main_widget):
#     main_widget._dhyana_metadata = {0: {"key": "value"}}
#     main_widget.save_meso_metadata()
#     mock_to_json.assert_called_once()

# @patch("pandas.DataFrame.to_json")
# def test_save_pupil_metadata(mock_to_json, main_widget):
#     main_widget._thor_metadata = {0: {"key": "value"}}
#     main_widget.save_pupil_metadata()
#     mock_to_json.assert_called_once()

def test_toggle_console(main_widget):
    main_widget.console_widget = MagicMock()
    main_widget.console_widget.isVisible.return_value = True
    main_widget.toggle_console()
    main_widget.console_widget.hide.assert_called_once()

    main_widget.console_widget.isVisible.return_value = False
    main_widget.toggle_console()
    main_widget.console_widget.show.assert_called_once()