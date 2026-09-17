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

def find_highlights(words_data: List[dict]) -> List[dict]:
    """
    Uses local Ollama API to analyze the transcript without needing an API key.
    Requires Ollama to be running with the 'llama3.2' model.
    """
    transcript_with_timestamps = prepare_transcript_for_llm(words_data)
    
    # Check if transcript is long enough
    if not words_data or len(words_data) < 10:
        print("Transcript is too short to find highlights.")
        return []
        
    prompt = f"""
You are an expert anime editor for TikTok and YouTube Shorts.
Your goal is to find the most epic, dramatic, action-packed, or highly emotional scenes from the following anime episode transcript.
The transcript contains timestamp markers (e.g., [10.5s]).
Find between 3 and 6 distinct highlights. It is very important that you find at least 3!
Each highlight must be between 25 and 60 seconds long. DO NOT select short boring clips. Focus ONLY on the climax, fights, or big reveals!
You MUST ONLY return the exact moments present in the text, using the provided timestamps. Do not invent new timestamps.

Return ONLY a valid JSON object without any markdown wrapping. It must exactly match this format:
{{
  "highlights": [
    {{
      "title": "A catchy title for the clip",
      "start_time": 10.5,
      "end_time": 45.2,
      "explanation": "Why this is viral"
    }}
  ]
}}

Transcript:
{transcript_with_timestamps}
"""

    print("Analyzing transcript with local Ollama AI to find highlights...")
    
    try:
        response = httpx.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "llama3.1",
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
                result.append({
                    "title": h.get("title", "Highlight"),
                    "start": start_t,
                    "end": end_t,
                    "explanation": h.get("explanation", "")
                })
                print(f"Found highlight: '{h.get('title')}' ({start_t}s - {end_t}s)")
            
        return result
    except Exception as e:
        print(f"Failed to parse AI response: {e}")
        print("Raw response:", response.json().get("response"))
        return []
