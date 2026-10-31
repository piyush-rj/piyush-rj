#!/usr/bin/env python3
"""
kerning.py  ·  builds the README hero: kerning-{light,dark}.svg and a still of each.

The README opens broken: the name's letters are scattered, the divider is snapped in two,
words are out of order, off the baseline, centred, the wrong colour, the wrong size. A stickman
walks in from beyond the right edge and fixes it by hand, then leans on the last full stop and
the whole thing falls apart again, which is exactly frame 0. Pure SMIL on one clock (no script,
no CSS, no fonts), so GitHub's image proxy plays it as-is.

    python3 kerning.py         (macOS + Chrome: word and letter positions come from Chrome)

BEAT SHEET (seconds, T = 40)
  0    the mess
  1    he walks in from off the right edge, stops, "!", facepalm, sigh, cracks his knuckles
  5.8  the divider: hauls the broken half off the floor, jumps onto the tilted half, which
       seesaws level under him, slides the piece home. Spark.
  9    the name: snaps his fingers, letter holders appear. Stands the toppled "ush" back up like
       dominoes, squeezes the giant "y" down, flips the "P", swaps "I" and "m", jumps down,
       finds the apostrophe under his foot and flicks it home, kicks "," "i" "H" up into place
 15.8  line 2: a baseline guide draws in; he hops along the staircase stomping each word onto it
 20.1  line 1: carries "I" to the front, the others make room, swaps "design" and "product"
 23.6  line 3: pushes the centred line to the margin, eyedroppers ink from "Currently" onto the
       grey "designing", stomps "Labs" down to size, flicks the full stop home
 31    admires it through a finger frame, nods, dusts off
 34.6  leans on the full stop. It pops out. Everything falls back to frame 0. He shrugs, runs off.
"""
import html
import json
import math
import os
import re
import subprocess
import tempfile

T, EPS = 40.0, 0.002
W, H, FLOOR = 830, 210, 204
H1_Y, RULE_Y, P_Y = 32, 50, [84, 124, 164]
CAP = 11.5                       # cap height of the 16px body text: where feet land on a word
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
FONT_STACK = "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif"

H1_TEXT = "Hi, I'm Piyush"
L1, L1_MESS, L1_MID = "I design product interfaces.", "product design interfaces. I", "I product design interfaces."
L2 = "Every screen starts as a sketch. This one did too."
L3 = "Currently designing at Lomi Labs."

PALETTES = {
    "light": dict(bg="#ffffff", fg="#1f2328", rule="#d1d9e0", smoke="#9aa3ad", wrong="#c3c9d0", accent="#3232ff"),
    "dark": dict(bg="#0d1117", fg="#f0f6fc", rule="#3d444d", smoke="#6e7781", wrong="#484f58", accent="#8c8cff"),
}
SPLINES = {"lin": "0 0 1 1", "out": "0.23 1 0.32 1", "in": "0.55 0 1 0.45", "inout": "0.65 0 0.35 1",
           "snap": "0 0 0.15 1"}
STILL = False                   # still mode: everything frozen at STILL_T, the page finished
STILL_T = None


def n(v):
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def rnd(i):
    x = math.sin(i * 12.9898 + 78.233) * 43758.5453
    return x - math.floor(x)


# ================================================================ keyframes
def ease(s, name):
    if name == "lin" or s <= 0 or s >= 1:
        return s
    x1, y1, x2, y2 = map(float, SPLINES[name].split())
    lo, hi = 0.0, 1.0
    for _ in range(26):
        u = (lo + hi) / 2
        if 3 * (1 - u) ** 2 * u * x1 + 3 * (1 - u) * u * u * x2 + u ** 3 < s:
            lo = u
        else:
            hi = u
    u = (lo + hi) / 2
    return 3 * (1 - u) ** 2 * u * y1 + 3 * (1 - u) * u * u * y2 + u ** 3


class Track:
    def __init__(self, v):
        self.keys = [[0.0, v, "lin"]]

    @property
    def v(self):
        return self.keys[-1][1]

    @property
    def t(self):
        return self.keys[-1][0]

    def add(self, t, v, e="lin"):
        self.keys.append([round(max(t, self.t + EPS), 4), v, e])

    def hold(self, t):
        if t > self.t + 1e-9:
            self.keys.append([round(t, 4), self.v, "lin"])

    def to(self, t0, t1, v, e="out"):
        self.hold(t0)
        self.add(t1, v, e)

    def set(self, t, v):
        self.hold(t - EPS)
        self.add(t, v)

    def seg(self, t):
        ks = self.keys
        i = max(j for j in range(len(ks)) if ks[j][0] <= t + 1e-9)
        if i == len(ks) - 1:
            return ks[i][1], ks[i][1], 0.0
        (t0, a, _), (t1, b, e) = ks[i], ks[i + 1]
        return a, b, ease((t - t0) / (t1 - t0), e)

    def at(self, t):
        a, b, s = self.seg(t)
        if isinstance(a, tuple):
            return tuple(x + (y - x) * s for x, y in zip(a, b))
        return a + (b - a) * s


def animate(attr, tr, fmt=n, tag="animate", extra=""):
    ks = [list(k) for k in tr.keys]
    assert ks[-1][0] <= T + 1e-9, (attr, ks[-1])
    if ks[-1][0] < T:
        ks.append([T, ks[-1][1], "lin"])
    if STILL or len({fmt(v) for _, v, _ in ks}) == 1:
        return ""
    return (f'<{tag} {extra}attributeName="{attr}" values="{";".join(fmt(v) for _, v, _ in ks)}" '
            f'keyTimes="{";".join(f"{t / T:.5f}" for t, _, _ in ks)}" '
            f'keySplines="{";".join(SPLINES[e] for _, _, e in ks[1:])}" calcMode="spline" dur="{n(T)}s" repeatCount="indefinite"/>')


def anim_tf(kind, tr, fmt):
    return animate("transform", tr, fmt, "animateTransform", f'type="{kind}" ')


f_xy = lambda v: f"{n(v[0])} {n(v[1])}"
f_s = lambda v: f"{v:.3f}".rstrip("0").rstrip(".")
f_ss = lambda v: f"{f_s(v[0])} {f_s(v[1])}"
f_u = lambda v: f"{f_s(v)} {f_s(v)}"


def first(tr, fmt=n):
    """The value an element starts with: frame 0, or in still mode the frozen moment."""
    if not STILL:
        return fmt(tr.keys[0][1])
    a, b, s = tr.seg(STILL_T)
    if isinstance(a, str):
        return fmt(a if s < 0.5 else b)
    return fmt(tuple(x + (y - x) * s for x, y in zip(a, b)) if isinstance(a, tuple) else a + (b - a) * s)


# ================================================================ measuring
def measure(lines):
    """Per character [ch, x, advance] for each (text, size, weight), as Chrome sets the line."""
    texts = "".join(f'<text font-size="{s}" font-weight="{w}">{html.escape(t)}</text>' for t, s, w in lines)
    js = ("const r=[...document.querySelectorAll('text')].map(e=>[...e.textContent].map((c,i)=>"
          "[c,e.getStartPositionOfChar(i).x,e.getSubStringLength(i,1)]));"
          "document.getElementById('o').textContent='@@'+JSON.stringify(r)+'@@'")
    page = (f'<!doctype html><meta charset="utf-8"><svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
            f'font-family="{FONT_STACK}">{texts}</svg><pre id="o"></pre><script>{js}</script>')
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
        f.write(page)
    dom = subprocess.run([CHROME, "--headless=new", "--dump-dom", "file://" + f.name],
                         capture_output=True, text=True, check=True).stdout
    os.unlink(f.name)
    return json.loads(html.unescape(re.search(r'<pre id="o">@@(.*?)@@</pre>', dom).group(1)))


def words_of(chars):
    """[(word, x0, x1)] from per-character boxes."""
    out, cur = [], None
    for c, x, w in chars:
        if c == " ":
            cur = None
        elif cur is None:
            cur = [c, x, x + w]
            out.append(cur)
        else:
            cur[0] += c
            cur[2] = x + w
    return [tuple(o) for o in out]


# ================================================================ letters and words
class Item:
    """One glyph or word. Its tracks are offsets from its final, correct place, so the rest of
    the code can say 'put it back' as (0, 0). Frame 0 is the mess."""

    def __init__(self, text, x0, x1, y, size, weight=400, pivot=None):
        self.text, self.x, self.w, self.y, self.size, self.weight = text, x0, x1 - x0, y, size, weight
        self.cx, self.cy = x0 + self.w / 2, y - size * 0.35
        self.pivot = pivot or (self.cx, self.cy)
        self.tr, self.rot, self.sc = Track((0.0, 0.0)), Track(0.0), Track((1.0, 1.0))
        self.ink, self.alt = Track(1), Track(0)
        self.home = dict(tr=(0.0, 0.0), rot=0.0, sc=(1.0, 1.0), wrong=False)

    def mess(self, dx=0.0, dy=0.0, rot=0.0, sc=1.0, wrong=False):
        self.tr.keys[0][1], self.rot.keys[0][1] = (float(dx), float(dy)), float(rot)
        self.sc.keys[0][1] = (float(sc), float(sc))
        if wrong:
            self.ink.keys[0][1], self.alt.keys[0][1] = 0, 1
        self.home = dict(tr=self.tr.keys[0][1], rot=float(rot), sc=self.sc.keys[0][1], wrong=wrong)
        return self

    def center(self, t):
        dx, dy = self.tr.at(t)
        return self.cx + dx, self.cy + dy

    def top(self, t):
        """Where a foot lands on this item at time t (only for upright words)."""
        return self.y + self.tr.at(t)[1] - CAP * self.sc.at(t)[1]

    def move(self, t0, t1, dx, dy, e="out"):
        self.tr.to(t0, t1, (float(dx), float(dy)), e)

    def arc(self, t0, t1, dx, dy, h, rot=None, step=0.03):
        """A thrown or kicked flight to offset (dx, dy), peaking h above the straight line."""
        self.tr.hold(t0)
        self.rot.hold(t0)
        (x0, y0), r0 = self.tr.v, self.rot.v
        k = max(4, round((t1 - t0) / step))
        for i in range(1, k + 1):
            s = i / k
            self.tr.add(t0 + (t1 - t0) * s, (x0 + (dx - x0) * s, y0 + (dy - y0) * s - 4 * h * s * (1 - s)))
            if rot is not None:
                self.rot.add(t0 + (t1 - t0) * s, r0 + (rot - r0) * s)

    def follow(self, c, t0, t1, joint="hands", off=(0.0, 0.0), step=1 / 30):
        """Ride in the stickman's grip from t0 to t1."""
        t = t0
        while True:
            hx, hy = c.grip(t, joint)
            self.tr.add(t, (hx + off[0] - self.cx, hy + off[1] - self.cy))
            if t >= t1 - 1e-6:
                break
            t = min(t1, t + step)

    def snap(self, t, amount=0.12):
        """Lands in its place: a little squash and settle."""
        self.sc.to(t, t + 0.06, (1 + amount, 1 - amount), "out")
        self.sc.to(t + 0.06, t + 0.2, (1.0, 1.0), "out")

    def svg(self, p):
        ax, ay = self.cx, self.y          # scale about the baseline centre: big words still sit on the line
        px, py = self.pivot
        tl = f' textLength="{n(self.w)}"' if len(self.text) > 1 else ""

        def text(col):
            return (f'<text x="{n(self.x)}" y="{self.y}" font-size="{self.size}" font-weight="{self.weight}" '
                    f'fill="{p[col]}"{tl}>{html.escape(self.text)}</text>')

        def layer(op, col):
            if len(op.keys) == 1 and op.keys[0][1] == 0:
                return ""
            return f'<g opacity="{first(op)}">' + animate("opacity", op) + text(col) + "</g>"
        return (f'<g transform="translate({first(self.tr, f_xy)})">' + anim_tf("translate", self.tr, f_xy)
                + f'<g transform="rotate({first(self.rot)} {n(px)} {n(py)})">'
                + anim_tf("rotate", self.rot, lambda a: f"{n(a)} {n(px)} {n(py)}")
                + f'<g transform="translate({n(ax)} {n(ay)})"><g transform="scale({first(self.sc, f_ss)})">'
                + anim_tf("scale", self.sc, f_ss) + f'<g transform="translate({n(-ax)} {n(-ay)})">'
                + layer(self.ink, "fg") + layer(self.alt, "wrong") + "</g></g></g></g></g>")


# ================================================================ the stickman
# feet at (0, 0), up is -y, facing +x. H head, N neck, P pelvis, E elbow, H hand, K knee, F foot.
def pose(*parts, **kw):
    out = {}
    for p in parts:
        out.update(p)
    out.update(kw)
    return out


BODY = dict(H=(0, -30), N=(0, -25), P=(0, -13))
DOWN = dict(LE=(-3, -19), LH=(-4, -12), RE=(3, -19), RH=(4, -12))
UP = dict(LE=(-4, -31), LH=(-3, -38), RE=(4, -31), RH=(3, -38))
LOW = dict(LE=(3, -19), LH=(7, -15), RE=(4, -20), RH=(8, -16))
LEGS = dict(LK=(-2, -6), LF=(-3, 0), RK=(2, -6), RF=(3, 0))
WIDE = dict(LK=(-3, -6), LF=(-5, 0), RK=(3, -6), RF=(5, 0))
POSES = {
    "stand": pose(BODY, DOWN, LEGS),
    "crouch": dict(H=(2, -21), N=(1, -17), P=(0, -9), LE=(-3, -12), LH=(-1, -6), RE=(5, -12), RH=(7, -6),
                   LK=(-6, -6), LF=(-6, 0), RK=(6, -6), RF=(6, 0)),
    "tuck": dict(H=(3, -26), N=(2, -21), P=(0, -12), LE=(5, -17), LH=(4, -12), RE=(6, -17), RH=(6, -11),
                 LK=(6, -10), LF=(1, -6), RK=(7, -11), RF=(2, -7)),
    "fall": pose(BODY, dict(LE=(-6, -30), LH=(-8, -36), RE=(6, -30), RH=(8, -36)),
                 dict(LK=(-3, -7), LF=(-5, -1), RK=(3, -7), RF=(5, -1))),
    "lift": dict(H=(4, -20), N=(3, -16), P=(0, -9), LE=(3, -10), LH=(6, -2), RE=(5, -10), RH=(7, -2),
                 LK=(-5, -6), LF=(-6, 0), RK=(6, -6), RF=(7, 0)),
    "lift_hi": pose(dict(H=(1, -28), N=(1, -23), P=(0, -12)), LOW, WIDE),
    "low": pose(BODY, LOW, LEGS),
    "hold": pose(BODY, UP, WIDE),
    "spread": pose(BODY, dict(LE=(-6, -30), LH=(-11, -37), RE=(6, -30), RH=(11, -37)), WIDE),
    "push": dict(H=(5, -27), N=(4, -22), P=(0, -12), LE=(8, -29), LH=(11, -36), RE=(9, -30), RH=(12, -37),
                 LK=(-4, -6), LF=(-9, 0), RK=(4, -7), RF=(3, 0)),
    "snap": pose(BODY, dict(LE=(-3, -19), LH=(-4, -12), RE=(6, -23), RH=(8, -30)), LEGS),
    "snap2": pose(BODY, dict(LE=(-3, -19), LH=(-4, -12), RE=(6, -22), RH=(10, -28)), LEGS),
    "facepalm": pose(dict(H=(1, -29), N=(0, -24), P=(0, -13)), dict(LE=(-3, -18), LH=(-4, -11), RE=(6, -23), RH=(3, -29)), LEGS),
    "sigh": pose(dict(H=(0, -28), N=(0, -23), P=(0, -12)), dict(LE=(-3, -17), LH=(-3, -10), RE=(3, -17), RH=(3, -10)), LEGS),
    "knuckle": pose(BODY, dict(LE=(4, -19), LH=(8, -22), RE=(5, -20), RH=(8, -23)), WIDE),
    "knuckle2": pose(BODY, dict(LE=(4, -20), LH=(9, -24), RE=(5, -19), RH=(9, -21)), WIDE),
    "kick_prep": dict(H=(2, -29), N=(1, -24), P=(0, -13), LE=(5, -20), LH=(8, -16), RE=(-4, -20), RH=(-7, -16),
                      LK=(1, -6), LF=(2, 0), RK=(-4, -8), RF=(-9, -3)),
    "kick": dict(H=(-2, -29), N=(-1, -24), P=(0, -13), LE=(-5, -21), LH=(-9, -17), RE=(4, -21), RH=(7, -17),
                 LK=(-1, -6), LF=(-2, 0), RK=(7, -8), RF=(13, -5)),
    "reach": pose(BODY, dict(LE=(-3, -19), LH=(-4, -12), RE=(4, -31), RH=(5, -39)), LEGS),
    "press": pose(dict(H=(1, -30), N=(1, -25), P=(0, -13)), dict(LE=(5, -30), LH=(9, -37), RE=(6, -31), RH=(10, -38)), WIDE),
    "press2": pose(dict(H=(1, -28), N=(1, -23), P=(0, -12)), dict(LE=(5, -28), LH=(9, -34), RE=(6, -29), RH=(10, -35)),
                   dict(LK=(-4, -5), LF=(-5, 0), RK=(4, -5), RF=(5, 0))),
    "poke": dict(H=(2, -30), N=(1, -25), P=(0, -13), LE=(-3, -19), LH=(-4, -12), RE=(8, -28), RH=(14, -33),
                 LK=(-3, -6), LF=(-5, 0), RK=(3, -7), RF=(6, 0)),
    "frame": pose(BODY, dict(LE=(5, -23), LH=(10, -30), RE=(6, -21), RH=(12, -25)), LEGS),
    "nod": pose(dict(H=(2, -28), N=(0, -25), P=(0, -13)), DOWN, LEGS),
    "dust": pose(BODY, dict(LE=(4, -20), LH=(7, -18), RE=(5, -19), RH=(8, -20)), LEGS),
    "dust2": pose(BODY, dict(LE=(5, -19), LH=(8, -21), RE=(4, -21), RH=(7, -17)), LEGS),
    "lean": dict(H=(5, -28), N=(4, -23), P=(0, -13), LE=(-1, -18), LH=(-4, -14), RE=(8, -31), RH=(13, -40),
                 LK=(1, -6), LF=(4, 0), RK=(-1, -6), RF=(-3, 0)),
    "stumble": dict(H=(8, -26), N=(6, -21), P=(1, -12), LE=(9, -26), LH=(14, -30), RE=(7, -16), RH=(11, -12),
                    LK=(-3, -6), LF=(-6, 0), RK=(6, -7), RF=(9, 0)),
    "shrug": pose(dict(H=(0, -29), N=(0, -24), P=(0, -13)), dict(LE=(-7, -19), LH=(-10, -24), RE=(7, -19), RH=(10, -24)), LEGS),
    "duck": dict(H=(2, -19), N=(1, -15), P=(0, -8), LE=(-2, -20), LH=(2, -24), RE=(4, -19), RH=(1, -24),
                 LK=(-6, -6), LF=(-7, 0), RK=(6, -6), RF=(7, 0)),
    # walk: contact, down, passing, up; the second step is the mirror
    "walkA": dict(H=(1, -30), N=(1, -25), P=(0, -13), LE=(2, -19), LH=(5, -13), RE=(-2, -19), RH=(-5, -13),
                  LK=(-3, -6), LF=(-8, 0), RK=(4, -7), RF=(8, 0)),
    "walkB": dict(H=(1, -29), N=(1, -24), P=(0, -12), LE=(1, -18), LH=(3, -12), RE=(-1, -18), RH=(-3, -12),
                  LK=(-2, -7), LF=(-6, -3), RK=(3, -6), RF=(4, 0)),
    "walkC": dict(H=(1, -31), N=(1, -26), P=(0, -14), LE=(0, -19), LH=(0, -12), RE=(0, -19), RH=(0, -12),
                  LK=(3, -9), LF=(1, -4), RK=(1, -7), RF=(-1, 0)),
    "walkD": dict(H=(1, -31), N=(1, -26), P=(0, -14), LE=(-1, -19), LH=(-3, -13), RE=(1, -19), RH=(3, -13),
                  LK=(5, -9), LF=(7, -3), RK=(-1, -7), RF=(-4, -1)),
    "runA": dict(H=(6, -28), N=(5, -23), P=(0, -13), LE=(-3, -19), LH=(-8, -15), RE=(9, -20), RH=(13, -25),
                 LK=(-5, -7), LF=(-11, -2), RK=(7, -9), RF=(11, -1)),
    "runB": dict(H=(6, -27), N=(5, -22), P=(0, -12), LE=(-2, -18), LH=(-5, -12), RE=(7, -19), RH=(9, -23),
                 LK=(-7, -8), LF=(-12, -6), RK=(3, -6), RF=(2, 0)),
    "runC": dict(H=(6, -30), N=(5, -25), P=(0, -14), LE=(2, -20), LH=(3, -14), RE=(4, -21), RH=(5, -15),
                 LK=(6, -9), LF=(3, -4), RK=(-3, -8), RF=(-6, -2)),
}
POSES["push2"] = pose(POSES["push"], LK=(3, -7), LF=(2, 0), RK=(-4, -6), RF=(-9, 0))


def mirror(p):
    q = dict(p)
    for a, b in (("LE", "RE"), ("LH", "RH"), ("LK", "RK"), ("LF", "RF")):
        q[a], q[b] = p[b], p[a]
    return q


for _k in ("walkA", "walkB", "walkC", "walkD", "runA", "runB", "runC"):
    POSES[_k + "2"] = mirror(POSES[_k])
for _k in ("walkA", "walkB", "walkC", "walkD", "walkA2", "walkB2", "walkC2", "walkD2"):   # walking with arms full
    POSES["c" + _k] = pose(POSES[_k], UP)
    POSES["l" + _k] = pose(POSES[_k], LOW)
for _k in ("stand", "hold", "low", "lean", "frame", "spread", "press", "knuckle", "reach"):
    POSES[_k + "_b"] = {j: (x, y - (1 if j in ("H", "N") else 0.6 if j[1:] in ("E", "H") and j != "H" else 0))
                        for j, (x, y) in POSES[_k].items()}
WALK = ["walkA", "walkB", "walkC", "walkD", "walkA2", "walkB2", "walkC2", "walkD2"]
RUN = ["runA", "runB", "runC", "runA2", "runB2", "runC2"]
LIMBS = [("N", "P"), ("N", "LE", "LH"), ("N", "RE", "RH"), ("P", "LK", "LF"), ("P", "RK", "RF")]


def lerp_pose(a, b, s):
    return {k: (a[k][0] + (b[k][0] - a[k][0]) * s, a[k][1] + (b[k][1] - a[k][1]) * s) for k in a}


class Man:
    def __init__(self, x, y, face=-1):
        self.pos, self.face = Track((float(x), float(y))), Track(face)
        self.sq, self.rot, self.pz = Track((1.0, 1.0)), Track(0.0), Track("stand")

    # -- primitives
    def pose(self, t, name, tween=0.08, e="out"):
        assert name in POSES, name
        self.pz.hold(t - tween)
        self.pz.add(t, name, e)

    def at(self, t, x, y, e="lin"):
        self.pos.add(t, (float(x), float(y)), e)

    def stay(self, t):
        self.pos.hold(t)

    def turn(self, t, d):
        self.face.set(t, d)

    def idle(self, t0, t1, base="stand", period=0.5):
        t, i = t0, 0
        while t < t1 - 1e-6:
            self.pose(t, base if i % 2 == 0 else base + "_b", period * 0.9, "inout")
            t += period
            i += 1

    def jitter(self, t0, t1, amp, hz=22):
        self.pos.hold(t0)
        x, y = self.pos.v
        t, i = t0, 0
        while t < t1 - 1 / hz:
            t += 1 / hz
            i += 1
            self.pos.add(t, (x + amp * (rnd(i * 3.1) - 0.5) * 2, y + amp * 0.5 * (rnd(i * 7.7) - 0.5) * 2))
        self.pos.add(t1, (x, y))

    def walk(self, t0, t1, x1, cycle=WALK, frame=0.075, e="lin"):
        self.pos.hold(t0)
        x0, y = self.pos.v
        t, i = t0, 0
        while t < t1 - 1e-6:
            self.pose(t, cycle[i % len(cycle)], frame * 0.95, "inout")
            t += frame
            i += 1
            tt = min(t, t1)
            self.pos.add(tt, (x0 + (x1 - x0) * ease((tt - t0) / (t1 - t0), e), y))

    def jump(self, t0, t1, x1, y1, h, step=0.03):
        self.pos.hold(t0)
        x0, y0 = self.pos.v
        k = max(4, round((t1 - t0) / step))
        for i in range(1, k + 1):
            s = i / k
            self.pos.add(t0 + (t1 - t0) * s, (x0 + (x1 - x0) * s, y0 + (y1 - y0) * s - 4 * h * s * (1 - s)))

    def takeoff(self, t, amount=0.14):
        self.sq.to(t - 0.05, t, (1 - amount, 1 + amount), "out")
        self.sq.to(t, t + 0.1, (1.0, 1.0), "out")

    def land(self, t, amount=0.24, pose_name="crouch"):
        self.sq.set(t, (1 + amount, 1 - amount))
        self.sq.to(t, t + 0.09, (0.96, 1.04), "out")
        self.sq.to(t + 0.09, t + 0.18, (1.0, 1.0), "out")
        if pose_name:
            self.pose(t, pose_name, 0.03)

    def hop(self, t0, t1, x1, y1, h, land=0.22, arms=None):
        """Crouch, spring, tuck, reach for the ground, land."""
        self.pose(t0 - 0.05, "crouch", 0.06)
        self.takeoff(t0)
        self.jump(t0, t1, x1, y1, h)
        self.pose(t0 + 0.05, arms or "tuck", 0.05)
        self.pose(t1 - 0.05, arms or "fall", 0.05)
        self.land(t1, land, None if arms else "crouch")

    def flip(self, t0, t1, deg):
        self.rot.hold(t0)
        self.rot.add(t1, self.rot.v + deg, "inout")
        self.rot.add(t1 + EPS, 0.0)

    def ride(self, t0, t1, fy, step=1 / 30):
        """Stand on something moving: feet y follows fy(t)."""
        t = t0
        x = self.pos.at(t0)[0]
        while True:
            self.pos.add(t, (x, fy(t)))
            if t >= t1 - 1e-6:
                break
            t = min(t1, t + step)

    # -- where things are
    def pose_at(self, t):
        a, b, s = self.pz.seg(t)
        return lerp_pose(POSES[a], POSES[b], s)

    def world(self, t, key):
        x, y = self.pose_at(t)[key]
        f = self.face.seg(t)[0]
        qx, qy = self.sq.at(t)
        x, y = x * f * qx, y * qy
        a = math.radians(self.rot.at(t))
        y0 = -13
        x, y = x * math.cos(a) - (y - y0) * math.sin(a), y0 + x * math.sin(a) + (y - y0) * math.cos(a)
        X, Y = self.pos.at(t)
        return X + x, Y + y

    def grip(self, t, joint="hands"):
        if joint == "hands":
            (ax, ay), (bx, by) = self.world(t, "LH"), self.world(t, "RH")
            return (ax + bx) / 2, (ay + by) / 2
        return self.world(t, joint)

    def svg(self, p):
        p0 = POSES[first(self.pz, lambda v: v)]
        pts = lambda P, limb: " ".join(f"{n(P[k][0])},{n(P[k][1])}" for k in limb)

        def body(col, width, r):
            out = [f'<circle r="{r}" fill="{col}" cx="{n(p0["H"][0])}" cy="{n(p0["H"][1])}">'
                   + animate("cx", self.pz, lambda nm: n(POSES[nm]["H"][0]))
                   + animate("cy", self.pz, lambda nm: n(POSES[nm]["H"][1])) + "</circle>"]
            for limb in LIMBS:
                out.append(f'<polyline fill="none" stroke="{col}" stroke-width="{width}" stroke-linecap="round" '
                           f'stroke-linejoin="round" points="{pts(p0, limb)}">'
                           + animate("points", self.pz, lambda nm, limb=limb: pts(POSES[nm], limb)) + "</polyline>")
            return "".join(out)
        return (f'<g transform="translate({first(self.pos, f_xy)})">' + anim_tf("translate", self.pos, f_xy)
                + f'<g transform="rotate({first(self.rot)} 0 -13)">' + anim_tf("rotate", self.rot, lambda a: f"{n(a)} 0 -13")
                + f'<g transform="scale({first(self.face)} 1)">' + anim_tf("scale", self.face, lambda f: f"{f} 1")
                + f'<g transform="scale({first(self.sq, f_ss)})">' + anim_tf("scale", self.sq, f_ss)
                + body(p["bg"], 5.2, 6.2) + body(p["fg"], 2.3, 4.6) + "</g></g></g></g>")


# ================================================================ effects
LAYERS = {k: [] for k in ("under", "props", "fx", "marks")}
FRAME = Track((0.0, 0.0))


def layer(name, fn):
    LAYERS[name].append(fn)
    return fn


def jolt(t, amp):
    FRAME.hold(t - EPS)
    for dt, fx, fy in ((0.03, 0.4, 1), (0.07, -0.3, -0.6), (0.11, 0.2, 0.35), (0.16, 0, 0)):
        FRAME.add(t + dt, (amp * fx, amp * fy), "out")


def rumble(t0, t1, amp):
    FRAME.hold(t0)
    t, i = t0, 0
    while t < t1 - 0.04:
        t += 0.04
        i += 1
        FRAME.add(t, (amp * (rnd(i * 5.3) - 0.5) * 2, amp * (rnd(i * 9.1) - 0.5) * 2))
    FRAME.add(t1, (0.0, 0.0))


def fade(t, peak=1.0, hold=0.0, dur=0.25):
    op = Track(0)
    op.set(t, peak)
    op.hold(t + hold)
    op.add(t + hold + dur, 0, "in")
    return op


def spark(x, y, t, size=8, lay="fx"):
    """An impact: a thin ring that widens and thins, and short lines shooting outward."""
    def svg(p):
        op, rr, sw = fade(t, 1, 0.06, 0.22), Track(size * 0.3), Track(2.0)
        rr.to(t, t + 0.28, size * 2.2)
        sw.to(t, t + 0.28, 0.3)
        out = [f'<g transform="translate({n(x)} {n(y)})"><g opacity="0">' + animate("opacity", op),
               f'<circle r="{n(size * .3)}" fill="none" stroke="{p["fg"]}" stroke-width="2">'
               + animate("r", rr) + animate("stroke-width", sw) + "</circle>"]
        for i in range(6):
            a = i * math.pi / 3 + rnd(i + size) * 0.6
            ux, uy = math.cos(a), math.sin(a)
            seg = Track((size * 0.6, size * 1.4))
            seg.to(t, t + 0.25, (size * 2.0, size * 2.3))
            f = lambda v, ux=ux, uy=uy: f"{n(v[0] * ux)},{n(v[0] * uy)} {n(v[1] * ux)},{n(v[1] * uy)}"
            out.append(f'<polyline fill="none" stroke="{p["fg"]}" stroke-width="1.3" stroke-linecap="round" '
                       f'points="{f(seg.keys[0][1])}">' + animate("points", seg, f) + "</polyline>")
        return "".join(out) + "</g></g>"
    layer(lay, svg)


def glint(x, y, t, size=5, col="fg"):
    """A small four-point twinkle: something clicked into place."""
    def svg(p):
        op, sc = fade(t, 1, 0.05, 0.16), Track(0.2)
        sc.to(t, t + 0.08, 1.0)
        sc.to(t + 0.08, t + 0.22, 0.4, "in")
        L = size
        return (f'<g transform="translate({n(x)} {n(y)})"><g opacity="0">' + animate("opacity", op)
                + f'<g transform="scale(0.2)">' + anim_tf("scale", sc, f_u)
                + f'<path d="M{-L},0 Q0,0 0,{-L} Q0,0 {L},0 Q0,0 0,{L} Q0,0 {-L},0 Z" fill="{p[col]}"/></g></g></g>')
    layer("fx", svg)


def dust(x, y, t, big=False):
    def svg(p):
        pts = [(-16, -5), (-9, -11), (-2, -13), (6, -12), (13, -9), (18, -4)] if big else [(-10, -4), (-4, -8), (4, -8), (10, -4)]
        out = []
        for i, (dx, dy) in enumerate(pts):
            tr = Track((0.0, 0.0))
            tr.to(t, t + 0.34, (dx * 1.2, dy), "out")
            op = fade(t, 0.7, 0, 0.34)
            out.append(f'<g transform="translate({n(x)} {n(y)})"><circle r="{n(1.6 + 0.7 * rnd(i + t))}" fill="{p["smoke"]}" opacity="0">'
                       + animate("opacity", op) + anim_tf("translate", tr, f_xy) + "</circle></g>")
        return "".join(out)
    layer("fx", svg)


def mark(txt, x, y, t, dur=0.55):
    def svg(p):
        op, sc = fade(t, 1, dur * 0.7, dur * 0.3), Track(0.3)
        sc.to(t, t + 0.1, 1.25)
        sc.to(t + 0.1, t + 0.2, 1.0, "inout")
        return (f'<g transform="translate({n(x)} {n(y)})"><g opacity="0">' + animate("opacity", op)
                + f'<g transform="scale(0.3)">' + anim_tf("scale", sc, f_u)
                + f'<text text-anchor="middle" font-size="14" font-weight="700" fill="{p["fg"]}" y="5">{html.escape(txt)}</text></g></g></g>')
    layer("marks", svg)


def guide(x0, y0, x1, y1, t_in, t_out, draw=0.35):
    """An accent design guide that draws itself in and fades away."""
    L = math.hypot(x1 - x0, y1 - y0)
    off, op = Track(L), Track(0)
    op.set(t_in, 1)
    off.to(t_in, t_in + draw, 0.0)
    op.to(t_out, t_out + 0.3, 0)

    def svg(p):
        return (f'<g opacity="0">' + animate("opacity", op)
                + f'<path d="M{n(x0)},{n(y0)} L{n(x1)},{n(y1)}" stroke="{p["accent"]}" stroke-width="1" '
                f'stroke-dasharray="{n(L)} {n(L)}" stroke-dashoffset="{n(L)}">' + animate("stroke-dashoffset", off) + "</path></g>")
    layer("under", svg)


# ================================================================ the page
CH = measure([(H1_TEXT, 32, 600), (L1, 16, 400), (L1_MESS, 16, 400), (L1_MID, 16, 400), (L2, 16, 400), (L3, 16, 400)])
H1 = [Item(c, x, x + w, H1_Y, 32, 600) for c, x, w in CH[0] if c != " "]
G = {f"{c}{i}": it for i, (c, it) in enumerate(zip([it.text for it in H1], H1))}   # H0 i1 ,2 I3 '4 m5 P6 i7 y8 u9 s10 h11
L1W = [Item(w, a, b, P_Y[0], 16) for w, a, b in words_of(CH[1])]
L1X = {w: (a, b) for w, a, b in words_of(CH[2])}
L1M = {w: (a, b) for w, a, b in words_of(CH[3])}
L2W = [Item(w, a, b, P_Y[1], 16) for w, a, b in words_of(CH[4])]
_l3 = words_of(CH[5])
_dot = [c for c in CH[5] if c[0] == "."][-1]
L3W = [Item(w, a, b, P_Y[2], 16) for w, a, b in _l3[:-1]]
LABS = Item("Labs", _l3[-1][1], _dot[1], P_Y[2], 16)
DOT = Item(".", _dot[1], _dot[1] + _dot[2], P_Y[2], 16)
L3W += [LABS, DOT]
ITEMS = H1 + L1W + L2W + L3W
W1 = {it.text: it for it in L1W}
W3 = {it.text: it for it in L3W}

# ---- the divider: the left half tilts on its centre, the right half lies on the floor
RL_ROT = Track(-5.0)              # left half, degrees about (HALF/2, RULE_Y)
RR_TR = Track((0.0, float(FLOOR - 1 - RULE_Y)))   # right half, offset from home
HALF = W / 2


def rule_svg(p):
    return (f'<g transform="rotate({first(RL_ROT)} {n(HALF / 2)} {RULE_Y})">' + anim_tf("rotate", RL_ROT, lambda a: f"{n(a)} {n(HALF / 2)} {RULE_Y}")
            + f'<path d="M0,{RULE_Y} H{n(HALF)}" stroke="{p["rule"]}" stroke-width="1.4"/></g>'
            + f'<g transform="translate({first(RR_TR, f_xy)})">' + anim_tf("translate", RR_TR, f_xy)
            + f'<path d="M{n(HALF)},{RULE_Y} H{W}" stroke="{p["rule"]}" stroke-width="1.4"/></g>')


def on_left_rule(x, ang):
    return RULE_Y + (x - HALF / 2) * math.tan(math.radians(ang))


# ---- frame 0: the mess
def lie(it, mx, rot, extra=0.0):
    """Lay a glyph on the floor at x = mx, turned by rot."""
    half = it.w / 2 if abs(abs(rot) - 90) < 30 else (it.y - it.cy)
    return it.mess(mx - it.cx, FLOOR - half - extra - it.cy, rot)


lie(G["H0"], 64, 90)
lie(G["i1"], 104, -90)
lie(G[",2"], 136, 25, -6)
lie(G["'4"], 178, 0, -8)
G["I3"].mess(G["m5"].cx - G["I3"].cx, 2, 9)
G["m5"].mess(G["I3"].cx - G["m5"].cx + 4, -3, -7)
G["P6"].mess(0, 0, 180)
G["y8"].mess(0, 0, 0, 1.6)
for key, ang in (("u9", 16), ("s10", 31), ("h11", 52)):     # toppled dominoes, leaning right
    it = G[key]
    it.pivot = (it.x + it.w, it.y)
    it.mess(0, 0, ang)
for it in L1W:
    a, _ = L1X[it.text]
    it.mess(a - it.x, (rnd(len(it.text)) - 0.5) * 3, (rnd(len(it.text) * 3) - 0.5) * 6)
STAIRS = [-18, -8, -14, -4, -11, -17, -6, -13, -20, -9]
for it, dy in zip(L2W, STAIRS):
    it.mess(0, dy)
SHIFT = 290                       # line 3 is centred
for it in L3W:
    it.mess(SHIFT, 0)
W3["designing"].mess(SHIFT, 0, wrong=True)
LABS.mess(SHIFT, 0, 0, 2.0)
DOT.mess(330 - DOT.cx, FLOOR - 1 - DOT.y, 0)

# ---- holders for the name's letters
HOLD = [(Track(0), Track(0.85)) for _ in H1]


def holder_in(i, t):
    op, sc = HOLD[i]
    op.to(t, t + 0.14, 1)
    sc.to(t, t + 0.2, 1.0)


def holder_out(i, t):
    op, sc = HOLD[i]
    op.to(t, t + 0.18, 0)
    sc.to(t, t + 0.18, 1.18)
    glint(H1[i].x + H1[i].w, 8, t, 4, "accent")


def holders_svg(p):
    out = []
    for it, (op, sc) in zip(H1, HOLD):
        cx, cy = it.cx, 22
        out.append(f'<g transform="translate({n(cx)} {cy})"><g opacity="0">' + animate("opacity", op)
                   + f'<g transform="scale(0.85)">' + anim_tf("scale", sc, f_u)
                   + f'<rect x="{n(-it.w / 2 - 1)}" y="-15" width="{n(it.w + 2)}" height="31" rx="2" fill="none" '
                   f'stroke="{p["accent"]}" stroke-width="1" stroke-dasharray="2.5 2"/></g></g></g>')
    return "".join(out)


layer("under", holders_svg)

# ---- the eyedropper
DROP_TR, DROP_OP, DROP_SC, DROP_INK = Track((0.0, 0.0)), Track(0), Track(0.4), Track(0)


def dropper_svg(p):
    return (f'<g transform="translate(0 0)">' + anim_tf("translate", DROP_TR, f_xy)
            + f'<g opacity="0">' + animate("opacity", DROP_OP) + f'<g transform="scale(0.4)">' + anim_tf("scale", DROP_SC, f_u)
            + f'<rect x="-1.4" y="-11" width="2.8" height="9" rx="1.2" fill="{p["bg"]}" stroke="{p["fg"]}" stroke-width="0.8"/>'
            + f'<g opacity="0">' + animate("opacity", DROP_INK) + f'<rect x="-0.7" y="-7.5" width="1.4" height="5" fill="{p["fg"]}"/></g>'
            + f'<path d="M0,-11 V-13" stroke="{p["fg"]}" stroke-width="0.9" stroke-linecap="round"/>'
            + f'<circle cy="0" r="2.6" fill="{p["accent"]}"/></g></g></g>')


layer("props", dropper_svg)

# ================================================================ the story
man = Man(870, FLOOR, -1)

# ---- ACT 1  the entrance
man.walk(1.0, 4.0, 629)
man.pose(4.08, "stand", 0.08)
man.turn(4.2, 1)                  # double take
man.turn(4.42, -1)
mark("!", *(lambda h: (h[0], h[1] - 14))(man.world(4.5, "H")), 4.46)
man.pose(4.75, "facepalm", 0.14)
man.pose(5.15, "sigh", 0.2, "inout")
man.sq.to(5.0, 5.2, (1.04, 0.95), "inout")
man.sq.to(5.25, 5.45, (1.0, 1.0), "inout")
man.pose(5.45, "knuckle", 0.12)
man.pose(5.58, "knuckle2", 0.06)
man.pose(5.66, "knuckle", 0.06)
spark(*man.world(5.6, "RH"), 5.6, 3)

# ---- ACT 2  the divider
man.pose(5.95, "lift", 0.18, "inout")
man.stay(5.95)
man.jitter(6.05, 6.45, 0.5)
man.pose(6.75, "lift_hi", 0.26, "inout")
# the right half rides in his hands (its centre is HALF * 1.5, RULE_Y); sampled once the moves exist
_pole = lambda t: (man.grip(t)[0] - HALF * 1.5, man.grip(t)[1] - RULE_Y)
T_LAND = 7.55
LAND_X = 405
man.pose(6.92, "crouch", 0.12)
man.takeoff(7.02)
man.jump(7.02, T_LAND, LAND_X, on_left_rule(LAND_X, -5), 42)
man.pose(7.08, "lift_hi", 0.04)
man.land(T_LAND, 0.24, "lift_hi")
# seesaw: the raised end goes down under him, overshoots, settles level
RL_ROT.hold(T_LAND)
RL_ROT.add(T_LAND + 0.22, 1.4, "in")
RL_ROT.add(T_LAND + 0.34, -0.5, "out")
RL_ROT.add(T_LAND + 0.46, 0.0, "inout")
man.ride(T_LAND, T_LAND + 0.48, lambda t: on_left_rule(LAND_X, RL_ROT.at(t)))
jolt(T_LAND + 0.22, 1.6)
dust(LAND_X, RULE_Y, T_LAND + 0.22)
# slide the half home along the line
T_HOME = 8.45
man.pose(8.0, "push", 0.12)
man.turn(7.95, 1)


def _rr_path():
    RR_TR.hold(6.05)
    t = 6.05
    while t < 7.95:
        t = min(7.95, t + 1 / 30)
        RR_TR.add(t, _pole(t))
    RR_TR.add(T_HOME, (0.0, 0.0), "out")


_rr_path()
spark(HALF, RULE_Y, T_HOME, 7)
jolt(T_HOME, 1.4)
man.pose(8.6, "dust", 0.1)
man.pose(8.72, "dust2", 0.06)
man.pose(8.84, "stand", 0.08)


def shimmer(t):
    """A glint runs along the mended divider."""
    def svg(p):
        tr, op = Track((HALF, float(RULE_Y))), fade(t, 1, 0.25, 0.12)
        tr.to(t, t + 0.4, (float(W), float(RULE_Y)), "inout")
        return (f'<g transform="translate({n(HALF)} {RULE_Y})">' + anim_tf("translate", tr, f_xy)
                + f'<g opacity="0">' + animate("opacity", op) + f'<ellipse rx="14" ry="1.6" fill="{p["accent"]}" opacity="0.8"/></g></g>')
    layer("fx", svg)


shimmer(T_HOME + 0.02)

# ---- ACT 3  the name
man.pose(9.05, "snap", 0.1)
man.pose(9.14, "snap2", 0.04, "snap")
glint(*man.world(9.14, "RH"), 9.14, 4)
for i in range(len(H1)):
    holder_in(i, 9.18 + 0.035 * i)
guide(0, H1_Y, H1[-1].x + H1[-1].w, H1_Y, 9.2, 16.0)
holder_out(7, 9.75)                # the second "i" was right all along
man.turn(9.3, -1)
man.walk(9.3, 9.95, 207)
# the dominoes: push "h" back up, the chain stands up right to left
man.pose(10.02, "poke", 0.07, "snap")
for k, (key, i) in enumerate((("h11", 11), ("s10", 10), ("u9", 9))):
    tt = 10.04 + 0.09 * k
    G[key].rot.to(tt, tt + 0.16, -4.0, "out")
    G[key].rot.to(tt + 0.16, tt + 0.28, 0.0, "inout")
    holder_out(i, tt + 0.2)
man.pose(10.4, "stand", 0.1)
# the giant "y": squeeze it down
man.walk(10.45, 10.65, 152)
yb = G["y8"]
man.pose(10.72, "press", 0.08)
for k, s in enumerate((1.4, 1.2, 1.0)):
    tt = 10.78 + 0.2 * k
    man.pose(tt, "press2", 0.06, "snap")
    man.pose(tt + 0.12, "press", 0.08)
    yb.sc.to(tt, tt + 0.08, (s - 0.06, s + 0.08), "snap")
    yb.sc.to(tt + 0.08, tt + 0.18, (s, s), "out")
yb.snap(11.38, 0.1)
holder_out(8, 11.42)
# the "P": grab it, hop, turn it the right way up mid-air
man.walk(11.45, 11.62, 120)
man.pose(11.68, "press", 0.06)
man.hop(11.74, 12.1, 120, RULE_Y, 12, 0.16, arms="press")
G["P6"].rot.to(11.78, 12.06, 360.0, "inout")
G["P6"].rot.add(12.06 + EPS, 0.0)
G["P6"].tr.to(11.74, 11.92, (0.0, -10.0), "out")
G["P6"].tr.to(11.92, 12.1, (0.0, 0.0), "in")
G["P6"].snap(12.1)
holder_out(6, 12.14)
# "I" and "m": one in each hand, crossed over
man.walk(12.2, 12.4, 68)
man.pose(12.46, "spread", 0.08)
gi, gm = G["I3"], G["m5"]
gi.rot.to(12.5, 12.8, 0.0)
gm.rot.to(12.5, 12.8, 0.0)
gi.arc(12.5, 12.85, 0.0, 0.0, 14)
gm.arc(12.5, 12.85, 0.0, 0.0, -6)
gi.snap(12.85)
gm.snap(12.88)
holder_out(3, 12.88)
holder_out(5, 12.9)
man.pose(12.95, "stand", 0.1)
# down to the floor, onto the apostrophe
man.turn(13.0, 1)
man.hop(13.05, 13.45, 176, FLOOR, 26)
ga = G["'4"]
ga.sc.to(13.45, 13.5, (1.5, 0.5), "snap")       # squashed under his foot
ga.sc.to(13.5, 13.62, (1.0, 1.0), "out")
mark("?", man.world(13.6, "H")[0], man.world(13.6, "H")[1] - 14, 13.58, 0.4)
man.pose(13.62, "stand", 0.1)
man.walk(13.66, 13.8, 186)
man.turn(13.82, -1)
man.pose(13.9, "kick_prep", 0.07)
man.pose(13.98, "kick", 0.04, "snap")
ga.arc(13.98, 14.42, 0.0, 0.0, 60, rot=360.0)
ga.rot.add(14.42 + EPS, 0.0)
ga.snap(14.42)
holder_out(4, 14.44)
# kicks: "," "i" "H"
t_k = 14.1
for key, i, stand_x in ((",2", 2, 150), ("i1", 1, 118), ("H0", 0, 80)):
    it = G[key]
    man.walk(t_k, t_k + 0.16, stand_x)
    man.pose(t_k + 0.22, "kick_prep", 0.06)
    tk = t_k + 0.28
    man.pose(tk, "kick", 0.04, "snap")
    it.arc(tk, tk + 0.42, 0.0, 0.0, 70 if key != "H0" else 90, rot=0.0)
    it.snap(tk + 0.42, 0.14)
    holder_out(i, tk + 0.44)
    dust(stand_x - 10, FLOOR, tk)
    t_k = tk + 0.22
jolt(t_k + 0.2, 1.2)               # the heavy "H" lands
man.pose(t_k + 0.05, "stand", 0.1)

# ---- ACT 5  line 2: stomp the staircase onto a baseline
man.pose(15.75, "snap", 0.1)
man.pose(15.83, "snap2", 0.04, "snap")
guide(0, P_Y[1], L2W[-1].x + L2W[-1].w, P_Y[1], 15.86, 20.0)
t_s = 16.1
first_word = L2W[0]
man.hop(t_s, t_s + 0.42, first_word.cx, first_word.top(0), 34)
man.flip(t_s + 0.05, t_s + 0.38, -360)
t_s += 0.42
man.turn(t_s + 0.02, 1)
for k, it in enumerate(L2W):
    if k:
        man.hop(t_s, t_s + 0.22, it.cx, it.top(0), 10, 0.18)
        t_s += 0.22
    it.move(t_s, t_s + 0.1, 0.0, 0.0, "snap")
    it.snap(t_s + 0.1, 0.08)
    man.ride(t_s, t_s + 0.1, lambda t, it=it: it.top(t))
    dust(it.cx, P_Y[1] - CAP, t_s + 0.06)
    jolt(t_s + 0.06, 0.5)
    t_s += 0.12
END_L2 = t_s
man.pose(END_L2 + 0.1, "stand", 0.1)

# ---- ACT 4  line 1: "I" to the front, swap "design" and "product"
STAND2 = P_Y[1] - CAP
wI = W1["I"]
man.turn(END_L2 + 0.15, -1)
man.walk(END_L2 + 0.2, 20.55, L1X["I"][0] + 1)
man.pose(20.62, "hold", 0.08)
man.pose(20.75, "hold", 0.05)
man.walk(20.75, 22.0, 6, cycle=["c" + k for k in WALK])
wI.follow(man, 20.62, 22.0, off=(0, -5))     # after the walk exists, so the grip is known
# the others make room as he arrives
for k, key in enumerate(("product", "design")):
    it = W1[key]
    a, _ = L1M[key]
    it.move(21.85 + 0.04 * k, 22.1 + 0.04 * k, a - it.x, 0.0)
    it.rot.to(21.85, 22.1, 0.0)
W1["interfaces."].move(21.93, 22.18, 0.0, 0.0)
W1["interfaces."].rot.to(21.93, 22.18, 0.0)
wI.rot.to(22.0, 22.2, 0.0)
wI.move(22.0, 22.22, 0.0, 0.0)
wI.snap(22.22)
man.pose(22.3, "stand", 0.1)
man.turn(22.35, 1)
man.walk(22.4, 22.68, 62)
man.pose(22.74, "spread", 0.08)
wp, wd = W1["product"], W1["design"]
wp.arc(22.8, 23.2, 0.0, 0.0, 18)
wd.arc(22.8, 23.2, 0.0, 0.0, -4)
wp.snap(23.2)
wd.snap(23.23)
glint(wp.x + wp.w, 74, 23.22, 4)
man.pose(23.3, "dust", 0.08)
man.pose(23.42, "dust2", 0.06)
man.pose(23.52, "stand", 0.08)

# ---- ACT 6  line 3: push it to the margin, fix the colour, the size, the full stop
man.hop(23.62, 24.02, 300, FLOOR, 20)
right_edge = W3["Labs"].cx + SHIFT + W3["Labs"].w * 2.0 / 2
man.walk(24.08, 24.55, right_edge + 12)
man.turn(24.57, -1)
man.pose(24.65, "push", 0.08)
T_P0, T_P1 = 24.7, 26.1
for it in L3W:
    if it is not DOT:
        it.tr.to(T_P0, T_P1, (0.0, 0.0), "inout")
man.walk(T_P0, T_P1, right_edge + 12 - SHIFT, cycle=["push", "push2"], frame=0.18, e="inout")
for k in range(4):
    dust(right_edge + 12 - SHIFT * (k + 0.5) / 4 + 4, FLOOR, T_P0 + (T_P1 - T_P0) * (k + 0.5) / 4)
jolt(T_P1, 1.8)
guide(0.5, 146, 0.5, 170, T_P1, T_P1 + 0.3, 0.12)       # the margin it hit
man.pose(T_P1 + 0.04, "stumble", 0.05, "snap")
man.pose(T_P1 + 0.3, "stand", 0.14)
# eyedropper
man.turn(26.5, 1)
man.pose(26.5, "snap", 0.08)
man.pose(26.58, "snap2", 0.04, "snap")
DROP_OP.set(26.6, 1)
DROP_SC.to(26.6, 26.72, 1.0)
cur = W3["Currently"]
man.turn(26.62, -1)
man.walk(26.65, 27.35, cur.cx + 2)
man.turn(27.36, 1)
man.pose(27.45, "reach", 0.1)
DROP_INK.to(27.5, 27.62, 1)
glint(cur.cx + 4, 168, 27.52, 3)
man.pose(27.7, "stand", 0.1)
dg = W3["designing"]
man.walk(27.72, 27.98, dg.cx - 6)
man.pose(28.06, "reach", 0.1)
DROP_INK.to(28.12, 28.22, 0)
dg.alt.to(28.16, 28.4, 0, "inout")
dg.ink.to(28.16, 28.4, 1, "inout")
dg.snap(28.2, 0.08)
DROP_SC.to(28.45, 28.55, 0.4, "in")
DROP_OP.set(28.55, 0)
_t = 26.6
while _t <= 28.56:                # the dropper rides in his right hand
    hx, hy = man.world(_t, "RH")
    DROP_TR.add(_t, (hx, hy - 1))
    _t += 1 / 30


def squirt(t):
    def svg(p):
        out = []
        for i in range(3):
            tr, op = Track((0.0, 0.0)), fade(t + 0.03 * i, 1, 0.05, 0.06)
            tr.to(t + 0.03 * i, t + 0.03 * i + 0.1, (0.0, -6.0 - 2 * i), "out")
            x, y = man.world(t, "RH")
            out.append(f'<g transform="translate({n(x)} {n(y - 14)})"><circle r="1" fill="{p["fg"]}" opacity="0">'
                       + animate("opacity", op) + anim_tf("translate", tr, f_xy) + "</circle></g>")
        return "".join(out)
    layer("fx", svg)


squirt(28.12)
man.pose(28.55, "stand", 0.08)
# "Labs": jump on it, stomp it down to size
lb = LABS
man.hop(28.62, 29.02, lb.cx, lb.top(28.62), 30)
t_l = 29.02
for s in (1.7, 1.35, 1.0):
    man.pose(t_l + 0.08, "tuck", 0.08)
    man.pose(t_l + 0.16, "crouch", 0.04, "snap")
    lb.sc.to(t_l + 0.16, t_l + 0.22, (s, s), "snap")
    man.ride(t_l + 0.16, t_l + 0.24, lambda t: lb.top(t))
    jolt(t_l + 0.18, 0.9)
    dust(lb.cx, lb.top(t_l + 0.24), t_l + 0.18)
    t_l += 0.26
lb.snap(t_l, 0.1)
man.pose(t_l + 0.06, "stand", 0.08)
man.turn(t_l + 0.1, 1)
man.hop(t_l + 0.14, t_l + 0.5, 346, FLOOR, 16)
man.turn(t_l + 0.6, -1)
man.pose(t_l + 0.68, "kick_prep", 0.06)
tf = t_l + 0.74
man.pose(tf, "kick", 0.04, "snap")
DOT.arc(tf, tf + 0.36, 0.0, 0.0, 30)
DOT.snap(tf + 0.36, 0.2)
glint(DOT.cx + 3, DOT.cy - 3, tf + 0.38, 4)
man.pose(tf + 0.15, "stand", 0.1)

# ---- ACT 7  admire (acts 7 and 8 run on from the flick)
A7 = tf + 0.45
man.turn(A7 + 0.00, 1)
man.walk(A7 + 0.05, A7 + 0.75, 470)
man.turn(A7 + 0.80, -1)
man.pose(A7 + 0.90, "frame", 0.12)
man.idle(A7 + 0.90, A7 + 1.55, "frame", 0.32)
man.pose(A7 + 1.65, "nod", 0.08)
man.pose(A7 + 1.75, "stand", 0.08)
man.pose(A7 + 1.85, "nod", 0.08)
man.pose(A7 + 1.97, "stand", 0.08)
man.pose(A7 + 2.10, "dust", 0.08)
man.pose(A7 + 2.22, "dust2", 0.06)
man.pose(A7 + 2.34, "dust", 0.06)
man.pose(A7 + 2.47, "stand", 0.08)

# ---- ACT 8  the full stop
LEAN_X = DOT.cx + 13
man.walk(A7 + 2.55, A7 + 3.50, LEAN_X)
man.pose(A7 + 3.65, "lean", 0.14, "inout")
man.idle(A7 + 3.65, A7 + 4.05, "lean", 0.4)
T_POP = A7 + 4.10
DOT.arc(T_POP, T_POP + 0.5, *DOT.home["tr"], 26)
man.pose(T_POP + 0.02, "stumble", 0.05, "snap")
man.at(T_POP + 0.16, LEAN_X - 6, FLOOR, "out")
mark("!", LEAN_X - 6, FLOOR - 50, T_POP + 0.1, 0.4)
man.pose(T_POP + 0.4, "stand", 0.12)
rumble(A7 + 4.55, A7 + 4.85, 0.8)
T_FALL = A7 + 4.85


def unfix(it, t, dur=0.55, h=14):
    """Back to frame 0: an arc to its mess offset, turning and scaling as it goes."""
    hm = it.home
    it.arc(t, t + dur, *hm["tr"], h, rot=hm["rot"])
    it.sc.to(t, t + dur, hm["sc"], "out")
    if hm["wrong"]:
        it.ink.to(t, t + 0.3, 0)
        it.alt.to(t, t + 0.3, 1)


_order = sorted((it for it in ITEMS if it is not DOT), key=lambda it: math.dist(it.center(T_FALL), DOT.center(0)))
for k, it in enumerate(_order):
    unfix(it, T_FALL + 0.025 * k, 0.5 if it in H1 else 0.42, 20 if it in H1 else 8)
RR_TR.to(T_FALL + 0.2, T_FALL + 0.55, RR_TR.keys[0][1], "in")
RL_ROT.to(T_FALL + 0.5, T_FALL + 0.75, RL_ROT.keys[0][1], "out")
jolt(T_FALL + 0.55, 2.2)
dust(HALF * 1.5, FLOOR, T_FALL + 0.55, big=True)
man.pose(T_FALL - 0.02, "duck", 0.08)              # line 3 sweeps over his head
man.pose(T_FALL + 0.95, "stand", 0.12)
man.turn(A7 + 5.95, 1)
man.turn(A7 + 6.17, -1)
man.pose(A7 + 6.40, "shrug", 0.14)
man.pose(A7 + 6.75, "stand", 0.1)
man.turn(A7 + 6.80, 1)
man.walk(A7 + 6.85, A7 + 8.25, 880, cycle=RUN, frame=0.06, e="in")
man.pose(A7 + 8.35, "stand", 0.05)
man.at(T, 870, FLOOR)                # back where frame 0 has him, out of sight


# ================================================================ render
def render(theme, still=False):
    global STILL, STILL_T
    STILL, STILL_T = still, A7 + 1.2     # the still: the finished page, him admiring it
    p = PALETTES[theme]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{FONT_STACK}">',
           f'<rect width="{W}" height="{H}" fill="{p["bg"]}"/>',
           f'<g transform="translate(0 0)">' + anim_tf("translate", FRAME, f_xy), rule_svg(p)]
    out += [fn(p) for fn in LAYERS["under"]]
    out += [it.svg(p) for it in ITEMS]
    out += [fn(p) for fn in LAYERS["props"]]
    out.append(man.svg(p))
    out += [fn(p) for fn in LAYERS["fx"] + LAYERS["marks"]]
    out.append("</g></svg>")
    return "".join(out)


if __name__ == "__main__":
    for theme in ("light", "dark"):
        for still in (False, True):
            name = f"kerning-{theme}{'-still' if still else ''}.svg"
            svg = render(theme, still)
            with open(name, "w", encoding="utf-8") as f:
                f.write(svg)
            print(f"{name}  {len(svg.encode()) / 1024:.0f} KB")
