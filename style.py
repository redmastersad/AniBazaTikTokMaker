"""Clip style: fonts, positions and colours of subtitles, the AI title and the logo.

Coordinates are percentages of the vertical 9:16 frame and point at the CENTRE
of an element, so the same numbers work in the preview and in ffmpeg/libass.
"""
from __future__ import annotations

import copy
import json
import os

from fontTools.ttLib import TTFont

APP_DIR = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR = os.path.join(APP_DIR, "Assets", "Fonts")
LOGOS_DIR = os.path.join(APP_DIR, "Assets", "Logo")
PRESETS_FILE = os.path.join(APP_DIR, "presets.json")

# Script resolution of the generated .ass files (libass scales it to the video).
PLAY_W, PLAY_H = 1080, 1920

DEFAULT_STYLE = {
    "subs": {
        "visible": True,
        "font": "Montserrat Black",
        "size": 110,
        "spacing": 0,
        "case": "upper",          # upper | as_is | lower
        "color": "#FFFFFF",
        "hl": "#FFE14A",          # active word
        "outline": 4,
        "outline_color": "#000000",
        "shadow": True,
        "anim": "pop",            # pop | karaoke | none
        "words": 3,
        "x": 50, "y": 66, "width": 80,
    },
    "title": {
        "visible": False,
        "font": "Unbounded ExtraBold",
        "size": 56,
        "spacing": 0,
        "case": "upper",
        "color": "#FFFFFF",
        "outline": 3,
        "outline_color": "#000000",
        "shadow": True,
        "x": 50, "y": 15, "width": 86,
    },
    "logo": {
        "visible": True,
        "file": "",               # name in Assets/Logo or an absolute path
        "x": 50, "y": 6, "width": 60,
    },
}

BUILTIN_PRESETS = {
    "АниБаза": DEFAULT_STYLE,
    "Классика": {
        "subs": {"font": "Montserrat Black", "size": 92, "case": "as_is", "color": "#FFFFFF", "hl": "#FFFFFF",
                 "outline": 5, "outline_color": "#000000", "shadow": False, "anim": "none", "words": 4, "y": 72},
        "title": {"visible": False},
    },
    "Неон": {
        "subs": {"font": "Russo One", "size": 104, "case": "upper", "color": "#FFFFFF", "hl": "#38E1FF",
                 "outline": 3, "outline_color": "#FF2E7E", "shadow": True, "anim": "pop", "words": 2, "y": 62},
        "title": {"visible": True, "font": "Russo One", "color": "#38E1FF", "outline_color": "#120C2A"},
    },
    "Манга": {
        "subs": {"font": "Rubik Mono One", "size": 84, "case": "upper", "color": "#000000", "hl": "#FF2E7E",
                 "outline": 6, "outline_color": "#FFFFFF", "shadow": False, "anim": "karaoke", "words": 2, "y": 70},
        "title": {"visible": True, "font": "Rubik Mono One", "size": 48, "color": "#FFFFFF", "outline_color": "#000000"},
    },
}


def merge_style(base: dict, patch: dict | None) -> dict:
    out = copy.deepcopy(base)
    for layer, values in (patch or {}).items():
        if isinstance(values, dict) and isinstance(out.get(layer), dict):
            out[layer].update(values)
    return out


def normalize_style(style: dict | None) -> dict:
    return merge_style(DEFAULT_STYLE, style)


# ---------------------------------------------------------------- presets

def load_presets() -> dict:
    presets = {name: normalize_style(p) for name, p in BUILTIN_PRESETS.items()}
    try:
        with open(PRESETS_FILE, "r", encoding="utf-8") as f:
            for name, p in json.load(f).items():
                presets[name] = normalize_style(p)
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"Could not read presets: {e}")
    return presets


def user_presets() -> dict:
    try:
        with open(PRESETS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_user_preset(name: str, style: dict):
    data = user_presets()
    data[name] = normalize_style(style)
    with open(PRESETS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def delete_user_preset(name: str):
    data = user_presets()
    data.pop(name, None)
    with open(PRESETS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------- fonts

def _font_info(path: str) -> dict | None:
    try:
        font = TTFont(path, lazy=True, fontNumber=0)
        names = font["name"]
        family = names.getDebugName(1) or names.getDebugName(4)
        if not family:
            return None
        upm = font["head"].unitsPerEm
        os2 = font["OS/2"] if "OS/2" in font else None
        if os2 and os2.usWinAscent + os2.usWinDescent:
            height = os2.usWinAscent + os2.usWinDescent
        else:
            hhea = font["hhea"]
            height = hhea.ascent - hhea.descent
        cmap = font.getBestCmap() or {}
        return {
            "name": family,
            "file": os.path.basename(path),
            # libass sizes a font by its line height; CSS sizes it by the em.
            # css_px = ass_size * em_ratio
            "em_ratio": round(upm / height, 4) if height else 0.8,
            "cyrillic": 0x0416 in cmap,
        }
    except Exception as e:
        print(f"Skipping font {path}: {e}")
        return None


def list_fonts() -> list[dict]:
    os.makedirs(FONTS_DIR, exist_ok=True)
    fonts, seen = [], set()
    for fn in sorted(os.listdir(FONTS_DIR)):
        if not fn.lower().endswith((".ttf", ".otf")):
            continue
        info = _font_info(os.path.join(FONTS_DIR, fn))
        if info and info["name"] not in seen:
            seen.add(info["name"])
            fonts.append(info)
    return fonts


def font_ratio(name: str) -> float:
    for f in list_fonts():
        if f["name"] == name:
            return f["em_ratio"]
    return 0.82


def import_font(src_path: str) -> dict:
    """Copies a user font into Assets/Fonts so libass can embed it in clips."""
    import shutil
    info = _font_info(src_path)
    if not info:
        raise ValueError("Не удалось прочитать шрифт")
    os.makedirs(FONTS_DIR, exist_ok=True)
    dst = os.path.join(FONTS_DIR, os.path.basename(src_path))
    if os.path.abspath(dst) != os.path.abspath(src_path):
        shutil.copyfile(src_path, dst)
    return info


# ---------------------------------------------------------------- logo

def resolve_logo(style: dict) -> str | None:
    logo = (style or {}).get("logo") or {}
    if not logo.get("visible"):
        return None
    name = logo.get("file") or ""
    if name and os.path.isabs(name) and os.path.exists(name):
        return name
    if name:
        p = os.path.join(LOGOS_DIR, name)
        if os.path.exists(p):
            return p
    # default: first PNG in Assets/Logo
    if os.path.isdir(LOGOS_DIR):
        for fn in sorted(os.listdir(LOGOS_DIR)):
            if fn.lower().endswith(".png"):
                return os.path.join(LOGOS_DIR, fn)
    return None


# ---------------------------------------------------------------- ASS helpers

def ass_color(hex_color: str, alpha: int = 0) -> str:
    """#RRGGBB -> &HAABBGGRR"""
    h = (hex_color or "#FFFFFF").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        r, g, b = 255, 255, 255
    return f"&H{alpha:02X}{b:02X}{g:02X}{r:02X}"


def ass_inline_color(hex_color: str) -> str:
    return ass_color(hex_color)[4:]  # BBGGRR for \c&H..&


def apply_case(text: str, case: str) -> str:
    if case == "upper":
        return text.upper()
    if case == "lower":
        return text.lower()
    return text


def ass_escape(text: str) -> str:
    return text.replace("\\", "⧵").replace("{", "(").replace("}", ")").replace("\n", " ")


def style_line(name: str, layer: dict) -> str:
    margin = max(0, int(PLAY_W * (100 - float(layer.get("width", 80))) / 200))
    shadow = 4 if layer.get("shadow") else 0
    return (
        f"Style: {name},{layer['font']},{int(layer['size'])},"
        f"{ass_color(layer['color'])},{ass_color(layer['color'])},{ass_color(layer['outline_color'])},&H80000000,"
        f"0,0,0,0,100,100,{float(layer.get('spacing', 0)):g},0,1,{float(layer.get('outline', 0)):g},{shadow},"
        f"5,{margin},{margin},0,1"
    )


def pos_tag(layer: dict) -> str:
    x = PLAY_W * float(layer.get("x", 50)) / 100
    y = PLAY_H * float(layer.get("y", 50)) / 100
    return f"\\an5\\pos({x:.0f},{y:.0f})"
