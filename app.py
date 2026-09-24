import base64
import os
import subprocess
import tempfile
import cv2
import numpy as np
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="Golf Tracer", 
    page_icon="⛳",
    layout="centered"
)

st.markdown("""
    <style>
    .block-container {
        padding-top: 1rem;
        padding-bottom: 1rem;
        max-width: 440px;
    }
    </style>
""", unsafe_allow_html=True)

st.title("⛳ Visual Golf Tracer")

uploaded_file = st.file_uploader("Upload Golf Swing", type=["mp4", "mov", "avi"])

if uploaded_file:
    # 1. Save uploaded file
    tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    tfile.write(uploaded_file.read())
    video_path = tfile.name

    # Read video properties
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    DISPLAY_WIDTH = 360
    aspect_ratio = height / width
    DISPLAY_HEIGHT = int(DISPLAY_WIDTH * aspect_ratio)

    # Base64 Encode video
    with open(video_path, "rb") as vf:
        video_bytes = vf.read()
    
    b64_video = base64.b64encode(video_bytes).decode('utf-8')
    video_data_url = f"data:video/mp4;base64,{b64_video}"

    # HTML5 Scrubber with iOS & Touch Optimizations
    custom_scrubber_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
        <style>
            * {{ -webkit-tap-highlight-color: transparent; box-sizing: border-box; }}
            body {{ margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: transparent; display: flex; flex-direction: column; align-items: center; }}
            .video-container {{ position: relative; width: {DISPLAY_WIDTH}px; height: {DISPLAY_HEIGHT}px; border-radius: 12px; overflow: hidden; background: #000; box-shadow: 0 4px 12px rgba(0,0,0,0.15); }}
            video {{ width: 100%; height: 100%; object-fit: contain; display: block; }}
            canvas {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; cursor: crosshair; touch-action: none; }}
            .controls {{ width: {DISPLAY_WIDTH}px; margin-top: 10px; display: flex; flex-direction: column; gap: 6px; }}
            .slider-header {{ display: flex; justify-content: space-between; font-size: 13px; font-weight: 600; color: #444; }}
            input[type=range] {{ width: 100%; accent-color: #007AFF; height: 28px; cursor: pointer; }}
        </style>
    </head>
    <body>

        <div class="video-container">
            <video id="vPlayer" playsinline webkit-playsinline muted preload="auto">
                <source src="{video_data_url}" type="video/mp4">
            </video>
            <canvas id="overlayCanvas" width="{DISPLAY_WIDTH}" height="{DISPLAY_HEIGHT}"></canvas>
        </div>

        <div class="controls">
            <div class="slider-header">
                <span>Scrub Frame</span>
                <span id="frameText">Frame 1 / {total_frames}</span>
            </div>
            <input type="range" id="scrubber" min="0" max="{total_frames - 1}" value="0" step="1">
        </div>

        <script>
            const video = document.getElementById('vPlayer');
            const scrubber = document.getElementById('scrubber');
            const frameText = document.getElementById('frameText');
            const canvas = document.getElementById('overlayCanvas');
            const ctx = canvas.getContext('2d');

            const totalFrames = {total_frames};
            const fps = {fps};

            video.load();
            video.currentTime = 0;

            scrubber.addEventListener('input', (e) => {{
                const frameIdx = parseInt(e.target.value);
                video.currentTime = frameIdx / fps;
                frameText.innerText = 'Frame ' + (frameIdx + 1) + ' / ' + totalFrames;
            }});

            canvas.addEventListener('pointerdown', (e) => {{
                const rect = canvas.getBoundingClientRect();
                const x = e.clientX - rect.left;
                const y = e.clientY - rect.top;
                drawTarget(x, y);
            }});

            function drawTarget(x, y) {{
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                
                ctx.beginPath();
                ctx.arc(x, y, 10, 0, 2 * Math.PI);
                ctx.strokeStyle = '#FF3B30';
                ctx.lineWidth = 3;
                ctx.stroke();

                ctx.beginPath();
                ctx.moveTo(x - 16, y); ctx.lineTo(x + 16, y);
                ctx.moveTo(x, y - 16); ctx.lineTo(x, y + 16);
                ctx.strokeStyle = '#FF3B30';
                ctx.lineWidth = 2;
                ctx.stroke();

                ctx.beginPath();
                ctx.arc(x, y, 3, 0, 2 * Math.PI);
                ctx.fillStyle = '#FFFFFF';
                ctx.fill();
            }}
        </script>
    </body>
    </html>
    """

    components.html(custom_scrubber_html, height=DISPLAY_HEIGHT + 75)

    st.markdown("---")
    st.subheader("🎯 Trajectory Controls")

    # Impact Frame and Starting Position
    col1, col2, col3 = st.columns(3)
    with col1:
        cx = st.number_input("Start X", min_value=0, max_value=width, value=int(width * 0.5))
    with col2:
        cy = st.number_input("Start Y", min_value=0, max_value=height, value=int(height * 0.75))
    with col3:
        impact_frame = st.number_input("Impact Frame", min_value=1, max_value=total_frames, value=1)

    # Flight Shape Customization
    st.caption("Adjust Flight Direction & Shape:")
    col_a, col_b = st.columns(2)
    with col_a:
        horizontal_direction = st.slider("Direction (Left ◄ ► Right)", min_value=-int(width * 0.4), max_value=int(width * 0.4), value=0, step=5)
        apex_height_pct = st.slider("Apex Height", min_value=5, max_value=50, value=20, step=1)
    with col_b:
        curve_bend = st.slider("Curve (Draw ◄ ► Fade)", min_value=-int(width * 0.2), max_value=int(width * 0.2), value=0, step=5)
        flight_time_sec = st.slider("Tracer Duration (s)", min_value=0.5, max_value=3.0, value=1.5, step=0.1)

    if st.button("🚀 Render Custom Flight Tracer", type="primary", use_container_width=True):
        with st.spinner("Processing flight parabola & rendering video..."):
            flight_duration = int(fps * flight_time_sec)

            # Dynamic Path Calculation
            # Start Point
            p0 = np.array([cx, cy])

            # Landing Point (Target end location based on horizontal direction slider)
            landing_x = int(cx + horizontal_direction)
            landing_y = int(cy - (height * 0.35))
            p2 = np.array([landing_x, landing_y])

            # Apex Point (Midpoint height + Draw/Fade curve bend)
            mid_x = (cx + landing_x) / 2
            apex_x = int(mid_x + curve_bend)
            apex_y = int(cy - (height * (apex_height_pct / 100.0)))
            p1 = np.array([apex_x, apex_y])

            # Quadratic Bezier Curve Math
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

                if curr_idx >= (impact_frame - 1):
                    elapsed = curr_idx - (impact_frame - 1)
                    pts_count = min(elapsed + 1, len(curve_points))

                    if pts_count > 1:
                        active_pts = np.array(curve_points[:pts_count], dtype=np.int32)
                        
                        # Draw Neon Green Tracer Line
                        cv2.polylines(
                            f,
                            [active_pts],
                            isClosed=False,
                            color=(0, 255, 0),
                            thickness=5,
                            lineType=cv2.LINE_AA,
                        )
                        # Draw White Leading Edge Ball Head
                        cv2.circle(
                            f,
                            curve_points[pts_count - 1],
                            7,
                            (255, 255, 255),
                            -1,
                            cv2.LINE_AA,
                        )

                out.write(f)
                curr_idx += 1

            cap.release()
            out.release()

            # Transcode video for mobile web playback
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
