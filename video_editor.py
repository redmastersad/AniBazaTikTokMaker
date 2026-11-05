from __future__ import annotations

import os
import subprocess
import threading

import ffmpeg

from style import FONTS_DIR


class Cancelled(Exception):
    pass


def _rel_for_filter(path: str) -> str:
    """ffmpeg filter args choke on Windows drive letters ("C:"), so pass paths relative to the app folder."""
    rel = os.path.relpath(os.path.abspath(path), os.getcwd())
    return rel.replace("\\", "/")


def run_ffmpeg(stream, cancel: threading.Event | None = None, on_time=None):
    """Runs an ffmpeg-python graph; kills it when `cancel` is set. on_time(seconds) gets encode progress."""
    args = stream.overwrite_output().global_args("-progress", "pipe:1", "-nostats", "-loglevel", "error").compile()
    proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    err_chunks = []

    def _drain_err():
        for chunk in iter(lambda: proc.stderr.read(4096), b""):
            err_chunks.append(chunk)

    t = threading.Thread(target=_drain_err, daemon=True)
    t.start()
    for raw in iter(proc.stdout.readline, b""):
        if cancel is not None and cancel.is_set():
            proc.kill()
            proc.wait()
            raise Cancelled()
        line = raw.decode("utf-8", "ignore").strip()
        if on_time and line.startswith("out_time_us="):
            try:
                on_time(int(line.split("=", 1)[1]) / 1_000_000)
            except ValueError:
                pass
    proc.wait()
    t.join(timeout=2)
    if cancel is not None and cancel.is_set():
        raise Cancelled()
    if proc.returncode != 0:
        err = b"".join(err_chunks).decode("utf-8", "ignore")
        print("FFMPEG ERROR:", err[-2000:])
        raise RuntimeError(f"FFmpeg failed: {err[-500:] or proc.returncode}")


def format_video(video_path: str, output_path: str, subclips: list, logo_path: str = None, music_path: str = None,
                 ass_path: str | None = None, logo_box: dict | None = None, music_volume_db: float = -16.0,
                 mirror: bool = True, filters: bool = True, cancel: threading.Event | None = None,
                 on_progress=None):
    """
    Creates a 9:16 vertical clip in ONE ffmpeg pass: concatenated subclips (jump cuts), the original
    16:9 picture centred over a blurred copy, optional logo, background music and burned-in .ass
    subtitles that use fonts from Assets/Fonts (no Windows font install needed).
    """
    probe = ffmpeg.probe(video_path)
    video_info = next(s for s in probe['streams'] if s['codec_type'] == 'video')
    orig_h = int(video_info['height'])

    target_w = orig_h
    target_h = int(target_w * 16 / 9)
    target_w -= target_w % 2
    target_h -= target_h % 2

    print(f"Formatting video to 9:16 ({target_w}x{target_h})...")

    streams = []
    for (start, end) in subclips:
        s = ffmpeg.input(video_path, ss=start, t=end - start)
        streams.append(s.video)
        streams.append(s.audio)

    if len(subclips) > 1:
        joined = ffmpeg.concat(*streams, v=1, a=1).node
        base_video, audio = joined[0], joined[1]
    else:
        base_video, audio = streams[0], streams[1]

    v = base_video
    if mirror:
        v = v.filter('hflip')
    if filters:
        v = (v.filter('eq', contrast=1.15, brightness=-0.02, saturation=1.3)
              .filter('unsharp', 5, 5, 1.0, 5, 5, 0.0)
              .filter('vignette')
              .filter('noise', alls=15, allf='t+u'))
    split = v.split()

    bg = (split[0]
          .filter('scale', -1, target_h)
          .filter('crop', target_w, target_h)
          .filter('boxblur', 20, 5))

    fg_h = int(target_h * 0.65)
    fg_h -= fg_h % 2
    fg = (split[1]
          .filter('scale', -1, fg_h)
          .filter('crop', target_w, fg_h))

    video = ffmpeg.overlay(bg, fg, x='(main_w-overlay_w)/2', y='(main_h-overlay_h)/2')

    if logo_path and os.path.exists(logo_path):
        box = logo_box or {"x": 50, "y": 6, "width": 60}
        logo_w = max(16, int(target_w * float(box.get("width", 60)) / 100))
        logo_w -= logo_w % 2
        cx = target_w * float(box.get("x", 50)) / 100
        cy = target_h * float(box.get("y", 6)) / 100
        logo = ffmpeg.input(logo_path).filter('scale', logo_w, -1)
        video = ffmpeg.overlay(video, logo, x=f'{cx:.0f}-overlay_w/2', y=f'{cy:.0f}-overlay_h/2')

    if ass_path and os.path.exists(ass_path):
        video = video.filter('ass', _rel_for_filter(ass_path), fontsdir=_rel_for_filter(FONTS_DIR))

    if music_path and os.path.exists(music_path):
        bg_music = ffmpeg.input(music_path, stream_loop=-1).audio.filter('volume', f'{music_volume_db}dB')
        audio = ffmpeg.filter([audio, bg_music], 'amix', inputs=2, duration='first', dropout_transition=2)

    total = sum(e - s for s, e in subclips) or 1.0
    out = ffmpeg.output(video, audio, output_path, format='mp4', vcodec='libx264', acodec='aac', preset='medium', crf=20,
                        pix_fmt='yuv420p', movflags='+faststart')
    run_ffmpeg(out, cancel=cancel,
               on_time=(lambda t: on_progress(min(1.0, t / total))) if on_progress else None)
    print(f"Clip saved to {output_path}")


def grab_frame(video_path: str, out_jpg: str, at: float | None = None, height: int = 360) -> str | None:
    """Saves one frame (default: 40% into the video) as JPEG. Used for thumbnails and the style preview."""
    try:
        if at is None:
            dur = float(ffmpeg.probe(video_path)['format'].get('duration', 0) or 0)
            at = dur * 0.4 if dur else 1.0
        (ffmpeg.input(video_path, ss=at)
               .filter('scale', -2, height)
               .output(out_jpg, vframes=1, q=4)
               .overwrite_output()
               .run(quiet=True))
        return out_jpg if os.path.exists(out_jpg) else None
    except Exception as e:
        print(f"Could not grab frame from {video_path}: {e}")
        return None


def probe_duration(path: str) -> float:
    try:
        return float(ffmpeg.probe(path)['format'].get('duration', 0) or 0)
    except Exception:
        return 0.0
