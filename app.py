import tempfile
import cv2
import numpy as np
from PIL import Image
import streamlit as st
from streamlit_image_coordinates import streamlit_image_coordinates

st.set_page_config(
    page_title="Golf Tracer", 
    page_icon="⛳",
    layout="centered"
)

# Custom mobile/PC friendly compact layout
st.markdown("""
    <style>
    .block-container {
        padding-top: 1rem;
        padding-bottom: 1rem;
        max-width: 450px;
    }
    div[data-testid="stImage"] {
        display: flex;
        justify-content: center;
    }
    </style>
""", unsafe_allow_html=True)

st.title("⛳ Visual Golf Tracer")

uploaded_file = st.file_uploader("Upload Golf Swing", type=["mp4", "mov", "avi"])

if uploaded_file:
    # 1. Save uploaded video to temp file
    if "video_path" not in st.session_state or st.session_state.get("file_name") != uploaded_file.name:
        tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
        tfile.write(uploaded_file.read())
        st.session_state.video_path = tfile.name
        st.session_state.file_name = uploaded_file.name
        # Clear old session data
        st.session_state.pop("frames_cache", None)
        st.session_state.pop("target_point", None)

    video_path = st.session_state.video_path

    # Read Video Info
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    DISPLAY_WIDTH = 360

    # 2. Fast Frame Extraction Helper
    def get_frame(frame_idx):
        cap = cv2.VideoCapture(video_path)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, f = cap.read()
        cap.release()
        if ret:
            return cv2.cvtColor(f, cv2.COLOR_BGR2RGB)
        return None

    # Initialize State Defaults
    if "impact_frame" not in st.session_state:
        st.session_state.impact_frame = min(15, total_frames)

    # 3. ISOLATED UI FRAGMENT (Prevents full page reloads on slider move)
    @st.fragment
    def render_scrubber():
        # Get active frame
        curr_frame_idx = st.session_state.impact_frame - 1
        frame_rgb = get_frame(curr_frame_idx)

        if frame_rgb is not None:
            pil_img = Image.fromarray(frame_rgb)

            # Draw persistent red target overlay on the frame if user tapped a ball point
            if "target_point" in st.session_state and st.session_state.target_point is not None:
                tx, ty = st.session_state.target_point
                # Overlay target crosshair on copy of image
                img_copy = frame_rgb.copy()
                # Red Ring & Crosshair
                cv2.circle(img_copy, (tx, ty), 12, (255, 0, 0), 2)
                cv2.line(img_copy, (tx - 18, ty), (tx + 18, ty), (255, 0, 0), 2)
                cv2.line(img_copy, (tx, ty - 18), (tx, ty + 18), (255, 0, 0), 2)
                pil_img = Image.fromarray(img_copy)

            # A. DISPLAY VIDEO FRAME (ALWAYS FIRST)
            click = streamlit_image_coordinates(
                pil_img,
                width=DISPLAY_WIDTH,
                key=f"frame_click_{st.session_state.impact_frame}"
            )

            # Handle Tap / Click on Ball
            if click:
                scale_factor = width / DISPLAY_WIDTH
                real_x = int(click["x"] * scale_factor)
                real_y = int(click["y"] * scale_factor)
                st.session_state.target_point = (real_x, real_y)
                st.rerun()

            # B. FRAME SCRUBBER SLIDER (POSITIONED DIRECTLY BELOW VIDEO FRAME)
            slider_val = st.slider(
                f"Impact Frame ({st.session_state.impact_frame} / {total_frames})",
                min_value=1,
                max_value=total_frames,
                value=st.session_state.impact_frame,
                step=1,
                key="impact_slider"
            )

            if slider_val != st.session_state.impact_frame:
                st.session_state.impact_frame = slider_val
                st.rerun()

    # Call Fragment UI
    render_scrubber()

    # Feedback Status
    if "target_point" in st.session_state and st.session_state.target_point is not None:
        tx, ty = st.session_state.target_point
        st.success(f"🎯 Target Locked at ({tx}, {ty}) on Frame {st.session_state.impact_frame}")

        # 4. RENDER BUTTON
        if st.button("🚀 Render Flight Tracer", type="primary", use_container_width=True):
            import subprocess
            with st.spinner("Calculating flight arc & processing video..."):
                flight_duration = int(fps * 1.5)
                apex_x = int(tx - (width * 0.12))
                apex_y = int(height * 0.22)
                landing_x = int(apex_x - (width * 0.05))
                landing_y = int(height * 0.45)

                p0 = np.array([tx, ty])
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

                cap = cv2.VideoCapture(video_path)
                raw_temp = tempfile.NamedTemporaryFile(delete=False, suffix="_raw.mp4")
                fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                out = cv2.VideoWriter(raw_temp.name, fourcc, fps, (width, height))

                curr_idx = 0
                while cap.isOpened():
                    r_flag, f = cap.read()
                    if not r_flag:
                        break

                    if curr_idx >= (st.session_state.impact_frame - 1):
                        elapsed = curr_idx - (st.session_state.impact_frame - 1)
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

                # Transcode for browser/mobile compatibility
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
    else:
        st.info("👆 Tap on the golf ball in the frame above to set impact target.")
