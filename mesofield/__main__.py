import os
import logging

import click

# Disable pymmcore-plus logger
package_logger = logging.getLogger('pymmcore-plus')
package_logger.setLevel(logging.CRITICAL)

# Disable debugger warning about the use of frozen modules
os.environ["PYDEVD_DISABLE_FILE_VALIDATION"] = "1"

# Disable ipykernel logger
logging.getLogger("ipykernel.inprocess.ipkernel").setLevel(logging.WARNING)

def get_experimental_summary(experiment_dir):
    import mesofield.data.load as load
    datadict =  load.file_hierarchy(experiment_dir)
    load.experiment_progress_summary(datadict)

def get_file_hierarchy_object(experiment_dir):
    import mesofield.data.load as load
    return load.file_hierarchy(experiment_dir)


'''
================================== Command Line Interface ======================================
Commands:
    launch: Launch the mesofield acquisition interface
        --params: Path to the config file
        
    batch_pupil: Convert the pupil videos to mp4 format
        --dir: Directory containing the BIDS formatted /data hierarchy
        
    plot_session: Plot the session data
        --dir: Path to experimental directory containing BIDS formatted /data hierarchy
        --sub: Subject ID (the name of the subject folder)
        --ses: Session ID (two digit number indicating the session)
        --save: Save the plot to the processing directory in the Experiment folder
        
    trace_meso: Get the mean trace of the mesoscopic data
        --dir: Path to experimental directory containing BIDS formatted /data hierarchy
        --sub: Subject ID (the name of the subject folder)
        
'''
@click.group()
def cli():
    """mesofields Command Line Interface"""


@cli.command()
@click.option('--params', default='hardware.yaml', help='Path to the config file')
def launch(params):
    from PyQt6.QtWidgets import QApplication
    from mesofield.gui.maingui import MainWindow
    from mesofield.config import ExperimentConfig

    """Launch the mesofield acquisition interface."""
    print('Launching mesofield acquisition interface...')
    app = QApplication([])
    config = ExperimentConfig(params)
    config.hardware._configure_engines(config)
    mesofield = MainWindow(config)
    mesofield.show()
    app.exec()


@cli.command()
@click.option('--dir', help='Save the plot to the processing directory in the Experiment folder')
@click.option('--sub', help='Subject ID (the name of the subject folder)')
def trace_meso(dir, sub):
    import pandas as pd
    import mesofield.data.load as load
    import mesofield.data.batch as batch
    
    datadict =  load.file_hierarchy(experiment_dir)
    session_paths = []
    for key in sorted(datadict[subject_id].keys()):
        if key.isdigit():
            session_paths.append(datadict[subject_id][key]['meso']['tiff'])
    
    results = batch.mean_trace_from_tiff(session_paths)
    for path, trace in results.items():
        print(f"{path}: {trace[:10]}") 
        
    outdir = os.path.join(experiment_dir, "processed", subject_id)
    os.makedirs(outdir, exist_ok=True)

    for path, trace in results.items():
        df = pd.DataFrame({"Slice": range(len(trace)), "Mean": trace})
        base_name = os.path.splitext(os.path.basename(path))[0]
        filename = f"{base_name}_meso-mean-trace.csv"
        df.to_csv(os.path.join(outdir, filename), index=False)


@cli.command()
@click.option('--dir', help='Directory containing the BIDS formatted /data hierarchy')
def batch_pupil(dir):
    """Convert the pupil videos to mp4 format."""
    from mesofield.data.batch import tiff_to_mp4
        
    tiff_to_mp4(
        parent_directory=parent_dir,
        fps=30,
        output_format="mp4",
        use_color=False
    )


@cli.command()
def psychopy():
    import sys
    from PyQt6.QtWidgets import QApplication
    import tests.test_psychopy as test_psychopy
    
    app = QApplication(sys.argv)
    gui = test_psychopy.DillPsychopyGui()
    gui.show()
    sys.exit(app.exec())


@cli.command()
@click.option('--params', default='hardware.yaml', help='Path to the config file')
def get_fps(params):
    from tqdm import tqdm   
    import numpy as np
    import datetime
    from useq import MDAEvent, MDASequence
    from pymmcore_plus import CMMCorePlus

    from mesofield.config import ExperimentConfig

    config = ExperimentConfig(params)
    config.hardware._configure_engines(config)

    num_frames = 300
    mmc: CMMCorePlus = config.hardware.ThorCam.core

    sequence = MDASequence(time_plan={"interval": 0, "loops": num_frames})
    
    times = []

    # initialize progress bar and image‐size tracker
    pbar = tqdm(total=num_frames, desc="Acquiring frames")
    img_size = 0

    @mmc.mda.events.frameReady.connect
    def new_frame(img: np.ndarray, event: MDAEvent, metadata: dict):
        nonlocal img_size
        # capture frame time
        frame_time_str = metadata['camera_metadata']['TimeReceivedByCore']
        frame_time = datetime.datetime.fromisoformat(frame_time_str)
        times.append(frame_time)
        # determine size of one image in bytes
        if img_size == 0:
            img_size = img.nbytes
        # update progress bar
        pbar.update(1)

    @mmc.mda.events.sequenceStarted.connect
    def on_start(sequence: MDASequence, metadata: dict):
        print(f"Measuring framerate...")

    # run the sequence and wait (blocking) for it to finish
    mmc.run_mda(sequence, block=True)
    deltas = [(t2 - t1).total_seconds() for t1, t2 in zip(times[:-1], times[1:])]
    fps = 1 / np.mean(deltas)
    print(f"FPS: {fps}")
    pbar.close()
    # estimate TIFF stack file size (bytes)
    file_size_bytes = img_size * num_frames
    print(f"Estimated TIFF stack size: {file_size_bytes / (1024**2):.2f} MB")

@cli.command()
@click.option('--yaml_path', default='tests/dev.yaml', help='Path to the YAML config file')
@click.option('--json_path', default='tests/devsub.json', help='Path to the JSON config file')
def ipython(yaml_path, json_path):
    """Load iPython terminal with ExperimentConfig in a dev configuration."""
    from mesofield.config import ExperimentConfig
    from IPython import embed
        
    config = ExperimentConfig(yaml_path)
    config.load_parameters(json_path)
    embed(header='Mesofield ExperimentConfig Terminal. Type `config.` + TAB ', local={'config': config})

if __name__ == "__main__":
    cli()