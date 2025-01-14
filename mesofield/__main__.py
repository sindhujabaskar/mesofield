"""CLI Interface entry point for mesofield python package"""

import os
import argparse
from PyQt6.QtWidgets import QApplication
from mesofield.gui.maingui import MainWindow
from mesofield.config import ExperimentConfig
from mesofield.startup import HardwareManager

def launch(dev, params):
    """Launch the mesofield acquisition interface."""
    print('Launching mesofield acquisition interface...')
    app = QApplication([])
    config = ExperimentConfig(params, dev)
    config.hardware.configure_engines(config)
    print(config.hardware.cameras[0])
    mesofield = MainWindow(config)
    mesofield.show()
    app.exec()

def controller():
    """Launch the mesofield controller."""
    from mesofield.gui.widgets.controller import Controller
    app = QApplication([])
    c = Controller()
    c.show()
    app.exec()

def test_mda(frames):
    """Run a test of the mesofield Multi-Dimensional Acquisition (MDA)."""
    from mesofield.startup import test_mda

def run_mda_command():
    """Run the Multi-Dimensional Acquisition (MDA) without the GUI."""

def main():
    parser = argparse.ArgumentParser(description="mesofields Command Line Interface")
    subparsers = parser.add_subparsers(dest='command', help='Available subcommands')

    # Subcommand: launch
    parser_launch = subparsers.add_parser('launch', help='Launch the mesofield acquisition interface')
    parser_launch.add_argument('--dev', default=False, action='store_true',
                               help='Launch in development mode with simulated MMCores')
    parser_launch.add_argument('--params', default='hardware.yaml',
                               help='Path to the config file')

    # Subcommand: controller
    parser_controller = subparsers.add_parser('controller', help='Launch the mesofield controller')

    # Subcommand: test_mda
    parser_test_mda = subparsers.add_parser('test_mda', help='Run a test MDA')
    parser_test_mda.add_argument('--frames', type=int, default=100,
                                 help='Number of frames for the MDA test')

    # Subcommand: run_mda
    subparsers.add_parser('run_mda', help='Run MDA without the GUI')

    args = parser.parse_args()

    if args.command == 'launch':
        launch(args.dev, args.params)
    elif args.command == 'controller':
        controller()
    elif args.command == 'test_mda':
        test_mda(args.frames)
    elif args.command == 'run_mda':
        run_mda_command()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()