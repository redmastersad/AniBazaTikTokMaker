import os
import site

# Fix for missing Windows CUDA DLLs (cublas64_12.dll)
try:
    for sp in site.getsitepackages():
        cublas = os.path.join(sp, "nvidia", "cublas", "bin")
        cudnn = os.path.join(sp, "nvidia", "cudnn", "bin")
        if os.path.exists(cublas):
            os.environ["PATH"] = cublas + os.pathsep + os.environ.get("PATH", "")
            os.add_dll_directory(cublas)
        if os.path.exists(cudnn):
            os.environ["PATH"] = cudnn + os.pathsep + os.environ.get("PATH", "")
            os.add_dll_directory(cudnn)
except Exception:
    pass

from faster_whisper import WhisperModel

def transcribe_video(video_path: str, model_size: str = "large-v3"):
    """
    Transcribes a video file and returns segments with word-level timestamps.
    """
    print(f"Loading faster-whisper model '{model_size}'...")
    try:
        model = WhisperModel(model_size, device="cuda", compute_type="float16")
        print("⚡ ИСПОЛЬЗУЕТСЯ ВИДЕОКАРТА (CUDA) ДЛЯ УЛЬТРА-БЫСТРОГО РАСПОЗНАВАНИЯ ⚡")
    except Exception as e:
        print(f"CUDA не найдена ({e}), падаем на CPU...")
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        
    print(f"Starting transcription for {video_path}...")
    
    try:
        # Принудительно ставим русский язык и фильтруем тишину
        segments, info = model.transcribe(video_path, word_timestamps=True, language="ru", vad_filter=True)
        print(f"Language forced to '{info.language}'")
        
        transcript_text = ""
        words_data = []
        
        for segment in segments:
            print(f"Распознавание: {segment.start:.1f}s - {segment.end:.1f}s...")
            transcript_text += segment.text + " "
            if segment.words:
                for word in segment.words:
                    words_data.append({
                        "word": word.word,
                        "start": word.start,
                        "end": word.end,
                        "probability": word.probability
                    })
    except Exception as e:
        print(f"CUDA error during transcription: {e}")
        print("Falling back to CPU with 'small' model due to missing NVIDIA DLLs...")
        model = WhisperModel("small", device="cpu", compute_type="int8")
        segments, info = model.transcribe(video_path, word_timestamps=True, language="ru", vad_filter=True)
        
        transcript_text = ""
        words_data = []
        for segment in segments:
            print(f"Распознавание (CPU): {segment.start:.1f}s - {segment.end:.1f}s...")
            transcript_text += segment.text + " "
            if segment.words:
                for word in segment.words:
                    words_data.append({
                        "word": word.word,
                        "start": word.start,
                        "end": word.end,
                        "probability": word.probability
                    })
                    
    print("Transcription complete.")
    return transcript_text.strip(), words_data

if __name__ == "__main__":
    # Simple test
    pass
