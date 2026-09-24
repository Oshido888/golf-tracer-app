import os
import subprocess
import tempfile
import cv2
import numpy as np
from PIL import Image, ImageDraw
import streamlit as st
from streamlit_image_coordinates import streamlit_image_coordinates

st.set_page_config(
    page_title="Golf Tracer", 
    page_icon="⛳",
    layout="centered"
)

# Custom CSS for compact iPhone-like editor layout
st.markdown("""
    <style>
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        max-width: 650px;
    }
    div[data-testid="stImage"] img {
        border-radius: 12px;
        max-height: 420px;
        object-fit: contain;
    }
    </style>
""", unsafe_allow_html=True)

st.title("⛳ Visual Golf Tracer")

uploaded_file = st.file_uploader("Upload Golf Swing", type=["mp4", "mov", "avi"])

if uploaded_file:
    # Save video to temp file
    tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    tfile.write(uploaded_file.read())
    video_path = tfile.name

    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    # Layout Container (Mobile Editor Frame)
    editor_container = st.container()

    with editor_container:
        st.caption("1. Scrub to impact frame and tap the golf ball on the image.")

        # Interactive Frame Scrubber (iPhone Style Slider)
        impact_frame = st.slider(
            "Impact Frame Scrubber",
            min_value=1,
            max_value=total_frames,
            value=min(15, total_frames),
            step=1,
            label_visibility="collapsed"
        )

        # Read exact frame from Video
        cap = cv2.VideoCapture(video_path)
        cap.set(cv2.CAP_PROP_POS_FRAMES, impact_frame - 1)
        ret, frame = cap.read()
        cap.release()

        if ret:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(frame_rgb)

            # Store click coords in session state so marker stays attached to frame
            click_key = f"impact_click_{impact_frame}"
            click = streamlit_image_coordinates(
                pil_img, 
                key=click_key,
                use_column_width=True
            )

            cx, cy = None, None
            if click:
                cx, cy = click["x"], click["y"]
                st.success(f"🎯 Ball position locked at ({cx}, {cy}) on Frame {impact_frame}")
            else:
                st.info("👆 Tap the golf ball directly on the frame above.")

            # Action Button
            if cx is not None and cy is not None:
                if st.button("🚀 Render Flight Tracer", type="primary", use_container_width=True):
                    with st.spinner("Processing flight physics & video..."):
                        # Parabola trajectory calculation
                        flight_duration = int(fps * 1.5)
                        apex_x = int(cx - (width * 0.12))
                        apex_y = int(height * 0.22)
                        landing_x = int(apex_x - (width * 0.05))
                        landing_y = int(height * 0.45)

                        p0 = np.array([cx, cy])
                        p1 = np.array([apex_x, apex_y])
                        p2 = np.array([landing_x, landing_y])

                        t = np.linspace(0, 1, flight_duration)
                        curve_points = [
                            (
                                int((1 - ti) ** 2 * p0[0] + 2 * (1 - ti) * ti * p1[0] + ti**2 * p2[0]),
                                int((1 - ti) ** 2 * p0[1] + 2 * (1 - ti) * ti * p1[1] + ti**2 * p2[1]),
                            )
                            for ti in t
                        ]

                        # Render tracer onto raw video
                        cap = cv2.VideoCapture(video_path)
                        raw_temp = tempfile.NamedTemporaryFile(delete=False, suffix="_raw.mp4")
                        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                        out = cv2.VideoWriter(raw_temp.name, fourcc, fps, (width, height))

                        curr_idx = 0
                        while cap.isOpened():
                            r_flag, f = cap.read()
                            if not r_flag:
                                break

                            # Draw tracer strictly starting at selected impact frame
                            if curr_idx >= (impact_frame - 1):
                                elapsed = curr_idx - (impact_frame - 1)
                                pts_count = min(elapsed + 1, len(curve_points))

                                if pts_count > 1:
                                    active_pts = np.array(curve_points[:pts_count], dtype=np.int32)
                                    cv2.polylines(
                                        f,
                                        [active_pts],
                                        isClosed=False,
                                        color=(0, 255, 0),
                                        thickness=4,
                                        lineType=cv2.LINE_AA,
                                    )
                                    cv2.circle(
                                        f,
                                        curve_points[pts_count - 1],
                                        6,
                                        (255, 255, 255),
                                        -1,
                                        cv2.LINE_AA,
                                    )

                            out.write(f)
                            curr_idx += 1

                        cap.release()
                        out.release()

                        # Convert video codec for iOS/Mobile Web compatibility
                        web_temp = tempfile.NamedTemporaryFile(delete=False, suffix="_web.mp4")
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
                        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                        st.video(web_temp.name)
