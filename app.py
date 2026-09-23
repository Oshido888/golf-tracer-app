import os
import subprocess
import cv2
import imageio_ffmpeg as ffmpeg_bin
import numpy as np
import streamlit as st
from filterpy.kalman import KalmanFilter
from ultralytics import YOLO

# Streamlit Page Config
st.set_page_config(page_title="Golf Ball Tracer AI", page_icon="⛳")
st.title("⛳ Golf Ball Tracer")
st.caption(
    "AI-powered trajectory tracker for White, Yellow, and Pink golf balls with sky loss protection."
)


# Initialize 2D Kalman Filter for Physics Flight Estimation
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

# --- UI CONTROLS ---
col1, col2 = st.columns(2)
with col1:
    ball_color = st.selectbox(
        "Golf Ball Color", ["White", "Yellow", "Pink"], index=0
    )
with col2:
    start_frame_offset = st.number_input(
        "Impact Start Frame",
        min_value=0,
        max_value=300,
        value=0,
        help="Set to skip address/setup frames and ignore ground markers.",
    )

uploaded_file = st.file_uploader(
    "Upload Golf Swing Video", type=["mp4", "mov", "avi"]
)

if uploaded_file is not None:
    input_path = "temp_input.mp4"
    with open(input_path, "wb") as f:
        f.write(uploaded_file.read())

    cap = cv2.VideoCapture(input_path)

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = int(cap.get(cv2.CAP_PROP_FPS)) or 30

    temp_output = "temp_traced.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(temp_output, fourcc, fps, (width, height))

    # UI Status & Progress Bar
    st.write("---")
    status_text = st.empty()
    progress_bar = st.progress(0)
    status_text.text("Processing golf swing...")

    kf = init_kalman()
    tracked_points = []
    kalman_initialized = False
    current_frame = 0

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        current_frame += 1

        # Only start tracking after impact frame to avoid static tee markers
        if current_frame >= start_frame_offset:
            # 1. COLOR MASKING (White, Yellow, Pink)
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            if ball_color == "White":
                mask = cv2.inRange(
                    hsv, np.array([0, 0, 180]), np.array([180, 60, 255])
                )
            elif ball_color == "Yellow":
                mask = cv2.inRange(
                    hsv, np.array([20, 100, 100]), np.array([35, 255, 255])
                )
            elif ball_color == "Pink":
                mask = cv2.inRange(
                    hsv, np.array([140, 50, 100]), np.array([170, 255, 255])
                )

            # 2. RUN AI DETECTION
            results = model.predict(source=frame, conf=0.10, verbose=False)

            ball_found = False
            detected_x, detected_y = 0, 0

            for r in results:
                for box in r.boxes:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    w, h = x2 - x1, y2 - y1

                    # Ball dimensions filter
                    if 2 <= w <= 50 and 2 <= h <= 50:
                        cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)

                        # Validate against HSV mask (ensure color match)
                        if mask[cy, cx] > 0:
                            # 3. MOTION-VELOCITY FILTER
                            # Ignore static tee markers by checking distance from last known point
                            if kalman_initialized:
                                dist = np.sqrt(
                                    (cx - kf.x[0]) ** 2 + (cy - kf.x[1]) ** 2
                                )
                                if dist < 10:  # Too static, likely a ground marker
                                    continue

                            detected_x, detected_y = cx, cy
                            ball_found = True
                            break

            # 4. TRACKING & KALMAN SKY PREDICTION
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
                # Ball lost in sky: predict position using momentum + pixel gravity
                if kalman_initialized and len(tracked_points) > 2:
                    kf.predict()
                    kf.x[3] += 0.8  # Add downward gravity acceleration
                    px, py = int(kf.x[0]), int(kf.x[1])

                    if 0 <= px < width and 0 <= py < height:
                        tracked_points.append((px, py))

        # 5. DRAW TRAJECTORY LINE
        if len(tracked_points) > 1:
            for i in range(1, len(tracked_points)):
                # Draw thick neon green line
                cv2.line(
                    frame,
                    tracked_points[i - 1],
                    tracked_points[i],
                    (0, 255, 0),
                    4,
                )

        out.write(frame)

        # UPDATE PROGRESS BAR
        if total_frames > 0:
            percent = min(current_frame / total_frames, 1.0)
            progress_bar.progress(percent)
            status_text.text(
                f"Processing frame {current_frame} of {total_frames} ({int(percent * 100)}%)"
            )

    cap.release()
    out.release()

    # Clear Progress Controls
    progress_bar.empty()
    status_text.text("Finalizing video encoding...")

    # Convert output using imageio-ffmpeg for universal mobile video playback
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
    st.success("Tracing complete!")
    st.video(final_output)
