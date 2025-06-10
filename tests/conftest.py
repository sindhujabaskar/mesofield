import sys
import types
import pytest

# Provide dummy nidaqmx module for environments without the package
dummy_nidaqmx = types.ModuleType("nidaqmx")
dummy_nidaqmx.system = types.ModuleType("nidaqmx.system")
dummy_nidaqmx.constants = types.ModuleType("nidaqmx.constants")
dummy_nidaqmx.constants.Edge = None
sys.modules.setdefault("nidaqmx", dummy_nidaqmx)
sys.modules.setdefault("nidaqmx.system", dummy_nidaqmx.system)
sys.modules.setdefault("nidaqmx.constants", dummy_nidaqmx.constants)

# Provide dummy PyQt6 modules
dummy_pyqt = types.ModuleType("PyQt6")
dummy_widgets = types.ModuleType("PyQt6.QtWidgets")
dummy_core = types.ModuleType("PyQt6.QtCore")
dummy_core.pyqtSignal = lambda *a, **k: None
class _DummyThread:
    def start(self):
        pass
    def wait(self):
        pass
dummy_core.QThread = _DummyThread
dummy_widgets.QWidget = object
dummy_widgets.QApplication = object
dummy_widgets.QVBoxLayout = object
dummy_core.QObject = object
sys.modules.setdefault("PyQt6", dummy_pyqt)
sys.modules.setdefault("PyQt6.QtWidgets", dummy_widgets)
sys.modules.setdefault("PyQt6.QtCore", dummy_core)


# each test runs on cwd to its temp dir
@pytest.fixture(autouse=True)
def go_to_tmpdir(request):
    # Get the fixture dynamically by its name.
    tmpdir = request.getfixturevalue("tmpdir")
    # ensure local test created packages can be imported
    sys.path.insert(0, str(tmpdir))
    # Chdir only for the duration of the test.
    with tmpdir.as_cwd():
        yield
