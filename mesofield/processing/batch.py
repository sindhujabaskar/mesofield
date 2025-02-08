import time
import numpy as np
import tifffile
import cv2
from tqdm import tqdm
import concurrent.futures
from concurrent.futures import ProcessPoolExecutor
import os

def tiff_to_video(
    tiff_path: str,
    output_path: str,
    fps: int = 30,
    output_format: str = "mp4",
    use_color: bool = False,
    show_progress: bool = True,
    tqdm_position: int = 0
):
    """
    Converts a multi-page TIFF stack to a video format.
    
    Parameters
    ----------
    tiff_path : str
        Path to the input TIFF file.
    output_path : str
        Path to the output video file.
    fps : int
        Frames per second for the output video.
    output_format : str
        Video format extension ('avi' or 'mp4'). 
        If 'mp4', chooses an appropriate fourcc code for H.264 or similar.
    use_color : bool
        Set to True if your images are RGB. For a single-channel grayscale, use False.
    show_progress : bool
        Whether to display a progress bar for frame processing.
    tqdm_position : int
        The line offset to display the progress bar.
    """
    tiff_array = tifffile.memmap(tiff_path)  # shape -> (num_frames, height, width) or (num_frames, height, width, channels)
    
    num_frames = tiff_array.shape[0]
    height = tiff_array.shape[1]
    width = tiff_array.shape[2] if not use_color else tiff_array.shape[2]
    
    if output_format.lower() == 'avi':
        fourcc = cv2.VideoWriter_fourcc(*'MJPG')  # or 'XVID'
    elif output_format.lower() == 'mp4':
        fourcc = cv2.VideoWriter_fourcc(*'H264')  # H.264 baseline
    else:
        raise ValueError(f"Unsupported output_format '{output_format}'. Use 'avi' or 'mp4'.")
    
    out = cv2.VideoWriter(
        filename=output_path,
        fourcc=fourcc,
        fps=fps,
        frameSize=(width, height),
        isColor=use_color
    )
    
    frame_iter = tqdm(
        range(num_frames),
        desc=f"Processing {os.path.basename(tiff_path)}",
        position=tqdm_position,
        leave=False,
        disable=not show_progress
    )
    
    for i in frame_iter:
        frame = tiff_array[i]
        if frame.dtype != np.uint8:
            frame = cv2.convertScaleAbs(frame)
        out.write(frame)
    
    out.release()
    

def convert_one(args):
    """
    Worker function to convert a single TIFF file to video.
    
    Parameters
    ----------
    args : tuple
        A tuple containing (file_path, processed_dir, output_format, fps, use_color, position)
    """
    file_path, processed_dir, output_format, fps, use_color, position = args
    base_filename = os.path.splitext(os.path.basename(file_path))[0]
    output_path = os.path.join(processed_dir, f"{base_filename}.{output_format}")
    
    tiff_to_video(
        tiff_path=file_path,
        output_path=output_path,
        fps=fps,
        output_format=output_format,
        use_color=use_color,
        show_progress=True,
        tqdm_position=position
    )
    
    #return f"Converted {file_path} to {output_path}"

def parse_bids_files_and_convert(parent_directory, fps=30, output_format="mp4", use_color=False):
    """
    Parses the BIDS directory to find pupil.ome.tiff files and converts them to video.
    
    Parameters
    ----------
    parent_directory : str
        Path to the parent directory containing the data folder.
    fps : int, optional
        Frames per second for the output video, by default 30.
    output_format : str, optional
        Output video format ('mp4' or 'avi'), by default "mp4".
    use_color : bool, optional
        Whether the TIFF images are in color, by default False.
    """
    found_files = []
    for root, dirs, files in os.walk(parent_directory):
        for file in files:
            if file.endswith("pupil.ome.tiff"):
                full_path = os.path.join(root, file)
                found_files.append(full_path)
    
    processed_dir = os.path.join(parent_directory, "data", "processed")
    print("Identified the following TIFF files:")
    for tiff_path in found_files:
        print(tiff_path)
    print(f"\nProcessed data will be saved to: {processed_dir}")
    
    user_input = input("\nContinue with conversion? (y/n): ")
    if user_input.lower().startswith('y'):
        os.makedirs(processed_dir, exist_ok=True)
        
        # Prepare arguments as a list of tuples, including unique positions
        args_list = [
            (file_path, processed_dir, output_format, fps, use_color, idx)
            for idx, file_path in enumerate(found_files)
        ]

        print("\nStarting conversion with multiprocessing...")
        with ProcessPoolExecutor(max_workers=os.cpu_count()) as executor:
            # Submit all tasks and collect futures
            for args in args_list:
                executor.submit(convert_one, args) 
            
        
    else:
        print("Conversion canceled.")

    print("\nConversion complete.")

if __name__ == "__main__":
    # Example usage
    parent_dir = r"D:\sbaskar\241220_etoh-checkerboard"  # Replace with your actual parent directory
    frames_per_second = 30
    
    parse_bids_files_and_convert(
        parent_directory=parent_dir,
        fps=frames_per_second,
        output_format="mp4",
        use_color=False
    )