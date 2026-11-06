"""Picks the best short-video moments of an episode.

How it works (each step fixes a reason the old version picked bad moments):

1. Whisper words are cleaned: typical Whisper junk ("Субтитры сделал…", "Продолжение следует…",
   endless repeats) is dropped, and lines that look like song lyrics (opening/ending: low
   confidence, long sung vowels) are marked as music, so they are never chosen.
2. The words are split into numbered LINES (sentence ends and pauses). The model never writes
   timestamps any more: it answers with line numbers, so every clip starts and ends on a whole
   phrase. The old prompt sent the whole episode in one request, which did not fit the 8192-token
   window of the model, so Ollama silently cut the start of the prompt (the rules) away.
3. The episode is read in overlapping ~3-minute blocks, each fits the model easily. For every block
   the model returns the best moment(s) with a 1-10 score and the key line (the punchline).
4. Every candidate is fitted to the wanted length around its key line (build-up before it, a
   short reaction after it) and gets bonus points for loud/emotional sound (shouting, music
   peaks from the dub track) and for lively dialogue.
5. The best candidates go to the model once more, side by side, to rank them against each other
   (block scores are not comparable between blocks).
6. Final cut points snap to a pause, and to a scene cut right next to it when there is one,
   so a clip never starts or ends in the middle of a word or a shot.

A JSON report of all candidates is written next to the app (_tmp/analysis_*.json) so a bad pick
can be explained afterwards.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from typing import Callable, List, Optional

import httpx

try:
    import nowindow  # noqa: F401  (hide ffmpeg console windows on Windows)
except Exception:  # pragma: no cover
    pass

OLLAMA_URL = "http://localhost:11434/api/generate"

# What the AI director may look for (ids are stored in settings, labels are shown in the app)
CATEGORIES = {
    "hype": ("Хайп и пафос", "Pure hype moments: characters trash-talking, revealing true power, epic threats, determination speeches, screaming with emotion."),
    "funny": ("Угар", "Extremely funny, absurd or highly awkward interactions."),
    "villain": ("Монологи злодеев", "Villain monologues and philosophy: cold, calculating or insane speeches about reality, pain or power."),
    "twist": ("Твисты", "Shocking betrayals, crazy plot twists or dramatic reveals."),
    "drama": ("Драма", "Heartbreaking, sad or emotional scenes: loss, confessions, tears."),
    "romance": ("Романтика", "Romantic, cute or flirty moments between characters."),
}
DEFAULT_CATEGORIES = ["hype", "funny", "villain", "twist"]

# ---------------------------------------------------------------- 1. clean the transcript

_JUNK = re.compile(
    r"субтитр|редактор|корректор|продолжение следует|спасибо за (?:просмотр|внимание)|подпис(?:ывайтесь|ка)"
    r"|ставьте лайк|dimatorzok|amara|перевод(?:чик)?:|озвуч(?:ка|ено|ил)|колокольчик|до новых встреч"
    r"|смотрите (?:в|на) следующ|в следующей серии|www\.|\.com|\.ru\b",
    re.I)
SENT_END = (".", "!", "?", "…")


def clean_words(words_data: List[dict]) -> List[dict]:
    """Drops Whisper hallucinations; the rest of the app (subtitles) can use the result too."""
    words = [dict(w) for w in words_data if str(w.get("word", "")).strip()]
    if not words:
        return []
    out, buf = [], []

    def flush():
        text = "".join(w["word"] for w in buf).strip()
        if buf and not _JUNK.search(text):
            out.extend(buf)
        buf.clear()

    for i, w in enumerate(words):
        buf.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        if w["word"].strip().endswith(SENT_END) or nxt is None or nxt["start"] - w["end"] > 1.0:
            flush()
    flush()

    # The same short phrase over and over (Whisper loop) -> keep only the first three
    res, seen = [], {}
    for line in _split_lines(out):
        key = re.sub(r"[^\wа-яё]+", "", line["text"].lower())
        if len(key) < 25:
            seen[key] = seen.get(key, 0) + 1
            if seen[key] > 3 and _recent_repeat(res, key):
                continue
        res.extend(out[line["w0"]:line["w1"] + 1])
    return res


def _recent_repeat(words: List[dict], key: str) -> bool:
    tail = re.sub(r"[^\wа-яё]+", "", "".join(w["word"] for w in words[-40:]).lower())
    return tail.count(key) >= 3


def _split_lines(words: List[dict], max_len: float = 12.0, max_words: int = 28) -> List[dict]:
    """Groups words into lines: a sentence end, a pause > 0.7 s, or a too-long run ends a line."""
    lines, w0 = [], 0
    for i, w in enumerate(words):
        nxt = words[i + 1] if i + 1 < len(words) else None
        txt = w["word"].strip()
        too_long = (w["end"] - words[w0]["start"] > max_len and txt.endswith((",", ";", ":", "—"))) \
            or (i - w0 + 1) >= max_words
        if nxt is None or txt.endswith(SENT_END) or nxt["start"] - w["end"] > 0.7 or too_long:
            seg = words[w0:i + 1]
            probs = [float(x.get("probability", 1.0) or 0) for x in seg]
            durs = sorted(x["end"] - x["start"] for x in seg)
            lines.append({
                "w0": w0, "w1": i,
                "start": float(seg[0]["start"]), "end": float(seg[-1]["end"]),
                "text": "".join(x["word"] for x in seg).strip(),
                "prob": sum(probs) / len(probs),
                "med_word": durs[len(durs) // 2],
                "gap_before": float(seg[0]["start"] - words[w0 - 1]["end"]) if w0 else 99.0,
                "gap_after": float(nxt["start"] - w["end"]) if nxt else 99.0,
            })
            w0 = i + 1
    for idx, ln in enumerate(lines):
        ln["i"] = idx
        n = max(1, ln["w1"] - ln["w0"] + 1)
        # sung lyrics: Whisper is unsure and words are stretched
        ln["music"] = (ln["prob"] < 0.45) or (ln["med_word"] > 0.85 and n >= 3) or \
            (ln["prob"] < 0.6 and ln["med_word"] > 0.55)
    _mark_song_blocks(lines)
    return lines


def _mark_song_blocks(lines: List[dict]):
    """An opening/ending is a ~1.5 min run of music-like lines: mark the whole run, holes included."""
    n = len(lines)
    for i in range(n):
        if not lines[i]["music"]:
            continue
        j, music, total = i, 0, 0
        while j < n and lines[j]["start"] - lines[i]["start"] < 90:
            total += 1
            music += lines[j]["music"]
            j += 1
        if total >= 6 and music / total >= 0.5:
            for k in range(i, j):
                if lines[k]["music"] or (lines[k]["prob"] < 0.7):
                    lines[k]["music"] = True


# ---------------------------------------------------------------- audio: loudness curve

def loudness_curve(video_path: str, hop: float = 0.5) -> Optional[List[float]]:
    """RMS loudness in dB per `hop` seconds of the episode's audio (None if ffmpeg/numpy fail)."""
    try:
        import numpy as np
        sr = 8000
        proc = subprocess.run(
            ["ffmpeg", "-nostdin", "-v", "error", "-i", video_path, "-vn", "-ac", "1", "-ar", str(sr),
             "-f", "s16le", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=600,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        a = np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0
        step = int(sr * hop)
        if len(a) < step * 10:
            return None
        a = a[: len(a) // step * step].reshape(-1, step)
        rms = np.sqrt((a ** 2).mean(axis=1) + 1e-10)
        return (20 * np.log10(rms)).tolist()
    except Exception as e:
        print(f"Loudness analysis skipped: {e}")
        return None


def _audio_bonus(curve: Optional[List[float]], start: float, end: float, ref: float, hop: float = 0.5) -> float:
    """0..2: how much louder than the episode's typical speech the loudest part of the moment is."""
    if not curve:
        return 0.0
    seg = curve[int(start / hop): max(int(start / hop) + 1, int(end / hop))]
    if not seg:
        return 0.0
    top = sorted(seg, reverse=True)[: max(1, len(seg) // 6)]
    peak = sum(top) / len(top)
    return max(0.0, min(2.0, (peak - ref) / 4.0))


def _speech_ref(curve: Optional[List[float]], lines: List[dict], hop: float = 0.5) -> float:
    if not curve:
        return 0.0
    vals = []
    for ln in lines:
        if not ln["music"]:
            vals.extend(curve[int(ln["start"] / hop): int(ln["end"] / hop) + 1])
    vals = sorted(vals or curve)
    return vals[int(len(vals) * 0.75)]  # loud-ish normal speech


# ---------------------------------------------------------------- LLM

def _ask(model: str, prompt: str, schema: dict, num_predict: int = 700) -> dict:
    """One Ollama call that returns parsed JSON ({} on failure). Uses a JSON schema when supported."""
    body = {"model": model, "prompt": prompt, "stream": False, "format": schema,
            "options": {"num_ctx": 8192, "temperature": 0.2, "num_predict": num_predict}}
    for attempt in range(2):
        try:
            r = httpx.post(OLLAMA_URL, json=body, timeout=300.0)
            if r.status_code >= 400 and body["format"] != "json":
                body["format"] = "json"  # old Ollama without structured outputs
                r = httpx.post(OLLAMA_URL, json=body, timeout=300.0)
            r.raise_for_status()
            text = r.json().get("response", "").strip()
            text = re.sub(r"^```(?:json)?|```$", "", text).strip()
            if text:
                return json.loads(text)
        except Exception as e:
            print(f"Ollama call failed ({attempt + 1}/2): {e}")
            time.sleep(1)
    return {}


_BLOCK_SCHEMA = {
    "type": "object",
    "properties": {"moments": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "first_line": {"type": "integer"}, "key_line": {"type": "integer"}, "last_line": {"type": "integer"},
            "category": {"type": "string"}, "score": {"type": "integer"},
            "title": {"type": "string"}, "why": {"type": "string"},
        },
        "required": ["first_line", "key_line", "last_line", "category", "score", "title", "why"]}}},
    "required": ["moments"],
}

_RANK_SCHEMA = {
    "type": "object",
    "properties": {"ranking": {"type": "array", "items": {
        "type": "object",
        "properties": {"id": {"type": "integer"}, "title": {"type": "string"}},
        "required": ["id", "title"]}}},
    "required": ["ranking"],
}


def _fmt_t(t: float) -> str:
    return f"{int(t // 60)}:{int(t % 60):02d}"


def _block_prompt(block: List[dict], cats: List[str], min_len: float, max_len: float) -> str:
    wanted = "\n".join(f"- {c}: {CATEGORIES[c][1]}" for c in cats)
    lines = "\n".join(f"[{ln['i']}] {_fmt_t(ln['start'])} {ln['text']}" for ln in block if not ln["music"])
    return f"""You are a top TikTok editor who cuts ANIME episodes into viral vertical shorts.
Below is a ~3 minute piece of an episode transcript (Russian dub, recognized by speech-to-text, so
some words may be wrong). Format of each line: [line number] minute:second text.

Find the single best moment for a {min_len:.0f}-{max_len:.0f} second short in this piece (at most 2 if
there are two truly great ones). A great short has: a hook in the first seconds, rising tension or a
joke setup, and a strong PAYOFF line (punchline, shocking reveal, epic declaration, emotional
breakdown). It must be understandable without watching the episode.

Wanted kinds of moments:
{wanted}

Bad moments (score them 1-3): exposition, explaining rules/plans, small talk, greetings, calm
conversation, recap of previous events, lines that only make sense with earlier context.

Score honestly from 1 to 10. 9-10: people would share it; 7-8: strong; 4-6: ordinary dialogue;
1-3: boring. Most pieces of an episode are 3-6. If nothing here is above 5, return an empty list.

For each moment answer with LINE NUMBERS from the transcript:
- key_line: the payoff line, the reason to watch;
- first_line: where the build-up starts (usually a few lines before key_line, a line that starts a
  new thought or exchange, never the middle of an answer);
- last_line: key_line or 1-3 lines after it (a reaction), never cut a conversation mid-reply.
"category" is one of: {", ".join(cats)}.
"title": Russian, a short clickable hook, max 50 characters, no quotes, no hashtags.
"why": Russian, one sentence why it will work.

Transcript:
{lines}
"""


def _rank_prompt(cands: List[dict], lines: List[dict]) -> str:
    parts = []
    for k, c in enumerate(cands):
        text = " ".join(ln["text"] for ln in lines[c["l0"]:c["l1"] + 1] if not ln["music"])
        if len(text) > 700:
            text = text[:700] + "…"
        parts.append(f"#{k} ({c['category']}, {c['end'] - c['start']:.0f}s) {text}")
    joined = "\n\n".join(parts)
    return f"""You are a top TikTok editor for an ANIME channel (Russian dub). Here are candidate clips
from one episode. Rank them from the most viral to the least: strong payoff, emotion, humour or hype,
understandable without context. Boring, calm or confusing clips go last.
Return ALL ids in your order. For each, give a better Russian clickable title (max 50 chars,
no quotes, no hashtags, no spoilers of character names in the first word).

Candidates:
{joined}
"""


# ---------------------------------------------------------------- fitting a moment to the length

def _fit(lines: List[dict], l0: int, key: int, l1: int, min_len: float, max_len: float) -> tuple[int, int]:
    """Grows/shrinks the line range around the key line until the length is within [min_len, max_len]."""
    n = len(lines)
    l0, l1 = max(0, min(l0, key)), min(n - 1, max(l1, key))

    def dur(a, b):
        return lines[b]["end"] - lines[a]["start"]

    # too long: drop lines from the side farther from the key line (keep 1 reaction line after it)
    while dur(l0, l1) > max_len and l1 > l0:
        before = lines[key]["start"] - lines[l0]["start"]
        if l1 > key + 1 and (lines[l1]["end"] - lines[key]["end"]) > before * 0.5:
            l1 -= 1
        elif l0 < key:
            l0 += 1
        elif l1 > key:
            l1 -= 1
        else:
            break
    # too short: add build-up before (until the key line sits at ~2/3) and reaction after
    while dur(l0, l1) < min_len:
        before = lines[key]["start"] - lines[l0]["start"]
        can_back = l0 > 0 and not lines[l0 - 1]["music"] and dur(l0 - 1, l1) <= max_len
        can_fwd = l1 < n - 1 and not lines[l1 + 1]["music"] and dur(l0, l1 + 1) <= max_len
        want_back = before < 2 * (dur(l0, l1) - before) or not can_fwd
        if can_back and want_back:
            l0 -= 1
        elif can_fwd:
            l1 += 1
        elif can_back:
            l0 -= 1
        else:
            break
    # start on a new thought: if the line before is glued to ours (no pause, no sentence end), take it
    for _ in range(3):
        prev = lines[l0 - 1] if l0 > 0 else None
        if prev and not prev["music"] and lines[l0]["gap_before"] < 0.35 \
                and not prev["text"].endswith(SENT_END) and dur(l0 - 1, l1) <= max_len:
            l0 -= 1
        else:
            break
    # do not stop on a question that is answered right away
    if lines[l1]["text"].endswith("?") and l1 < n - 1 and lines[l1]["gap_after"] < 1.5 \
            and not lines[l1 + 1]["music"] and dur(l0, l1 + 1) <= max_len:
        l1 += 1
    return l0, l1


def _text_bonus(lines: List[dict], l0: int, l1: int) -> float:
    """0..1: lively dialogue (exclamations, questions, short lines back and forth)."""
    seg = lines[l0:l1 + 1]
    if not seg:
        return 0.0
    excl = sum(ln["text"].count("!") for ln in seg)
    q = sum(ln["text"].count("?") for ln in seg)
    span = max(1.0, seg[-1]["end"] - seg[0]["start"])
    talk = sum(ln["end"] - ln["start"] for ln in seg) / span  # how much of the clip has speech
    return min(1.0, 0.08 * excl + 0.04 * q + max(0.0, talk - 0.5))


# ---------------------------------------------------------------- scene cuts / final cut points

def _scene_cuts(video_path: str, t0: float, t1: float) -> List[float]:
    """Scene change times (absolute seconds) inside [t0, t1], read by ffmpeg from a small window."""
    if not video_path or t1 <= t0:
        return []
    try:
        proc = subprocess.run(
            ["ffmpeg", "-nostdin", "-hide_banner", "-ss", f"{max(0.0, t0):.2f}", "-t", f"{t1 - t0:.2f}",
             "-i", video_path, "-an", "-vf", "scale=320:-2,select='gt(scene,0.3)',showinfo", "-f", "null", "-"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=60,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        err = proc.stderr.decode("utf-8", "ignore")
        return [max(0.0, t0) + float(m) for m in re.findall(r"pts_time:([\d.]+)", err)]
    except Exception:
        return []


def _cut_points(video_path: str, lines: List[dict], l0: int, l1: int) -> tuple[float, float]:
    first, last = lines[l0], lines[l1]
    prev_end = lines[l0 - 1]["end"] if l0 > 0 else 0.0
    next_start = lines[l1 + 1]["start"] if l1 + 1 < len(lines) else last["end"] + 3.0

    # start: a scene cut shortly before the first word (and after the previous line) is the cleanest
    lo = max(prev_end + 0.05, first["start"] - 1.5)
    start = max(lo, first["start"] - 0.3)
    cuts = [c for c in _scene_cuts(video_path, lo, first["start"] + 0.05) if lo <= c <= first["start"] + 0.05]
    if cuts:
        start = cuts[-1]
    # end: let the last word ring, end on a scene cut if one comes soon, never into the next line
    hi = min(next_start - 0.1, last["end"] + 1.5)
    end = max(last["end"] + 0.1, min(hi, last["end"] + 0.6))
    cuts = [c for c in _scene_cuts(video_path, last["end"], hi) if last["end"] + 0.1 <= c <= hi]
    if cuts:
        end = cuts[0]
    return round(max(0.0, start), 2), round(end, 2)


# ---------------------------------------------------------------- main entry

def find_highlights(words_data: List[dict], model_name: str = "llama3.1", categories: List[str] | None = None,
                    min_len: float = 25, max_len: float = 60, max_clips: int = 6,
                    video_path: str | None = None, on_progress: Callable[[float], None] | None = None,
                    report_path: str | None = None, cancel=None) -> List[dict]:
    """Returns [{title, start, end, explanation, category, score(1-5)}] in timeline order."""
    progress = on_progress or (lambda p: None)
    cats = [c for c in (categories or DEFAULT_CATEGORIES) if c in CATEGORIES] or DEFAULT_CATEGORIES
    min_len = float(min_len)
    max_len = float(max(max_len, min_len + 5))
    max_clips = max(1, int(max_clips or 6))

    words = clean_words(words_data)
    if len(words) < 10:
        print("Transcript is too short to find highlights.")
        return []
    lines = _split_lines(words)
    music = sum(1 for ln in lines if ln["music"])
    print(f"Transcript: {len(words)} words, {len(lines)} lines ({music} look like songs and are skipped).")

    curve = loudness_curve(video_path) if video_path else None
    ref = _speech_ref(curve, lines)
    progress(0.05)

    # blocks of ~3 min with 1 min overlap
    blocks, t, total = [], lines[0]["start"], lines[-1]["end"]
    while t < total:
        blk = [ln for ln in lines if t <= ln["start"] < t + 180]
        if sum(1 for ln in blk if not ln["music"]) >= 4:
            blocks.append(blk)
        t += 120

    print(f"Analyzing {len(blocks)} parts of the episode with local Ollama AI ({model_name})...")
    cands = []
    for b, blk in enumerate(blocks):
        if cancel is not None and cancel.is_set():
            from video_editor import Cancelled
            raise Cancelled()
        res = _ask(model_name, _block_prompt(blk, cats, min_len, max_len), _BLOCK_SCHEMA)
        ids = {ln["i"] for ln in blk if not ln["music"]}
        for m in (res.get("moments") or [])[:2]:
            try:
                key, a, z = int(m["key_line"]), int(m["first_line"]), int(m["last_line"])
                score = float(m.get("score", 5))
            except (KeyError, TypeError, ValueError):
                continue
            if key not in ids:
                continue
            # the model sometimes mixes up the order or points far away: keep it near the key line
            a = max(key - 40, min(a, key))
            z = min(key + 15, max(z, key), len(lines) - 1)
            l0, l1 = _fit(lines, a, key, z, min_len, max_len)
            if any(lines[k]["music"] for k in range(l0, l1 + 1)):
                # trim song lines off the edges; drop if a song sits inside
                while l0 < key and lines[l0]["music"]:
                    l0 += 1
                while l1 > key and lines[l1]["music"]:
                    l1 -= 1
                if any(lines[k]["music"] for k in range(l0, l1 + 1)):
                    continue
            start, end = lines[l0]["start"], lines[l1]["end"]
            if end - start < min(15.0, min_len * 0.6):
                continue
            ab = _audio_bonus(curve, start, end, ref)
            tb = _text_bonus(lines, l0, l1)
            cat = m.get("category") if m.get("category") in cats else cats[0]
            cands.append({
                "l0": l0, "l1": l1, "key": key, "start": start, "end": end,
                "llm": max(1.0, min(10.0, score)), "audio": round(ab, 2), "lively": round(tb, 2),
                "total": round(max(1.0, min(10.0, score)) + ab + tb, 2),
                "category": cat, "title": str(m.get("title") or "").strip().strip('"«»') or "Момент",
                "why": str(m.get("why") or "").strip(),
            })
        progress(0.05 + 0.8 * (b + 1) / max(1, len(blocks)))

    # merge duplicates from overlapping blocks: keep the better one
    cands.sort(key=lambda c: -c["total"])
    uniq = []
    for c in cands:
        if all(min(c["end"], u["end"]) - max(c["start"], u["start"]) < 0.3 * (c["end"] - c["start"]) for u in uniq):
            uniq.append(c)
    pool = [c for c in uniq if c["llm"] >= 5] or uniq
    pool = pool[: max(max_clips * 2, 8)]

    # compare the best ones side by side
    if len(pool) > 1:
        res = _ask(model_name, _rank_prompt(pool, lines), _RANK_SCHEMA, num_predict=900)
        order = []
        for r in res.get("ranking") or []:
            try:
                k = int(r["id"])
            except (KeyError, TypeError, ValueError):
                continue
            if 0 <= k < len(pool) and k not in order:
                order.append(k)
                title = str(r.get("title") or "").strip().strip('"«»')
                if 3 <= len(title) <= 70:
                    pool[k]["title"] = title
        if order:
            n = len(pool)
            for pos, k in enumerate(order):
                pool[k]["rank"] = pos + 1
                # ranking counts as much as the block score; unranked ones get the lowest place
                pool[k]["total"] = round(pool[k]["total"] * 0.5 + 10 * (1 - pos / n) * 0.5 + 0.5 * pool[k]["audio"], 2)
            for c in pool:
                if "rank" not in c:
                    c["total"] = round(c["total"] * 0.5, 2)
    progress(0.92)

    # choose the best non-overlapping ones (5 s gap between clips)
    pool.sort(key=lambda c: -c["total"])
    chosen = []
    for c in pool:
        if len(chosen) >= max_clips:
            break
        if all(c["end"] + 5 <= o["start"] or c["start"] >= o["end"] + 5 for o in chosen):
            chosen.append(c)

    result = []
    for c in chosen:
        start, end = _cut_points(video_path, lines, c["l0"], c["l1"])
        c["cut"] = [start, end]
        result.append({
            "title": c["title"][:70],
            "start": start,
            "end": end,
            "explanation": c["why"],
            "category": c["category"],
            "score": max(1, min(5, int(round(c["total"] / 2)))),
        })
        print(f"Found highlight: '{c['title']}' ({start:.1f}s - {end:.1f}s), score {c['total']}")
    result.sort(key=lambda x: x["start"])

    if report_path:
        try:
            os.makedirs(os.path.dirname(report_path) or ".", exist_ok=True)
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump({
                    "model": model_name, "categories": cats, "min_len": min_len, "max_len": max_len,
                    "song_lines": [[round(ln["start"], 1), ln["text"]] for ln in lines if ln["music"]],
                    "candidates": [{**{k: v for k, v in c.items() if k not in ("l0", "l1", "key")},
                                    "key_line": lines[c["key"]]["text"],
                                    "text": " ".join(ln["text"] for ln in lines[c["l0"]:c["l1"] + 1])}
                                   for c in sorted(uniq, key=lambda c: c["start"])],
                    "chosen": result,
                }, f, ensure_ascii=False, indent=1)
        except Exception as e:
            print(f"Could not write analysis report: {e}")
    progress(1.0)
    return result
