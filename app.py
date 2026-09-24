import os
import subprocess
import tempfile
import cv2
import numpy as np
import streamlit as st
from PIL import Image
from streamlit_image_coordinates import streamlit_image_coordinates

st.set_page_config(page_title="Golf Tracer", page_icon="⛳")
st.title("⛳ Visual Golf Tracer")

uploaded_file = st.file_uploader("Upload Golf Swing", type=["mp4", "mov"])

if uploaded_file:
    # Save uploaded file
    tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    tfile.write(uploaded_file.read())
    video_path = tfile.name

    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    st.subheader("1. Select Impact Frame")
    frame_no = st.slider(
        "Scrub to Impact Frame",
        min_value=1,
        max_value=total_frames,
        value=min(15, total_frames),
    )

    # Read selected frame
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no - 1)
    ret, frame = cap.read()
    cap.release()

    if ret:
        # Convert frame to RGB for PIL
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(frame_rgb)

        st.subheader("2. Tap/Click the Golf Ball")
        st.caption("Tap directly on the ball on the image below.")

        # Display clickable image
        click = streamlit_image_coordinates(pil_img, key="ball_click")

        if click:
            start_x, start_y = click["x"], click["y"]
            st.success(f"Ball targeted at: ({start_x}, {start_y})")

            if st.button("🚀 Generate Flight Tracer", type="primary"):
                with st.spinner("Generating tracer..."):
                    # Generate 3D parabolic trajectory from clicked point
                    flight_duration = int(fps * 1.5)
                    apex_x = int(start_x - (width * 0.12))
                    apex_y = int(height * 0.22)
                    landing_x = int(apex_x - (width * 0.05))
                    landing_y = int(height * 0.45)

                    p0 = np.array([start_x, start_y])
                    p1 = np.array([apex_x, apex_y])
                    p2 = np.array([landing_x, landing_y])

                    t = np.linspace(0, 1, flight_duration)
                    curve_points = [
                        (
                            int(
                                (1 - ti) ** 2 * p0[0]
                                + 2 * (1 - ti) * ti * p1[0]
                                + ti**2 * p2[0]
                            ),
                            int(
                                (1 - ti) ** 2 * p0[1]
                                + 2 * (1 - ti) * ti * p1[1]
                                + ti**2 * p2[1]
                            ),
                        )
                        for ti in t
                    ]

                    # Process video
                    cap = cv2.VideoCapture(video_path)
                    raw_temp = tempfile.NamedTemporaryFile(
                        delete=False, suffix="_raw.mp4"
                    )
                    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                    out = cv2.VideoWriter(
                        raw_temp.name, fourcc, fps, (width, height)
                    )

                    curr_idx = 0
                    while cap.isOpened():
                        r, f = cap.read()
                        if not r:
                            break

                        if curr_idx >= (frame_no - 1):
                            elapsed = curr_idx - (frame_no - 1)
                            pts_count = min(elapsed + 1, len(curve_points))

                            if pts_count > 1:
                                active_pts = np.array(
                                    curve_points[:pts_count], dtype=np.int32
                                )
                                cv2.polylines(
                                    f,
                                    [active_pts],
                                    False,
                                    (0, 255, 0),
                                    4,
                                    cv2.LINE_AA,
                                )
                                cv2.circle(
                                    f,
                                    curve_points[pts_count - 1],
                                    6,
                                    (255, 255, 255),
                                    -1,
                                )

                        out.write(f)
                        curr_idx += 1

                    cap.release()
                    out.release()

                    # Transcode to web-compatible H.264
                    web_temp = tempfile.NamedTemporaryFile(
                        delete=False, suffix="_web.mp4"
                    )
                    cmd = [
                        "ffmpeg",
                        "-y",
                        "-i",
                        raw_temp.name,
                        "-vcodec",
                        "libx264",
                        "-pix_fmt",
                        "yuv420p",
                        web_temp.name,
                    ]
                    subprocess.run(
                        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )

                    st.video(web_temp.name)
