import sys
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QLineEdit,
    QPushButton,
    QFormLayout
)
from PyQt6.QtCore import QProcess

""" This test_script is used to test a launching a prebuilt Psychopy experiment script 
as a subprocess which epxects parameters piped from a parent process. 

Below is the custom-code in a Psychopy experiment that accepts the sysargs:

# Run 'Before Experiment' code from get_input_arguments
#=============================== Custom Codeblock jgronemeyer =====================================#
#add system argument functionality
#Get command line arguments passed if present
#sysarg_protocol_id = 'prot'
sysarg_subject_id = 'sub'
sysarg_session_id = 'ses'
sysarg_save_dir = None
nTrials = 1 # changed data.TrialHandler2 object value nReps value to call this variable
if len(sys.argv) > 1:
    sysarg_subject_id = sys.argv[1]  # get the second argument from command line
    sysarg_session_id = sys.argv[2]  # get the third argument from command line
    sysarg_save_dir = sys.argv[3]  # get the fourth argument from command line
    nTrials = sys.argv[4] # get the fifth argument from the command line
    save_path = sys.argv[5] #used to assign the data_file_path or `filename` variable for saving
#==================================================================================================#
"""

def launch_experiment(python_path, experiment_path, subject, session, save_dir, num_trials, filename):
    
    args = [
        f'{python_path}',
        f'{experiment_path}',
        f'{subject}',
        f'{session}',
        f'{save_dir}',
        f'{num_trials}',
        f'{filename}'
    ]
    
    # Create and start the QProcess
    psychopy_process = QProcess()
    psychopy_process.start(args[0], args[1:])
    
    return psychopy_process

class PsychopyGui(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        self.setWindowTitle("PsychoPy Launcher")
        form_layout = QFormLayout()

        self.python_path_edit = QLineEdit(r"C:\\Program Files\\PsychoPy\\python.exe")
        self.experiment_path_edit = QLineEdit(r"D:\Experiment Types\Checkerboard Experiment\CheckerBar_vis_build-v0.8.py")
        self.subject_edit = QLineEdit("Subject1")
        self.session_edit = QLineEdit("Session1")
        self.save_dir_edit = QLineEdit(r"C:\\")
        self.trials_edit = QLineEdit("10")
        self.file_name_edit = QLineEdit(r"D:\Experiment Types\Checkerboard Experiment\data\filename_test2")

        form_layout.addRow("Python Path:", self.python_path_edit)
        form_layout.addRow("Experiment Path:", self.experiment_path_edit)
        form_layout.addRow("Subject:", self.subject_edit)
        form_layout.addRow("Session:", self.session_edit)
        form_layout.addRow("Save Dir:", self.save_dir_edit)
        form_layout.addRow("Num Trials:", self.trials_edit)
        form_layout.addRow("File Name:", self.file_name_edit)

        run_button = QPushButton("Run")
        run_button.clicked.connect(self.on_run_clicked)
        form_layout.addRow(run_button)

        self.setLayout(form_layout)

    def on_run_clicked(self):
        python_path = self.python_path_edit.text()
        experiment_path = self.experiment_path_edit.text()
        subject = self.subject_edit.text()
        session = self.session_edit.text()
        save_dir = self.save_dir_edit.text()
        num_trials = self.trials_edit.text()
        filename = self.file_name_edit.text()

        try:
            self.process = launch_experiment(
                python_path,
                experiment_path,
                subject,
                session,
                save_dir,
                num_trials,
                filename
            )
        except Exception as e:
            print(f"Error launching PsychoPy: {e}")

def main():
    app = QApplication(sys.argv)
    gui = PsychopyGui()
    gui.show()
    sys.exit(app.exec())
    
    # process = launch_experiment(
    #     python_path=r"C:\\Program Files\\PsychoPy\\python.exe",
    #     experiment_path=r"D:\Experiment Types\Checkerboard Experiment\CheckerBar_vis_build-v0.8.py",
    #     subject="Subject1",
    #     session="Session1",
    #     save_dir=r"C:\\",
    #     num_trials="1",
    #     filename=r"D:\Experiment Types\Checkerboard Experiment\data\filename_test2"
    #     )
    


if __name__ == "__main__":
    main()