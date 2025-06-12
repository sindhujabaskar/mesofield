import pytest
pytest.skip("Skipping GUI dependent tests", allow_module_level=True)
from mesofield.config import ExperimentConfig
from mesofield.gui.maingui import MainWindow

@pytest.fixture
def experiment_config(tmp_path, monkeypatch):
    # Patch HardwareManager to avoid real hardware
    monkeypatch.setattr('mesofield.config.HardwareManager', lambda path: type('HM', (), {'devices': {}, 'cameras': []})())
    return ExperimentConfig(str(tmp_path))

@pytest.fixture
def main_window(experiment_config):
    # Initialize MainWindow with only the ExperimentConfig
    return MainWindow(experiment_config)

def test_initialization(main_window):
    assert main_window.windowTitle() == "Mesofield"
    assert main_window.acquisition_gui is not None
    assert main_window.config_controller is not None
    assert main_window.encoder_widget is not None

# Test console toggle functionality
def test_toggle_console(monkeypatch, main_window):
    # Initially, console_widget created by initialize_console in constructor
    assert hasattr(main_window, 'console_widget')
    # Toggle hides and shows console
    main_window.console_widget.show = lambda: setattr(main_window, '_shown', True)
    main_window.console_widget.hide = lambda: setattr(main_window, '_shown', False)
    # First toggle should hide
    main_window.toggle_console()
    assert getattr(main_window, '_shown') is False
    # Second toggle should show
    main_window.toggle_console()
    assert getattr(main_window, '_shown') is True