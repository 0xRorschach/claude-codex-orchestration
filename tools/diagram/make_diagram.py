#!/usr/bin/env python3
"""Generate the orchestration-flow diagram for the README.

Outputs (relative to the repository root):
  docs/assets/orchestration-flow.svg  static, every step visible, real <text>
  docs/assets/orchestration-flow.gif  animated, one step lit per frame, loops

Both files are drawn from the same scene description below, so they never
drift apart.

Requirements: Python 3.9+ and Pillow. Pillow draws the GIF frames and
measures text widths, so every line is checked to fit its card before
anything is written (with Arial and, when found, DejaVu Sans).
Install it with:  python3 -m pip install pillow

Usage (from the repository root):
  python3 tools/diagram/make_diagram.py
"""

import importlib.util
import os
import sys

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.stderr.write("Pillow is required: python3 -m pip install pillow\n")
    sys.exit(1)

from xml.sax.saxutils import escape

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT_DIR = os.path.join(ROOT, "docs", "assets")
SVG_PATH = os.path.join(OUT_DIR, "orchestration-flow.svg")
GIF_PATH = os.path.join(OUT_DIR, "orchestration-flow.gif")

W, H = 1200, 956
SS = 2                 # supersampling factor for the raster (antialiasing)
STEPS = 9
FRAME_MS = 1200        # one lit step per frame
LAST_FRAME_MS = 3000   # final "everything visible" frame holds longer

# Palette: neutral, opaque, readable whether GitHub shows a light or dark page.
BG = "#F6F8FA"
CARD = "#FFFFFF"
BORDER = "#D0D7DE"
TEXT = "#1F2328"
MUTED = "#57606A"
CLAUDE = "#D97757"       # accent; also marks the Claude family
CLAUDE_FILL = "#FDF0EA"  # fill of the lit step
CODEX = "#0E8A6E"        # second family (Codex)
CONTAINER = "#EEF1F4"

# Opacity per state: lit and final are full, done steps are faded, steps not
# reached yet are ghosts so the layout stays readable but quiet.
ALPHA = {"full": 1.0, "active": 1.0, "past": 0.5, "ghost": 0.16}

FONT_FAMILY_SVG = "Helvetica, Arial, 'DejaVu Sans', 'Liberation Sans', sans-serif"
FONT_CANDIDATES = {
    "regular": [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ],
    "bold": [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ],
}

# name -> (weight, size px, colour)
STYLES = {
    "h1": ("bold", 24, TEXT),
    "sub": ("regular", 15, MUTED),
    "title": ("bold", 17, TEXT),
    "body": ("regular", 15, TEXT),
    "muted": ("regular", 15, MUTED),
    "small": ("regular", 14, MUTED),
    "label": ("bold", 14, MUTED),
    "badge": ("bold", 14, "#FFFFFF"),
}

PAD = 16          # inner left/right padding of cards
LINE_GAP = 22     # baseline distance between body lines
DOT_INDENT = 16   # text indent after a family dot


def find_font(weight):
    for path in FONT_CANDIDATES[weight]:
        if os.path.exists(path):
            return path
    sys.exit("No usable sans-serif font found for weight %r" % weight)


FONT_PATHS = {"regular": find_font("regular"), "bold": find_font("bold")}
_font_cache = {}


def font(style, scale=1):
    weight, size, _ = STYLES[style]
    key = (weight, size * scale)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(FONT_PATHS[weight], size * scale)
    return _font_cache[key]


def text_width(s, style):
    return font(style).getlength(s)


# The SVG is shown with whatever sans-serif the viewer has. DejaVu Sans is
# about 8-10 % wider than Arial/Helvetica, so the layout check measures with
# both. If DejaVu is not installed, Arial widths get a 10 % safety margin.
DEJAVU_DIRS = [
    "/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/TTF",
    "/usr/share/fonts/dejavu", "/Library/Fonts",
    os.path.expanduser("~/Library/Fonts"), "C:/Windows/Fonts",
]
FALLBACK_MARGIN = 1.10


def find_dejavu():
    names = {"regular": "DejaVuSans.ttf", "bold": "DejaVuSans-Bold.ttf"}
    dirs = list(DEJAVU_DIRS)
    # matplotlib bundles DejaVu; locate it without importing matplotlib
    spec = importlib.util.find_spec("matplotlib")
    if spec and spec.submodule_search_locations:
        for loc in spec.submodule_search_locations:
            dirs.append(os.path.join(loc, "mpl-data", "fonts", "ttf"))
    for d in dirs:
        paths = {w: os.path.join(d, n) for w, n in names.items()}
        if all(os.path.exists(p_) for p_ in paths.values()):
            return paths
    return None


DEJAVU_PATHS = find_dejavu()


def check_widths(s, style):
    """Widths used by the layout check: (label, px) per measuring font."""
    weight, size, _ = STYLES[style]
    out = [("Arial", text_width(s, style))]
    if DEJAVU_PATHS:
        f = ImageFont.truetype(DEJAVU_PATHS[weight], size)
        out.append(("DejaVu", f.getlength(s)))
    else:
        out.append(("Arial+10%", out[0][1] * FALLBACK_MARGIN))
    return out


# ---------------------------------------------------------------- scene ----
# A card: lines are (style, text); style "claude"/"codex" draws a family dot
# and renders the text in body style. step 0 = always visible.

def card(cid, x, y, w, h, step, title, lines, kind="card", badge=True, x_text=None):
    return dict(id=cid, x=x, y=y, w=w, h=h, step=step, title=title,
                lines=lines, kind=kind, badge=badge, x_text=x_text)


# Steps follow the visual reading order: 1 User, 2 Main session, 3 gate,
# 4 parallel subagents, 5 evidence, 6 K1, 7 K2, 8 advisor, 9 synthesis.
SUB_W, SUB_GAP, SUB_Y, SUB_H = 257, 20, 410, 118
SUB_X0 = (W - (4 * SUB_W + 3 * SUB_GAP)) // 2
SUB_XC = [SUB_X0 + i * (SUB_W + SUB_GAP) + SUB_W // 2 for i in range(4)]

CARDS = [
    card("legend", 860, 95, 300, 140, 0, "Legend", [
        ("claude", "Claude family (Opus, Sonnet)"),
        ("codex", "Codex family (Astra, Sol)"),
        ("body", "lit card = current step"),
        ("muted", "faded card = step done"),
    ], badge=False),
    card("user_in", 40, 125, 150, 72, 1, "User", [("muted", "gives a task")]),
    card("main", 270, 95, 560, 140, 2, "Main session", [
        ("claude", "Claude Code: Opus · high"),
        ("codex", "Codex: Astra · high"),
        ("body", "plan · decide · brief · review · synthesize"),
        ("muted", "does no hands-on work"),
    ]),
    card("gate", 330, 264, 440, 82, 3, "Agent-type gate (hook)", [
        ("small", "blocks general-purpose / Explore / fork"),
        ("small", "enforces the model from the agent file"),
    ], kind="gate", x_text=58),
    card("pool", 40, 374, 1120, 170, 4, None, [], kind="container"),
    card("explorer", SUB_X0 + 0 * (SUB_W + SUB_GAP), SUB_Y, SUB_W, SUB_H, 4,
         "explorer", [("body", "read-only review")], badge=False),
    card("worker", SUB_X0 + 1 * (SUB_W + SUB_GAP), SUB_Y, SUB_W, SUB_H, 4,
         "worker", [("body", "implements + tests")], badge=False),
    card("researcher", SUB_X0 + 2 * (SUB_W + SUB_GAP), SUB_Y, SUB_W, SUB_H, 4,
         "researcher", [("body", "docs / API check")], badge=False),
    card("scanner", SUB_X0 + 3 * (SUB_W + SUB_GAP), SUB_Y, SUB_W, SUB_H, 4,
         "scanner", [("body", "fast search"), ("claude", "Sonnet (Claude)"),
                      ("codex", "Sol (Codex)")], badge=False),
    card("evidence", 330, 568, 540, 70, 5, "Evidence back to the main session", [
        ("body", "command · exit code · diffstat · file:line"),
    ]),
    card("k1", 40, 682, 330, 140, 6, "K1 · same-family review", [
        ("body", "fresh explorer per task"),
        ("body", "checks spec + quality"),
    ]),
    card("k2", 400, 682, 440, 140, 7, "K2 · cross-family critic", [
        ("codex", "Claude session → Codex"),
        ("small", "Sol at task boundary, Astra at branch end"),
        ("claude", "Codex session → Claude Opus"),
        ("small", "“find the weakest point; if none, say none”"),
    ]),
    card("advisor", 870, 682, 290, 140, 8, "Advisor", [
        ("claude", "Claude sessions only"),
        ("body", "consulted before “done”"),
    ]),
    card("synth", 330, 864, 500, 68, 9, "Main session synthesizes", [
        ("body", "one checked answer goes back"),
    ]),
    card("user_out", 40, 864, 150, 68, 9, "User", [("muted", "gets the result")],
         badge=False),
    card("rule", 960, 838, 200, 108, 9, "Rule", [
        ("small", "irreversible actions"),
        ("small", "(push, publish)"),
        ("small", "→ user approval"),
    ], kind="note", badge=False),
]

# Arrows: polyline points (arrowhead at the last point), step, optional label.
# An arrow lights with the step it leads into.
ARROWS = [
    dict(step=2, pts=[(190, 161), (268, 161)], label=("task", 229, 151, "middle")),
    dict(step=3, pts=[(550, 235), (550, 262)], label=("briefs", 562, 254, "start")),
]
for xc in SUB_XC:
    ARROWS.append(dict(step=4, pts=[(550, 346), (550, 360), (xc, 360), (xc, 408)]))
for xc, tx in zip(SUB_XC, [420, 540, 660, 780]):
    ARROWS.append(dict(step=5, pts=[(xc, 528), (xc, 552), (tx, 552), (tx, 566)]))
ARROWS += [
    dict(step=6, pts=[(330, 603), (205, 603), (205, 680)]),
    dict(step=7, pts=[(370, 752), (398, 752)]),
    dict(step=8, pts=[(840, 752), (868, 752)]),
    dict(step=9, pts=[(920, 822), (920, 898), (832, 898)]),
    dict(step=9, pts=[(330, 898), (192, 898)]),
]

HEADER = [
    ("h1", 40, 46, "Claude Code + Codex orchestration flow"),
    ("sub", 40, 72, "The main session plans, briefs and reviews; subagents do the work "
                    "and return evidence."),
]

POOL_LABEL = ("label", 64, 398, "PARALLEL SUBAGENTS · MEDIUM EFFORT · ONE BRIEF EACH")
# Model per family for the subagent pool, drawn right of the label with dots.
POOL_MODELS = [("claude", 870, 398, "Claude: Opus"), ("codex", 1010, 398, "Codex: Sol")]


# ---------------------------------------------------------------- colour ----

def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def blend(fg, a, bg=BG):
    """Pre-multiply a colour toward the background (no real transparency)."""
    f, b = hex_rgb(fg), hex_rgb(bg)
    return "#%02X%02X%02X" % tuple(round(b[i] + (f[i] - b[i]) * a) for i in range(3))


def state_of(step, current):
    if current is None or step == 0:
        return "full"
    if step < current:
        return "past"
    if step == current:
        return "active"
    return "ghost"


# ------------------------------------------------------------- backends ----

class SvgCanvas:
    def __init__(self):
        self.parts = []

    def rect(self, x, y, w, h, r, fill, stroke=None, sw=1, dash=False):
        attrs = 'x="%g" y="%g" width="%g" height="%g" rx="%g" fill="%s"' % (x, y, w, h, r, fill)
        if stroke:
            attrs += ' stroke="%s" stroke-width="%g"' % (stroke, sw)
            if dash:
                attrs += ' stroke-dasharray="6 5"'
        self.parts.append("<rect %s/>" % attrs)

    def circle(self, cx, cy, r, fill):
        self.parts.append('<circle cx="%g" cy="%g" r="%g" fill="%s"/>' % (cx, cy, r, fill))

    def line(self, pts, color, sw):
        d = " ".join("%g,%g" % p for p in pts)
        self.parts.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="%g" '
                          'stroke-linejoin="round" stroke-linecap="round"/>' % (d, color, sw))

    def polygon(self, pts, color):
        d = " ".join("%g,%g" % p for p in pts)
        self.parts.append('<polygon points="%s" fill="%s"/>' % (d, color))

    def text(self, x, y, s, style, color=None, anchor="start"):
        weight, size, default = STYLES[style]
        self.parts.append(
            '<text x="%g" y="%g" font-size="%d" font-weight="%s" fill="%s" text-anchor="%s">%s</text>'
            % (x, y, size, "700" if weight == "bold" else "400", color or default,
               anchor, escape(s)))

    def render(self):
        head = ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
                'viewBox="0 0 %d %d" role="img" aria-labelledby="t d" '
                'font-family="%s">\n<title id="t">Claude Code + Codex orchestration flow</title>\n'
                '<desc id="d">User gives a task to the main session, which briefs parallel '
                'subagents through an agent-type gate; subagents return evidence; K1 same-family '
                'review, K2 cross-family critic and the advisor check the work; the main session '
                'synthesizes the answer for the user. Irreversible actions need user approval.'
                '</desc>\n' % (W, H, W, H, FONT_FAMILY_SVG))
        return head + "\n".join(self.parts) + "\n</svg>\n"


class PilCanvas:
    def __init__(self):
        self.img = Image.new("RGB", (W * SS, H * SS), BG)
        self.d = ImageDraw.Draw(self.img)

    @staticmethod
    def _s(v):
        return v * SS

    def rect(self, x, y, w, h, r, fill, stroke=None, sw=1, dash=False):
        s = self._s
        box = [s(x), s(y), s(x + w), s(y + h)]
        if dash and stroke:
            self.d.rounded_rectangle(box, radius=s(r), fill=fill)
            self._dashed_round_rect(x, y, w, h, r, stroke, sw)
        else:
            self.d.rounded_rectangle(box, radius=s(r), fill=fill,
                                     outline=stroke, width=int(s(sw)) if stroke else 0)

    def _dashed_round_rect(self, x, y, w, h, r, color, sw):
        s, on, off = self._s, 6, 5
        width = max(1, int(s(sw)))
        segs = [((x + r, y), (x + w - r, y)), ((x + w, y + r), (x + w, y + h - r)),
                ((x + w - r, y + h), (x + r, y + h)), ((x, y + h - r), (x, y + r))]
        for (x1, y1), (x2, y2) in segs:
            length = abs(x2 - x1) + abs(y2 - y1)
            dx, dy = (x2 - x1) / length, (y2 - y1) / length
            t = 0.0
            while t < length:
                e = min(t + on, length)
                self.d.line([s(x1 + dx * t), s(y1 + dy * t), s(x1 + dx * e), s(y1 + dy * e)],
                            fill=color, width=width)
                t += on + off
        for cx, cy, a0 in ((x + r, y + r, 180), (x + w - r, y + r, 270),
                           (x + w - r, y + h - r, 0), (x + r, y + h - r, 90)):
            self.d.arc([s(cx - r), s(cy - r), s(cx + r), s(cy + r)], a0, a0 + 90,
                       fill=color, width=width)

    def circle(self, cx, cy, r, fill):
        s = self._s
        self.d.ellipse([s(cx - r), s(cy - r), s(cx + r), s(cy + r)], fill=fill)

    def line(self, pts, color, sw):
        s = self._s
        self.d.line([(s(x), s(y)) for x, y in pts], fill=color, width=int(s(sw)), joint="curve")

    def polygon(self, pts, color):
        s = self._s
        self.d.polygon([(s(x), s(y)) for x, y in pts], fill=color)

    def text(self, x, y, s_, style, color=None, anchor="start"):
        a = {"start": "ls", "middle": "ms", "end": "rs"}[anchor]
        self.d.text((self._s(x), self._s(y)), s_, font=font(style, SS),
                    fill=color or STYLES[style][2], anchor=a)

    def render(self):
        return self.img.resize((W, H), Image.LANCZOS)


# --------------------------------------------------------------- drawing ----

def draw_gate_icon(cv, x, y, color):
    """A small barrier gate: two posts and two bars."""
    cv.rect(x, y, 5, 30, 1.5, color)
    cv.rect(x + 27, y, 5, 30, 1.5, color)
    cv.rect(x + 3, y + 7, 26, 4, 1, color)
    cv.rect(x + 3, y + 17, 26, 4, 1, color)


def draw_card(cv, c, st):
    a = ALPHA[st]
    active = st == "active"
    kind = c["kind"]
    if kind == "container":
        cv.rect(c["x"], c["y"], c["w"], c["h"], 14, blend(CONTAINER, a),
                blend(CLAUDE if active else "#AFB8C1", a), 2 if active else 1.2, dash=True)
        st_, x, y, txt = POOL_LABEL
        cv.text(x, y, txt, st_, blend(CLAUDE if active else MUTED, a))
        for fam, mx, my, mtxt in POOL_MODELS:
            cv.circle(mx + 5, my - 5, 5, blend(CLAUDE if fam == "claude" else CODEX, a))
            cv.text(mx + DOT_INDENT, my, mtxt, "body", blend(TEXT, a))
    else:
        fill = CLAUDE_FILL if active else CARD
        if kind == "note":
            stroke, sw, dash = (CLAUDE if active else MUTED), 1.6, True
        else:
            stroke, sw, dash = (CLAUDE if active else BORDER), (3 if active else 1.2), False
        cv.rect(c["x"], c["y"], c["w"], c["h"], 10, blend(fill, a), blend(stroke, a), sw, dash)
        tx = c["x"] + (c["x_text"] or PAD)
        if kind == "gate":
            draw_gate_icon(cv, c["x"] + 14, c["y"] + 26, blend(CLAUDE if active else MUTED, a))
        ty = c["y"] + 28
        if c["title"]:
            cv.text(tx, ty, c["title"], "title", blend(TEXT, a))
        ly = ty + (24 if kind in ("gate",) else 26)
        for style, txt in c["lines"]:
            if style in ("claude", "codex"):
                dot = CLAUDE if style == "claude" else CODEX
                cv.circle(tx + 5, ly - 5, 5, blend(dot, a))
                cv.text(tx + DOT_INDENT, ly, txt, "body", blend(TEXT, a))
            else:
                cv.text(tx, ly, txt, style, blend(STYLES[style][2], a))
            ly += 20 if style == "small" else LINE_GAP
    if c["badge"] and c["step"]:
        bx, by = c["x"], c["y"]
        cv.circle(bx, by, 13, blend(CLAUDE if st != "ghost" else MUTED, a))
        cv.text(bx, by + 5, str(c["step"]), "badge", "#FFFFFF" if st != "ghost" else blend("#FFFFFF", a))


def draw_arrow(cv, ar, st):
    a = ALPHA[st]
    active = st == "active"
    color = blend(CLAUDE if active else "#8C959F", a)
    pts = ar["pts"]
    (x1, y1), (x2, y2) = pts[-2], pts[-1]
    hl = 9  # arrowhead length
    if x1 == x2:
        sgn = 1 if y2 > y1 else -1
        head = [(x2, y2), (x2 - 5.5, y2 - sgn * hl), (x2 + 5.5, y2 - sgn * hl)]
        end = (x2, y2 - sgn * (hl - 1))
    else:
        sgn = 1 if x2 > x1 else -1
        head = [(x2, y2), (x2 - sgn * hl, y2 - 5.5), (x2 - sgn * hl, y2 + 5.5)]
        end = (x2 - sgn * (hl - 1), y2)
    cv.line(pts[:-1] + [end], color, 2.6 if active else 1.8)
    cv.polygon(head, color)
    if ar.get("label"):
        txt, lx, ly, anchor = ar["label"]
        cv.text(lx, ly, txt, "label", blend(CLAUDE if active else MUTED, a), anchor)


def draw_scene(cv, current):
    cv.rect(0, 0, W, H, 18, BG)
    for style, x, y, txt in HEADER:
        cv.text(x, y, txt, style)
    # container first so subagent cards sit on top of it
    order = sorted(CARDS, key=lambda c: 0 if c["kind"] == "container" else 1)
    for ar in ARROWS:
        draw_arrow(cv, ar, state_of(ar["step"], current))
    for c in order:
        draw_card(cv, c, state_of(c["step"], current))


# ---------------------------------------------------------------- checks ----

def check_layout():
    """Fail loudly if any text line would overflow its card or the canvas."""
    problems = []
    for c in CARDS:
        if c["kind"] == "container":
            continue
        avail = c["w"] - (c["x_text"] or PAD) - PAD
        items = ([("title", c["title"])] if c["title"] else []) + c["lines"]
        for style, txt in items:
            extra = DOT_INDENT if style in ("claude", "codex") else 0
            for fname, wpx in check_widths(txt, "body" if extra else style):
                if wpx + extra > avail:
                    problems.append("%s [%s]: %r is %.0f px, room %.0f px"
                                    % (c["id"], fname, txt, wpx + extra, avail))
        n_small = sum(1 for s, _ in c["lines"] if s == "small")
        bottom = 28 + 26 + (len(c["lines"]) - 1) * LINE_GAP - n_small * 2 + 6
        if c["lines"] and bottom > c["h"]:
            problems.append("%s: text needs %d px height, card is %d" % (c["id"], bottom, c["h"]))
    for style, x, _, txt in HEADER + [POOL_LABEL]:
        for fname, wpx in check_widths(txt, style):
            if x + wpx > W - 40:
                problems.append("header/label overflow [%s]: %r" % (fname, txt))
    # pool label and the two model tags share one row inside the container
    _, lx, _, ltxt = POOL_LABEL
    right_edge = [lx + max(w_ for _, w_ in check_widths(ltxt, "label"))]
    for _, mx, _, mtxt in POOL_MODELS:
        if mx <= right_edge[-1] + 12:
            problems.append("pool row crowded before %r" % mtxt)
        right_edge.append(mx + DOT_INDENT + max(w_ for _, w_ in check_widths(mtxt, "body")))
    if right_edge[-1] > 1160 - PAD:
        problems.append("pool models overflow the container")
    for a in CARDS:
        for b in CARDS:
            if a["id"] >= b["id"] or "container" in (a["kind"], b["kind"]):
                continue
            if (a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"]
                    and a["y"] < b["y"] + b["h"] and b["y"] < a["y"] + a["h"]):
                problems.append("cards overlap: %s / %s" % (a["id"], b["id"]))
    if problems:
        sys.exit("Layout check failed:\n  " + "\n  ".join(problems))


# ------------------------------------------------------------------ main ----

def main():
    check_layout()
    print("layout check fonts: Arial (%s) + %s" % (
        FONT_PATHS["regular"],
        "DejaVu Sans (%s)" % DEJAVU_PATHS["regular"] if DEJAVU_PATHS
        else "no DejaVu found, Arial +10 %% margin"))
    os.makedirs(OUT_DIR, exist_ok=True)

    svg = SvgCanvas()
    draw_scene(svg, None)
    with open(SVG_PATH, "w", encoding="utf-8") as fh:
        fh.write(svg.render())

    frames = []
    for current in list(range(1, STEPS + 1)) + [None]:
        cv = PilCanvas()
        draw_scene(cv, current)
        rgb = cv.render()
        nodither = getattr(getattr(Image, "Dither", Image), "NONE", 0)
        frames.append(rgb.quantize(colors=256, method=Image.FASTOCTREE, dither=nodither))
    durations = [FRAME_MS] * STEPS + [LAST_FRAME_MS]
    frames[0].save(GIF_PATH, save_all=True, append_images=frames[1:],
                   duration=durations, loop=0, optimize=True, disposal=1)

    print("font regular: %s" % FONT_PATHS["regular"])
    print("font bold:    %s" % FONT_PATHS["bold"])
    print("wrote %s (%d bytes)" % (os.path.relpath(SVG_PATH, ROOT), os.path.getsize(SVG_PATH)))
    print("wrote %s (%d bytes, %d frames)" % (os.path.relpath(GIF_PATH, ROOT),
                                              os.path.getsize(GIF_PATH), len(frames)))


if __name__ == "__main__":
    main()
