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

# Custom mobile layout styling
st.markdown("""
    <style>
    .block-container {
        padding-top: 1rem;
        padding-bottom: 1rem;
        max-width: 460px;
    }
    </style>
""", unsafe_allow_html=True)

st.title("⛳ Visual Golf Tracer")

uploaded_file = st.file_uploader("Upload Golf Swing", type=["mp4", "mov", "avi"])

if uploaded_file:
    # 1. Save uploaded video file
    if "video_path" not in st.session_state or st.session_state.get("file_name") != uploaded_file.name:
        tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
        tfile.write(uploaded_file.read())
        st.session_state.video_path = tfile.name
        st.session_state.file_name = uploaded_file.name

    video_path = st.session_state.video_path

    # Read video properties
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    # Convert video to base64 data URL so mobile HTML video element can play/scrub locally
    with open(video_path, "rb") as vf:
        video_bytes = vf.read()
    
    import base64
    b64_video = base64.b64encode(video_bytes).decode('utf-8')
    video_data_url = f"data:video/mp4;base64,{b64_video}"

    DISPLAY_WIDTH = 380
    aspect_ratio = height / width
    DISPLAY_HEIGHT = int(DISPLAY_WIDTH * aspect_ratio)

    # 2. NATIVE IPHONE-STYLE SCRUBBER & CANVAS (HTML5/JS)
    custom_scrubber_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{
                margin: 0;
                font-family: -apple-system, BlinkMacSystemFont, sans-serif;
                background: transparent;
                display: flex;
                flex-direction: column;
                align-items: center;
            }}
            .video-container {{
                position: relative;
                width: {DISPLAY_WIDTH}px;
                height: {DISPLAY_HEIGHT}px;
                border-radius: 12px;
                overflow: hidden;
                background: #000;
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            }}
            video {{
                width: 100%;
                height: 100%;
                object-fit: contain;
                display: block;
            }}
            canvas {{
                position: absolute;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                cursor: crosshair;
            }}
            .controls {{
                width: {DISPLAY_WIDTH}px;
                margin-top: 10px;
                display: flex;
                flex-direction: column;
                gap: 6px;
            }}
            .slider-header {{
                display: flex;
                justify-content: space-between;
                font-size: 13px;
                font-weight: 600;
                color: #444;
            }}
            input[type=range] {{
                width: 100%;
                accent-color: #007AFF;
                height: 6px;
                cursor: pointer;
            }}
        </style>
    </head>
    <body>

        <!-- VIDEO FRAME DISPLAY -->
        <div class="video-container">
            <video id="vPlayer" playsinline muted preload="auto">
                <source src="{video_data_url}" type="video/mp4">
            </video>
            <canvas id="overlayCanvas" width="{DISPLAY_WIDTH}" height="{DISPLAY_HEIGHT}"></canvas>
        </div>

        <!-- SMOOTH SLIDER BELOW VIDEO FRAME -->
        <div class="controls">
            <div class="slider-header">
                <span>Scrub Frame (iPhone Smooth)</span>
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
            const origWidth = {width};
            const origHeight = {height};
            const dispWidth = {DISPLAY_WIDTH};

            let selectedX = null;
            let selectedY = null;

            // Wait for video metadata to load
            video.addEventListener('loadedmetadata', () => {{
                video.currentTime = 0;
            }});

            // 60 FPS SMOOTH SCRUBBING (Pure Browser JS)
            scrubber.addEventListener('input', (e) => {{
                const frameIdx = parseInt(e.target.value);
                const targetTime = frameIdx / fps;
                video.currentTime = targetTime;
                frameText.innerText = 'Frame ' + (frameIdx + 1) + ' / ' + totalFrames;
            }});

            // TAP / CLICK ON GOLF BALL
            canvas.addEventListener('click', (e) => {{
                const rect = canvas.getBoundingClientRect();
                selectedX = e.clientX - rect.left;
                selectedY = e.clientY - rect.top;

                // Scale display coords to video resolution
                const scale = origWidth / dispWidth;
                const realX = Math.round(selectedX * scale);
                const realY = Math.round(selectedY * scale);
                const currentFrame = parseInt(scrubber.value) + 1;

                drawTarget(selectedX, selectedY);

                // Update hidden inputs in Streamlit UI
                window.parent.postMessage({{
                    type: 'GOLF_BALL_SELECTED',
                    x: realX,
                    y: realY,
                    frame: currentFrame
                }}, '*');
            }});

            function drawTarget(x, y) {{
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                
                // Red Circle Target
                ctx.beginPath();
                ctx.arc(x, y, 10, 0, 2 * Math.PI);
                ctx.strokeStyle = '#FF3B30';
                ctx.lineWidth = 3;
                ctx.stroke();

                // Crosshairs
                ctx.beginPath();
                ctx.moveTo(x - 16, y);
                ctx.lineTo(x + 16, y);
                ctx.moveTo(x, y - 16);
                ctx.lineTo(x, y + 16);
                ctx.strokeStyle = '#FF3B30';
                ctx.lineWidth = 2;
                ctx.stroke();

                // Center White Dot
                ctx.beginPath();
                ctx.arc(x, y, 3, 0, 2 * Math.PI);
                ctx.fillStyle = '#FFFFFF';
                ctx.fill();
            }}
        </script>
    </body>
    </html>
    """

    # Embed HTML JS Scrubber
    components.html(custom_scrubber_html, height=DISPLAY_HEIGHT + 70)

    # 3. MANUAL / CONFIRMATION INPUTS (Guarantees Render Button is NEVER missing)
    st.markdown("---")
    st.subheader("🎯 Target Settings")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        cx = st.number_input("Target X", min_value=0, max_value=width, value=int(width * 0.5))
    with col2:
        cy = st.number_input("Target Y", min_value=0, max_value=height, value=int(height * 0.7))
    with col3:
        impact_frame = st.number_input("Impact Frame", min_value=1, max_value=total_frames, value=1)

    # 4. ALWAYS-VISIBLE RENDER BUTTON
    if st.button("🚀 Render Flight Tracer", type="primary", use_container_width=True):
        with st.spinner("Calculating flight parabola & rendering output..."):
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

            # Transcode with ffmpeg for browser playback
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
