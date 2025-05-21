import os
import winreg
import base64
from dataclasses import dataclass

import dill
from PyQt6.QtCore import QProcess

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from mesofield.config import ExperimentConfig

class PsychopyParameters:
    def __init__(self, params: dict):
        for key, value in params.items():
            setattr(self, key, value)

    def __repr__(self):
        return f"<PsychopyParameters {self.__dict__}>"
    
def get_psychopy_python_exe():
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\PsychoPy", 0, winreg.KEY_READ)
        install_path, _ = winreg.QueryValueEx(key, "InstallPath")
        winreg.CloseKey(key)
        python_exe = os.path.join(install_path, "python.exe")
        if os.path.exists(python_exe):
            return python_exe
    except OSError:
        pass
    return "C:\Program Files\PsychoPy\python.exe"

def launch(config: 'ExperimentConfig', parent=None):
    """Launches a PsychoPy experiment as a subprocess with the given ExperimentConfig parameters."""

    params = PsychopyParameters(config.psychopy_parameters)
    serialized_config = dill.dumps(params, byref=True) #dill handles complex objects, pickle does not
    b64_serialized_config = base64.b64encode(serialized_config).decode('ascii') # Qprocesses require strings
    psychopy_exe = get_psychopy_python_exe()
    psychopy_script_path = os.path.join(config._save_dir, config.psychopy_filename)
    # Create and start the QProcess
    psychopy_process = QProcess(parent)
    psychopy_process.readyReadStandardOutput.connect(lambda: print(psychopy_process.readAllStandardOutput().data().decode()))
    psychopy_process.readyReadStandardError.connect(lambda: print(psychopy_process.readAllStandardError().data().decode()))
    psychopy_process.start(psychopy_exe, [psychopy_script_path, b64_serialized_config])
    
    return psychopy_process