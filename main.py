from __future__ import annotations

import argparse
import json
import os
import re
import time

from dotenv import load_dotenv

from analyzer import clean_words, find_highlights
from manual import subtitles_to_words
from style import APP_DIR, normalize_style, resolve_logo
from subtitles import generate_ass_subtitles
from transcriber import transcribe_video
from video_editor import Cancelled, format_video

CLIPS_INDEX = "clips.json"

DEFAULT_OPTIONS = {
    "whisper_model": "large-v3",
    "categories": None,       # None -> analyzer defaults
    "clip_min": 25,
    "clip_max": 60,
    "max_clips": 6,
    "silence_gap": 2.0,
    "music_volume": -16.0,
    "mirror": True,
    "filters": True,
    "cut_hardsubs": False,
    "hardsub_band": 20,
    "subs_file": None,        # ready .ass/.srt: used instead of Whisper
    "moments": None,          # typed timecodes [{start, end, title}]
    "moments_plus_ai": True,  # True: the AI still picks its moments too; False: only the typed ones
}


def get_subclips(words_data: list, start_time: float, end_time: float, max_silence: float = 2.0, remove_silence: bool = True) -> list:
    clip_words = [w for w in words_data if w['start'] >= start_time - 0.5 and w['end'] <= end_time + 0.5]
    if not clip_words or not remove_silence:
        return [(start_time, end_time)]

    subclips = []
    current_start = start_time
    for i in range(len(clip_words) - 1):
        w1 = clip_words[i]
        w2 = clip_words[i + 1]
        # If silence between words is greater than max_silence, cut it out
        if w2['start'] - w1['end'] > max_silence:
            subclips.append((current_start, w1['end'] + 0.5))
            current_start = max(w1['end'] + 0.5, w2['start'] - 0.3)
    subclips.append((current_start, end_time))

    valid_subclips = [(s, e) for s, e in subclips if e - s > 0.1]
    return valid_subclips or [(start_time, end_time)]


def parse_episode_name(path: str) -> tuple[str, str]:
    """'Магическая битва - 05.mkv' -> ('Магическая битва', '05')."""
    stem = os.path.splitext(os.path.basename(path))[0]
    clean = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", stem).replace("_", " ").replace(".", " ")
    m = re.search(r"^(.*?)[\s\-–—]*(?:s\d+\s*)?(?:ep?|серия|episode)?\s*(\d{1,4})\s*$", clean.strip(), re.I)
    if m and m.group(1).strip():
        return m.group(1).strip(" -–—"), m.group(2)
    return clean.strip(), ""


def read_clips_index(output_dir: str) -> list:
    try:
        with open(os.path.join(output_dir, CLIPS_INDEX), "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def write_clips_index(output_dir: str, items: list):
    path = os.path.join(output_dir, CLIPS_INDEX)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _wait_if_paused(pause, cancel):
    while pause is not None and pause.is_set():
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        time.sleep(0.3)
    if cancel is not None and cancel.is_set():
        raise Cancelled()


def process_video(video_path: str, output_dir: str, logo_path: str = None, music_path: str = None,
                  remove_silence: bool = True, ai_model: str = "llama3.1", style: dict | None = None,
                  options: dict | None = None, on_event=None, cancel=None, pause=None):
    """
    Full pipeline for one episode. Returns the list of generated clip paths.
    on_event(kind, data) reports progress to the app: step / moments / clip_start / clip_progress / clip_done.
    """
    opts = dict(DEFAULT_OPTIONS)
    opts.update(options or {})
    st = normalize_style(style)
    if logo_path is None:
        logo_path = resolve_logo(st)
    emit = on_event or (lambda kind, data: None)

    print("\n=======================================================")
    print(f"        PROCESSING: {os.path.basename(video_path)}       ")
    print("=======================================================\n")

    show, episode = parse_episode_name(video_path)
    manual_moments = opts.get("moments") or None
    only_manual = bool(manual_moments) and not opts.get("moments_plus_ai", True)

    # 1. Transcribe (or take the ready subtitle file)
    print("\n--- Step 1: Transcription ---")
    emit("step", {"step": 0, "progress": 0})
    if opts.get("subs_file"):
        print(f"Using subtitles from {opts['subs_file']} instead of Whisper")
        words_data = subtitles_to_words(opts["subs_file"])
    elif only_manual and not st["subs"].get("visible", True):
        print("Manual timecodes and no subtitles: skipping Whisper")
        words_data = []
    else:
        _, words_data = transcribe_video(
            video_path, model_size=opts["whisper_model"],
            on_progress=lambda p: emit("step", {"step": 0, "progress": p}), cancel=cancel)
    emit("step", {"step": 0, "progress": 1, "words": len(words_data)})
    _wait_if_paused(pause, cancel)

    # 2. Analyze
    print("\n--- Step 2: AI Analysis ---")
    emit("step", {"step": 1, "progress": 0})
    if not only_manual and not opts.get("subs_file"):
        words_data = clean_words(words_data)  # drop Whisper junk («Субтитры сделал…») from subtitles too
    report = os.path.join(APP_DIR, "_tmp", "analysis_" + re.sub(r"[^\w\-]+", "_", f"{show}_{episode}")[:80] + ".json")
    highlights = []
    if manual_moments:
        print(f"Using {len(manual_moments)} hand-typed timecodes" + (" only" if only_manual else " + AI moments"))
        highlights = [{
            "start": float(m["start"]), "end": float(m["end"]),
            "title": m.get("title") or f"{show} {episode} момент {n}".replace("  ", " ").strip(),
            "overlay": m.get("title") or "",
            "explanation": "Таймкоды вручную", "category": "manual", "score": 5,
        } for n, m in enumerate(manual_moments, 1)]
    if not only_manual:
        ai = find_highlights(words_data, model_name=ai_model, categories=opts["categories"],
                             min_len=opts["clip_min"], max_len=opts["clip_max"], max_clips=opts["max_clips"],
                             video_path=video_path, report_path=report, cancel=cancel,
                             on_progress=lambda p: emit("step", {"step": 1, "progress": p}))
        # skip AI moments that mostly repeat a typed one
        for h in ai or []:
            if not any(min(h["end"], m["end"]) - max(h["start"], m["start"]) > 0.5 * (h["end"] - h["start"])
                       for m in highlights):
                highlights.append(h)
    emit("moments", {"moments": highlights})
    emit("step", {"step": 1, "progress": 1})
    if not highlights:
        print("No highlights found by AI.")
        return []
    _wait_if_paused(pause, cancel)

    os.makedirs(output_dir, exist_ok=True)
    tmp_dir = os.path.join(APP_DIR, "_tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    generated_files = []

    # 3. Montage + subtitles (one ffmpeg pass per clip)
    print("\n--- Step 3: Video Processing ---")
    for i, h in enumerate(highlights):
        _wait_if_paused(pause, cancel)
        print(f"\nProcessing highlight {i + 1}: '{h['title']}'")
        emit("clip_start", {"index": i})
        emit("step", {"step": 2, "progress": i / len(highlights)})

        safe_title = re.sub(r'[\\/*?:"<>|]', "", h['title']).strip()[:80] or f"Highlight_{i + 1}"
        final_output_path = os.path.join(output_dir, f"{safe_title}.mp4")
        counter = 1
        while os.path.exists(final_output_path):
            final_output_path = os.path.join(output_dir, f"{safe_title}_{counter}.mp4")
            counter += 1

        ass_path = os.path.join(tmp_dir, f"subs_{os.getpid()}_{i}.ass")
        subclips = get_subclips(words_data, h['start'], h['end'], max_silence=float(opts["silence_gap"]),
                                remove_silence=remove_silence)
        generate_ass_subtitles(words_data, ass_path, subclips, style=st, title=h.get('overlay', h['title']))

        def _clip_progress(p, i=i):
            emit("clip_progress", {"index": i, "progress": p})
            emit("step", {"step": 2, "progress": (i + p) / len(highlights)})

        part_path = final_output_path + ".part"
        try:
            format_video(video_path, part_path, subclips, logo_path=logo_path, music_path=music_path,
                         ass_path=ass_path, logo_box=st["logo"], music_volume_db=float(opts["music_volume"]),
                         mirror=bool(opts["mirror"]), filters=bool(opts["filters"]),
                         crop_bottom=float(opts["hardsub_band"]) / 100 if opts.get("cut_hardsubs") else 0.0, cancel=cancel,
                         on_progress=_clip_progress)
            os.replace(part_path, final_output_path)
        except BaseException:
            if os.path.exists(part_path):
                try:
                    os.remove(part_path)
                except OSError:
                    pass
            raise
        finally:
            if os.path.exists(ass_path):
                try:
                    os.remove(ass_path)
                except OSError:
                    pass

        duration = sum(e - s for s, e in subclips)
        entry = {
            "file": os.path.basename(final_output_path),
            "title": h['title'],
            "why": h.get("explanation", ""),
            "category": h.get("category", ""),
            "score": h.get("score", 3),
            "duration": round(duration, 1),
            "source": os.path.basename(video_path),
            "show": show,
            "episode": episode,
            "start": h['start'],
            "end": h['end'],
            "created": time.time(),
        }
        index = read_clips_index(output_dir)
        index.append(entry)
        write_clips_index(output_dir, index)

        generated_files.append(final_output_path)
        emit("clip_done", {"index": i, "file": final_output_path, "entry": entry})

    emit("step", {"step": 3, "progress": 1})
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
