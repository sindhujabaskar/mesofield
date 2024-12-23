"""Entry point for mesofield."""

import os
# os.environ['NUMEXPR_MAX_THREADS'] = '4'
# os.environ['NUMEXPR_NUM_THREADS'] = '2'
# import numexpr as ne 

import click
from PyQt6.QtWidgets import QApplication
from mesofield.gui.maingui import MainWindow
from mesofield.config import ExperimentConfig
from mesofield.startup import Startup
'''
This is the client terminal command line interface

The client terminal commands are:

    launch: Launch the mesofield acquisition interface
        - dev: Set to True to launch in development mode with simulated MMCores
    test_mda: Test the mesofield acquisition interface

'''


@click.group()
def cli():
    """mesofields Command Line Interface"""
    pass

@cli.command()
@click.option('--dev', default=False, help='launch in development mode with simulated MMCores.')
@click.option('--params', default='params.json', help='Path to the config JSON file.')
def launch(dev, params):
    """ Launch mesofield acquisition interface.
    
    This function initializes and launches the mesofield acquisition application. 
    
    It sets up the necessary hardware and configuration based on
    the provided parameters.
    
    Parameters:
    `dev (str)`: The device identifier to be used for the acquisition.
    `params (str)`: The path to the configuration file. Default is the params.json file in the current directory.
    
    """
    
    print('Launching mesofield acquisition interface...')
    app = QApplication([])
    config_path = params
    config = ExperimentConfig(config_path, dev)
    config.hardware.initialize_cores(config)
    mesofield = MainWindow(config)
    mesofield.show()
    app.exec_()

@cli.command()
def controller():
    """Launch the mesofield controller."""
    from mesofield.controller import Controller
    app = QApplication([])
    controller = Controller()
    controller.show()
    app.exec_()

@cli.command()
@click.option('--frames', default=100, help='Number of frames for the MDA test.')
def test_mda(frames):
    """
    Run a test of the mesofield Multi-Dimensional Acquisition (MDA) 
    """
    from mesofield.startup import test_mda

@cli.command()
def run_mda():
    """Run the Multi-Dimensional Acquisition (MDA) without the GUI."""
    run_mda()


if __name__ == "__main__":  # pragma: no cover
    cli()




