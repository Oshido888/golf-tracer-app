import os
import subprocess
import tempfile
import cv2
import numpy as np
from PIL import Image, ImageDraw
import streamlit as st
from streamlit_image_coordinates import streamlit_image_coordinates

st.set_page_config(page_title="Golf Tracer AI", page_icon="⛳")
st.title("⛳ Visual Golf Tracer")

uploaded_file = st.file_uploader("Upload Golf Swing", type=["mp4", "mov", "avi"])

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
    cap.release()

    st.subheader("1. Select Impact Frame")
    impact_frame = st.slider(
        "Scrub to Impact Frame",
        min_value=1,
        max_value=total_frames,
        value=min(15, total_frames),
    )

    # Read selected frame for display
    cap = cv2.VideoCapture(video_path)
    cap.set(cv2.CAP_PROP_POS_FRAMES, impact_frame - 1)
    ret, frame = cap.read()
    cap.release()

    if ret:
        # Convert BGR to RGB for PIL
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(frame_rgb)

        # Check if user clicked on image
        click = streamlit_image_coordinates(pil_img, key=f"click_{impact_frame}")

        # If user clicked, draw target crosshair marker over PIL image
        if click:
            cx, cy = click["x"], click["y"]
            
            # Draw visual marker on ball
            draw_img = pil_img.copy()
            draw = ImageDraw.Draw(draw_img)
            r = 10
            # Red target circle & crosshair
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline="red", width=3)
            draw.line((cx - r - 5, cy, cx + r + 5, cy), fill="red", width=2)
            draw.line((cx, cy - r - 5, cx, cy + r + 5), fill="red", width=2)
            
            # Re-render image showing the marker
            st.image(draw_img, caption=f"Ball Targeted at ({cx}, {cy})")

            st.subheader("2. Generate Trajectory")
            if st.button("🚀 Render Flight Tracer", type="primary"):
                with st.spinner("Generating tracer video..."):
                    # Estimate parabola curve points starting at clicked location
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

                    # Video Writer Setup
                    cap = cv2.VideoCapture(video_path)
                    raw_temp = tempfile.NamedTemporaryFile(delete=False, suffix="_raw.mp4")
                    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                    out = cv2.VideoWriter(raw_temp.name, fourcc, fps, (width, height))

                    curr_idx = 0
                    while cap.isOpened():
                        r_flag, f = cap.read()
                        if not r_flag:
                            break

                        # FIX: ONLY DRAW TRACER AT OR AFTER IMPACT FRAME
                        if curr_idx >= (impact_frame - 1):
                            elapsed = curr_idx - (impact_frame - 1)
                            pts_count = min(elapsed + 1, len(curve_points))

                            if pts_count > 1:
                                active_pts = np.array(curve_points[:pts_count], dtype=np.int32)
                                # Green flight trace
                                cv2.polylines(
                                    f,
                                    [active_pts],
                                    isClosed=False,
                                    color=(0, 255, 0),
                                    thickness=4,
                                    lineType=cv2.LINE_AA,
                                )
                                # Leading ball glow
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

                    # Transcode to H.264 Web Player Format
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

                    st.success("Tracing Complete!")
                    st.video(web_temp.name)
        else:
            st.info("👆 Tap on the golf ball in the image above to set the launch point.")
