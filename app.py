import base64
import os
import subprocess
import tempfile
import cv2
import numpy as np
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="Golf Tracer (3-Tap)", 
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

st.title("⛳ 3-Tap Golf Tracer")

uploaded_file = st.file_uploader("Upload Golf Swing", type=["mp4", "mov", "avi"])

if uploaded_file:
    tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    tfile.write(uploaded_file.read())
    video_path = tfile.name

    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    DISPLAY_WIDTH = 360
    aspect_ratio = height / width
    DISPLAY_HEIGHT = int(DISPLAY_WIDTH * aspect_ratio)

    with open(video_path, "rb") as vf:
        video_bytes = vf.read()
    
    b64_video = base64.b64encode(video_bytes).decode('utf-8')
    video_data_url = f"data:video/mp4;base64,{b64_video}"

    # HTML Canvas with 3-Point Sequential Tap
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
            .tap-status {{ font-size: 13px; font-weight: 700; color: #007AFF; text-align: center; margin-top: 4px; }}
            input[type=range] {{ width: 100%; accent-color: #007AFF; height: 28px; cursor: pointer; }}
            .reset-btn {{ background: #e5e5ea; border: none; padding: 6px 12px; border-radius: 6px; font-size: 12px; font-weight: 600; cursor: pointer; align-self: center; }}
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
            <div id="tapStatus" class="tap-status">Tap 1/3: Select START / IMPACT point</div>
            <button class="reset-btn" onclick="resetPoints()">Reset Points</button>
        </div>

        <script>
            const video = document.getElementById('vPlayer');
            const scrubber = document.getElementById('scrubber');
            const frameText = document.getElementById('frameText');
            const tapStatus = document.getElementById('tapStatus');
            const canvas = document.getElementById('overlayCanvas');
            const ctx = canvas.getContext('2d');

            const totalFrames = {total_frames};
            const fps = {fps};
            const scale = {width} / {DISPLAY_WIDTH};

            let points = [];

            video.load();
            video.currentTime = 0;

            scrubber.addEventListener('input', (e) => {{
                const frameIdx = parseInt(e.target.value);
                video.currentTime = frameIdx / fps;
                frameText.innerText = 'Frame ' + (frameIdx + 1) + ' / ' + totalFrames;
            }});

            canvas.addEventListener('pointerdown', (e) => {{
                if (points.length >= 3) return;

                const rect = canvas.getBoundingClientRect();
                const x = e.clientX - rect.left;
                const y = e.clientY - rect.top;

                // Scale to full video dimensions
                const realX = Math.round(x * scale);
                const realY = Math.round(y * scale);

                points.push({{ dispX: x, dispY: y, realX: realX, realY: realY }});
                redraw();
                updateStatus();
            }});

            function resetPoints() {{
                points = [];
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                updateStatus();
            }}

            function updateStatus() {{
                if (points.length === 0) {{
                    tapStatus.innerText = "Tap 1/3: Select START / IMPACT point";
                    tapStatus.style.color = "#007AFF";
                }} else if (points.length === 1) {{
                    tapStatus.innerText = "Tap 2/3: Select APEX (highest) point";
                    tapStatus.style.color = "#FF9500";
                }} else if (points.length === 2) {{
                    tapStatus.innerText = "Tap 3/3: Select LANDING / END point";
                    tapStatus.style.color = "#34C759";
                }} else {{
                    tapStatus.innerText = "✅ All 3 Points Set! Scroll down to render.";
                    tapStatus.style.color = "#34C759";
                }}
            }}

            function redraw() {{
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                
                const colors = ['#007AFF', '#FF9500', '#34C759'];
                const labels = ['1: Start', '2: Apex', '3: End'];

                // Draw Dots
                points.forEach((p, idx) => {{
                    ctx.beginPath();
                    ctx.arc(p.dispX, p.dispY, 7, 0, 2 * Math.PI);
                    ctx.fillStyle = colors[idx];
                    ctx.fill();
                    ctx.lineWidth = 2;
                    ctx.strokeStyle = '#FFFFFF';
                    ctx.stroke();

                    ctx.font = '11px sans-serif';
                    ctx.fillStyle = '#FFFFFF';
                    ctx.fillText(labels[idx], p.dispX + 10, p.dispY + 4);
                }});

                // Draw preview curve if all 3 points selected
                if (points.length === 3) {{
                    ctx.beginPath();
                    ctx.moveTo(points[0].dispX, points[0].dispY);
                    ctx.quadraticCurveTo(points[1].dispX, points[1].dispY, points[2].dispX, points[2].dispY);
                    ctx.strokeStyle = '#34C759';
                    ctx.lineWidth = 3;
                    ctx.setLineDash([4, 4]);
                    ctx.stroke();
                    ctx.setLineDash([]);
                }}
            }}
        </script>
    </body>
    </html>
    """

    components.html(custom_scrubber_html, height=DISPLAY_HEIGHT + 115)

    st.markdown("---")
    st.subheader("⚙️ Render Settings")

    col1, col2 = st.columns(2)
    with col1:
        impact_frame = st.number_input("Impact Frame", min_value=1, max_value=total_frames, value=60)
    with col2:
        tracer_speed = st.slider("Flight Duration (sec)", min_value=0.5, max_value=3.0, value=1.5, step=0.1)

    # Coords Input fallback / fine tuning
    st.caption("Coordinate Inputs (Auto-filled by tapping above):")
    c1, c2, c3 = st.columns(3)
    with c1:
        x0 = st.number_input("Start X", value=int(width * 0.5))
        y0 = st.number_input("Start Y", value=int(height * 0.75))
    with c2:
        x1 = st.number_input("Apex X", value=int(width * 0.45))
        y1 = st.number_input("Apex Y", value=int(height * 0.25))
    with c3:
        x2 = st.number_input("End X", value=int(width * 0.42))
        y2 = st.number_input("End Y", value=int(height * 0.40))

    if st.button("🚀 Render 3-Tap Tracer", type="primary", use_container_width=True):
        with st.spinner("Drawing parabolic trajectory & rendering..."):
            flight_duration = int(fps * tracer_speed)

            p0 = np.array([x0, y0])
            p1 = np.array([x1, y1])
            p2 = np.array([x2, y2])

            # Quadratic Bezier fit across 3 points
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
                        
                        # Solid Tracer Line
                        cv2.polylines(
                            f,
                            [active_pts],
                            isClosed=False,
                            color=(0, 255, 0),
                            thickness=5,
                            lineType=cv2.LINE_AA,
                        )
                        # Ball Head
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
