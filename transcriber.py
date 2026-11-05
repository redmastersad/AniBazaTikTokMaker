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


def _collect(segments, info, on_progress=None, cancel=None, label=""):
    transcript_text = ""
    words_data = []
    duration = float(getattr(info, "duration", 0) or 0)
    for segment in segments:
        if cancel is not None and cancel.is_set():
            from video_editor import Cancelled
            raise Cancelled()
        print(f"Transcribing{label}: {segment.start:.1f}s - {segment.end:.1f}s...")
        if on_progress and duration:
            on_progress(min(1.0, segment.end / duration))
        transcript_text += segment.text + " "
        for word in segment.words or []:
            words_data.append({
                "word": word.word,
                "start": word.start,
                "end": word.end,
                "probability": word.probability,
            })
    return transcript_text, words_data


def transcribe_video(video_path: str, model_size: str = "large-v3", language: str = "ru",
                     on_progress=None, cancel=None):
    """
    Transcribes a video file and returns (text, words) with word-level timestamps.
    on_progress(0..1) is called as segments arrive; setting `cancel` stops it.
    """
    print(f"Loading faster-whisper model '{model_size}'...")
    try:
        model = WhisperModel(model_size, device="cuda", compute_type="float16")
        print("USING GPU (CUDA) FOR ACCELERATED TRANSCRIPTION")
    except Exception as e:
        print(f"CUDA not found ({e}), falling back to CPU...")
        model = WhisperModel(model_size, device="cpu", compute_type="int8")

    print(f"Starting transcription for {video_path}...")
    try:
        segments, info = model.transcribe(video_path, word_timestamps=True, language=language, vad_filter=True)
        transcript_text, words_data = _collect(segments, info, on_progress, cancel)
    except Exception as e:
        from video_editor import Cancelled
        if isinstance(e, Cancelled):
            del model
            raise
        print(f"CUDA error during transcription: {e}")
        print("Falling back to CPU with 'small' model due to missing NVIDIA DLLs...")
        del model
        model = WhisperModel("small", device="cpu", compute_type="int8")
        segments, info = model.transcribe(video_path, word_timestamps=True, language=language, vad_filter=True)
        transcript_text, words_data = _collect(segments, info, on_progress, cancel, " (CPU)")

    print("Transcription complete.")

    # Free VRAM for Ollama
    del model
    import gc
    gc.collect()

    return transcript_text.strip(), words_data
