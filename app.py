import os
import subprocess
import cv2
import imageio_ffmpeg as ffmpeg_bin
import numpy as np
from scipy.interpolate import splprep, splev
import streamlit as st
from filterpy.kalman import KalmanFilter
from ultralytics import YOLO

st.set_page_config(page_title="Pro Golf Tracer AI", page_icon="⛳")
st.title("⛳ Pro Golf Ball Tracer")


def init_kalman():
    kf = KalmanFilter(dim_x=4, dim_z=2)
    kf.x = np.array([0.0, 0.0, 0.0, 0.0])
    kf.F = np.array([[1, 0, 1, 0], [0, 1, 0, 1], [0, 0, 1, 0], [0, 0, 0, 1]])
    kf.H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]])
    kf.P *= 1000.0
    kf.R = np.array([[5, 0], [0, 5]])
    kf.Q = np.eye(4) * 0.05
    return kf


@st.cache_resource
def load_yolo():
    return YOLO("yolov8n.pt")


model = load_yolo()


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


def fit_bspline(points, num_points=100):
    if len(points) < 4:
        return points

    pts = np.array(points)
    unique_mask = np.ones(len(pts), dtype=bool)
    for i in range(1, len(pts)):
        if np.linalg.norm(pts[i] - pts[i - 1]) < 2:
            unique_mask[i] = False
    pts = pts[unique_mask]

    if len(pts) < 4:
        return points

    try:
        x, y = pts[:, 0], pts[:, 1]
        tck, _ = splprep([x, y], s=30, k=min(3, len(pts) - 1))
        u_new = np.linspace(0, 1, num_points)
        x_new, y_new = splev(u_new, tck)
        return list(zip(x_new.astype(int), y_new.astype(int)))
    except Exception:
        return points


def draw_glow_line(
    frame, pts, color_bgr=(0, 255, 255), thickness=3, apex_pt=None
):
    if len(pts) < 2:
        return frame

    pts_array = np.array(pts, dtype=np.int32).reshape((-1, 1, 2))

    # Outer Glow Layer
    overlay = frame.copy()
    cv2.polylines(
        overlay, [pts_array], isClosed=False, color=color_bgr, thickness=9
    )
    frame = cv2.addWeighted(overlay, 0.4, frame, 0.6, 0)

    # Core Bright White Center Line
    cv2.polylines(
        frame,
        [pts_array],
        isClosed=False,
        color=(255, 255, 255),
        thickness=thickness,
    )

    # Apex Badge Overlay
    if apex_pt:
        ax, ay = apex_pt
        cv2.circle(frame, (ax, ay), 5, color_bgr, -1)
        cv2.circle(frame, (ax, ay), 7, (255, 255, 255), 2)
        cv2.putText(
            frame,
            "APEX",
            (ax - 18, ay - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (255, 255, 255),
            2,
        )

    return frame


# --- UI CONTROLS ---
col1, col2, col3 = st.columns(3)
with col1:
    ball_color = st.selectbox(
        "Golf Ball Color", ["White", "Yellow", "Pink"], index=0
    )

with col2:
    tracer_style = st.selectbox(
        "Tracer Color", ["Neon Yellow", "Cyan", "Magenta"], index=0
    )
    color_map = {
        "Neon Yellow": (0, 255, 255),
        "Cyan": (255, 255, 0),
        "Magenta": (255, 0, 255),
    }

with col3:
    mode = st.radio(
        "Impact Frame Mode", ["Manual Override", "Auto-Detect"], index=0
    )
    if mode == "Manual Override":
        start_frame_offset = st.number_input(
            "Impact Frame (e.g., Frame 60)", min_value=0, max_value=600, value=60
        )
    else:
        start_frame_offset = 60  # Default fallback

uploaded_file = st.file_uploader(
    "Upload Golf Swing Video", type=["mp4", "mov", "avi"]
)

if uploaded_file is not None:
    input_path = "temp_input.mp4"
    with open(input_path, "wb") as f:
        f.write(uploaded_file.read())

    with st.status("Processing Golf Swing...", expanded=True) as status:
        cap = cv2.VideoCapture(input_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = int(cap.get(cv2.CAP_PROP_FPS)) or 30

        temp_output = "temp_traced.mp4"
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(temp_output, fourcc, fps, (width, height))

        status.write(
            f"🚀 Processing from **Frame {start_frame_offset}** onwards..."
        )
        progress_bar = st.progress(0, text="Reading frames...")

        kf = init_kalman()
        raw_tracked_points = []
        kalman_initialized = False
        current_frame = 0

        # Pass 1: Collect coordinates ONLY AFTER impact frame
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            current_frame += 1

            if current_frame >= start_frame_offset:
                hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                mask = get_color_mask(hsv, ball_color)

                results = model.predict(source=frame, conf=0.08, verbose=False)
                ball_found = False
                detected_x, detected_y = 0, 0

                for r in results:
                    for box in r.boxes:
                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                        w, h = x2 - x1, y2 - y1

                        if 2 <= w <= 45 and 2 <= h <= 45:
                            cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)

                            if mask[cy, cx] > 0:
                                detected_x, detected_y = cx, cy
                                ball_found = True
                                break

                if ball_found:
                    if not kalman_initialized:
                        kf.x = np.array(
                            [detected_x, detected_y, 0, 0], dtype=float
                        )
                        kalman_initialized = True

                    kf.predict()
                    kf.update(np.array([detected_x, detected_y]))
                    raw_tracked_points.append((int(kf.x[0]), int(kf.x[1])))
                else:
                    if kalman_initialized and len(raw_tracked_points) > 2:
                        kf.predict()
                        kf.x[3] += 0.85  # Gravity force simulation
                        px, py = int(kf.x[0]), int(kf.x[1])

                        if 0 <= px < width and 0 <= py < height:
                            raw_tracked_points.append((px, py))

        cap.release()

        # Pass 2: Fit B-Spline curve across trajectory
        smoothed_points = fit_bspline(raw_tracked_points, num_points=100)

        # Identify Apex
        apex_point = None
        if len(smoothed_points) > 0:
            apex_idx = np.argmin([p[1] for p in smoothed_points])
            apex_point = smoothed_points[apex_idx]

        # Pass 3: Render video (Do NOT draw anything before impact)
        cap = cv2.VideoCapture(input_path)
        render_frame = 0

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            render_frame += 1

            # ONLY draw tracer if render_frame has reached or passed start_frame_offset
            if render_frame >= start_frame_offset and len(smoothed_points) > 1:
                frames_since_impact = render_frame - start_frame_offset
                flight_duration = max(1, total_frames - start_frame_offset)

                # Reveal line progressively as time passes
                progress_ratio = min(
                    frames_since_impact / flight_duration, 1.0
                )
                visible_count = max(
                    2, int(progress_ratio * len(smoothed_points))
                )
                current_pts = smoothed_points[:visible_count]

                show_apex = (
                    apex_point if visible_count >= len(smoothed_points) // 2 else None
                )
                frame = draw_glow_line(
                    frame,
                    current_pts,
                    color_bgr=color_map[tracer_style],
                    apex_pt=show_apex,
                )

            out.write(frame)

            if total_frames > 0 and render_frame % 5 == 0:
                percent = min(render_frame / total_frames, 1.0)
                progress_bar.progress(
                    percent,
                    text=f"Rendering frame {render_frame}/{total_frames}",
                )

        cap.release()
        out.release()

        status.write("🎬 Transcoding to web format...")
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
        subprocess.run(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

        status.update(
            label="Tracing Complete!", state="complete", expanded=False
        )

    st.success("Traced video ready!")
    st.video(final_output)
