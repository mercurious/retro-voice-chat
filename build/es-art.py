#!/usr/bin/env python3
"""EmulationStation artwork for the Retro Voice Chat Ports entry, drawn in the app's own world: the 5x7
pixel font, the four hosts' colours and marquee fields, the title screen's square lattice and the timing bar.

  python3 build/es-art.py      -> ports/images/retro-voice-chat-image.png, ports/images/retro-voice-chat-icon.png

Sized for ROCKNIX's default theme (art-book-next-es, Game Artwork setting):
  image  <image>    1280x720 header. Image shows it whole; Image (Cropped) fills a ~1.87:1 box, losing ~4% at
                    top and bottom, and lays the marquee over the bottom right, so that corner stays quiet.
  icon   <marquee>  512x512 on transparency. Logo view shows it alone; Image (Cropped) shrinks it into the
                    header's bottom right corner (a 60 px box on the Flip 2).
install.sh copies both to the Ports images folder and adds them to gamelist.xml.
Needs Pillow (on the build machine only). Deterministic.
"""
import math
import os
import sys

from PIL import Image, ImageDraw

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "app"))
from screen import F57, hx, lerp, x256          # noqa: E402

OUT = os.path.join(ROOT, "ports", "images")
GROUND = "#0b0d12"                               # portmart's ground, shared by the bar and the credit line
# the hosts, as app/modes/*.py have them: name, host colour (256-colour index), marquee (field, ink)
HOSTS = [("GEMMA", 111, "#1d3270", "#e8eeff"), ("TRIXY", 46, "#0d4a1e", "#d2ffdc"),
         ("ENIGMA", 222, "#45285e", "#f6ead0"), ("ZORK", 214, "#4d2c00", "#ffe2a8")]
HOST = [x256(c) for _, c, _, _ in HOSTS]
HEAR, THINK, SPEAK = "#5fd7ff", "#ffd75f", "#e8eaf0"     # the timing bar's three parts


def glyphs(text, gap=1):
    """The text in the 5x7 font as rows of '#'/'.', and each pixel column's letter index."""
    rows, owner = [""] * 7, []
    for i, ch in enumerate(text.upper()):
        g = F57.get(ch, F57[" "]).split("|")
        for r in range(7):
            rows[r] += g[r] + "." * gap
        owner += [i] * (len(g[0]) + gap)
    return [r[:-gap] for r in rows], owner[:-gap]


def text_px(d, x, y, text, u, colorf, gap=1):
    """Pixel text at (x, y), u screen pixels per font pixel; colorf(letter index) per letter. Returns width."""
    rows, owner = glyphs(text, gap)
    for r, line in enumerate(rows):
        for c, v in enumerate(line):
            if v == "#":
                d.rectangle([x + c * u, y + r * u, x + (c + 1) * u - 1, y + (r + 1) * u - 1], fill=colorf(owner[c]))
    return len(rows[0]) * u


def text_w(text, u, gap=1):
    return len(glyphs(text, gap)[0][0]) * u


def header():
    W, H = 1280, 720
    img = Image.new("RGB", (W, H), GROUND)
    d = ImageDraw.Draw(img)
    # the sweep lattice: squares on a 32 px grid that swell and brighten along a diagonal wave, each band of
    # the wave tinted by the next host, faded out toward the bottom right where the theme lays the logo
    S = 32
    for gy in range(H // S + 1):
        for gx in range(W // S + 1):
            ph = (gx + gy) * 0.05
            lv = (math.sin(2 * math.pi * (0.35 - ph)) + 1) / 2
            quiet = max(0.0, min(1.0, (gx / (W / S) + gy / (H / S)) - 0.95))    # 0 top left .. 1 bottom right
            lv *= 1 - 0.85 * quiet
            size = round(2 + 8 * lv)
            col = lerp(GROUND, HOST[(gx + gy) // 9 % 4], 0.10 + 0.30 * lv)
            cx, cy = gx * S + S // 2, gy * S + S // 2
            d.rectangle([cx - size // 2, cy - size // 2, cx - size // 2 + size - 1, cy - size // 2 + size - 1], fill=col)
    # the marquee rail: the four hosts' fields down the left edge, each name in its ink
    rail_w, top = 236, 40
    band = (H - 2 * top) // 4
    for i, (name, _, field, ink) in enumerate(HOSTS):
        y0 = top + i * band
        d.rectangle([0, y0, rail_w - 1, y0 + band - 9], fill=field)
        d.rectangle([24, y0 + 24, 24 + 15, y0 + 24 + 15], fill=HOST[i])              # the host's swatch
        text_px(d, 56, y0 + 22, name, 3, lambda k, c=ink: c)
    # the wordmark, the hosts' colours one per letter (the title screen's chase, caught mid-step)
    x0, u, y0 = rail_w + 56, 18, 64
    # the words sit on clean ground, as on the title screen: the squares move around them, not through them
    d.rectangle([x0 - 24, y0 - 18, x0 + text_w("RETRO", u) + 24, y0 + 25 * u + 26 + 30], fill=GROUND)
    for line, y, step in (("RETRO", y0, 0), ("VOICE", y0 + 9 * u, 1), ("CHAT", y0 + 18 * u, 2)):
        text_px(d, x0, y, line, u, lambda k, s=step: HOST[(k + s) % 4])
    # a turn's timing bar under it: hear, think, speak, each as long as it took, and the time in pixel digits
    by = y0 + 25 * u + 26
    x = x0
    for secs, col in ((1.2, HEAR), (1.4, THINK), (0.8, SPEAK)):
        w = round(secs * 64)
        d.rectangle([x, by, x + w - 5, by + 11], fill=col)
        x += w
    text_px(d, x + 28, by - 11, "3.4", 5, lambda k: HOST[1])
    return img


def icon():
    N, P = 512, 32                   # a 16 x 16 pixel grid
    img = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # a speech bubble drawn in pixels, its body in the four hosts' colours (a 4-pixel band each), the tail at
    # the bottom left, and "RV" in the 5x7 font knocked out of it in the ground colour
    body = ["................",
            "................",
            "..############..",
            ".##############.",
            "################",
            "################",
            "################",
            "################",
            "################",
            "################",
            ".##############.",
            "..############..",
            ".###............",
            ".##.............",
            ".#..............",
            "................"]
    for r, line in enumerate(body):
        for c, v in enumerate(line):
            if v == "#":
                d.rectangle([c * P, r * P, (c + 1) * P - 1, (r + 1) * P - 1], fill=HOST[c * 4 // 16])
    u = 20
    tw = text_w("RV", u, gap=2)
    text_px(d, (N - tw) // 2, 2 * P + (10 * P - 7 * u) // 2, "RV", u, lambda k: GROUND, gap=2)
    return img


def main():
    os.makedirs(OUT, exist_ok=True)
    header().save(os.path.join(OUT, "retro-voice-chat-image.png"), optimize=True)
    icon().save(os.path.join(OUT, "retro-voice-chat-icon.png"), optimize=True)
    for n in ("retro-voice-chat-image.png", "retro-voice-chat-icon.png"):
        print(os.path.join(OUT, n))


if __name__ == "__main__":
    main()
