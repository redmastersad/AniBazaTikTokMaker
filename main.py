import os
import argparse
from dotenv import load_dotenv

from transcriber import transcribe_video
from analyzer import find_highlights
from video_editor import format_video
from subtitles import generate_ass_subtitles, burn_subtitles

def process_video(video_path: str, output_dir: str, logo_path: str = None, language: str = "ru"):
    print("=== TikTok AI Video Generator ===")
    
    # 1. Transcribe (Generate subtitles data)
    print("\n--- Step 1: Transcription ---")
    transcript, words_data = transcribe_video(video_path, model_size="large-v3", language=language)
    
    # 2. Analyze (Find highlights)
    print("\n--- Step 2: AI Analysis ---")
    highlights = find_highlights(words_data)
    
    if not highlights:
        print("No highlights found by AI.")
        raise ValueError("AI could not find interesting moments in this video. It might be too short or lack dialogue.")
        
    os.makedirs(output_dir, exist_ok=True)
    generated_files = []
    
    # 3. Process each highlight
    print("\n--- Step 3: Video Processing ---")
    for i, h in enumerate(highlights):
        print(f"\nProcessing highlight {i+1}: '{h['title']}'")
        
        title_clean = "".join([c if c.isalnum() else "_" for c in h['title']])
        temp_cropped_path = os.path.join(output_dir, f"temp_cropped_{i}.mp4")
        ass_path = os.path.join(output_dir, f"subs_{i}.ass")
        final_output_path = os.path.join(output_dir, f"tiktok_{i}_{title_clean}.mp4")
        
        # Crop and Format
        print(f"Formatting clip {i+1} / {len(highlights)} (Blur background, vertical layout)...")
        format_video(video_path, temp_cropped_path, h['start'], h['end'], logo_path=logo_path)
        
        # 3b. Subtitles
        print("Generating subtitles...")
        generate_ass_subtitles(words_data, ass_path, h['start'], h['end'])
        burn_subtitles(temp_cropped_path, ass_path, final_output_path)
        
        # Cleanup temp file
        if os.path.exists(temp_cropped_path):
            try:
                os.remove(temp_cropped_path)
            except Exception as e:
                print(f"Could not remove temp file: {e}")
                
        generated_files.append(final_output_path)

            
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
