import os
import math
import ffmpeg

def generate_ass_subtitles(words_data, output_ass_path, highlight_start, highlight_end):
    """
    Generates an Advanced SubStation Alpha (.ass) file with TikTok style subtitles.
    Only includes words within the highlight window.
    """
    # Filter words for this highlight
    clip_words = []
    for w in words_data:
        # Give a small 0.2s margin
        if w['end'] >= highlight_start - 0.2 and w['start'] <= highlight_end + 0.2:
            # Adjust timestamps relative to the start of the clip
            clip_words.append({
                'word': w['word'].strip(),
                'start': max(0.0, w['start'] - highlight_start),
                'end': max(0.1, w['end'] - highlight_start)
            })

    # ASS Header
    ass_content = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 1

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: TikTokStyle,Segoe UI Black,110,&H00FFFFFF,&H0000FF00,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,10,0,2,10,10,50,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    def format_time(seconds):
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        cs = int((s - int(s)) * 100) # Centiseconds
        return f"{h}:{m:02d}:{int(s):02d}.{cs:02d}"

    # Group words into chunks of max 3 words
    chunks = []
    phrases = []
    phrase = []
    
    for i, w in enumerate(clip_words):
        # Cap single word duration to max 1.0s to prevent Whisper stretching timestamps into silence
        if w['end'] - w['start'] > 1.0:
            w['end'] = w['start'] + 1.0
            
        # If there's a large gap (e.g., >0.5s) between this word and the last, break the phrase
        if phrase and (w['start'] - phrase[-1]['end'] > 0.5):
            phrases.append(phrase)
            phrase = []
            
        phrase.append(w)
        
        # Break phrase if it gets too long or hits punctuation
        if len(phrase) >= 5 or w['word'].endswith(('.', '!', '?')):
            phrases.append(phrase)
            phrase = []
            
    if phrase:
        phrases.append(phrase)

    for p in phrases:
        current_chunk = []
        for j, word in enumerate(p):
            current_chunk.append(word)
            if len(current_chunk) >= 3 or j == len(p) - 1:
                chunks.append(current_chunk)
                current_chunk = []

    # Generate ASS events
    for chunk in chunks:
        chunk_start = format_time(chunk[0]['start'])
        chunk_end = format_time(chunk[-1]['end'])
        
        text = " ".join([w['word'] for w in chunk]).strip()
        ass_content += f"Dialogue: 0,{chunk_start},{chunk_end},TikTokStyle,,0,0,0,,{text}\n"

    with open(output_ass_path, 'w', encoding='utf-8') as f:
        f.write(ass_content)
        
    print(f"Generated ASS subtitle file: {output_ass_path}")

def burn_subtitles(video_path, ass_path, output_path):
    """
    Burns the .ass subtitles into the video using ffmpeg.
    """
    import os
    # Use relative paths for the ASS filter to avoid absolute path escaping hell on Windows
    rel_ass_path = os.path.relpath(ass_path, os.getcwd())
    ass_path_escaped = rel_ass_path.replace('\\', '/')
    
    print(f"Burning subtitles into {output_path}...")
    stream = ffmpeg.input(video_path)
    video = stream.video.filter('ass', ass_path_escaped)
    audio = stream.audio
    
    try:
        out = ffmpeg.output(video, audio, output_path, vcodec='libx264', acodec='aac', strict='experimental')
        out.run(overwrite_output=True, quiet=True)
    except ffmpeg.Error as e:
        print("FFMPEG ERROR STDOUT:", e.stdout.decode('utf8', errors='ignore') if e.stdout else "None")
        print("FFMPEG ERROR STDERR:", e.stderr.decode('utf8', errors='ignore') if e.stderr else "None")
        raise RuntimeError(f"FFmpeg failed: {e.stderr.decode('utf8', errors='ignore') if e.stderr else 'Unknown error'}")
        
    print(f"Final video saved to {output_path}")
