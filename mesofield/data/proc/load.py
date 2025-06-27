import os
import re
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, Tuple, Optional, Callable
from pathlib import Path
import pandas as pd

'''
https://bids-website.readthedocs.io/en/latest/getting_started/folders_and_files/folders.html

Experiment/
├──
processed/
├──
data/ 
└── subject
    └── session
        └── datatype
            └── data

Experiment/
├──
data/
└── sub-01
    └── ses-01
        └── anat
            └── sub-01_ses-01_meso.tiff
'''


# Pre-compiled regex patterns to extract subject and session from the file path
SUBJECT_REGEX = re.compile(r"sub-([A-Za-z0-9]+)")
SESSION_REGEX = re.compile(r"ses-([A-Za-z0-9]+)")

GLOB_PATTERNS: Dict[str, Tuple[str, ...]] = {
    "meso.ome.tiff": ("raw", "meso", "tiff"),
    "meso.ome.tiff_frame_metadata.json": ("raw", "meso", "metadata"),
    "pupil.ome.tiff": ("raw", "pupil", "tiff"),
    "pupil.ome.tiff_frame_metadata.json": ("raw", "pupil", "metadata"),
    "encoder-data.csv": ("raw", "encoder",),
    "*.psydat": ("raw", "psydat",),
    "configuration.csv": ("raw", "session_config",),
    "full.pickle": ("processed", "dlc_pupil"),
    "meso-mean-trace.csv": ("processed", "meso_trace"),
}


class ExperimentData:
    """
    Encapsulates experimental data stored in a MultiIndex pandas DataFrame,
    providing intuitive dot notation for further processing and export.
    
    Attributes:
    - data_dict (dict): Original nested dictionary with experimental file info.
    - data (pd.DataFrame): DataFrame with file paths, indexed by (Subject, Session)
                             and with MultiIndex columns (raw/processed, category).
    - progress (pd.DataFrame): DataFrame summarizing data presence (1 if file path exists,
                                 0 otherwise) with a similar MultiIndex column structure.
    """

    def __init__(self, dir) -> None:
        """
        Initialize the ExperimentData object.
        
        Args:
            data_dict (dict): Nested dictionary structured as:
                {subject: {session: {category: data, ...}, ...}, ...}
        """
        self.experiment_dir = dir
        self.dict = file_hierarchy(dir)
        self.data = self._create_df_from_file_hierarchy(self.dict)

    def _flatten_nested(self, d: Dict[Any, Any], parent: Tuple[Any, ...] = ()) -> Dict[Tuple[Any, ...], Any]:
        """
        Recursively flatten a nested dictionary into a dictionary with tuple keys.
        
        Args:
            d (dict): The dictionary to flatten.
            parent (tuple): Accumulated keys from higher levels.
        
        Returns:
            dict: A flat dictionary with tuple keys representing the hierarchy.
        """
        items = {}
        for k, v in d.items():
            new_key = parent + (k,)
            if isinstance(v, dict):
                items.update(self._flatten_nested(v, new_key))
            else:
                items[new_key] = v
        return items

    def _create_df_from_file_hierarchy(self, datadict: Dict[str, Dict[str, Any]]) -> pd.DataFrame:
        """
        Convert a nested file hierarchy dictionary into a DataFrame with:
        - Row MultiIndex: ("Subject", "Session")
        - Column MultiIndex: constructed from the flattened tuple keys derived from GLOB_PATTERNS.
        
        This function assumes that the inner dictionaries (for each subject/session)
        were built using the GLOB_PATTERNS tuples (e.g. ("raw", "meso", "tiff")).
        
        Args:
            datadict (dict): Nested dictionary organized as {subject: {session: nested_dict}}.
        
        Returns:
            pd.DataFrame: DataFrame with hierarchical row and column indices.
        """
        records = {}  # Keys: (subject, session); Values: flattened dict with tuple keys.
        all_keys = set()
        
        for subject, sessions in datadict.items():
            for session, inner_dict in sessions.items():
                flat = self._flatten_nested(inner_dict)
                records[(subject, session)] = flat
                all_keys.update(flat.keys())
        
        max_depth = max((len(k) for k in all_keys), default=0) # Determine the maximum depth among all flattened keys.
        
        df = pd.DataFrame.from_dict(records, orient="index") # Create the DataFrame from the records.
        
        df.columns = pd.MultiIndex.from_tuples(df.columns, 
                                                names=["Data_Type"] + [f"Level_{i}" for i in range(2, max_depth+1)])
        
        df.index = pd.MultiIndex.from_tuples(df.index, names=["Subject", "Session"]) # Set the row MultiIndex with names.
        
        return df    
    
    def load_camera_metadata(self, metadata_path: str) -> pd.DataFrame:
        """
        Load camera metadata from a JSON file and return a DataFrame.
        
        Args:
            metadata_path (str): Path to the JSON file containing camera metadata.
            
        Returns:
            pd.DataFrame: DataFrame with camera metadata.
        """
        return camera_metadata(metadata_path)
    
    @property
    def progress_summary(self) -> pd.DataFrame:
        """
        Return the progress summary DataFrame.
        
        Returns:
            pd.DataFrame: A DataFrame indicating file presence (1 if exists, 0 otherwise).
        """
        # Create the progress summary DataFrame.
        progress_df = self.data.notna().astype(int)
        progress_df.columns = pd.MultiIndex.from_tuples(
            [("progress",) + col for col in progress_df.columns]
        )
        return progress_df
    
    @property
    def subjects(self) -> pd.Index:
        """
        Return the unique subject identifiers.
        ```python
        self.data.index.get_level_values("Subject").unique()
        ```
        https://pandas.pydata.org/docs/user_guide/advanced.html#reconstructing-the-level-labels
        
        Returns:
            pd.Index: A pandas Index with unique subject identifiers.
        """
        return self.data.index.get_level_values("Subject").unique()
    
    def raw(self):
        """
        Returns a list of raw meso data tiff filepaths
        ```python
        self.data.loc[:, ("raw")]
        ```
        https://pandas.pydata.org/docs/user_guide/advanced.html#advanced-indexing-with-hierarchical-index
        """
        
        return self.data.loc[:, ("raw")]

    def processed(self):
        """
        Returns a list of processed meso data tiff filepaths
        ```python
        self.data.loc[:, ("processed")]
        ```
        https://pandas.pydata.org/docs/user_guide/advanced.html#advanced-indexing-with-hierarchical-index
        """
        return self.data.loc[:, ("processed")]
    
    @property
    def encoder_data(self):
        """
        ```python
        
        self.data[("raw", "encoder")]
        ```
        """
        return self.data[("raw", "encoder")]

    @property
    def meso_tiffs(self):
        """
        ```python
        
        self.data[("raw", "meso", "tiff")]
        ```
        """
        return self.data[("raw", "meso", "tiff")]

    @property
    def meso_metadata(self):
        """
        ```python
        
        self.data[("raw", "meso", "metadata")]
        ```
        """
        return self.data[("raw", "meso", "metadata")]

    @property
    def meso_means(self):
        """
        ```python
        
        self.data[("processed", "meso_trace")]
        ```
        """
        return self.data[("processed", "meso_trace")]

    @property
    def pupil_tiffs(self):
        """
        ```python
        
        self.data[("raw", "pupil", "tiff")]
        ```
        """
        return self.data[("raw", "pupil", "tiff")]

    @property
    def pupil_metadata(self):
        """
        ```python
        
        self.data[("raw", "pupil", "metadata")]
        ```
        """
        return self.data[("raw", "pupil", "metadata")]

    @property
    def dlc_pupil(self):
        """
        ```python
        
        self.data[("processed", "dlc_pupil")]
        ```
        """
        return self.data[("processed", "dlc_pupil")]
    
    def process_dlc_pupil(self, max_files: Optional[int] = None) -> pd.DataFrame:
        """
        Returns a MultiIndex DataFrame of DeepLabCut pupil data, loading files incrementally
        to manage memory usage.
        """
        paths = self.data.loc[:, ("processed", "dlc_pupil")]
        if max_files:
            paths = paths.iloc[:max_files]
        # Initialize with first file
        if len(paths) == 0:
            return pd.DataFrame()
            
        result = pd.DataFrame()
        
        # Process one file at a time
        for idx, filepath in paths.items():
            df = pickle_to_df(filepath)
            # Add MultiIndex using current path keys
            df_indexed = pd.DataFrame(df, index=pd.MultiIndex.from_tuples([idx]))
            result = pd.concat([result, df_indexed])
            # Force garbage collection after each file
            del df
            import gc
            gc.collect()
            
        return result

    def _pdseries_iterator(self, series: pd.Series, func: Callable) -> pd.Series:
        """
        Iterate over a pandas Series and apply a function to each element.
        
        Args:
            series (pd.Series): A pandas Series.
        
        Returns:
            pd.Series: A pandas Series with the function applied to each element.
        """
        return series.apply(func)



def set_nested_value(d: Dict[str, Any], keys: Tuple[str, ...], value: Any) -> None:
    """
    Recursively set a nested value in a dictionary using a tuple of keys.

    Args:
        d (dict): The dictionary in which to set the value.
        keys (tuple): A tuple of keys representing the nested path.
        value (Any): The value to set.
    """
    for key in keys[:-1]:
        d = d.setdefault(key, {})
    d[keys[-1]] = value


def file_hierarchy(root_dir: str) -> Dict[str, Dict[str, Any]]:
    """
    Build a file hierarchy using pathlib's match method with support for deeper hierarchies.
    Subject and session IDs are extracted from the entire file path string. Files that do not 
    contain both "sub-" and "ses-" are excluded.

    Args:
        root_dir (str): Root directory containing experiment data.

    Returns:
        dict: A nested dictionary organized by subject and session, then further nested 
              according to the destination tuple defined in GLOB_PATTERNS.
    """
    db: Dict[str, Dict[str, Any]] = defaultdict(lambda: defaultdict(dict))
    root = Path(root_dir)

    # Iterate recursively over all files
    for file_path in root.rglob("*"):
        if not file_path.is_file():
            continue

        path_str = str(file_path)

        # Extract subject and session IDs from the full file path string
        subject_match = SUBJECT_REGEX.search(path_str)
        session_match = SESSION_REGEX.search(path_str)
        if not (subject_match and session_match):
            continue  # Exclude files without both identifiers

        subject = subject_match.group(1)
        session = session_match.group(1)

        # Match file using glob patterns
        for glob_pattern, dest in GLOB_PATTERNS.items():
            if file_path.match(f"*{glob_pattern}"):
                set_nested_value(db[subject][session], dest, path_str)
                break  # Only process the first matching pattern

    return db
    


def pickle_to_df(pickle_path) -> pd.DataFrame:
    """
    Load a DeepLabCut output pickle file and return raw data in a pandas DataFrame.
    """ 
    df = pd.DataFrame(pd.read_pickle(pickle_path))
    return df

def pupil_means(pickle_path) -> pd.DataFrame:
    from mesofield.data.proc.transform import process_deeplabcut_pupil_data
    process_deeplabcut_pupil_data(pickle_to_df(pickle_path))
    

def camera_metadata(metadata_path) -> pd.DataFrame:
    import json
    
    # Load the JSON Data
    with open(metadata_path, 'r') as file:
        data = json.load(file)
    
    p0_data = data['p0'] #p0 is a list of the frames at Position 0 \
                            #(artifact of hardware sequencing in MMCore)
    df = pd.DataFrame(p0_data) # dataframe it

    # Expand 'camera_metadata' into separate columns
    camera_metadata_df = pd.json_normalize(df['camera_metadata'])
    df = df.join(camera_metadata_df)
    return df

def csv_to_df(csv_path) -> pd.DataFrame:
    """
    Load a CSV file and return a DataFrame.
    """
    dataframe = pd.read_csv(csv_path)
    return dataframe