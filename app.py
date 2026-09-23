import cv2
import numpy as np
import streamlit as st
import tempfile
import os

def generate_bezier_points(p0, p1, p2, num_points=60):
    """Calculates a smooth quadratic Bezier curve from start to finish."""
    t = np.linspace(0, 1, num_points)
    curve = []
    for ti in t:
        # B(t) = (1-t)^2 * P0 + 2(1-t)t * P1 + t^2 * P2
        point = (1 - ti)**2 * p0 + 2 * (1 - ti) * ti * p1 + ti**2 * p2
        curve.append((int(point[0]), int(point[1])))
    return curve

def process_video(video_path, impact_frame, flight_duration, impact_xy, apex_xy, landing_xy, line_color, line_thickness):
    cap = cv2.VideoCapture(video_path)
    
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # Prepare temporary output file
    temp_output = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(temp_output.name, fourcc, fps, (width, height))

    # Pre-calculate full shot trajectory points
    curve_points = generate_bezier_points(impact_xy, apex_xy, landing_xy, num_points=flight_duration)

    frame_idx = 0
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        # Render tracer ONLY after impact occurs
        if frame_idx >= impact_frame:
            # Determine how much of the line to reveal based on current frame
            elapsed_frames = frame_idx - impact_frame
            points_to_draw = min(elapsed_frames + 1, len(curve_points))

            if points_to_draw > 1:
                active_pts = np.array(curve_points[:points_to_draw], dtype=np.int32)
                
                # Draw main tracer trajectory
                cv2.polylines(frame, [active_pts], isClosed=False, color=line_color, thickness=line_thickness, lineType=cv2.LINE_AA)
                
                # Draw leading ball head at the front of the trace
                current_ball_pos = curve_points[points_to_draw - 1]
                cv2.circle(frame, current_ball_pos, line_thickness + 2, (255, 255, 255), -1)

                # Add APEX indicator once the ball reaches peak trajectory
                apex_index = len(curve_points) // 2
                if points_to_draw >= apex_index:
                    apex_pt = curve_points[apex_index]
                    cv2.circle(frame, apex_pt, 6, (0, 255, 255), -1)
                    cv2.putText(frame, "APEX", (apex_pt[0] - 20, apex_pt[1] - 15), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)

        out.write(frame)
        frame_idx += 1

    cap.release()
    out.release()
    return temp_output.name

# ----------------- STREAMLIT UI -----------------
st.title("⛳ Custom Golf Shot Tracer")

uploaded_file = st.file_uploader("Upload Golf Swing Video", type=["mp4", "mov"])

if uploaded_file:
    tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    tfile.write(uploaded_file.read())
    
    cap = cv2.VideoCapture(tfile.name)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    st.subheader("1. Setup Timing & Coordinates")
    
    # Timing Sliders
    impact_frame = st.slider("Impact Frame Number", 0, total_frames, int(total_frames * 0.35))
    flight_duration = st.slider("Flight Duration (Frames)", 10, 120, 45)
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Impact Location (X, Y)**")
        impact_x = st.slider("Impact X", 0, width, int(width * 0.5))
        impact_y = st.slider("Impact Y", 0, height, int(height * 0.75))

        st.markdown("**Apex Location (X, Y)**")
        apex_x = st.slider("Apex X", 0, width, int(width * 0.25))
        apex_y = st.slider("Apex Y", 0, height, int(height * 0.25))

    with col2:
        st.markdown("**Landing Location (X, Y)**")
        landing_x = st.slider("Landing X", 0, width, int(width * 0.35))
        landing_y = st.slider("Landing Y", 0, height, int(height * 0.45))
        
        line_thickness = st.slider("Tracer Thickness", 1, 10, 4)

    # Convert RGB color picker to BGR for OpenCV
    color_hex = st.color_picker("Tracer Color", "#00FF00")
    bgr_color = tuple(int(color_hex.lstrip('#')[i:i+2], 16) for i in (4, 2, 0))

    if st.button("Generate Traced Video"):
        with st.spinner("Processing trajectory..."):
            output_path = process_video(
                tfile.name,
                impact_frame,
                flight_duration,
                (impact_x, impact_y),
                (apex_x, apex_y),
                (landing_x, landing_y),
                bgr_color,
                line_thickness
            )
            st.video(output_path)
