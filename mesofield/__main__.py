import os
import logging

import click
from PyQt6.QtWidgets import QApplication
from mesofield.gui.maingui import MainWindow
from mesofield.config import ExperimentConfig

# Disable pymmcore-plus logger
package_logger = logging.getLogger('pymmcore-plus')
package_logger.setLevel(logging.CRITICAL)

# Disable debugger warning about the use of frozen modules
os.environ["PYDEVD_DISABLE_FILE_VALIDATION"] = "1"

# Disable ipykernel logger
logging.getLogger("ipykernel.inprocess.ipkernel").setLevel(logging.WARNING)

def launch_mesofield(params):
    """Launch the mesofield acquisition interface."""
    print('Launching mesofield acquisition interface...')
    app = QApplication([])
    config = ExperimentConfig(params)
    config.hardware._configure_engines(config)
    mesofield = MainWindow(config)
    mesofield.show()
    app.exec()

def controller():
    """Launch the mesofield controller."""
    import  mesofield.gui.controller
    app = QApplication([])
    c = Controller()
    c.show()
    app.exec()

def run_mda_command():
    """Run the Multi-Dimensional Acquisition (MDA) without the GUI."""

def test_psychopy():
    import tests.test_psychopy as test_psychopy
    import sys
    app = QApplication(sys.argv)
    gui = test_psychopy.PsychopyGui()
    gui.show()
    sys.exit(app.exec())

@click.group()
def cli():
    """mesofields Command Line Interface"""

@cli.command()
@click.option('--params', default='hardware.yaml', help='Path to the config file')
def launch(params):
    launch_mesofield(params)

@cli.command()
def controller_cmd():
    controller()

@cli.command()
def psychopy():
    test_psychopy()

@cli.command()
def run_mda():
    run_mda_command()

if __name__ == "__main__":
    cli()
