from __future__ import annotations

import os

from style import (PLAY_H, PLAY_W, apply_case, ass_escape, ass_inline_color,
                   normalize_style, pos_tag, style_line)


def _format_time(t: float) -> str:
    if t < 0:
        t = 0
    h = int(t / 3600)
    m = int((t % 3600) / 60)
    s = t % 60
    cs = int(round((s - int(s)) * 100))
    if cs == 100:
        cs = 99
    return f"{h}:{m:02d}:{int(s):02d}.{cs:02d}"


def _clip_words(words_data, subclips):
    """Maps absolute word timestamps to the timeline of the concatenated clip."""
    clip_words = []
    current_relative_time = 0.0
    for (start, end) in subclips:
        for w in words_data:
            if w['end'] >= start - 0.2 and w['start'] <= end + 0.2:
                w_start = max(start, w['start'])
                w_end = min(end, w['end'])
                if w_end > w_start:
                    clip_words.append({
                        'word': w['word'].strip(),
                        'start': current_relative_time + (w_start - start),
                        'end': current_relative_time + (w_end - start),
                    })
        current_relative_time += (end - start)
    return clip_words, current_relative_time


def _phrases(clip_words, max_words):
    phrases, phrase = [], []
    for w in clip_words:
        # Whisper sometimes stretches a word into the following silence
        if w['end'] - w['start'] > 1.0:
            w['end'] = w['start'] + 1.0
        if phrase and (w['start'] - phrase[-1]['end'] > 0.5):
            phrases.append(phrase)
            phrase = []
        phrase.append(w)
        if len(phrase) >= max_words or w['word'].endswith(('.', '!', '?')):
            phrases.append(phrase)
            phrase = []
    if phrase:
        phrases.append(phrase)
    return phrases


def generate_ass_subtitles(words_data, output_ass_path, subclips, style: dict | None = None, title: str | None = None):
    """
    Writes an .ass file with TikTok-style subtitles (and optionally the AI title on top)
    using fonts, colours and positions from the clip style.
    """
    st = normalize_style(style)
    subs, ttl = st["subs"], st["title"]
    clip_words, total = _clip_words(words_data, subclips)

    lines = [
        "[Script Info]",
        "Title: AniBaza Auto Subtitles",
        "ScriptType: v4.00+",
        f"PlayResX: {PLAY_W}",
        f"PlayResY: {PLAY_H}",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding",
        style_line("Subs", subs),
        style_line("Title", ttl),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    if ttl.get("visible") and title:
        text = ass_escape(apply_case(title.strip(), ttl.get("case", "upper")))
        lines.append(f"Dialogue: 1,{_format_time(0)},{_format_time(total)},Title,,0,0,0,,{{{pos_tag(ttl)}}}{text}")

    if subs.get("visible", True):
        base = ass_inline_color(subs["color"])
        hl = ass_inline_color(subs["hl"])
        anim = subs.get("anim", "pop")
        pos = pos_tag(subs)
        for p in _phrases(clip_words, max(1, int(subs.get("words", 3)))):
            words = [ass_escape(apply_case(w['word'].strip(), subs.get("case", "upper"))) for w in p]
            if anim == "none":
                start, end = p[0]['start'], p[-1]['end'] + 0.15
                lines.append(f"Dialogue: 0,{_format_time(start)},{_format_time(end)},Subs,,0,0,0,,{{{pos}\\blur1}}{' '.join(words)}")
                continue
            for i, target in enumerate(p):
                # Hold each state until the next word starts so the phrase doesn't flicker
                if i < len(p) - 1:
                    end_t = min(target['end'] + 0.3, p[i + 1]['start'])
                else:
                    end_t = target['end']
                text = f"{{{pos}\\blur1}}"
                for j, word in enumerate(words):
                    if j == i:
                        if anim == "pop":
                            text += f"{{\\c&H{hl}&\\fscx88\\fscy88\\t(0,100,\\fscx100\\fscy100)}}{word}{{\\c&H{base}&\\fscx100\\fscy100}} "
                        else:  # karaoke
                            text += f"{{\\c&H{hl}&}}{word}{{\\c&H{base}&}} "
                    else:
                        text += f"{word} "
                lines.append(f"Dialogue: 0,{_format_time(target['start'])},{_format_time(end_t)},Subs,,0,0,0,,{text.strip()}")

    os.makedirs(os.path.dirname(os.path.abspath(output_ass_path)), exist_ok=True)
    with open(output_ass_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines) + "\n")
    print(f"Generated ASS subtitle file: {output_ass_path}")
