import math
import numpy as np
import statistics as st

import pandas as pd
import matplotlib.pyplot as plt

def euclidean_distance(coord1, coord2):
    """Calculate the Euclidean distance between two points."""
    return math.dist(coord1, coord2)


def confidence_filter_coordinates(frames_coords, frames_conf, threshold):
    """
    Apply a boolean label to coordinates based on whether 
    their confidence exceeds `threshold`.
    
    Parameters
    ----------
    frames_coords : list
        List of numpy arrays containing pupil coordinates for each frame.
    frames_conf : list
        List of numpy arrays containing confidence values corresponding 
        to the coordinates in `frames_coords`.
    threshold : float
        Confidence cutoff.

    Returns
    -------
    list
        A list of [coords, conf, labels] for each frame, where 'labels' 
        is a list of booleans (True if above threshold, else False).
    """
    thresholded = []
    for coords, conf in zip(frames_coords[1:], frames_conf[1:]):
        frame_coords, frame_conf, frame_labels = [], [], []
        # Each frame has 8 sets of pupil points 
        for i in range(8):
            point = coords[0, i, 0, :]
            cval = conf[i, 0, 0]
            label = (cval >= threshold)
            frame_coords.append(point)
            frame_conf.append(cval)
            frame_labels.append(label)
        thresholded.append([frame_coords, frame_conf, frame_labels])
    return thresholded


def apply_filters(df, speed_col='Speed', clamp_negative=False, threshold=None,
                  smoothing='rolling_median', window_size=10, alpha=0.5):
    """
    Applies optional filtering/smoothing to a speed column in a DataFrame.
    
    Parameters
    ----------
    df : pd.DataFrame
        The DataFrame containing speed data.
    speed_col : str
        Name of the column with raw speed values.
    clamp_negative : bool
        If True, speeds < 0 are set to 0.
    threshold : float or None
        A value below which absolute speeds are set to 0. If None, no threshold filter is applied.
    smoothing : str
        The type of smoothing to apply. Options: 'rolling_mean', 'rolling_median', 'ewm', or None for no smoothing.
    window_size : int
        Window size for rolling operations.
    alpha : float
        Smoothing factor for exponential smoothing, between 0 and 1.
        
    Returns
    -------
    pd.DataFrame
        The DataFrame with additional 'Speed_filtered' column.
    """
    df['Speed_filtered'] = df[speed_col]

    # 1. Clamp negative speeds
    if clamp_negative:
        df['Speed_filtered'] = df['Speed_filtered'].clip(lower=0)

    # 2. Threshold near-zero speeds
    if threshold is not None:
        df.loc[df['Speed_filtered'].abs() < threshold, 'Speed_filtered'] = 0

    # 3. Apply smoothing
    if smoothing == 'rolling_mean':
        df['Speed_filtered'] = df['Speed_filtered'].rolling(window=window_size, center=True).mean()
    elif smoothing == 'rolling_median':
        df['Speed_filtered'] = df['Speed_filtered'].rolling(window=window_size, center=True).median()
    elif smoothing == 'ewm':
        df['Speed_filtered'] = df['Speed_filtered'].ewm(alpha=alpha).mean()

    # Fill any NaNs from rolling or ewm at start/end
    df['Speed_filtered'].bfill()
    df['Speed_filtered'].ffill()
    
    return df


def process_deeplabcut_pupil_data(
    pickle_data: pd.DataFrame,
    show_plot: bool = False,
    confidence_threshold: float = 0.1,
    pixel_to_mm: float = 53.6
) -> pd.DataFrame:
    """
    Load a DeepLabCut output pickle file and compute the pupil diameter per frame.
    
    Parameters
    ----------
    pickle_path : str
        Path to the DLC output pickle file (e.g., '*full.pickle').
    show_plot : bool, optional
        If True, displays a matplotlib plot of pupil diameter (in mm) across frames.
        Defaults to False.
    confidence_threshold : float, optional
        Minimum confidence required to include two landmarks in the diameter calculation.
        Defaults to 0.1.
    pixel_to_mm : float, optional
        Conversion factor from pixels to millimeters. Defaults to 53.6.
    
    Returns
    -------
    pd.DataFrame
        A DataFrame with one column ('pupil_diameter_mm') indexed by frame number.
        Frames for which no valid diameter could be calculated will have NaN values.
    """
    
    # 1) Load the raw dataframe from the pickle
    raw_df = pickle_data

    # 2) Convert each column's 'coordinates' & 'confidence' to arrays
    frame_coordinates_array = []
    frame_confidence_array = []
    for frame_column in raw_df.columns:
        coords_list = raw_df.at['coordinates', frame_column]
        conf_list = raw_df.at['confidence', frame_column]
        frame_coordinates_array.append(np.array(coords_list))
        frame_confidence_array.append(np.array(conf_list))
    
    # 3) Filter coordinates by confidence
    labeled_frames = confidence_filter_coordinates(
        frame_coordinates_array,
        frame_confidence_array,
        confidence_threshold
    )
    
    # 4) Calculate mean pupil diameter (in pixels) per frame
    pupil_diameters = []
    for frame_data in labeled_frames:
        coords, conf, labels = frame_data
        frame_diameters = []
        
        # Pairs: (0,1), (2,3), (4,5), (6,7)
        for i in range(0, 7, 2):
            if labels[i] and labels[i+1]:
                diameter_pix = euclidean_distance(coords[i], coords[i+1])
                frame_diameters.append(diameter_pix)
        
        # If multiple diameters exist, use the average
        if len(frame_diameters) > 1:
            pupil_diameters.append(st.mean(frame_diameters))
        else:
            pupil_diameters.append(np.nan)
    
    # 5) Convert diameters to Series and interpolate missing values
    diam_series = pd.Series(pupil_diameters).interpolate()
    
    # 6) Convert from pixels to mm
    diam_series = diam_series / pixel_to_mm
    
    # 7) Optionally plot the results
    if show_plot:
        plt.figure(dpi=300)
        plt.plot(diam_series, color='blue')
        plt.xlabel('Frame')
        plt.ylabel('Pupil Diameter (mm)')
        plt.title('Pupil Diameter Over Frames')
        plt.show()
    
    # 8) Return a DataFrame with the final diameters
    result_df = pd.DataFrame({'pupil_diameter_mm': diam_series})
    return result_df
