"""Hand-made input for an episode: a ready subtitle file instead of Whisper, and typed timecodes instead of the AI.

Subtitle files (.ass / .ssa / .srt / .vtt) become the same word list Whisper produces
({"word", "start", "end"}), so the rest of the pipeline (silence cuts, TikTok subtitles) works unchanged.
Subtitle lines only have line timings, so each word gets a share of its line by length.
"""
from __future__ import annotations

import os
import re

SUBS_EXT = (".ass", ".ssa", ".srt", ".vtt")

# Fansub .ass files also carry signs, songs and notes; those are not speech.
_SKIP_STYLE = re.compile(
    r"sign|надп|note|прим|comment|коммент|logo|лого|title|титр|op\b|ed\b|^op|^ed|opening|ending|song|песн|"
    r"karaoke|кара|kar\b|romaji|lyrics|текст\s*песни",
    re.I,
)


def _read_text(path: str) -> str:
    raw = open(path, "rb").read()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    for enc in ("utf-8-sig", "cp1251"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "ignore")


def _ass_time(t: str) -> float:
    h, m, s = t.strip().split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def _srt_time(t: str) -> float:
    t = t.strip().replace(",", ".")
    parts = t.split(":")
    if len(parts) == 2:
        parts = ["0"] + parts
    h, m, s = parts
    return int(h) * 3600 + int(m) * 60 + float(s)


def _clean_ass_text(text: str) -> str:
    text = re.sub(r"\{[^}]*\}", "", text)
    text = text.replace("\\N", " ").replace("\\n", " ").replace("\\h", " ")
    return re.sub(r"\s+", " ", text).strip()


def _parse_ass(text: str) -> list[tuple[float, float, str]]:
    lines, fmt, in_events = [], None, False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("["):
            in_events = line.lower() == "[events]"
            continue
        if not in_events:
            continue
        if line.lower().startswith("format:"):
            fmt = [f.strip().lower() for f in line.split(":", 1)[1].split(",")]
            continue
        if not line.lower().startswith("dialogue:"):
            continue  # Comment: lines and the rest
        fields = fmt or ["layer", "start", "end", "style", "name", "marginl", "marginr", "marginv", "effect", "text"]
        values = line.split(":", 1)[1].split(",", len(fields) - 1)
        if len(values) < len(fields):
            continue
        ev = {k: v.strip() for k, v in zip(fields, values)}
        body = ev.get("text", "")
        if _SKIP_STYLE.search(ev.get("style", "")) or _SKIP_STYLE.search(ev.get("effect", "")):
            continue
        if re.search(r"\\p[1-9]", body) or re.search(r"\\(pos|move)\s*\(", body):
            continue  # drawings and placed signs
        clean = _clean_ass_text(body)
        if not clean:
            continue
        try:
            lines.append((_ass_time(ev["start"]), _ass_time(ev["end"]), clean))
        except (KeyError, ValueError):
            continue
    return lines


def _parse_srt(text: str) -> list[tuple[float, float, str]]:
    lines = []
    for block in re.split(r"\n\s*\n", text.replace("\r", "")):
        rows = [r for r in block.split("\n") if r.strip()]
        for i, row in enumerate(rows):
            m = re.match(r"\s*([\d:.,]+)\s*-->\s*([\d:.,]+)", row)
            if not m:
                continue
            body = " ".join(rows[i + 1:])
            body = re.sub(r"<[^>]*>|\{[^}]*\}", "", body)
            body = re.sub(r"\s+", " ", body).strip()
            if body:
                try:
                    lines.append((_srt_time(m.group(1)), _srt_time(m.group(2)), body))
                except ValueError:
                    pass
            break
    return lines


def subtitle_lines(path: str) -> list[tuple[float, float, str]]:
    text = _read_text(path)
    ext = os.path.splitext(path)[1].lower()
    lines = _parse_ass(text) if ext in (".ass", ".ssa") or "[events]" in text.lower() else _parse_srt(text)
    lines.sort(key=lambda x: x[0])
    return lines


def subtitles_to_words(path: str) -> list[dict]:
    """Words with estimated timings from a subtitle file. Raises ValueError if nothing usable is inside."""
    words, prev_end = [], 0.0
    for start, end, text in subtitle_lines(path):
        text = re.sub(r"^[\-–—]\s*", "", text)
        text = re.sub(r"\s[\-–—]\s", " ", text)
        tokens = text.split()
        if not tokens or end <= start:
            continue
        start = max(start, prev_end)  # two speakers at once: keep the timeline moving forward
        if end - start < 0.2:
            end = start + 0.2 * len(tokens)
        weights = [len(t) + 2 for t in tokens]
        total = float(sum(weights))
        t = start
        for i, (tok, wgt) in enumerate(zip(tokens, weights)):
            dur = (end - start) * wgt / total
            words.append({"word": " " + tok, "start": round(t, 3), "end": round(t + dur, 3),
                          "probability": 1.0, "brk": i == len(tokens) - 1})
            t += dur
        prev_end = end
    if not words:
        raise ValueError("В файле субтитров не нашлось реплик")
    return words


def find_subtitles_for(video_path: str) -> str | None:
    """A subtitle file with the same name next to the video ('Серия 05.mkv' -> 'Серия 05.ass')."""
    stem = os.path.splitext(video_path)[0]
    for ext in SUBS_EXT:
        for cand in (stem + ext, stem + ext.upper()):
            if os.path.isfile(cand):
                return cand
    return None


# ---------------------------------------------------------------- timecodes

_TIME = r"\d{1,2}(?::\d{1,2}){0,2}(?:[.,]\d+)?"


def _to_sec(t: str) -> float:
    parts = t.replace(",", ".").split(":")
    sec = 0.0
    for p in parts:
        sec = sec * 60 + float(p)
    return sec


def parse_timecodes(text: str, duration: float = 0.0) -> tuple[list[dict], list[str]]:
    """
    One clip per line: "12:30 - 13:15 Годжо всех разносит" (title optional).
    Times: 75, 1:15, 0:01:15, 1:15.5. Returns (moments, errors) — errors are human readable.
    """
    moments, errors = [], []
    for n, raw in enumerate((text or "").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(rf"^({_TIME})\s*(?:-|–|—|до|\.\.|\s)\s*({_TIME})(?:\s+|\s*[-–—:|]\s*|$)(.*)$", line, re.I)
        if not m:
            errors.append(f"Строка {n}: не понял «{line}». Пиши так: 12:30 - 13:15 Название")
            continue
        try:
            start, end = _to_sec(m.group(1)), _to_sec(m.group(2))
        except ValueError:
            errors.append(f"Строка {n}: странное время в «{line}»")
            continue
        if end <= start:
            errors.append(f"Строка {n}: конец раньше начала")
            continue
        if end - start > 600:
            errors.append(f"Строка {n}: клип длиннее 10 минут")
            continue
        if duration and start >= duration:
            errors.append(f"Строка {n}: серия короче ({int(duration // 60)}:{int(duration % 60):02d})")
            continue
        if duration:
            end = min(end, duration)
        moments.append({"start": start, "end": end, "title": m.group(3).strip()})
    return moments, errors
