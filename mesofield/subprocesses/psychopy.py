from PyQt6.QtCore import QProcess

def launch(config, parent=None):
    """Launches a PsychoPy experiment as a subprocess with the given ExperimentConfig parameters."""
    # Build the command arguments
    args = [
        "C:\\Program Files\\PsychoPy\\python.exe",
        f'{config.psychopy_path}',
        f'{config.protocol}',
        f'{config.subject}',
        f'{config.session}',
        f'{config.save_dir}',
        f'{config.num_trials}'
    ]
    
    # Create and start the QProcess
    psychopy_process = QProcess(parent)
    psychopy_process.finished.connect(parent._handle_process_finished)
    psychopy_process.start(args[0], args[1:])
    
    return psychopy_process