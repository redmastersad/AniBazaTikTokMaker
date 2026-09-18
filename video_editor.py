import cv2
import mediapipe as mp
import ffmpeg
import os
import numpy as np

def get_average_face_x(video_path: str, start_time: float, end_time: float) -> float:
    """
    Analyzes the video segment and returns the average X coordinate of the anime face.
    Returns a value between 0.0 and 1.0 (relative to video width).
    """
    cascade_path = os.path.join(os.path.dirname(__file__), "lbpcascade_animeface.xml")
    if not os.path.exists(cascade_path):
        print("Anime face cascade not found, defaulting to center.")
        return 0.5
        
    face_cascade = cv2.CascadeClassifier(cascade_path)
    
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    
    # Seek to start time
    cap.set(cv2.CAP_PROP_POS_MSEC, start_time * 1000)
    
    face_xs = []
    
    current_time = start_time
    frame_skip = int(fps / 2) # Check 2 frames per second
    frames_processed = 0
    
    while cap.isOpened() and current_time <= end_time:
        ret, frame = cap.read()
        if not ret:
            break
            
        if frames_processed % frame_skip == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            # Detect anime faces
            faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(24, 24))
            
            if len(faces) > 0:
                # Take the largest face
                largest_face = max(faces, key=lambda rect: rect[2] * rect[3])
                x, y, w, h = largest_face
                face_center_x = x + (w / 2)
                
                # Normalize to 0.0 - 1.0
                width = frame.shape[1]
                face_xs.append(face_center_x / width)
        
        frames_processed += 1
        current_time = start_time + (frames_processed / fps)
        
    cap.release()
    
    if not face_xs:
        return 0.5 # Default to center if no face found
        
    return float(np.mean(face_xs))

def format_video(video_path: str, output_path: str, subclips: list, logo_path: str = None, music_path: str = None):
    """
    Creates a 9:16 TikTok video by concatenating subclips, placing the original 16:9 video in the center,
    and filling the background with a blurred, scaled version of the video.
    """
    probe = ffmpeg.probe(video_path)
    video_info = next(s for s in probe['streams'] if s['codec_type'] == 'video')
    orig_w = int(video_info['width'])
    orig_h = int(video_info['height'])
    
    target_w = orig_h
    target_h = int(target_w * 16 / 9)
    
    # Ensure they are even
    target_w -= target_w % 2
    target_h -= target_h % 2
    
    print(f"Formatting video to 9:16 (Resolution: {target_w}x{target_h}) with blurred background...")
    
    # Build concat streams
    streams = []
    for (start, end) in subclips:
        s = ffmpeg.input(video_path, ss=start, t=end - start)
        streams.append(s.video)
        streams.append(s.audio)
        
    if len(subclips) > 1:
        joined = ffmpeg.concat(*streams, v=1, a=1).node
        base_video = joined[0]
        audio = joined[1]
    else:
        base_video = streams[0]
        audio = streams[1]
    
    # Anti-copyright & Polish: Mirror video, advanced color grading, vignette, sharpen, and film grain
    vid_stream = (
        base_video
        .filter('hflip') # Mirroring (avoids copyright issues)
        .filter('eq', contrast=1.15, brightness=-0.02, saturation=1.3) # Deep contrast and saturated colors
        .filter('unsharp', 5, 5, 1.0, 5, 5, 0.0) # Light sharpening
        .filter('vignette') # Dark edges (focus on center)
        .filter('noise', alls=15, allf='t+u') # Film grain
        .split() # Split stream in two, otherwise ffmpeg will throw an error
    )
    
    # 1. Background: Scale to cover the height, crop to target width, and heavily blur
    bg = (
        vid_stream[0]
        .filter('scale', -1, target_h)
        .filter('crop', target_w, target_h)
        .filter('boxblur', 20, 5)
    )
    
    # 2. Foreground: Make it take up ~65% of the vertical space (zoomed in slightly)
    fg_h = int(target_h * 0.65)
    fg_h -= fg_h % 2 # Must be even
    
    fg = (
        vid_stream[1]
        .filter('scale', -1, fg_h)
        .filter('crop', target_w, fg_h)
    )
    
    # 3. Overlay foreground onto background in the center
    video = ffmpeg.overlay(bg, fg, x='(main_w-overlay_w)/2', y='(main_h-overlay_h)/2')
    
    # 4. Logo Overlay (if provided)
    if logo_path and os.path.exists(logo_path):
        logo = ffmpeg.input(logo_path)
        # Scale logo if it's too big (e.g. max width 700), keep aspect ratio
        logo = logo.filter('scale', 'min(700,iw)', '-1')
        # Overlay at the top center, y=80 for some padding
        video = ffmpeg.overlay(video, logo, x='(main_w-overlay_w)/2', y='80')
        
    # 5. Background Music (if provided)
    if music_path and os.path.exists(music_path):
        # -8dB as requested, looped indefinitely to match video length
        bg_music = ffmpeg.input(music_path, stream_loop=-1).audio.filter('volume', '-8dB')
        # Mix audio tracks. duration='first' ensures it stops when the main video audio stops.
        audio = ffmpeg.filter([audio, bg_music], 'amix', inputs=2, duration='first', dropout_transition=2)
    
    try:
        out = ffmpeg.output(video, audio, output_path, vcodec='libx264', acodec='aac', strict='experimental')
        out.run(overwrite_output=True, quiet=True)
    except ffmpeg.Error as e:
        print("FFMPEG FORMAT ERROR STDERR:", e.stderr.decode('utf8', errors='ignore') if e.stderr else "None")
        raise RuntimeError(f"FFmpeg format failed: {e.stderr.decode('utf8', errors='ignore') if e.stderr else 'Unknown error'}")
        
    print(f"Formatted video saved to {output_path}")
