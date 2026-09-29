import os
import json
import httpx
from pydantic import BaseModel
from typing import List

class Highlight(BaseModel):
    title: str
    start_time: float
    end_time: float
    explanation: str

class HighlightResponse(BaseModel):
    highlights: List[Highlight]

def prepare_transcript_for_llm(words_data: List[dict]) -> str:
    text_with_timestamps = ""
    current_chunk = ""
    chunk_start = 0.0
    
    for word in words_data:
        if current_chunk == "":
            chunk_start = word['start']
        
        current_chunk += word['word']
        
        if word['end'] - chunk_start > 10.0:
            text_with_timestamps += f"[{chunk_start:.1f}s] {current_chunk.strip()}\n"
            current_chunk = ""
            
    if current_chunk:
        text_with_timestamps += f"[{chunk_start:.1f}s] {current_chunk.strip()}\n"
        
    return text_with_timestamps

def snap_to_sentence_boundaries(start_t: float, end_t: float, words_data: List[dict]) -> tuple[float, float]:
    if not words_data:
        return start_t, end_t
        
    # Find word closest to start_t
    start_idx = 0
    min_start_diff = float('inf')
    for i, w in enumerate(words_data):
        diff = abs(w['start'] - start_t)
        if diff < min_start_diff:
            min_start_diff = diff
            start_idx = i
            
    # Find word closest to end_t
    end_idx = len(words_data) - 1
    min_end_diff = float('inf')
    for i, w in enumerate(words_data):
        diff = abs(w['end'] - end_t)
        if diff < min_end_diff:
            min_end_diff = diff
            end_idx = i
            
    # Snap start to the beginning of the sentence if possible
    new_start_idx = start_idx
    for i in range(start_idx - 1, max(-1, start_idx - 15), -1):
        if words_data[i]['word'].strip().endswith(('.', '!', '?')):
            new_start_idx = i + 1
            break
            
    if new_start_idx >= len(words_data):
        new_start_idx = start_idx
        
    # Snap end to the end of the sentence if possible
    new_end_idx = end_idx
    for i in range(end_idx, min(len(words_data), end_idx + 15)):
        if words_data[i]['word'].strip().endswith(('.', '!', '?')):
            new_end_idx = i
            break
            
    snapped_start = max(0.0, words_data[new_start_idx]['start'] - 0.3)
    snapped_end = words_data[new_end_idx]['end'] + 0.5
    
    return snapped_start, snapped_end

def find_highlights(words_data: List[dict], model_name: str = "llama3.1") -> List[dict]:
    """
    Uses local Ollama API to analyze the transcript without needing an API key.
    Requires Ollama to be running with the specified model.
    """
    transcript_with_timestamps = prepare_transcript_for_llm(words_data)
    
    # Check if transcript is long enough
    if not words_data or len(words_data) < 10:
        print("Transcript is too short to find highlights.")
        return []
        
    prompt = f"""
You are a genius-level viral video editor for TikTok, Shorts, and Reels. 
Your goal is to extract the absolute BEST, most engaging, and viral segments from the provided video transcript.
The transcript contains timestamp markers (e.g., [10.5s]).

What makes a segment viral?
- A powerful "hook" in the first 3 seconds (a controversial statement, a loud reaction, a crazy reveal, or an emotional peak).
- High tension, intense arguments, deep philosophical quotes, or extremely funny/awkward moments.
- A satisfying conclusion or a dramatic cliffhanger that makes people want to watch it again or argue in the comments.

Find exactly 3 to 6 distinct viral highlights.

STRICT RULES:
1. LENGTH: Each highlight MUST be between 25 and 60 seconds long. TikToks need enough time to build context, but must not exceed 1 minute.
2. CONTENT: Focus ONLY on segments with dense, engaging dialogue. Avoid segments that are mostly silence or boring exposition.
3. CONTEXT: The clip must make sense on its own. Start the clip slightly before the main action so the viewer understands what's happening.
4. ACCURACY: You MUST ONLY return the exact moments present in the text. DO NOT invent timestamps.

Return ONLY a valid JSON object. No markdown, no explanations outside the JSON. Format exactly like this:
{{
  "highlights": [
    {{
      "title": "A highly clickable, clickbait-style title",
      "start_time": 10.5,
      "end_time": 45.2,
      "explanation": "Why this will go viral and get high retention"
    }}
  ]
}}

Transcript:
{transcript_with_timestamps}
"""

    print(f"Analyzing transcript with local Ollama AI ({model_name}) to find highlights...")
    
    try:
        response = httpx.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model_name,
                "prompt": prompt,
                "format": "json",
                "stream": False,
                "options": {
                    "num_ctx": 16384
                }
            },
            timeout=300.0
        )
        response.raise_for_status()
    except Exception as e:
        print(f"Error connecting to Ollama: {e}")
        return []
        
    try:
        text = response.json()["response"].strip()
        # Clean markdown if present
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        
        # Sometimes Ollama returns empty string or just `{}` 
        if not text:
            print("Ollama returned empty response.")
            return []
            
        result_json = json.loads(text)
        
        result = []
        for h in result_json.get("highlights", []):
            start_t = float(h.get("start_time", 0))
            end_t = float(h.get("end_time", 0))
            if start_t > 0 and end_t > start_t:
                # Snap boundaries and add padding
                start_t, end_t = snap_to_sentence_boundaries(start_t, end_t, words_data)
                
                # Strict limit: maximum 60 seconds per clip
                if end_t - start_t > 60.0:
                    end_t = start_t + 60.0
                
                # Protection against micro-clips
                if end_t - start_t < 15.0:
                    continue
                    
                result.append({
                    "title": h.get("title", "Highlight"),
                    "start": start_t,
                    "end": end_t,
                    "explanation": h.get("explanation", "")
                })
        
        # Protection against duplicates and overlapping moments
        result.sort(key=lambda x: x["start"])
        filtered_result = []
        
        for h in result:
            if not filtered_result:
                filtered_result.append(h)
                print(f"Found highlight: '{h['title']}' ({h['start']}s - {h['end']}s)")
            else:
                last_h = filtered_result[-1]
                # If the new moment starts before the old one ends (+ 5 sec buffer), skip it
                if h["start"] < last_h["end"] + 5.0:
                    print(f"Skipping overlapping highlight: '{h['title']}'")
                    continue
                filtered_result.append(h)
                print(f"Found highlight: '{h['title']}' ({h['start']}s - {h['end']}s)")
            
        return filtered_result
    except Exception as e:
        print(f"Failed to parse AI response: {e}")
        print("Raw response:", response.json().get("response"))
        return []
