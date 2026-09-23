import os
import subprocess
import cv2
import imageio_ffmpeg as ffmpeg_bin
import numpy as np
import streamlit as st
from filterpy.kalman import KalmanFilter
from ultralytics import YOLO

# Streamlit Page Setup
st.set_page_config(page_title="Golf Ball Tracer AI", page_icon="⛳")
st.title("⛳ Smart Golf Ball Tracer")
st.caption(
    "Automated trajectory tracking for White, Yellow, and Pink golf balls."
)


# Initialize 2D Kalman Filter
def init_kalman():
    kf = KalmanFilter(dim_x=4, dim_z=2)
    kf.x = np.array([0.0, 0.0, 0.0, 0.0])
    kf.F = np.array([[1, 0, 1, 0], [0, 1, 0, 1], [0, 0, 1, 0], [0, 0, 0, 1]])
    kf.H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]])
    kf.P *= 1000.0
    kf.R = np.array([[10, 0], [0, 10]])
    kf.Q = np.eye(4) * 0.1
    return kf


# Cache model loading
@st.cache_resource
def load_yolo():
    return YOLO("yolov8n.pt")


model = load_yolo()


# Color Range Mask Generator
def get_color_mask(hsv, color):
    if color == "White":
        return cv2.inRange(
            hsv, np.array([0, 0, 180]), np.array([180, 60, 255])
        )
    elif color == "Yellow":
        return cv2.inRange(
            hsv, np.array([20, 100, 100]), np.array([35, 255, 255])
        )
    elif color == "Pink":
        return cv2.inRange(
            hsv, np.array([140, 50, 100]), np.array([170, 255, 255])
        )
    return None


# Auto Detect Impact Frame Pass
def auto_detect_impact(video_path, ball_color):
    cap = cv2.VideoCapture(video_path)
    prev_pos = None
    frame_idx = 0
    impact_frame = 0

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        frame_idx += 1

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = get_color_mask(hsv, ball_color)

        # Quick detection pass for moving ball
        results = model.predict(source=frame, conf=0.10, verbose=False)
        curr_pos = None

        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                w, h = x2 - x1, y2 - y1
                if 2 <= w <= 50 and 2 <= h <= 50:
                    cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)
                    if mask[cy, cx] > 0:
                        curr_pos = (cx, cy)
                        break

        if prev_pos and curr_pos:
            speed = np.sqrt(
                (curr_pos[0] - prev_pos[0]) ** 2
                + (curr_pos[1] - prev_pos[1]) ** 2
            )
            # Velocity burst threshold indicating ball launch
            if speed > 20:
                impact_frame = max(1, frame_idx - 2)
                break

        prev_pos = curr_pos

    cap.release()
    return impact_frame


# --- UI CONTROLS ---
col1, col2 = st.columns(2)
with col1:
    ball_color = st.selectbox(
        "Golf Ball Color", ["White", "Yellow", "Pink"], index=0
    )

with col2:
    mode = st.radio("Impact Frame Mode", ["Auto-Detect", "Manual Override"])
    if mode == "Manual Override":
        start_frame_offset = st.number_input(
            "Start Frame Number", min_value=0, max_value=500, value=0
        )
    else:
        start_frame_offset = None

uploaded_file = st.file_uploader(
    "Upload Golf Swing Video", type=["mp4", "mov", "avi"]
)

if uploaded_file is not None:
    input_path = "temp_input.mp4"
    with open(input_path, "wb") as f:
        f.write(uploaded_file.read())

    # Calculate or Set Impact Frame
    if mode == "Auto-Detect":
        with st.spinner("Auto-detecting impact frame..."):
            detected_frame = auto_detect_impact(input_path, ball_color)
            st.info(f"Auto-detected Impact Frame: {detected_frame}")
            start_frame_offset = detected_frame

    cap = cv2.VideoCapture(input_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = int(cap.get(cv2.CAP_PROP_FPS)) or 30

    temp_output = "temp_traced.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(temp_output, fourcc, fps, (width, height))

    # UI Status Controls
    st.write("---")
    status_text = st.empty()
    progress_bar = st.progress(0)

    kf = init_kalman()
    tracked_points = []
    kalman_initialized = False
    current_frame = 0

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        current_frame += 1

        # Only process ball trajectory from impact onwards
        if current_frame >= start_frame_offset:
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            mask = get_color_mask(hsv, ball_color)

            results = model.predict(source=frame, conf=0.10, verbose=False)
            ball_found = False
            detected_x, detected_y = 0, 0

            for r in results:
                for box in r.boxes:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    w, h = x2 - x1, y2 - y1

                    if 2 <= w <= 50 and 2 <= h <= 50:
                        cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)

                        if mask[cy, cx] > 0:
                            # Filter static ground objects
                            if kalman_initialized:
                                dist = np.sqrt(
                                    (cx - kf.x[0]) ** 2 + (cy - kf.x[1]) ** 2
                                )
                                if dist < 10:
                                    continue

                            detected_x, detected_y = cx, cy
                            ball_found = True
                            break

            # Kalman Filter State Update & Sky Prediction
            if ball_found:
                if not kalman_initialized:
                    kf.x = np.array(
                        [detected_x, detected_y, 0, 0], dtype=float
                    )
                    kalman_initialized = True

                kf.predict()
                kf.update(np.array([detected_x, detected_y]))
                tracked_points.append((int(kf.x[0]), int(kf.x[1])))
            else:
                if kalman_initialized and len(tracked_points) > 2:
                    kf.predict()
                    kf.x[3] += 0.8  # Downward pixel gravity compensation
                    px, py = int(kf.x[0]), int(kf.x[1])

                    if 0 <= px < width and 0 <= py < height:
                        tracked_points.append((px, py))

        # Render Trajectory Line
        if len(tracked_points) > 1:
            for i in range(1, len(tracked_points)):
                cv2.line(
                    frame,
                    tracked_points[i - 1],
                    tracked_points[i],
                    (0, 255, 0),
                    4,
                )

        out.write(frame)

        # Update Progress Bar
        if total_frames > 0:
            percent = min(current_frame / total_frames, 1.0)
            progress_bar.progress(percent)
            status_text.text(
                f"Processing frame {current_frame} of {total_frames} ({int(percent * 100)}%)"
            )

    cap.release()
    out.release()

    progress_bar.empty()
    status_text.text("Encoding final mobile video format...")

    # Transcode video to H.264
    final_output = "final_traced_h264.mp4"
    ffmpeg_exe = ffmpeg_bin.get_ffmpeg_exe()
    cmd = [
        ffmpeg_exe,
        "-y",
        "-i",
        temp_output,
        "-vcodec",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        final_output,
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    status_text.empty()
    st.success("Tracing Complete!")
    st.video(final_output)
