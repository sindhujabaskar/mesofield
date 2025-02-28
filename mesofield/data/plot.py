import json
import os

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt


def plot_session(
    session_name, 
    df_fluorescence, 
    df_encoder,
    df_pupil, 
    fluorescence_x='Slice', 
    fluorescence_y='Mean',
    speed_col='Speed_filtered',
    locomotion_threshold=0.001,
    downsample=10,
    x_limit=None
):
    """
    Plots a single session as a two-panel figure:
    1) Fluorescence trace with underlaid locomotion bouts
    2) Speed trace
    3) pupil diameter trace
    
    Parameters
    ----------
    session_name : str
        Name/title for the session (e.g. 'Session 1').
    df_fluorescence : pd.DataFrame
        DataFrame containing columns for 'Slice' (x-axis) and 'Mean' (fluorescence).
    df_encoder : pd.DataFrame
        DataFrame containing the speed information, including 'Speed_filtered'.
    fluorescence_x : str
        Column name for x-axis (frame slices).
    fluorescence_y : str
        Column name for fluorescence intensities.
    speed_col : str
        Column name in df_encoder representing the speed to plot (e.g. 'Speed_filtered').
    locomotion_threshold : float
        Threshold for marking locomotion as active.
    downsample : int
        How much to downsample speed data for plotting (plot every Nth point).
    x_limit : tuple or None
        (min, max) for x-axis range, or None to let Matplotlib set automatically.
    """
    # Identify bouts of locomotion based on threshold
    locomotion_mask = df_encoder[speed_col] > locomotion_threshold

    # Create figure
    fig, axs = plt.subplots(3, 1, figsize=(12, 8), sharex=False)
    fig.suptitle(session_name)
    
    # Calculate x-axis time range based on number of frames in meso_df captured at 50 fps (20 ms exposure)
    meso_x_range = int(len(df_fluorescence[fluorescence_x]) / 50)
    # Calculate pupil x-axis time range based on number of frames in pupil_df captured at 30 fps 
    pupil_x_range = len(df_pupil) - (meso_x_range - int(len(df_pupil)/30)) * 30
    pupil_time_axis = np.arange(0, len(df_pupil['pupil_diameter_mm'])/30, 1/30)
    # Create an array for x ticks at 20-second intervals
    meso_time_axis = np.arange(0, len(df_fluorescence[fluorescence_x])/50, 1/50)
    
    # Create x-ticks at 20-second intervals; note that the x-axis is in seconds now.
    total_seconds = meso_time_axis[-1]
    x_ticks = list(range(0, int(total_seconds) + 20, 60))
    
    axs[0].set_xticks(x_ticks)
    axs[2].set_xticks(x_ticks)

    
    # -- Top subplot: Fluorescence + shaded locomotion
    axs[0].plot(
        meso_time_axis, 
        df_fluorescence[fluorescence_y], 
        linestyle='-', 
        label='Mean Fluorescence'
    )
    axs[0].set_ylabel('Mean Fluorescence')
    axs[0].set_title(f'Fluorescence (with Locomotion Underlay) - {session_name}')
    axs[0].set_xlim(0,len(df_fluorescence[fluorescence_x]))
    axs[0].grid(True)
    axs[0].legend()
    axs[0].set_xlim(meso_time_axis[1], meso_time_axis[-1])
    #fig.align_xlabels(axs[:1])

    # Underlay locomotion on top subplot
    axs[0].fill_between(
        df_encoder.index, 
        axs[0].get_ylim()[0], 
        axs[0].get_ylim()[1],
        where=locomotion_mask,
        color='gray',
        alpha=0.2,
        label='Locomotion'
    )

    # -- Second subplot: Speed
    axs[1].plot(df_encoder.iloc[::downsample].index, 
                df_encoder.iloc[::downsample][speed_col],
                linestyle='-',
                label='Speed (Filtered)')
    axs[1].set_xlabel('Time (s)')
    axs[1].set_ylabel('Speed (m/s)')
    axs[1].set_title(f'Speed - {session_name}')
    axs[1].grid(True)
    axs[1].legend()

    # Optionally set x-limit if provided
    if x_limit is not None:
        axs[1].set_xlim(x_limit)

    # -- Third subplot: Pupil Diameter
    axs[2].plot(pupil_time_axis, 
                df_pupil['pupil_diameter_mm'], 
                label='Pupil Diameter (mm)', 
                color='green')
    axs[2].set_xlabel('Time (s)')
    axs[2].set_ylabel('Pupil Diameter (mm)')
    axs[2].set_title(f'Pupil Diameter - {session_name}')
    axs[2].grid(True)
    #axs[2].set_xlim = (pupil_time_axis[1], pupil_time_axis[-1])
    axs[2].legend()
    

    plt.tight_layout()
    return plt

def load_frame_metadata(path):
    # Load the JSON Data
    with open(path, 'r') as file:
        data = json.load(file)

    # Extract Data and Create DataFrame
    p0_data = data['p0']  # p0 is a list of the frames at Position 0 (artifact of hardware sequencing in MMCore)
    df = pd.DataFrame(p0_data)  # dataframe it

    # Expand 'camera_metadata' into separate columns
    camera_metadata_df = pd.json_normalize(df['camera_metadata'])
    df = df.join(camera_metadata_df)

    return df

def load_metadata(directory):
    frame_metadata_df = None
    pupil_frame_metadata_df = None

    # Parse the directory for files ending with '_frame_metadata.json' and 'pupil_frame_metadata.json'
    for file in os.listdir(directory):
        if file.endswith('meso_frame_metadata.jsonf'): #need an 'f' after json???????????????????
            frame_metadata_path = os.path.join(directory, file)
            frame_metadata_df = load_frame_metadata(frame_metadata_path)
        elif file.endswith('pupil_frame_metadata.jsonf'):
            pupil_frame_metadata_path = os.path.join(directory, file)
            pupil_frame_metadata_df = load_frame_metadata(pupil_frame_metadata_path)

    return frame_metadata_df, pupil_frame_metadata_df

def plot_camera_intervals(frame_metadata_df, pupil_frame_metadata_df, threshold=1):
    
    def process_dataframe(df):
        df['TimeReceivedByCore'] = pd.to_datetime(df['TimeReceivedByCore'], format='%Y-%m-%d %H:%M:%S.%f')  # Convert to datetime
        df['runner_time_ms'] = df['runner_time_ms'].astype(float)  # Convert to float

        # Compute Time Intervals Between Frames
        df = df.sort_values('TimeReceivedByCore').reset_index(drop=True)
        df['runner_interval'] = df['runner_time_ms'].diff()  # Compute differential
        df['time_received_ms'] = df['TimeReceivedByCore'].astype(np.int64) / 1e6  # Convert to milliseconds
        df['core_interval'] = df['time_received_ms'].diff()  # Compute differential

        # Compute Differences Between Intervals
        df['interval_difference'] = df['runner_interval'] - df['core_interval']
        
        # Identify divergence points
        df['divergence'] = (df['interval_difference'].abs() > threshold)
        
        # Compute cumulative times
        df['cumulative_runner_time'] = df['runner_interval'].cumsum()
        df['cumulative_core_time'] = df['core_interval'].cumsum()
        
        return df
    
    plt.figure(figsize=(12, 20))
    
    if frame_metadata_df is not None:
        df1 = process_dataframe(frame_metadata_df)
    
    if pupil_frame_metadata_df is not None:
        df2 = process_dataframe(pupil_frame_metadata_df)
    
    # ----------- Camera 1: Runner Time Intervals and Core Time Interval Plot 1
    plt.subplot(6, 1, 1)
    plt.plot(df1.index, df1['runner_interval'], label='Runner Time Intervals', marker='o')
    plt.plot(df1.index, df1['core_interval'], label='Core Time Intervals', marker='x')
    plt.xlabel('Frame Index')
    plt.ylabel('Interval (ms)')
    plt.title('Camera 1: Intervals Between Frames')
    plt.legend()
    plt.grid(True)

    # Highlighting divergence points
    for idx in df1[df1['divergence']].index:
        plt.axvline(x=idx, color='red', linestyle='--', alpha=0.5)

    # ----------- Camera 1: Difference Between Intervals Plot 2
    plt.subplot(6, 1, 2)
    plt.plot(df1.index, df1['interval_difference'], label='Interval Difference (Runner - Core)', marker='d')
    plt.xlabel('Frame Index')
    plt.ylabel('Interval Difference (ms)')
    plt.title('Camera 1: Difference Between Runner and Core Intervals')
    plt.axhline(y=threshold, color='red', linestyle='--', alpha=0.5, label='Threshold')
    plt.axhline(y=-threshold, color='red', linestyle='--', alpha=0.5)
    plt.legend()
    plt.grid(True)

    # Highlight divergence points
    for idx in df1[df1['divergence']].index:
        plt.axvline(x=idx, color='red', linestyle='--', alpha=0.5)

    # ----------- Camera 1: Cumulative Time Comparison Plot 3
    plt.subplot(6, 1, 3)
    df1['cumulative_runner_time'] = df1['runner_interval'].cumsum()
    df1['cumulative_core_time'] = df1['core_interval'].cumsum()
    plt.plot(df1.index, df1['cumulative_runner_time'], label='Cumulative Runner Time', marker='o')
    plt.plot(df1.index, df1['cumulative_core_time'], label='Cumulative Core Time', marker='x')
    plt.xlabel('Frame Index')
    plt.ylabel('Cumulative Time (ms)')
    plt.title('Camera 1: Cumulative Time Comparison')
    plt.legend()
    plt.grid(True)

    # ----------- Camera 2: Runner Time Intervals and Core Time Interval Plot 4
    plt.subplot(6, 1, 4)
    plt.plot(df2.index, df2['runner_interval'], label='Runner Time Intervals', marker='o')
    plt.plot(df2.index, df2['core_interval'], label='Core Time Intervals', marker='x')
    plt.xlabel('Frame Index')
    plt.ylabel('Interval (ms)')
    plt.title('Camera 2: Intervals Between Frames')
    plt.legend()
    plt.grid(True)

    # Highlighting divergence points
    for idx in df2[df2['divergence']].index:
        plt.axvline(x=idx, color='red', linestyle='--', alpha=0.5)

    # ----------- Camera 2: Difference Between Intervals Plot 5
    plt.subplot(6, 1, 5)
    plt.plot(df2.index, df2['interval_difference'], label='Interval Difference (Runner - Core)', marker='d')
    plt.xlabel('Frame Index')
    plt.ylabel('Interval Difference (ms)')
    plt.title('Camera 2: Difference Between Runner and Core Intervals')
    plt.axhline(y=threshold, color='red', linestyle='--', alpha=0.5, label='Threshold')
    plt.axhline(y=-threshold, color='red', linestyle='--', alpha=0.5)
    plt.legend()
    plt.grid(True)

    # Highlight divergence points
    for idx in df2[df2['divergence']].index:
        plt.axvline(x=idx, color='red', linestyle='--', alpha=0.5)

    # ----------- Camera 2: Cumulative Time Comparison Plot 6
    plt.subplot(6, 1, 6)
    df2['cumulative_runner_time'] = df2['runner_interval'].cumsum()
    df2['cumulative_core_time'] = df2['core_interval'].cumsum()
    plt.plot(df2.index, df2['cumulative_runner_time'], label='Cumulative Runner Time', marker='o')
    plt.plot(df2.index, df2['cumulative_core_time'], label='Cumulative Core Time', marker='x')
    plt.xlabel('Frame Index')
    plt.ylabel('Cumulative Time (ms)')
    plt.title('Camera 2: Cumulative Time Comparison')
    plt.legend()
    plt.grid(True)

    plt.tight_layout()
    plt.show()

def load_wheel_data(directory) -> pd.DataFrame:

    # Parse the beh_path directory for a file ending with 'wheel_df.csv'
    path = os.path.join(os.path.dirname(directory), 'beh')
    for file in os.listdir(path):
        if file.endswith('wheeldf.csv'):
            file_path = os.path.join(path, file)
            break
    df = pd.read_csv(file_path)
    # Create a pandas dataframe
    return df
    
def plot_wheel_data2(wheel_df: pd.DataFrame):
    # Calculate the time difference in seconds
    total_seconds = wheel_df['timestamp'].array[-1] - wheel_df['timestamp'][0]  # Get Range
    time = np.arange(0, total_seconds, 1)  # create array [0,1,...12] with the total_seconds

    # Create separate plots for each variable
    plt.figure(figsize=(10, 6))#, dpi=300)

    # Plot 'speed' over time
    plt.subplot(3, 1, 1)
    plt.plot(wheel_df['timestamp'], wheel_df['speed'])
    plt.title('Speed')
    plt.xlabel('Time (secs)')
    plt.ylabel('Speed')

    # Plot 'distance' over time
    plt.subplot(3, 1, 2)
    plt.plot(wheel_df['timestamp'], wheel_df['distance'])
    plt.title('Distance')
    plt.xlabel('Time (secs)')
    plt.ylabel('Distance')

    # Plot 'direction' over time
    plt.subplot(3, 1, 3)
    plt.plot(wheel_df['timestamp'], wheel_df['direction'])
    plt.title('Direction')
    plt.xlabel('Time (secs)')
    plt.ylabel('Direction')

    # Adjust the layout
    plt.tight_layout()

    # Show the plots
    plt.show()

    # # Reverse (flip) backwards data due to wrong encoder direction
    # wheel_df['speed'] = wheel_df['speed'] * -1
    # wheel_df['distance'] = wheel_df['distance'] * -1

    # return wheel_df

def load_psychopy_data(directory):
    # Parse the beh_path directory for a file ending with 'wheel_df.csv'
    path = os.path.join(os.path.dirname(directory), 'beh')
    for file in os.listdir(path):
        if file.endswith('.csv'):
            file_path = os.path.join(path, file)
            break
        
    # Load the CSV file into a pandas DataFrame
    df = pd.read_csv(file_path)

    # Display the first few rows of the DataFrame
    print(df.head())

    # List the columns from the DataFrame
    print(df.columns)
    
    return df

def plot_stim_times(df):
    import matplotlib.pyplot as plt

    # Create a scatter plot for 'thisRow.t'
    plt.figure(figsize=(10, 6))
    plt.scatter(df['thisRow.t'], [0] * len(df['thisRow.t']), label='thisRow.t', color='blue')

    # Add vertical lines for 'stim_grayScreen.started'
    for start_time in df['stim_grayScreen.started']:
        plt.axvline(x=start_time, color='red', linestyle='--', label='stim_grayScreen.started')

    # Add vertical lines for 'stim_grating.started'
    for start_time in df['stim_grating.started']:
        plt.axvline(x=start_time, color='green', linestyle='--', label='stim_grating.started')

    plt.title('Visual stim presentation timepoints')
    plt.xlabel('Time')
    plt.legend()
    plt.grid(True)
    plt.show()

def plot_wheel_data(wheel_df: pd.DataFrame, stim_df: pd.DataFrame):
    # Calculate the time difference in seconds
    total_seconds = wheel_df['timestamp'].array[-1] - wheel_df['timestamp'][0]  # Get Range
    time = np.arange(0, total_seconds, 1)  # create array [0,1,...12] with the total_seconds

    # Create separate plots for each variable
    plt.figure(figsize=(10, 6))#, dpi=300)

    # Plot 'speed' over time
    plt.subplot(3, 1, 1)
    plt.plot(wheel_df['timestamp'], wheel_df['speed'])
    plt.title('Speed')
    plt.xlabel('Time (secs)')
    plt.ylabel('Speed')
    for start_time in stim_df['stim_grayScreen.started']:
        plt.axvline(x=start_time, color='red', linestyle='--', label='stim_grayScreen.started')
    for start_time in stim_df['stim_grating.started']:
        plt.axvline(x=start_time, color='green', linestyle='--', label='stim_grating.started')

    # Plot 'distance' over time
    plt.subplot(3, 1, 2)
    plt.plot(wheel_df['timestamp'], wheel_df['distance'])
    plt.title('Distance')
    plt.xlabel('Time (secs)')
    plt.ylabel('Distance')
    for start_time in stim_df['stim_grayScreen.started']:
        plt.axvline(x=start_time, color='red', linestyle='--', label='stim_grayScreen.started')
    for start_time in stim_df['stim_grating.started']:
        plt.axvline(x=start_time, color='green', linestyle='--', label='stim_grating.started')

    # Plot 'direction' over time
    plt.subplot(3, 1, 3)
    plt.plot(wheel_df['timestamp'], wheel_df['direction'])
    plt.title('Direction')
    plt.xlabel('Time (secs)')
    plt.ylabel('Direction')
    for start_time in stim_df['stim_grayScreen.started']:
        plt.axvline(x=start_time, color='red', linestyle='--', label='stim_grayScreen.started')
    for start_time in stim_df['stim_grating.started']:
        plt.axvline(x=start_time, color='green', linestyle='--', label='stim_grating.started')

    # Adjust the layout
    plt.tight_layout()

    # Show the plots
    plt.show()

def plot_stim_times2(df):
    import plotly.express as px
    import plotly.graph_objects as go
    
    # Create an interactive scatter plot for 'thisRow.t'
    fig = px.scatter(df, x='thisRow.t', title='Scatter Plot of thisRow.t')
    fig.update_layout(xaxis_title='thisRow.t', yaxis_title='na')
    #fig.show()

    # Create an interactive plot with vertical lines for 'stim_grayScreen.started' and 'stim_grating.started'
    fig = go.Figure()

    # Add scatter plot for 'thisRow.t'
    fig.add_trace(go.Scatter(x=df['thisRow.t'], mode='markers', name='thisRow.t'))

    # Add vertical lines for 'stim_grayScreen.started'
    for start_time in df['stim_grayScreen.started']:
        fig.add_vline(x=start_time, line=dict(color='red', dash='dash'), name='stim_grayScreen.started')

    # Add vertical lines for 'stim_grating.started'
    for start_time in df['stim_grating.started']:
        fig.add_vline(x=start_time, line=dict(color='green', dash='dash'), name='stim_grating.started')

    fig.update_layout(title='Visual stim presentation timepoints',
                    xaxis_title='Time')
    fig.show()
    
