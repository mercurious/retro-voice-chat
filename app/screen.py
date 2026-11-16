"""The screen as a grid of cells: what render() draws into, then writes out in one go.

Colours are "#rrggbb" (truecolour, which foot shows as is) or an int (a 256-colour index, the modes' own
palettes). The 5x7 pixel font and the button pills are portmart's (ui/draw.py), so the two apps look like one
family on the same handheld.
"""

import math

RST = "\033[0m"

# pad colours, by the label printed on the button (as portmart)
PAD = {"A": "#4ade80", "B": "#ff5a6e", "X": "#5aa9ff", "Y": "#ffb000", "R1": "#9ca3b0",
       "SELECT": "#d4c090", "START": "#d4c090", "▲▼": "#9ca3b0"}
INK = "#05060a"

F57 = {
    "A": ".###.|#...#|#...#|#####|#...#|#...#|#...#", "B": "####.|#...#|#...#|####.|#...#|#...#|####.",
    "C": ".###.|#...#|#....|#....|#....|#...#|.###.", "D": "####.|#...#|#...#|#...#|#...#|#...#|####.",
    "E": "#####|#....|#....|####.|#....|#....|#####", "F": "#####|#....|#....|####.|#....|#....|#....",
    "G": ".###.|#...#|#....|#.###|#...#|#...#|.####", "H": "#...#|#...#|#...#|#####|#...#|#...#|#...#",
    "I": ".###.|..#..|..#..|..#..|..#..|..#..|.###.", "J": "..###|...#.|...#.|...#.|#..#.|#..#.|.##..",
    "K": "#...#|#..#.|#.#..|##...|#.#..|#..#.|#...#", "L": "#....|#....|#....|#....|#....|#....|#####",
    "M": "#...#|##.##|#.#.#|#.#.#|#...#|#...#|#...#", "N": "#...#|#...#|##..#|#.#.#|#..##|#...#|#...#",
    "O": ".###.|#...#|#...#|#...#|#...#|#...#|.###.", "P": "####.|#...#|#...#|####.|#....|#....|#....",
    "Q": ".###.|#...#|#...#|#...#|#.#.#|#..#.|.##.#", "R": "####.|#...#|#...#|####.|#.#..|#..#.|#...#",
    "S": ".####|#....|#....|.###.|....#|....#|####.", "T": "#####|..#..|..#..|..#..|..#..|..#..|..#..",
    "U": "#...#|#...#|#...#|#...#|#...#|#...#|.###.", "V": "#...#|#...#|#...#|#...#|#...#|.#.#.|..#..",
    "W": "#...#|#...#|#...#|#.#.#|#.#.#|#.#.#|.#.#.", "X": "#...#|#...#|.#.#.|..#..|.#.#.|#...#|#...#",
    "Y": "#...#|#...#|.#.#.|..#..|..#..|..#..|..#..", "Z": "#####|....#|...#.|..#..|.#...|#....|#####",
    "0": ".###.|#...#|#..##|#.#.#|##..#|#...#|.###.", "1": "..#..|.##..|..#..|..#..|..#..|..#..|.###.",
    "2": ".###.|#...#|....#|...#.|..#..|.#...|#####", "3": "####.|....#|....#|.###.|....#|....#|####.",
    "4": "...#.|..##.|.#.#.|#..#.|#####|...#.|...#.", "5": "#####|#....|####.|....#|....#|#...#|.###.",
    "6": "..##.|.#...|#....|####.|#...#|#...#|.###.", "7": "#####|....#|...#.|..#..|.#...|.#...|.#...",
    "8": ".###.|#...#|#...#|.###.|#...#|#...#|.###.", "9": ".###.|#...#|#...#|.####|....#|...#.|.##..",
    " ": "...|...|...|...|...|...|...", ".": "..|..|..|..|..|##|##", "-": ".....|.....|.....|.###.|.....|.....|.....",
}


def x256(n):
    """A 256-colour index as "#rrggbb" (xterm's palette), for blending a mode's colours."""
    if n < 16:
        return ("#000000", "#800000", "#008000", "#808000", "#000080", "#800080", "#008080", "#c0c0c0",
                "#808080", "#ff0000", "#00ff00", "#ffff00", "#0000ff", "#ff00ff", "#00ffff", "#ffffff")[n]
    if n < 232:
        lv = (0, 95, 135, 175, 215, 255)
        n -= 16
        return "#%02x%02x%02x" % (lv[n // 36], lv[n // 6 % 6], lv[n % 6])
    v = 8 + 10 * (n - 232)
    return "#%02x%02x%02x" % (v, v, v)


def hx(c):
    return int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)


def lerp(a, b, t):
    (r0, g0, b0), (r1, g1, b1) = hx(a), hx(b)
    return "#%02x%02x%02x" % (round(r0 + (r1 - r0) * t), round(g0 + (g1 - g0) * t), round(b0 + (b1 - b0) * t))


_SGR = {}


def sgr(c, base):
    """The escape for a foreground (38) or background (48) colour, memoized: a frame repeats a few colours
    thousands of times."""
    s = _SGR.get((c, base))
    if s is None:
        if c is None:
            s = ""
        elif isinstance(c, int):
            s = f"\033[{base};5;{c}m"
        else:
            s = "\033[%d;2;%d;%d;%dm" % ((base,) + hx(c))
        if len(_SGR) > 4096:       # the header's throb blends colours; keep the table bounded
            _SGR.clear()
        _SGR[(c, base)] = s
    return s


class Buffer:
    """cols x rows cells of [char, fg, bg, bold]; None colours are the terminal's own (OSC 10/11)."""

    def __init__(self, cols, rows):
        self.cols, self.rows = cols, rows
        self.cells = [[[" ", None, None, False] for _ in range(cols)] for _ in range(rows)]

    def put(self, x, y, text, fg=None, bg=None, bold=False):
        """Text at (x, y), clipped to the row; bg None keeps what is under it. Returns the x after it."""
        if 0 <= y < self.rows:
            row = self.cells[y]
            for i, ch in enumerate(text):
                if 0 <= x + i < self.cols:
                    cell = row[x + i]
                    cell[0], cell[1], cell[3] = ch, fg, bold
                    if bg is not None:
                        cell[2] = bg
        return x + len(text)

    def rput(self, x_end, y, text, fg=None, bg=None, bold=False):
        """Text that ends at x_end (exclusive)."""
        return self.put(x_end - len(text), y, text, fg, bg, bold)

    def fill(self, x, y, w, h, bg):
        for r in range(max(0, y), min(self.rows, y + h)):
            for c in range(max(0, x), min(self.cols, x + w)):
                self.cells[r][c] = [" ", None, bg, False]

    BACKDROPS = ("ripple", "breathe", "sweep")
    DOTS = " ·▪■"                   # a square's sizes, smallest to largest
    STEPS = 6                       # brightness levels; quantized, so calm parts of the screen don't change
    _phases = {}

    def backdrop(self, kind, y, h, t, ground, ink):
        """The title screen's moving background over rows y..y+h, in near shades between `ground` and `ink`.
        A square is 2 columns by 1 row (a cell is about 1:2), so the grid is square on screen.
          ripple   a checkerboard whose lit squares brighten and fade in rings spreading from the centre
          breathe  a lattice of squares that grow and shrink, alternate squares in counter-phase
          sweep    the lattice again, with a wave of size and brightness rolling across it diagonally
        Each square's phase offset is worked out once per screen size; a frame is one sine per square."""
        n, rows = self.STEPS, range(max(0, y), min(self.rows, y + h))
        nsq = (self.cols + 1) // 2
        key = (kind, self.cols, self.rows)
        phases = self._phases.get(key)
        if phases is None:      # per row, per square: (phase offset, lit) for ripple, offset for the lattices
            cx, cy = self.cols / 4, self.rows / 2
            if kind == "ripple":
                phases = [[(-math.hypot(s - cx, r - cy) * 0.09, (s + r) % 2) for s in range(nsq)]
                          for r in range(self.rows)]
            elif kind == "breathe":
                phases = [[0.5 * ((s + r) % 2) for s in range(nsq)] for r in range(self.rows)]
            else:
                phases = [[-(s + r) * 0.05 for s in range(nsq)] for r in range(self.rows)]
            self._phases[key] = phases
        speed = {"ripple": 0.6, "breathe": 0.5}.get(kind, 0.4)
        level = lambda off: int((math.sin(6.283185307 * (t * speed + off)) + 1) / 2 * (n - 1) + 0.5)
        cols = self.cols
        if kind == "ripple":
            tint = [lerp(ground, ink, 0.03 + 0.12 * k / (n - 1)) for k in range(n)]      # a lit square's ground
            for r in rows:
                row, ph = self.cells[r], phases[r]
                for s in range(nsq):
                    off, lit = ph[s]
                    bg = tint[level(off)] if lit else ground
                    row[2 * s] = [" ", None, bg, False]
                    if 2 * s + 1 < cols:
                        row[2 * s + 1] = [" ", None, bg, False]
            return
        dots = [lerp(ground, ink, 0.08 + 0.22 * k / (n - 1)) for k in range(n)]           # a square glyph's ink
        glyph = [self.DOTS[int(k * (len(self.DOTS) - 1) / (n - 1) + 0.5)] for k in range(n)]
        for r in rows:
            row, ph = self.cells[r], phases[r]
            for s in range(nsq):
                k = level(ph[s])
                row[2 * s] = [glyph[k], dots[k], ground, False]
                if 2 * s + 1 < cols:        # same colours as its glyph cell, so the escape run isn't broken
                    row[2 * s + 1] = [" ", dots[k], ground, False]

    def pixels(self, x, y, grid, colorf):
        """Pixel art, two pixel rows per cell (half blocks); grid rows are strings, '#' = lit.
        colorf(px, py) gives each lit pixel's colour."""
        for cy in range((len(grid) + 1) // 2):
            top, bot = grid[2 * cy], grid[2 * cy + 1] if 2 * cy + 1 < len(grid) else ""
            for px in range(len(top)):
                a, b = top[px] == "#", px < len(bot) and bot[px] == "#"
                if not (a or b) or not (0 <= x + px < self.cols and 0 <= y + cy < self.rows):
                    continue
                cell = self.cells[y + cy][x + px]
                ca, cb = colorf(px, 2 * cy) if a else None, colorf(px, 2 * cy + 1) if b else None
                if a and b and ca == cb:
                    cell[0], cell[1] = "█", ca
                elif a and b:
                    cell[0], cell[1], cell[2] = "▀", ca, cb
                elif a:
                    cell[0], cell[1] = "▀", ca
                else:
                    cell[0], cell[1] = "▄", cb
                cell[3] = False

    def big(self, x, y, text, colorf, gap=1):
        """Text in the 5x7 pixel font (4 rows tall); returns its width in cells."""
        rows = [""] * 7
        for ch in text.upper():
            g = F57.get(ch, F57[" "]).split("|")
            for i in range(7):
                rows[i] += g[i] + "." * gap
        rows = [r[:-gap] if gap else r for r in rows]
        self.pixels(x, y, rows, colorf)
        return len(rows[0])

    def pill(self, x, y, label, color, on=None):
        """A button cap, portmart style: ◖A◗ in the pad's colour."""
        self.put(x, y, "◖", color, on)
        self.put(x + 1, y, label, INK, color, True)
        return self.put(x + 1 + len(label), y, "◗", color, on)

    def ansi(self, prev=None):
        """The grid as one write, colours changed only where they change. With the previous frame (same size),
        only the rows that differ are sent: a spinner turning rewrites one row, not the screen."""
        same = prev is not None and (prev.cols, prev.rows) == (self.cols, self.rows)
        out = []
        for y, row in enumerate(self.cells):
            if same and prev.cells[y] == row:
                continue
            out.append(f"\033[{y + 1};1H")
            cur = None
            for ch, fg, bg, bold in row:
                key = (fg, bg, bold)
                if key != cur:
                    out.append(RST + ("\033[1m" if bold else "") + sgr(fg, 38) + sgr(bg, 48))
                    cur = key
                out.append(ch)
            out.append(RST)
        return "".join(out)


def big_width(text, gap=1):
    return sum(len(F57.get(ch, F57[" "]).split("|")[0]) + gap for ch in text.upper()) - gap
