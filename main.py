import os
import argparse
from dotenv import load_dotenv

from transcriber import transcribe_video
from analyzer import find_highlights
from video_editor import format_video
from subtitles import generate_ass_subtitles, burn_subtitles

def get_next_video_number(output_dir: str) -> int:
    max_num = 0
    if os.path.exists(output_dir):
        for f in os.listdir(output_dir):
            if f.endswith(".mp4"):
                name = os.path.splitext(f)[0]
                if name.isdigit():
                    num = int(name)
                    if num > max_num:
                        max_num = num
    return max_num + 1

def get_subclips(words_data: list, start_time: float, end_time: float, max_silence: float = 2.0) -> list:
    clip_words = [w for w in words_data if w['start'] >= start_time - 0.5 and w['end'] <= end_time + 0.5]
    if not clip_words:
        return [(start_time, end_time)]
        
    subclips = []
    current_start = start_time
    
    for i in range(len(clip_words) - 1):
        w1 = clip_words[i]
        w2 = clip_words[i+1]
        
        # If silence between words is greater than max_silence, cut it out
        if w2['start'] - w1['end'] > max_silence:
            subclips.append((current_start, w1['end'] + 0.5))
            current_start = max(w1['end'] + 0.5, w2['start'] - 0.3)
            
    subclips.append((current_start, end_time))
    
    # Filter out empty or negative duration clips
    valid_subclips = [(s, e) for s, e in subclips if e - s > 0.1]
    
    if not valid_subclips:
        return [(start_time, end_time)]
        
    return valid_subclips

def process_video(video_path: str, output_dir: str, logo_path: str = None):
    print("=== TikTok AI Video Generator ===")
    
    # 1. Transcribe (Generate subtitles data)
    print("\n--- Step 1: Transcription ---")
    transcript, words_data = transcribe_video(video_path, model_size="large-v3")
    
    # 2. Analyze (Find highlights)
    print("\n--- Step 2: AI Analysis ---")
    highlights = find_highlights(words_data)
    
    if not highlights:
        print("No highlights found by AI.")
        raise ValueError("AI could not find interesting moments in this video. It might be too short or lack dialogue.")
        
    os.makedirs(output_dir, exist_ok=True)
    generated_files = []
    
    next_num = get_next_video_number(output_dir)
    
    # 3. Process each highlight
    print("\n--- Step 3: Video Processing ---")
    for i, h in enumerate(highlights):
        print(f"\nProcessing highlight {i+1}: '{h['title']}'")
        
        temp_cropped_path = os.path.join(output_dir, f"temp_cropped_{i}.mp4")
        ass_path = os.path.join(output_dir, f"subs_{i}.ass")
        final_output_path = os.path.join(output_dir, f"{next_num}.mp4")
        
        subclips = get_subclips(words_data, h['start'], h['end'])
        
        # Crop and Format
        print(f"Formatting clip {i+1} / {len(highlights)} (Blur background, vertical layout, jump cuts)...")
        format_video(video_path, temp_cropped_path, subclips, logo_path=logo_path)
        
        # 3b. Subtitles
        print("Generating subtitles...")
        generate_ass_subtitles(words_data, ass_path, subclips)
        burn_subtitles(temp_cropped_path, ass_path, final_output_path)
        
        # Cleanup temp file
        if os.path.exists(temp_cropped_path):
            try:
                os.remove(temp_cropped_path)
            except Exception as e:
                print(f"Could not remove temp file: {e}")
                
        # Cleanup ASS file
        if os.path.exists(ass_path):
            try:
                os.remove(ass_path)
            except Exception as e:
                print(f"Could not remove ASS file: {e}")
                
        generated_files.append(final_output_path)
        next_num += 1

            
    print("\n=== All Done! ===")
    return generated_files

if __name__ == "__main__":
    load_dotenv()
    
    parser = argparse.ArgumentParser(description="AI TikTok Video Generator")
    parser.add_argument("video_path", help="Path to the input video file")
    parser.add_argument("--output", default="output", help="Output directory")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.video_path):
        print(f"Error: Video file '{args.video_path}' not found.")
        exit(1)
        
    process_video(args.video_path, args.output)
