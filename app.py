import cv2
import numpy as np
import streamlit as st
from filterpy.kalman import KalmanFilter
from ultralytics import YOLO

# Streamlit Page Setup
st.set_page_config(page_title="Golf Ball Tracer", page_icon="⛳")
st.title("⛳ Golf Ball Tracer")
st.write(
    "Upload a golf swing clip. The AI and physics filter will track the ball flight even against bright skies."
)


# Initialize Kalman Filter for Physics State Estimation
def init_kalman():
    kf = KalmanFilter(dim_x=4, dim_z=2)
    # State vector: [x, y, velocity_x, velocity_y]
    kf.x = np.array([0.0, 0.0, 0.0, 0.0])
    # State Transition Matrix
    kf.F = np.array([[1, 0, 1, 0], [0, 1, 0, 1], [0, 0, 1, 0], [0, 0, 0, 1]])
    # Measurement Matrix
    kf.H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]])
    kf.P *= 1000.0
    kf.R = np.array([[10, 0], [0, 10]])
    kf.Q = np.eye(4) * 0.1
    return kf


# Load YOLO Model
@st.cache_resource
def load_yolo_model():
    return YOLO("yolov8n.pt")


model = load_yolo_model()

# File Uploader UI Widget
uploaded_file = st.file_uploader(
    "Upload Golf Swing Video", type=["mp4", "mov", "avi"]
)

if uploaded_file is not None:
    # Save uploaded file locally
    input_path = "temp_input.mp4"
    with open(input_path, "wb") as f:
        f.write(uploaded_file.read())

    st.info("Processing video... Please wait.")

    cap = cv2.VideoCapture(input_path)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = int(cap.get(cv2.CAP_PROP_FPS)) or 30

    output_path = "traced_output.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    kf = init_kalman()
    tracked_points = []
    kalman_initialized = False

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        # Run AI detection (low confidence threshold for small objects)
        results = model.predict(source=frame, conf=0.15, verbose=False)

        ball_found = False
        detected_x, detected_y = 0, 0

        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                w, h = x2 - x1, y2 - y1

                # Basic size filtering to isolate ball-sized contours
                if 2 <= w <= 40 and 2 <= h <= 40:
                    detected_x = int((x1 + x2) / 2)
                    detected_y = int((y1 + y2) / 2)
                    ball_found = True
                    break

        if ball_found:
            if not kalman_initialized:
                kf.x = np.array([detected_x, detected_y, 0, 0], dtype=float)
                kalman_initialized = True

            kf.predict()
            kf.update(np.array([detected_x, detected_y]))
            tracked_points.append((int(kf.x[0]), int(kf.x[1])))
        else:
            # SKY HANDSHAKE: If AI loses the ball against bright sky, predict via physics
            if kalman_initialized and len(tracked_points) > 3:
                kf.predict()
                # Apply slight down-force acceleration (gravity in pixel space)
                kf.x[3] += 0.5
                predicted_x = int(kf.x[0])
                predicted_y = int(kf.x[1])

                if 0 <= predicted_x < width and 0 <= predicted_y < height:
                    tracked_points.append((predicted_x, predicted_y))

        # Draw trajectory line
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

    cap.release()
    out.release()

    st.success("Tracing complete!")
    st.video(output_path)
