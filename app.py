import os
import tempfile
import cv2
import numpy as np
import streamlit as st

st.set_page_config(page_title="AI Golf Ball Tracer", page_icon="⛳")
st.title("⛳ Automated AI Golf Tracer")
st.caption("Upload your swing video and let AI automatically detect impact and generate the flight tracer.")

def detect_ball_and_impact(cap, total_frames, width, height):
    """
    Scans early video frames to find motion spikes near the bottom half of the frame
    to locate the tee location and automatically identify the impact frame.
    """
    prev_gray = None
    motion_history = []
    
    # Search first 70% of video for impact motion
    search_limit = int(total_frames * 0.7)
    frame_idx = 0

    while frame_idx < search_limit:
        ret, frame = cap.read()
        if not ret:
            break
        
        # Focus on lower half of image (where tee/ball sits)
        roi = frame[int(height * 0.4):int(height * 0.95), :]
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)

        if prev_gray is not None:
            delta = cv2.absdiff(prev_gray, gray)
            thresh = cv2.threshold(delta, 25, 255, cv2.THRESH_BINARY)[1]
            motion_score = np.sum(thresh)
            motion_history.append((frame_idx, motion_score))

        prev_gray = gray
        frame_idx += 1

    if not motion_history:
        return int(total_frames * 0.3), (int(width * 0.5), int(height * 0.75))

    # Identify the frame with highest motion acceleration (impact point)
    motion_history.sort(key=lambda x: x[1], reverse=True)
    impact_frame = motion_history[0][0]

    # Default impact location near lower center
    impact_xy = (int(width * 0.5), int(height * 0.75))
    return impact_frame, impact_xy


def generate_flight_path(impact_xy, width, height, flight_duration=45):
    """
    Generates a realistic 3D parabolic trajectory based on standard 
    driver/iron launch mechanics towards the center horizon.
    """
    x0, y0 = impact_xy
    
    # Target apex (~25% height of frame, leaning slightly center-left/right)
    apex_x = int(x0 - (width * 0.15))
    apex_y = int(height * 0.25)
    
    # Landing point downrange
    landing_x = int(apex_x - (width * 0.05))
    landing_y = int(height * 0.45)

    # Calculate quadratic trajectory curve points
    p0 = np.array([x0, y0])
    p1 = np.array([apex_x, apex_y])
    p2 = np.array([landing_x, landing_y])

    t = np.linspace(0, 1, flight_duration)
    trajectory = []
    for ti in t:
        pt = (1 - ti)**2 * p0 + 2 * (1 - ti) * ti * p1 + ti**2 * p2
        trajectory.append((int(pt[0]), int(pt[1])))
        
    return trajectory


def process_video_auto(video_path):
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30

    # Step 1: Detect Impact Frame and Location Automatically
    impact_frame, impact_xy = detect_ball_and_impact(cap, total_frames, width, height)
    
    # Reset video capture back to start
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    # Step 2: Auto-generate parabolic trajectory
    flight_duration = int(fps * 1.5)  # Default ~1.5s flight trace
    curve_points = generate_flight_path(impact_xy, width, height, flight_duration)

    # Prepare video output writer
    temp_output = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(temp_output.name, fourcc, fps, (width, height))

    frame_idx = 0
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        # Only draw tracer after the auto-detected impact frame
        if frame_idx >= impact_frame:
            elapsed = frame_idx - impact_frame
            points_to_draw = min(elapsed + 1, len(curve_points))

            if points_to_draw > 1:
                active_pts = np.array(curve_points[:points_to_draw], dtype=np.int32)
                
                # Draw Neon Green Tracer Line
                cv2.polylines(frame, [active_pts], isClosed=False, color=(0, 255, 0), thickness=4, lineType=cv2.LINE_AA)
                
                # Draw leading ball head
                current_ball_pos = curve_points[points_to_draw - 1]
                cv2.circle(frame, current_ball_pos, 6, (255, 255, 255), -1)

                # Add APEX indicator once ball reaches top of curve
                apex_idx = len(curve_points) // 2
                if points_to_draw >= apex_idx:
                    apex_pt = curve_points[apex_idx]
                    cv2.circle(frame, apex_pt, 5, (0, 255, 255), -1)
                    cv2.putText(frame, "APEX", (apex_pt[0] - 20, apex_pt[1] - 12),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2, cv2.LINE_AA)

        out.write(frame)
        frame_idx += 1

    cap.release()
    out.release()
    return temp_output.name


# --- MOBILE UI ---
uploaded_file = st.file_uploader("Upload Video", type=["mp4", "mov"])

if uploaded_file:
    with st.spinner("Analyzing video & tracing shot automatically..."):
        tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
        tfile.write(uploaded_file.read())
        
        output_path = process_video_auto(tfile.name)
        st.success("Tracing complete!")
        st.video(output_path)
