# Mesofield

This is a PyQt application that is designed to interface with scientific hardware through serial connections and [MicroManager](https://micro-manager.org/)

The core of the application is the `ExperimentConfig` class (`mesofield.config.ExperimentConfig`) and the corresponding `ConfigController` widget (`mesofield.gui.widgets.ConfigController`)

`ExperimentConfig` loads hardware configurations via the `mesofield.config.HardwareManager` dataclass which loads a `hardware.yaml` file in the module directory

All hardware and GUI components inherit the `ExperimentConfig` providing global state access to parameters defining filename, directories, and experimental settings.

The `ConfigController` loads additional parameters to the `ExperimentConfig` instance by passing a JSON file path to the `ExperimentConfig.load_parameters()` method.

NOTE: This has only been tested on Windows 10/11. Hardware control features rely on pymmcore-plus and an installation of MicroManager with specific device drivers. 

The GUI components include live views for cameras (with optional pyqtgraph ImageView), encoder velocity pyqtgraphics, buttons for hardware control, and an iPython terminal for access to the backend

# Setting Up Mesofield in Visual Studio Code

Below is a brief tutorial on how to set up a Python environment in VS Code, install mesofield, and run the [mesofield] CLI.

## 1. Clone and Open in VS Code

1. Clone this repository (or download it) to your local machine.
2. Open the folder in Visual Studio Code.

## 2. Create a Virtual Environment

*You can use a conda environment or a venv*

Open VS Code’s integrated terminal and create a virtual environment:

```
python -m venv .venv
```

Activate it:

- On Windows:

```
.venv\Scripts\activate
```

## 3. Install Dependencies

Install the required dependencies using [requirements.txt]:

```
pip install -r requirements.txt
```

Optionally, you can install directly from [setup.py]:

```
pip install .
```

Notable dependencies include: [pymmcore-plus](https://pymmcore-plus.github.io/pymmcore-plus/), [pymmcore-widgets](https://pymmcore-plus.github.io/pymmcore-widgets/) (for the MDAWidget), [useq](https://pymmcore-plus.github.io/useq-schema/), [PyQt](https://doc.qt.io/qtforpython-6/), [pyqtgraph](https://pyqtgraph.readthedocs.io/en/latest/), [pyserial](https://pyserial.readthedocs.io/en/latest/), pandas, numpy, matplotlib, and OpenCV (if using Arducam or other OpenCV compatible camera)

## 4. Launch Mesofield

Run the mesofield module in development mode from [mesofield.__main__]:

```
python -m mesofield launch --dev True
```

That’s it! This will open the main Mesofield GUI and set it up with simulated hardware for development.

# Using the Console in Mesofield

The IPython terminal can be launched with the `Toggle Console` button in the top-left menu bar. 

The console gives you access to the backend of the application. Type >>locals() into the terminal to see the accesible namespace using dot-notation

`self` provides access to the MainWindow and its attributes
`config` provides you access to the ExperimentConfig
`mda` provides access to the MDAWidget

The `config` command is the most useful outside of development. Type `config.hardware` to see the loaded hardware, for example.
Type `config.` + `tab` to see the available methods and parameters. Test them out, nothing should break in development mode. 
