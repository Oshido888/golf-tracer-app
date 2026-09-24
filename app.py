import base64
import io
import os
import subprocess
import tempfile
import cv2
import numpy as np
from PIL import Image
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="Golf Tracer", 
    page_icon="⛳",
    layout="centered"
)

# CSS for compact layout
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
    # Save uploaded video
    tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    tfile.write(uploaded_file.read())
    video_path = tfile.name

    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    # Extract & downscale frames to JPEG strings for client-side JS scrubbing
    DISPLAY_WIDTH = 380
    aspect_ratio = height / width
    DISPLAY_HEIGHT = int(DISPLAY_WIDTH * aspect_ratio)

    frame_data_urls = []
    # Sample up to 100 frames evenly if video is long to save memory
    step = max(1, total_frames // 100)
    frame_indices = list(range(0, total_frames, step))

    for idx in frame_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if ret:
            frame_resized = cv2.resize(frame, (DISPLAY_WIDTH, DISPLAY_HEIGHT))
            _, buffer = cv2.imencode('.jpg', frame_resized, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            b64_str = base64.b64encode(buffer).decode('utf-8')
            frame_data_urls.append(f"data:image/jpeg;base64,{b64_str}")
    cap.release()

    # Pass frame array to JavaScript HTML Component
    js_frames = str(frame_data_urls)

    # HTML/JS Custom Scrubber Component
    custom_scrubber_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{
                margin: 0;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                background-color: transparent;
                display: flex;
                flex-direction: column;
                align-items: center;
            }}
            .canvas-container {{
                position: relative;
                width: {DISPLAY_WIDTH}px;
                height: {DISPLAY_HEIGHT}px;
                border-radius: 12px;
                overflow: hidden;
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                background: #000;
            }}
            #frameImg {{
                width: 100%;
                height: 100%;
                object-fit: contain;
                display: block;
            }}
            #targetCanvas {{
                position: absolute;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                cursor: crosshair;
            }}
            .controls {{
                width: {DISPLAY_WIDTH}px;
                margin-top: 12px;
                display: flex;
                flex-direction: column;
                gap: 6px;
            }}
            .slider-label {{
                font-size: 13px;
                color: #555;
                font-weight: 600;
                display: flex;
                justify-content: space-between;
            }}
            input[type=range] {{
                width: 100%;
                accent-color: #007AFF;
                cursor: pointer;
            }}
        </style>
    </head>
    <body>

        <!-- 1. VIDEO FRAME & TARGET CANVAS -->
        <div class="canvas-container">
            <img id="frameImg" src="{frame_data_urls[0]}" />
            <canvas id="targetCanvas" width="{DISPLAY_WIDTH}" height="{DISPLAY_HEIGHT}"></canvas>
        </div>

        <!-- 2. SLIDER CONTROL BELOW FRAME -->
        <div class="controls">
            <div class="slider-label">
                <span>Scrub Impact Frame</span>
                <span id="frameNum">Frame 1</span>
            </div>
            <input type="range" id="frameSlider" min="0" max="{len(frame_indices)-1}" value="0" step="1">
        </div>

        <script>
            const frames = {js_frames};
            const frameIndices = {frame_indices};
            const img = document.getElementById('frameImg');
            const slider = document.getElementById('frameSlider');
            const frameNumLabel = document.getElementById('frameNum');
            const canvas = document.getElementById('targetCanvas');
            const ctx = canvas.getContext('2d');

            let selectedX = null;
            let selectedY = null;

            // Instant Client-Side Frame Scrubbing (No Python Refresh)
            slider.addEventListener('input', (e) => {{
                const idx = parseInt(e.target.value);
                img.src = frames[idx];
                frameNumLabel.innerText = 'Frame ' + (frameIndices[idx] + 1);
            }});

            // Draw Target Marker on Click
            canvas.addEventListener('click', (e) => {{
                const rect = canvas.getBoundingClientRect();
                selectedX = e.clientX - rect.left;
                selectedY = e.clientY - rect.top;

                drawTarget(selectedX, selectedY);
                
                // Store click coordinates in parent window
                if (window.parent) {{
                    window.parent.postMessage({{
                        type: 'GOLF_BALL_TARGET',
                        x: selectedX,
                        y: selectedY,
                        frameIdx: frameIndices[parseInt(slider.value)] + 1
                    }}, '*');
                }}
            }});

            function drawTarget(x, y) {{
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                
                // Red Target Ring
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

                // Inner Dot
                ctx.beginPath();
                ctx.arc(x, y, 3, 0, 2 * Math.PI);
                ctx.fillStyle = '#FFFFFF';
                ctx.fill();
            }}
        </script>
    </body>
    </html>
    """

    # Embed HTML JS Component
    components.html(custom_scrubber_html, height=DISPLAY_HEIGHT + 75)

    # Form to accept inputs for rendering
    st.caption("Enter ball target coordinates manually or click above:")
    col1, col2, col3 = st.columns(3)
    with col1:
        cx_in = st.number_input("Target X", min_value=0, max_value=width, value=int(width*0.5))
    with col2:
        cy_in = st.number_input("Target Y", min_value=0, max_value=height, value=int(height*0.7))
    with col3:
        impact_frame_in = st.number_input("Impact Frame", min_value=1, max_value=total_frames, value=1)

    if st.button("🚀 Render Flight Tracer", type="primary", use_container_width=True):
        with st.spinner("Processing flight physics & video..."):
            flight_duration = int(fps * 1.5)
            apex_x = int(cx_in - (width * 0.12))
            apex_y = int(height * 0.22)
            landing_x = int(apex_x - (width * 0.05))
            landing_y = int(height * 0.45)

            p0 = np.array([cx_in, cy_in])
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

                if curr_idx >= (impact_frame_in - 1):
                    elapsed = curr_idx - (impact_frame_in - 1)
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
