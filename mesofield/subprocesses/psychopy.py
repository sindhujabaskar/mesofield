import base64
import dill
from dataclasses import dataclass

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

def launch(config: 'ExperimentConfig', parent=None):
    """Launches a PsychoPy experiment as a subprocess with the given ExperimentConfig parameters."""

    params = PsychopyParameters(config.psychopy_parameters)
    serialized_config = dill.dumps(params, byref=True) #dill handles complex objects, pickle does not
    b64_serialized_config = base64.b64encode(serialized_config).decode('ascii') # Qprocesses require strings
    
    # Create and start the QProcess
    psychopy_process = QProcess(parent)
    psychopy_process.readyReadStandardOutput.connect(lambda: print(psychopy_process.readAllStandardOutput().data().decode()))
    psychopy_process.readyReadStandardError.connect(lambda: print(psychopy_process.readAllStandardError().data().decode()))
    psychopy_process.start(r"C:/Program Files/PsychoPy/python.exe", [r"D:\Experiment Types\Checkerboard Experiment\CheckerBar_vis_build-v0.8.py", b64_serialized_config])
    
    return psychopy_process