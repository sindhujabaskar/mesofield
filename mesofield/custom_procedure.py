from mesofield.protocols import Procedure

from mesofield.config import ExperimentConfig

class CustomProcedure(Procedure):
    """Custom procedure for mesofield experiments."""
    
    def __init__(self, experiment_id: str, experimentor: str, config: ExperimentConfig, hardware_yaml: str, data_dir: str):
        self.experiment_id = experiment_id
        self.experimentor = experimentor
        self.config = config
        self.hardware_yaml = hardware_yaml
        self.data_dir = data_dir

    def initialize_hardware(self) -> bool:
        """Setup the experiment procedure."""
        # Custom hardware initialization logic here
        return True

    def setup_configuration(self, json_config: str) -> None:
        """Set up the configuration for the experiment procedure."""
        # Custom configuration setup logic here
        pass

    def run(self) -> None:
        """Run the experiment procedure."""
        # Custom run logic here
        pass

    def save_data(self) -> None:
        """Save data from the experiment."""
        # Custom data saving logic here
        pass

    def cleanup(self) -> None:
        """Clean up after the experiment procedure."""
        # Custom cleanup logic here
        pass