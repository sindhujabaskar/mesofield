import os
import concurrent.futures
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

import numpy as np
from tqdm import tqdm
import tifffile


def mean_trace_from_tiff(tiff_paths, show_progress=True, save=False):
    """
    Computes the mean traces for multiple TIFF files concurrently.
    Returns a dictionary mapping each file path to its mean trace.
    """
    import concurrent.futures
    
    def _compute_mean_trace(tiff_path):
        tiff_array = tifffile.memmap(tiff_path)
        return np.mean(tiff_array, axis=(1, 2))
    
    with ThreadPoolExecutor() as executor:
        futures = {executor.submit(_compute_mean_trace, path): path for path in tiff_paths}
        results = {}
        
        if show_progress:
            with tqdm(total=len(tiff_paths), desc="Computing mean traces", leave=False) as pbar:
                for future in concurrent.futures.as_completed(futures):
                    path = futures[future]
                    results[path] = future.result()
                    pbar.update(1)
        else:
            for future in concurrent.futures.as_completed(futures):
                path = futures[future]
                results[path] = future.result()
    
    return results


def tiff_to_video(tiff_path: str,
                  output_path: str,
                  fps: int = 30,
                  output_format: str = "mp4",
                  use_color: bool = False,
                  show_progress: bool = True,
                  tqdm_position: int = 0):
    """
    Converts a multi-page TIFF stack to a video format.
    """
    import cv2

    tiff_array = tifffile.memmap(tiff_path)  # shape -> (num_frames, height, width) or (num_frames, height, width, channels)
    
    num_frames = tiff_array.shape[0]
    height = tiff_array.shape[1]
    width = tiff_array.shape[2] if not use_color else tiff_array.shape[2]
    
    if output_format.lower() == 'avi':
        fourcc = cv2.VideoWriter_fourcc(*'MJPG')
    elif output_format.lower() == 'mp4':
        fourcc = cv2.VideoWriter_fourcc(*'H264')
    else:
        raise ValueError(f"Unsupported output_format '{output_format}'. Use 'avi' or 'mp4'.")
    
    out = cv2.VideoWriter(
        filename=output_path,
        fourcc=fourcc,
        fps=fps,
        frameSize=(width, height),
        isColor=use_color
    )
    
    # Create a progress bar that updates and then clears itself when done.
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
            # Normalize the frame to the range [0, 255] before converting to uint8
            frame = cv2.normalize(frame, None, 0, 255, cv2.NORM_MINMAX)
            frame = cv2.convertScaleAbs(frame)
        out.write(frame)
    
    out.release()


def _convert_one(args):
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
    # Optionally, you could write a message for each finished conversion:
    tqdm.write(f"Finished converting {os.path.basename(file_path)}")


def tiff_to_mp4(parent_directory, fps=30, output_format="mp4", use_color=False):
    """
    Parses the BIDS directory to find pupil.ome.tiff files and converts them to video.
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
        
        # Prepare arguments as a list of tuples, including unique progress bar positions
        args_list = [
            (file_path, processed_dir, output_format, fps, use_color, idx)
            for idx, file_path in enumerate(found_files)
        ]

        print("\nStarting conversion with multiprocessing...")
        futures = []
        with ProcessPoolExecutor(max_workers=os.cpu_count()) as executor:
            # Submit all tasks and store futures to ensure they all complete.
            for args in args_list:
                futures.append(executor.submit(_convert_one, args))
            # Optionally, wait for all futures to complete
            for future in concurrent.futures.as_completed(futures):
                future.result()
                
    else:
        print("Conversion canceled.")

    print("\nConversion complete.")


if __name__ == "__main__":
    # Example usage
    parent_dir = r""  # Replace with your actual parent directory
    frames_per_second = 30
    
    tiff_to_mp4(
        parent_directory=parent_dir,
        fps=frames_per_second,
        output_format="mp4",
        use_color=False
    )