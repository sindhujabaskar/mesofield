import sys
import cv2

def get_video_codec(video_path: str) -> str:
    """Return the FOURCC codec string for the given video file.

    Raises IOError if the file cannot be opened.
    """
    cap = cv2.VideoCapture(video_path)
    try:
        if not cap.isOpened():
            raise IOError(f"Cannot open video: {video_path!r}")
        codec_int = int(cap.get(cv2.CAP_PROP_FOURCC))
        codec = "".join(chr((codec_int >> 8 * i) & 0xFF) for i in range(4))
        return codec
    finally:
        cap.release()

if __name__ == "__main__":
    video_path = r"D:\jgronemeyer\250627_HFSA\data\sub-STREHAB10\ses-01\func\20250921_133040_sub-STREHAB10_ses-01_task-widefield_pupil.mp4"
    try:
        print("Codec:", get_video_codec(video_path))
    except Exception as e:
        print("Error:", e)
        sys.exit(1)
