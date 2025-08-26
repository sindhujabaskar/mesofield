import cv2
import os
import multiprocessing as mp
import numpy as np
import json
from pathlib import Path

# Set environment variables to suppress OpenCV/FFMPEG output BEFORE importing cv2
os.environ['OPENCV_LOG_LEVEL'] = 'SILENT'
os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'loglevel;quiet'
os.environ['OPENCV_VIDEOIO_DEBUG'] = '0'

cv2.setLogLevel(0)  # 0 = Silent

# ─── USER-ADJUSTABLE GLOBALS ─────────────────────────────────────────
INPUT_DIR      = r'D:\jgronemeyer\250627_HFSA\processed\pupil_mp4_links'
OUTPUT_DIR     = r'D:\jgronemeyer\250627_HFSA\processed\pupil_mp4_links\data\processed\cropped_enhanced'
CACHE_FILE     = r'D:\jgronemeyer\250627_HFSA\processed\pupil_mp4_links\data\processed\cropped_enhanced\crop_enhance_cache.json'
NUM_PROCESSES  = 10
FRAME_ROI      = 0    # index of frame for ROI selection
FRAME_ADJUST   = 0    # index of frame for contrast/brightness/gamma
NUM_SAMPLES    = 3    # how many ROI-cropped samples for adjustment
ROI_SIZE       = 128  # fixed ROI width & height
# OpenH264 codec paths for video conversion compatibility
# These paths point to external H.264 codec DLLs needed for OpenCV video encoding
# when the built-in codecs are not available or compatible with target software
BASE_DIR = Path(__file__).resolve().parent.parent
CODEC_DIRECTORY = str(BASE_DIR / 'video-codecs')
OPENH264_DLL_PATH = str(Path(CODEC_DIRECTORY) / 'openh264-1.8.0-win64.dll')
# ─────────────────────────────────────────────────────────────────

# --- initialize H264 support before any VideoWriter calls ---
os.environ['OPENH264_LIBRARY'] = OPENH264_DLL_PATH
if CODEC_DIRECTORY not in os.environ.get('PATH', ''):
    os.environ['PATH'] = CODEC_DIRECTORY + os.pathsep + os.environ.get('PATH', '')
if hasattr(os, 'add_dll_directory'):
    os.add_dll_directory(CODEC_DIRECTORY)
    
def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r') as f:
            return json.load(f)
    return {'rois': {}, 'adjust': {}}


def save_cache(cache):
    with open(CACHE_FILE, 'w') as f:
        json.dump(cache, f, indent=2)


def select_rois(video_paths, cached_rois):
    rois = cached_rois.copy()
    for path in video_paths:
        key = os.path.basename(path)
        if key in rois:
            continue
        cap = cv2.VideoCapture(path)
        cap.set(cv2.CAP_PROP_POS_FRAMES, FRAME_ROI)
        _, frame = cap.read()
        cap.release()
        x, y, w, h = cv2.selectROI(f'Select ROI – {key}', frame, False, False)
        cv2.destroyAllWindows()
        rois[key] = [int(x), int(y), int(w), int(h)]
    return rois


def calibrate_adjust(samples, cached_adjust):
    if cached_adjust:
        return cached_adjust['alpha'], cached_adjust['beta'], cached_adjust['gamma']

    # pad for uniform height
    heights = [f.shape[0] for f in samples]
    max_h = max(heights)
    padded = []
    for f in samples:
        h, w = f.shape[:2]
        if h < max_h:
            delta = max_h - h
            f = cv2.copyMakeBorder(f, 0, delta, 0, 0, cv2.BORDER_CONSTANT, value=[0,0,0])
        padded.append(f)

    def nothing(_): pass
    win = 'Adjust – press s to save'
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.createTrackbar('Contrast×100', win, 100, 300, nothing)
    cv2.createTrackbar('Brightness',    win, 100, 200, nothing)
    cv2.createTrackbar('Gamma×100',     win, 100, 300, nothing)

    while True:
        c = cv2.getTrackbarPos('Contrast×100', win) / 100.0
        b = cv2.getTrackbarPos('Brightness',    win) - 100
        g = cv2.getTrackbarPos('Gamma×100',     win) / 100.0

        invG = 1.0 / g if g > 0 else 1.0
        table = np.array([((i / 255.0) ** invG) * 255 for i in range(256)], dtype=np.uint8)
        adjusted_list = [cv2.LUT(cv2.convertScaleAbs(f, alpha=c, beta=b), table) for f in padded]

        combo = np.hstack(adjusted_list)
        cv2.imshow(win, combo)
        if cv2.waitKey(1) & 0xFF == ord('s'):
            break

    cv2.destroyAllWindows()
    return c, b, g


def process_video(args):
    path, roi, alpha, beta, gamma = args
    x, y, w, h = roi
    cap = cv2.VideoCapture(path)
    fps    = cap.get(cv2.CAP_PROP_FPS)
    fourcc = cv2.VideoWriter.fourcc(*'mp4v')
    out    = cv2.VideoWriter(os.path.join(OUTPUT_DIR, os.path.basename(path)), fourcc, fps, (w, h))
    invG   = 1.0 / gamma if gamma > 0 else 1.0
    table  = np.array([((i / 255.0) ** invG) * 255 for i in range(256)], dtype=np.uint8)

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        crop = frame[y:y+h, x:x+w]
        adj  = cv2.convertScaleAbs(crop, alpha=alpha, beta=beta)
        adj  = cv2.LUT(adj, table)
        out.write(adj)

    cap.release()
    out.release()


if __name__ == '__main__':
    vids = [os.path.join(INPUT_DIR, f) for f in os.listdir(INPUT_DIR) if f.lower().endswith('.mp4')]
    if not vids:
        print(f'No .mp4 files found in {INPUT_DIR}')
        exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # load or initialize cache
    cache = load_cache()

    # ROI selection, respecting cache
    rois = select_rois(vids, cache.get('rois', {}))
    cache['rois'] = rois
    save_cache(cache)

    # prepare samples for adjustment
    samples = []
    for v in vids[:NUM_SAMPLES]:
        cap = cv2.VideoCapture(v)
        cap.set(cv2.CAP_PROP_POS_FRAMES, FRAME_ADJUST)
        _, frame = cap.read()
        cap.release()
        key = os.path.basename(v)
        x, y, w, h = rois[key]
        samples.append(frame[y:y+h, x:x+w])

    # calibration, respecting cache
    alpha, beta, gamma = calibrate_adjust(samples, cache.get('adjust', {}))
    if not cache.get('adjust'):
        cache['adjust'] = {'alpha': alpha, 'beta': beta, 'gamma': gamma}
        save_cache(cache)

    # batch processing
    tasks = [(v, rois[os.path.basename(v)], alpha, beta, gamma) for v in vids]
    with mp.Pool(NUM_PROCESSES) as pool:
        pool.map(process_video, tasks)