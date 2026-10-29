"""Blend modes and shape masks, measured on lossless exports and rendered frames. Port of
packages/core/scripts/smoke-masks.ts (judge/PORTING.md has the map of its sections).

a. Blend modes: a picture of grey bands on v1 over a picture of colour bands on v0, one v1 clip per mode (the 13
   modes, and five of them at opacity 0.6). Every flat cell of every mode must be the W3C formula applied to the two
   pictures as the same export shows each alone (with the original's slack: 2 levels of each input carried through
   the formula, and 3 more); `add` is min(1, base + opacity x layer). The pictures alone are checked against the
   stills' own colours first, so the reference is not whatever the editor exported. A mode set back to normal
   exports the same frames as a clip that never had one.
b. Masks on a square red picture on v1 (fitted 360x360 in the middle of a 640x360 canvas) over blue: ellipse, rect
   (and its corner roundness), linear (and turned 90 degrees), mirror, invert (the letterbox stays transparent), an
   anti-aliased edge, a feathered edge (graded, monotonic, and as wide as PROTOCOL's `feather` says: 90 % to 10 % of
   the clip across 0.3 of the picture's short side, centred on the line), the mask following the clip's transform and
   rotation, a mask with a blend mode, render_frame after a mask change, undo, clamping, and the refusals (a blend
   mode on an adjustment layer, a mode the editor does not have). The mask on a clip whose scale is animated
   (set_keyframes: the editor's other transform path) at the animation's two ends.
c. A mask on a keyed clip (it multiplies the key, it does not undo it), on a clip with its own alpha, on an adjustment
   layer (the look only inside it), and a blend mode set on a clip joined by a transition (the whole run gets it).
d. `add` leaves the frames before the layer and the picture outside it exactly as they were; a multiply clip's white
   text stays white (only the picture blends); after the run's first clip loses its mode, a frame shown only by the
   second clip of the run composites normally (render_frame).
e. The same mask (an ellipse, w and h 0.5) on two pictures of different sizes in one export: on the square picture it
   is a circle, on a picture that fills the canvas a wide ellipse, each drawn for its own picture; then the canvas is
   doubled (set_project) and the project exported again: it exports, and each shape is twice as large.

Every picture is a fixture of make.sh (mk-*: exact RGB stills, and an FFV1 clip with alpha). The exports are lossless
(PROTOCOL.md, "Exports"), so the pixels are the compositing's own values. Colours are read from an export as BT.709
limited range (as it is written), as the mean of a small block, with the original's tolerances.

Two exports that would look the same by design (a mode set back to normal and a clip that never had one; a turned
clip and a turned mask) differ in length (the picture below runs TAIL frames longer in the second), and the third of
the render_frame shots moves the mask, so no earlier export or frame passes for another (README.md, threat model).

Every check is recorded on every path (a check whose input is missing fails with the reason), so CHECKS is exact.
"""
import observe
import edits

PORT_BOUND = True
TIMEOUT = 1500
CHECKS = 108
EXTRA_MEDIA = ("mk-bands.png", "mk-greys.png", "mk-blue.png", "mk-red.png", "mk-white.png", "mk-grey64.png",
               "mk-redsq.png", "mk-greenbox.png", "mk-disc.mkv")

W, H, FPS = 640, 360, 30
RED, BLUE = (255, 0, 0), (0, 0, 255)
C = (320, 180)
BASES = [(230, 40, 40), (40, 200, 60), (40, 60, 220), (240, 220, 60), (128, 128, 128), (20, 20, 20), (250, 250, 250),
         (200, 120, 180)]
GREYS = [0, 40, 100, 160, 210, 255]
BW, GH = W // len(BASES), H // len(GREYS)
MODES = ["normal", "multiply", "screen", "overlay", "darken", "lighten", "color-dodge", "color-burn", "hard-light",
         "soft-light", "difference", "exclusion", "add"]
CASES = [(mode, 1) for mode in MODES] + [(mode, 0.6) for mode in ("screen", "add", "soft-light", "color-dodge",
                                                                    "multiply")]
SEG = 8  # frames per v1 clip of the blend modes
TAIL = 3  # frames by which an export runs longer than the one it must not be taken for


def _soft_light(b, s):
    if s <= 0.5:
        return b - (1 - 2 * s) * b * (1 - b)
    dd = ((16 * b - 12) * b + 4) * b if b <= 0.25 else b ** 0.5
    return b + (2 * s - 1) * (dd - b)


# The W3C compositing formulas (0..1), base b below, layer s.
W3C = {
    "multiply": lambda b, s: b * s,
    "screen": lambda b, s: b + s - b * s,
    "overlay": lambda b, s: s * 2 * b if b <= 0.5 else 1 - (1 - s) * (1 - (2 * b - 1)),
    "darken": min,
    "lighten": max,
    "color-dodge": lambda b, s: 0 if b == 0 else (1 if s == 1 else min(1, b / (1 - s))),
    "color-burn": lambda b, s: 1 if b == 1 else (0 if s == 0 else 1 - min(1, (1 - b) / s)),
    "hard-light": lambda b, s: b * 2 * s if s <= 0.5 else 1 - (1 - b) * (1 - (2 * s - 1)),
    "soft-light": _soft_light,
    "difference": lambda b, s: abs(b - s),
    "exclusion": lambda b, s: b + s - 2 * b * s,
}


def composite(mode, b255, s255, a):
    """The composited value (0..255) of one channel for `mode` at layer opacity `a`."""
    b, s = min(255, max(0, b255)) / 255, min(255, max(0, s255)) / 255
    if mode == "normal":
        return 255 * ((1 - a) * b + a * s)
    if mode == "add":
        return 255 * min(1, b + a * s)
    return 255 * ((1 - a) * b + a * min(1, max(0, W3C[mode](b, s))))


def ref_range(mode, b, s, a, slack=2):
    vals = [composite(mode, b + db, s + ds, a) for db in range(-slack, slack + 1) for ds in range(-slack, slack + 1)]
    return min(vals), max(vals)


def near(c, want, tol):
    return c is not None and all(abs(a - b) <= tol for a, b in zip(c, want))


def fmt(c):
    return "(" + ",".join(str(int(round(v))) for v in c) + ")" if c else str(c)


# The feathered edge: PROTOCOL's `feather` is the soft edge's width from where the clip shows at 90 % to where it shows
# at 10 %, as a fraction of the picture's short side. v0.2.0 reads 107.3 px for 108; an edge 1.2 times as wide would
# read about 130, one 1.6 times as wide about 173 (judge/PORTING.md, masks b).
FEATHER, FEATHER_TOL, FEATHER_MID = 0.3, 0.10, 3


def soft_edge(pic, centre, reach=150, band=20):
    """The red across a horizontal edge at row centre[1] of `pic` (the clip's red above, the track below's blue under
    it): the mean red of each row of the columns centre[0] +- band, from `reach` rows above to `reach` rows under.
    -> {"top", "bottom": the red at the two ends; "worst_rise": the largest rise from a row to the next; "width": the
    distance between the 90 % and 10 % points of top..bottom (linear between row middles), "middle": their midpoint's
    distance from the line (the top of row centre[1]), or None when the red does not cross them; "samples": red at -60,
    -30, -10, 0, 10, 30, 60 px}"""
    cx, cy = centre
    y0 = cy - reach
    prof = [pic.box(cx - band, y, 2 * band + 1, 1)[0] for y in range(y0, cy + reach + 1)]
    top, bottom = prof[0], prof[-1]

    def crossing(level):
        for i in range(1, len(prof)):
            if prof[i] <= level <= prof[i - 1] and prof[i] < prof[i - 1]:
                return y0 + i - 0.5 + (prof[i - 1] - level) / (prof[i - 1] - prof[i])
        return None
    y90, y10 = crossing(bottom + 0.9 * (top - bottom)), crossing(bottom + 0.1 * (top - bottom))
    ok = y90 is not None and y10 is not None
    return {"top": round(top, 1), "bottom": round(bottom, 1),
            "worst_rise": round(max(b - a for a, b in zip(prof, prof[1:])), 1),
            "width": round(y10 - y90, 1) if ok else None, "middle": round((y10 + y90) / 2 - cy, 1) if ok else None,
            "samples": [round(prof[reach + o]) for o in (-60, -30, -10, 0, 10, 30, 60)]}


class Shots:
    """The test's exports and rendered frames, and the pictures read from them."""

    def __init__(self, t, d):
        self.t, self.d, self.out, self.pics = t, d, {}, {}

    def export(self, name):
        path = self.t.path("out", f"{name}.mp4")
        try:
            job = self.d.export(path, lossless=True)
            self.out[name] = (path, None if job.get("status") == "done" else f"export {job}")
        except Exception as e:  # noqa: BLE001 (a refused export fails the checks on it, with the reason)
            self.out[name] = (path, f"export failed: {e}")
        return name

    def render(self, name, time):
        path = self.t.path("out", f"{name}.png")
        try:
            self.d.render_frame(time, path)
            self.out[name] = (path, None)
        except Exception as e:  # noqa: BLE001
            self.out[name] = (path, f"render_frame failed: {e}")
        return name

    def path(self, name):
        path, failed = self.out.get(name, (None, f"no export {name}"))
        if failed:
            raise observe.Unmeasurable(failed)
        return path

    def pic(self, name, t=0.5):
        key = (name, t)
        if key not in self.pics:
            path = self.path(name)
            chain = "null" if path.endswith(".png") else observe.read_as("bt709", "tv")
            self.pics[key] = observe.Picture(path, t, chain)
        return self.pics[key]


def run(t):
    d = t.driver()
    d.set_project(width=W, height=H, fps=FPS)
    v1 = d.add_track("video")
    s = Shots(t, d)
    blend_modes(t, d, s, v1)
    masks(t, d, s, v1)
    keyframed(t, d, s, v1)
    keyed_and_alpha(t, d, s, v1)
    blend_edges(t, d, s, v1)
    one_mask_two_pictures(t, d, s, v1)


def at(n):
    """A time that seeks to timeline frame n (the first frame at or after it is frame n: a quarter frame before
    its start, which stays between the frames after rounding to the millisecond)."""
    return (n - 0.25) / FPS


def blend_modes(t, d, s, v1):
    bands, greys = d.import_media(t.media("mk-bands.png")), d.import_media(t.media("mk-greys.png"))
    n = SEG * len(CASES)
    d.place_clip(bands, "v0", 0, 0, n)
    d.place_clip(bands, "v0", n, 0, SEG)          # the bands alone
    d.place_clip(greys, "v0", n + SEG, 0, SEG)    # the greys alone
    clips = [d.place_clip(greys, v1, k * SEG, 0, SEG) for k in range(len(CASES))]
    for clip, (mode, opacity) in zip(clips, CASES):
        d.set_blend_mode(clip, mode)
        if opacity != 1:
            d.set_transform(clip, opacity=opacity)
    s.export("blend")
    centres = [(i * BW + BW // 2, j * GH + GH // 2) for i in range(len(BASES)) for j in range(len(GREYS))]

    def refs():
        base, layer = s.pic("blend", at(n + SEG // 2)), s.pic("blend", at(n + SEG + SEG // 2))
        got_b = [base.mean(x, y, 6) for x, y in centres]
        got_l = [layer.mean(x, y, 6) for x, y in centres]
        want_b = [BASES[x // BW] for x, _ in centres]
        want_l = [(GREYS[y // GH],) * 3 for _, y in centres]
        return observe.max_error(got_b, want_b), observe.max_error(got_l, want_l), got_b, got_l
    ref = t.measure("control: the colour bands alone and the grey bands alone export as the stills' colours (each of "
                    "the 48 cells within 3)", refs, lambda v: v[0] <= 3 and v[1] <= 3,
                    "within 3; the detail starts with the largest error of each")
    for k, (mode, opacity) in enumerate(CASES):
        label = mode + ("" if opacity == 1 else f" at opacity {opacity}")

        def cells(k=k, mode=mode, opacity=opacity):
            if ref is None:
                raise observe.Unmeasurable("the pictures alone could not be read")
            f = s.pic("blend", at(k * SEG + SEG // 2))
            out, worst, differs = 0, (0, ""), False
            for (x, y), b, l in zip(centres, ref[2], ref[3]):
                got = f.mean(x, y, 6)
                for c in range(3):
                    want = composite(mode, b[c], l[c], opacity)
                    lo, hi = ref_range(mode, b[c], l[c], opacity)
                    if abs(got[c] - want) > worst[0]:
                        worst = (abs(got[c] - want), f"base {b[c]} layer {l[c]} -> {got[c]}, formula {want:.1f}")
                    if got[c] < lo - 3 or got[c] > hi + 3:
                        out += 1
                    if abs(composite("normal", b[c], l[c], opacity) - want) > 20 and abs(got[c] - want) < 6:
                        differs = True
            return out, round(worst[0], 1), worst[1], differs
        v = t.measure(f"{label}: all 48 cells are the W3C formula of the two pictures (2 levels of input slack, +3)",
                      cells, lambda v: v[0] == 0, "no channel out of range; the detail has the largest deviation")
        if mode != "normal":
            t.check(f"{label}: visibly differs from normal layering", v is not None and v[3],
                    "no cell where the formula is 20 or more from normal and the export within 6 of it" if v else
                    "unmeasurable")
    # A mode set back to normal exports the same frames as a clip that never had one. Before the last export the
    # bands run TAIL frames longer (the bands alone), so each of the three exports has a length of its own and none of
    # them passes for another.
    edits.clear(d)
    under = d.place_clip(bands, "v0", 0, 0, SEG)
    pc = d.place_clip(greys, v1, 0, 0, SEG)
    d.set_transform(pc, opacity=0.7)
    s.export("plain-a")
    d.set_blend_mode(pc, "multiply")
    mode_set = edits.clip(d.get_state(), pc)
    s.export("plain-m")
    d.set_blend_mode(pc, "normal")
    mode_reset = edits.clip(d.get_state(), pc)
    d.trim_clip(under, out_frame=SEG + TAIL)
    s.export("plain-b")
    t.check("get_state shows the clip's blend mode: multiply once set, normal once set back",
            (mode_set or {}).get("blend_mode") == "multiply" and (mode_reset or {}).get("blend_mode") == "normal",
            f"after multiply: {(mode_set or {}).get('blend_mode')!r}; after normal: {(mode_reset or {}).get('blend_mode')!r}")

    one = W * H * 3 // 2

    def frames(name):
        return observe.pixels(s.path(name), 0, "null", "yuv420p", frames=SEG + TAIL + 1)

    def diff(x, y):
        fx, fy = frames(x), frames(y)
        return len(fx) // one, len(fy) // one, max((abs(p - q) for p, q in zip(fx[:SEG * one], fy)), default=None), \
            sum(1 for p, q in zip(fx[:SEG * one], fy) if abs(p - q) > 10)
    t.measure(f"normal, set back after multiply, exports the same frames as a clip that never had a blend mode "
              f"(every sample of the 8 frames within 1; the first export {SEG} frames, the second {SEG + TAIL}: the "
              f"bands run {TAIL} frames longer)", lambda: diff("plain-a", "plain-b"),
              lambda v: v[0] == SEG and v[1] == SEG + TAIL and v[2] is not None and v[2] <= 1,
              f"{SEG} and {SEG + TAIL} frames, the largest difference <= 1")
    t.measure(f"multiply changes the frames ({SEG} frames each)", lambda: diff("plain-a", "plain-m"),
              lambda v: v[0] == v[1] == SEG and v[3] > 1000,
              f"{SEG} frames each, more than 1000 samples 10 or more apart")


def masks(t, d, s, v1):
    edits.clear(d)
    blue, redsq = d.import_media(t.media("mk-blue.png")), d.import_media(t.media("mk-redsq.png"))
    under = d.place_clip(blue, "v0", 0, 0, FPS)
    over = d.place_clip(redsq, v1, 0, 0, FPS)

    def px(name, x, y, want, label, tol=12):
        t.measure(f"{label}: {fmt(want)} +-{tol}", lambda: s.pic(name).mean(x, y, 1), lambda c: near(c, want, tol),
                  f"{fmt(want)} +- {tol} a channel")

    s.export("fit")
    t.measure("control: the square red picture is fitted 360x360 in the middle of the canvas (red from x 140 to 499, "
              "blue beside it)", lambda: [s.pic("fit").mean(x, 180, 1) for x in (134, 145, 320, 494, 505)],
              lambda v: near(v[0], BLUE, 12) and near(v[4], BLUE, 12) and all(near(c, RED, 12) for c in v[1:4]),
              "blue at x 134 and 505, red at 145, 320 and 494")
    d.set_mask(over, shape="ellipse")
    mk = (edits.clip(d.get_state(), over) or {}).get("mask")
    t.check("a new ellipse is a centred circle half the picture's short side (get_state: x, y 0.5, w, h 0.5)",
            isinstance(mk, dict) and mk.get("shape") == "ellipse" and
            all(isinstance(mk.get(k), (int, float)) and abs(mk[k] - 0.5) < 1e-6 for k in ("x", "y", "w", "h")), mk)
    s.export("ellipse")
    px("ellipse", *C, RED, "ellipse: the middle shows the clip")
    px("ellipse", C[0] + 70, C[1], RED, "ellipse: inside the radius (90 px)")
    px("ellipse", C[0] + 110, C[1], BLUE, "ellipse: outside it the track below shows")
    px("ellipse", C[0] + 75, C[1] + 75, BLUE, "ellipse: the picture's corner is outside the circle")

    def edge():
        luma = observe.pixels(s.path("ellipse"), 0.5, "null", "gray")
        y_in, y_out = luma[C[1] * W + C[0]], luma[C[1] * W + C[0] + 110]
        lo, span = min(y_in, y_out), abs(y_in - y_out)
        diag = [luma[(C[1] + o) * W + C[0] + o] for o in range(60, 68)]
        return span, lo, diag
    t.measure("ellipse: its edge is anti-aliased (along the diagonal some pixel is partly covered: its luma between "
              "the inside's and the outside's)", edge,
              lambda v: v[0] > 10 and any(v[1] + v[0] * 0.1 < x < v[1] + v[0] * 0.9 for x in v[2]),
              "a span over 10, one diagonal luma 10..90 % into it; the detail: span, the lower luma, the diagonal")
    d.set_mask(over, invert=True)
    s.export("ellipse-inv")
    px("ellipse-inv", *C, BLUE, "invert: the middle shows the track below")
    px("ellipse-inv", C[0] + 120, C[1], RED, "invert: outside the circle shows the clip")
    px("ellipse-inv", 60, C[1], BLUE, "invert: the letterbox stays transparent")
    d.set_mask(over, shape="rect", invert=False, w=0.6, h=0.4, roundness=0)
    s.export("rect")
    px("rect", C[0] + 100, C[1] + 65, RED, "rect: near its corner, inside")
    px("rect", C[0] + 120, C[1], BLUE, "rect: right of it")
    px("rect", C[0], C[1] + 80, BLUE, "rect: below it")
    d.set_mask(over, roundness=1)
    s.export("rect-round")
    px("rect-round", C[0] + 100, C[1] + 65, BLUE, "roundness 1: the corner is cut off")
    px("rect-round", C[0] + 100, C[1], RED, "roundness 1: the side is still inside")
    d.set_mask(over, shape="linear", roundness=0, rotation=0)
    s.export("linear")
    px("linear", C[0], C[1] - 60, RED, "linear: above the line shows the clip")
    px("linear", C[0], C[1] + 60, BLUE, "linear: below the line shows the track below")
    d.set_mask(over, rotation=90)
    s.export("linear-90")
    px("linear-90", C[0] + 60, C[1], RED, "linear turned 90 degrees: the right side shows the clip")
    px("linear-90", C[0] - 60, C[1], BLUE, "linear turned 90 degrees: the left side shows the track below")
    d.set_mask(over, rotation=0, feather=0.3)
    s.export("linear-feather")
    edge_w = FEATHER * min(W, H)  # the picture is 360x360: its short side is the canvas's height
    feather_edge = (lambda: soft_edge(s.pic("linear-feather"), C))
    t.measure("a feathered linear edge (feather 0.3) grades from the clip to the track below: the clip whole 150 px "
              "above the line and the track below 150 px under it (red 245 or more, then 10 or less), and the red "
              "never rises on the way down (by more than 2, row by row)", feather_edge,
              lambda v: v["top"] >= 245 and v["bottom"] <= 10 and v["worst_rise"] <= 2,
              "red 150 px either side of the line, the largest rise between rows; the detail has red at -60, -30, -10, "
              "0, 10, 30, 60 px")
    t.measure(f"...its soft edge is as wide as feather 0.3 says (PROTOCOL: from 90 % of the clip to 10 %, 0.3 of the "
              f"picture's short side, {edge_w:.0f} px within {FEATHER_TOL:.0%}), centred on the line (its middle "
              f"within {FEATHER_MID} px)", feather_edge,
              lambda v: v["width"] is not None and abs(v["width"] - edge_w) <= FEATHER_TOL * edge_w and
              abs(v["middle"]) <= FEATHER_MID, f"{edge_w:.0f} px +- {FEATHER_TOL:.0%}, middle within {FEATHER_MID} px")
    d.set_mask(over, shape="mirror", feather=0, h=0.25)
    s.export("mirror")
    px("mirror", *C, RED, "mirror: inside the band")
    px("mirror", C[0], C[1] - 65, BLUE, "mirror: above the band")
    px("mirror", C[0], C[1] + 65, BLUE, "mirror: below the band")
    # The mask follows the transform: scale 0.5 and moved right by a quarter of the canvas.
    d.set_mask(over, shape="ellipse", w=0.5, h=0.5)
    d.set_transform(over, scale=0.5, x=0.25)
    s.export("follow")
    p = (C[0] + 160, C[1])
    px("follow", *p, RED, "transformed: the circle moved with the picture")
    px("follow", p[0] + 35, p[1], RED, "transformed: inside the halved radius (45 px)")
    px("follow", p[0] + 60, p[1], BLUE, "transformed: outside the halved radius, inside the picture")
    px("follow", *C, BLUE, "transformed: nothing left at the old middle")
    # Turned: a wide rect mask on a clip turned 90 degrees is a vertical band, as the mask turned 90 degrees.
    d.set_transform(over, scale=1, x=0, rotation=90)
    d.set_mask(over, shape="rect", w=0.8, h=0.2, rotation=0)
    s.export("rot-clip")
    px("rot-clip", C[0], C[1] - 120, RED, "the clip turned 90 degrees: the band is vertical (above the middle)")
    px("rot-clip", C[0] + 60, C[1], BLUE, "the clip turned 90 degrees: beside the band")
    # The second of these exports runs TAIL frames longer (the blue below alone), so the first does not pass for it.
    d.set_transform(over, rotation=0)
    d.set_mask(over, rotation=90)
    d.trim_clip(under, out_frame=FPS + TAIL)
    s.export("rot-mask")
    d.trim_clip(under, out_frame=FPS)
    px("rot-mask", C[0], C[1] - 120, RED, "the mask turned 90 degrees: the same vertical band")
    pts = ((320, 60), (320, 300), (380, 180), (260, 180), (340, 100))
    t.measure(f"the clip turned 90 degrees and the mask turned 90 degrees give the same picture (a square clip; five "
              f"points within 6; the second export {FPS + TAIL} frames long, the first {FPS})",
              lambda: ([(s.pic("rot-clip").mean(x, y, 1), s.pic("rot-mask").mean(x, y, 1)) for x, y in pts],
                       [observe.decode(s.path(n))["video_frames"] for n in ("rot-clip", "rot-mask")]),
              lambda v: all(near(a, b, 6) for a, b in v[0]) and v[1] == [FPS, FPS + TAIL],
              "each point within 6; the frames of each export")
    # A blend mode with a mask: screen inside a circle (red screen blue is magenta).
    d.set_mask(over, shape="ellipse", w=0.5, h=0.5, rotation=0)
    d.set_blend_mode(over, "screen")
    s.export("blend-mask")
    px("blend-mask", *C, (255, 0, 255), "screen with a mask: magenta inside the circle")
    px("blend-mask", C[0] + 120, C[1], BLUE, "screen with a mask: the track below untouched outside it")
    # render_frame shows a mask change at once, and the mask made large again, moved right by a tenth of the picture
    # (36 px: so the third frame is neither of the first two).
    shots = [s.render("frame-1", 0.5)]
    d.set_mask(over, w=0.2, h=0.2)
    shots.append(s.render("frame-2", 0.5))
    d.set_mask(over, w=0.5, h=0.5, x=0.6)
    shots.append(s.render("frame-3", 0.5))
    d.set_mask(over, x=0.5)
    reds = (lambda: [[s.pic(n, 0).px(C[0] + dx, C[1])[0] for dx in (70, -70)] for n in shots])
    t.measure("render_frame shows a mask change at once: 70 px right of the middle (and 70 px left) is inside the "
              "circle, then outside the smaller one", reds,
              lambda v: v[0][0] > 200 and v[0][1] > 200 and v[1][0] < 60 and v[1][1] < 60,
              "red > 200, then < 60 (right, left)")
    t.measure("...and the mask large again and moved right (x 0.6, its middle 36 px right): 70 px right of the old "
              "middle inside, 70 px left of it outside (106 px from the new middle)", reds,
              lambda v: v[2][0] > 200 and v[2][1] < 60, "red > 200 right, < 60 left")
    # Undo: one step each.
    before = (edits.clip(d.get_state(), over) or {}).get("mask")
    d.set_mask(over, shape="none")
    gone = (edits.clip(d.get_state(), over) or {}).get("mask", "no field")
    t.check("shape none removes the mask (get_state: null)", gone is None, f"{gone!r}")
    d.undo()
    back = (edits.clip(d.get_state(), over) or {}).get("mask")
    t.check("one undo puts the mask back (get_state: the same mask)", back == before and before is not None,
            f"before {before}; after the undo {back}")
    d.set_blend_mode(over, "multiply")
    d.undo()
    mode = (edits.clip(d.get_state(), over) or {}).get("blend_mode")
    t.check("one undo puts the blend mode back (screen)", mode == "screen", f"{mode!r}")
    # Clamping.
    d.set_mask(over, feather=5, w=-1, rotation=270)
    mk = (edits.clip(d.get_state(), over) or {}).get("mask") or {}
    t.check("out-of-range values are clamped: feather 5 to 1, w -1 to the bottom of its range (0.01 or less), "
            "rotation 270 kept as the same angle (-90)",
            mk.get("feather") == 1 and isinstance(mk.get("w"), (int, float)) and 0 <= mk["w"] <= 0.01 and
            isinstance(mk.get("rotation"), (int, float)) and round(mk["rotation"]) % 360 == 270, mk)
    v2 = d.add_track("video")
    adj = d.add_adjustment_layer(0, FPS, track=v2)
    ok, why = edits.refused_unchanged(d, lambda: d.set_blend_mode(adj, "screen"))
    t.check("a blend mode on an adjustment layer is refused, nothing changes", ok, why)
    ok, why = edits.refused_unchanged(d, lambda: d.set_blend_mode(over, "glow"))
    t.check("a blend mode the editor does not have (glow) is refused, nothing changes", ok, why)


def keyframed(t, d, s, v1):
    """The mask on a clip whose scale is animated (set_keyframes): the circle (w, h 0.5) of the picture moved right by
    a quarter of the canvas, its scale from 0.5 at its first frame to 1 at its last, over blue. At the first frame the
    picture is 180 px wide around x 480 and the circle's radius 45 px; at the last 360 px (x 300 to the canvas's
    edge) and 90 px. Outside the circle, inside the picture and beside it, the track below shows at both ends, and the
    circle grows with the picture between them (the judge's proof that the editor animated the scale)."""
    edits.clear(d)
    blue, redsq = d.import_media(t.media("mk-blue.png")), d.import_media(t.media("mk-redsq.png"))
    d.place_clip(blue, "v0", 0, 0, FPS)
    clip = d.place_clip(redsq, v1, 0, 0, FPS)
    d.set_mask(clip, shape="ellipse", w=0.5, h=0.5)
    d.set_transform(clip, x=0.25)
    d.set_keyframes(clip, "scale", [{"frame": 0, "value": 0.5}, {"frame": FPS - 1, "value": 1}])
    s.export("keyframed")
    p = C[0] + 160
    for n, red, blue_at, what in (
            (0, (p, p + 35), (p + 60, p + 120),
             "at its first frame (scale 0.5): red at the circle's middle and 35 px right, blue 60 px right (outside "
             "the 45 px circle, inside the picture) and 120 px right (beside the picture)"),
            (FPS - 1, (p, p + 60, p + 75), (p + 110, 250),
             "at its last frame (scale 1): red at the middle, 60 and 75 px right (the circle grew to 90 px), blue 110 "
             "px right (outside it, inside the picture) and at x 250 (beside the picture)")):
        def look(n=n, red=red, blue_at=blue_at):
            f = s.pic("keyframed", at(n) if n else 0)
            return [f.mean(x, C[1], 1) for x in red], [f.mean(x, C[1], 1) for x in blue_at]
        t.measure(f"a mask on a clip whose scale is animated (set_keyframes, 0.5 to 1) moves and scales with it, the "
                  f"track below showing outside it, {what}", look,
                  lambda v: all(near(c, RED, 12) for c in v[0]) and all(near(c, BLUE, 12) for c in v[1]),
                  "red, then blue, +- 12 a channel")
    # The keyframes are one undo step (the clip is at its set scale, 1, from its first frame again; redo brings them
    # back), and a locked track refuses them (product_error, nothing changes, the undo history kept:
    # edits.refused_unchanged).
    d.undo()
    shot = s.render("keyframes-undone", 0)
    d.redo()
    again = s.render("keyframes-redone", 0)
    t.measure("one undo takes the keyframes back: at its first frame the clip is at its set scale (1), the circle 90 "
              "px (render_frame: red 60 px right of its middle, blue 110 px right); redo brings them back (blue 60 px "
              "right again, the 45 px circle red at its middle and 35 px right)",
              lambda: [s.pic(n, 0).mean(x, C[1], 1) for n in (shot, again) for x in (p + 60, p + 110, p, p + 35)],
              lambda v: near(v[0], RED, 12) and near(v[1], BLUE, 12) and near(v[4], BLUE, 12) and near(v[5], BLUE, 12)
              and near(v[6], RED, 12) and near(v[7], RED, 12),
              "undone: red, blue; redone: blue, blue, and red at its middle and 35 px right; +- 12 a channel")
    d.set_track(v1, locked=True)
    ok, why = edits.refused_unchanged(d, lambda: d.set_keyframes(clip, "scale", [{"frame": 0, "value": 0.3}]))
    t.check("set_keyframes on a clip on a locked track: refused, nothing changes", ok, why)
    d.set_track(v1, locked=False)


def keyed_and_alpha(t, d, s, v1):
    def px(name, x, y, want, label, tol=14):
        t.measure(f"{label}: {fmt(want)} +-{tol}", lambda: s.pic(name).mean(x, y, 1), lambda c: near(c, want, tol),
                  f"{fmt(want)} +- {tol} a channel")
    blue = d.import_media(t.media("mk-blue.png"))
    # A green screen with a red box, keyed, then a mask on its left half.
    edits.clear(d)
    d.place_clip(blue, "v0", 0, 0, FPS)
    k = d.place_clip(d.import_media(t.media("mk-greenbox.png")), v1, 0, 0, FPS)
    d.apply_effect(k, "colorkey", color="0x00FF00")
    d.set_mask(k, shape="rect", x=0.25, y=0.5, w=0.5, h=1)
    s.export("keyed")
    px("keyed", 260, 180, RED, "keyed and masked: the box inside the mask shows")
    px("keyed", 100, 50, BLUE, "keyed and masked: the keyed green inside the mask stays transparent (the mask "
       "multiplies the key, it does not undo it)")
    px("keyed", 400, 180, BLUE, "keyed and masked: the box outside the mask is hidden")
    # A clip with its own alpha (a red disc on transparency), masked by a line through its middle.
    edits.clear(d)
    d.place_clip(blue, "v0", 0, 0, FPS)
    a = d.place_clip(d.import_media(t.media("mk-disc.mkv")), v1, 0, 0, FPS)
    d.set_mask(a, shape="linear", y=0.5)
    s.export("alpha")
    px("alpha", 320, 120, RED, "an alpha clip with a mask: the disc above the line shows")
    px("alpha", 320, 240, BLUE, "an alpha clip with a mask: the disc below the line is masked")
    px("alpha", 190, 90, BLUE, "an alpha clip with a mask: its transparent part above the line, outside the disc, "
       "stays transparent")
    d.set_mask(a, invert=True)
    s.export("alpha-inv")
    px("alpha-inv", 320, 240, RED, "an alpha clip with an inverted mask: the disc below the line shows")
    t.measure("an alpha clip with an inverted mask: its transparency is kept below the line (outside the disc), and "
              "above the line the disc is masked: (0,0,255) +-14 at both",
              lambda: [s.pic("alpha-inv").mean(x, y, 1) for x, y in ((190, 270), (320, 120))],
              lambda v: all(near(c, BLUE, 14) for c in v), "(0,0,255) +- 14 a channel, at each")
    # An adjustment layer (black and white) limited to the left half by its mask.
    edits.clear(d)
    d.place_clip(d.import_media(t.media("mk-bands.png")), "v0", 0, 0, FPS)
    adj = d.add_adjustment_layer(0, FPS, track=v1)
    d.apply_effect(adj, "grayscale")
    d.set_mask(adj, shape="rect", x=0.25, y=0.5, w=0.5, h=1)
    s.export("adjust")
    t.measure("an adjustment layer's mask: inside it the picture is black and white (the red band: channel spread "
              "under 12)", lambda: s.pic("adjust").mean(40, 180, 2), lambda c: max(c) - min(c) < 12, "spread < 12")
    t.measure("an adjustment layer's mask: outside it the picture keeps its colour (the last band: spread over 40)",
              lambda: s.pic("adjust").mean(600, 180, 2), lambda c: max(c) - min(c) > 40, "spread > 40")
    # A blend mode set on a clip joined by a transition is set on the whole run.
    edits.clear(d)
    redsq = d.import_media(t.media("mk-redsq.png"))
    d.place_clip(blue, "v0", 0, 0, 2 * FPS)
    first = d.place_clip(redsq, v1, 0, 0, FPS)
    second = d.place_clip(redsq, v1, FPS, 0, FPS)
    d.set_transition(second, "fade", 10)
    d.set_blend_mode(second, "multiply")
    st = d.get_state()
    modes = [(edits.clip(st, c) or {}).get("blend_mode") for c in (first, second)]
    t.check("a blend mode set on a clip joined by a transition is set on the whole run (get_state: both clips "
            "multiply)", modes == ["multiply", "multiply"], f"{modes}")


def blend_edges(t, d, s, v1):
    def px(name, x, y, want, label, tol=12, time=0.5, r=1):
        t.measure(f"{label}: {fmt(want)} +-{tol}", lambda: s.pic(name, time).mean(x, y, r),
                  lambda c: near(c, want, tol), f"{fmt(want)} +- {tol} a channel")
    # add: a small grey picture-in-picture in the last 10 frames, top left, over the colour bands.
    edits.clear(d)
    d.place_clip(d.import_media(t.media("mk-bands.png")), "v0", 0, 0, FPS)
    pip = d.place_clip(d.import_media(t.media("mk-grey64.png")), v1, FPS - 10, 0, 10)
    d.set_transform(pip, scale=0.2, x=-0.4, y=-0.4)
    s.export("pip-plain")
    d.set_blend_mode(pip, "add")
    s.export("pip-add")
    late = at(FPS - 4)
    t.measure("control: the plain export shows the colour bands with the grey picture-in-picture at the top left from "
              "frame 20 (its middle (64, 36) grey 64, (64, 200) the first band, frame 19 the band at (64, 36))",
              lambda: (s.pic("pip-plain", late).mean(64, 36, 3), s.pic("pip-plain", late).mean(64, 200, 3),
                       s.pic("pip-plain", at(FPS - 11)).mean(64, 36, 3)),
              lambda v: near(v[0], (64, 64, 64), 3) and near(v[1], BASES[0], 3) and near(v[2], BASES[0], 3),
              "(64,64,64), (230,40,40) and (230,40,40), each within 3")

    def before():
        a = observe.pixels(s.path("pip-plain"), 0, "null", "yuv420p", frames=FPS)
        b = observe.pixels(s.path("pip-add"), 0, "null", "yuv420p", frames=FPS)
        n = W * H * 3 // 2 * (FPS - 10)
        return len(a), len(b), max((abs(p - q) for p, q in zip(a[:n], b[:n])), default=None)
    t.measure(f"add: the {FPS - 10} frames before the layer are the frames of the export without its mode (every sample "
              "within 1), and both exports have every frame", before,
              lambda v: v[0] == v[1] == W * H * 3 // 2 * FPS and v[2] is not None and v[2] <= 1,
              "30 whole frames each, the largest difference <= 1")

    def outside():
        a, b = s.pic("pip-plain", late), s.pic("pip-add", late)
        off = 120 * W * 3
        return max(abs(p - q) for p, q in zip(a.rgb[off:], b.rgb[off:]))
    t.measure("add: while the layer shows, the picture outside it is untouched (every pixel of rows 120 and below "
              "within 1)", outside, lambda v: v <= 1, "<= 1")
    want = tuple(round(composite("add", b, 64, 1)) for b in BASES[0])
    px("pip-add", 64, 36, want, "add: inside the picture-in-picture the layer adds light", 4, late, 3)
    # Text on a multiply clip stays white: only the picture blends.
    edits.clear(d)
    d.place_clip(d.import_media(t.media("mk-blue.png")), "v0", 0, 0, FPS)
    white = d.place_clip(d.import_media(t.media("mk-white.png")), v1, 0, 0, FPS)
    d.add_text(white, "HELLO WORLD", position="center", font_size=72, color="white", outline_width=0, shadow_y=0)
    d.set_blend_mode(white, "multiply")
    s.export("text-blend")

    def brightest():
        f = s.pic("text-blend")
        return max((f.px(x, y) for y in range(150, 210) for x in range(160, 480)), key=sum)
    t.measure("a multiply clip's white text stays white (the brightest pixel of the text's area 245 or more in each "
              "channel)", brightest, lambda c: all(v >= 245 for v in c), ">= 245 each")
    px("text-blend", 20, 20, BLUE, "a multiply clip: white multiplied by the blue below is blue", 12, 0.5, 2)
    # The run's mode: a frame shown only by the run's second clip composites as the first clip says.
    edits.clear(d)
    d.place_clip(d.import_media(t.media("mk-blue.png")), "v0", 0, 0, 5 * FPS)
    red = d.import_media(t.media("mk-red.png"))
    lead = d.place_clip(red, v1, 0, 0, 2 * FPS)
    follower = d.place_clip(red, v1, 2 * FPS, 0, 70)
    d.set_transition(follower, "fade", 10)
    d.set_blend_mode(lead, "screen")
    s.render("run-1", 3.0)
    t.measure("a run in screen: red over blue is magenta where only its second clip shows, all over the canvas "
              "(render_frame; the middle and the top left corner): (255,0,255) +-8",
              lambda: [s.pic("run-1", 0).mean(x, y, 0) for x, y in (C, (20, 20))],
              lambda v: all(near(c, (255, 0, 255), 8) for c in v), "(255,0,255) +- 8 a channel, at each")
    d.clear_effects(lead)
    s.render("run-2", 3.0)
    px("run-2", *C, RED, "after the run's first clip loses its mode (clear_effects), that frame composites normally: "
       "red (render_frame)", 8, 0, 0)


def one_mask_two_pictures(t, d, s, v1):
    """The same ellipse (w, h 0.5) on the square red picture (frames 0 to 29: fitted 360x360, a circle of radius 90)
    and on mk-red.png, which fills the canvas (frames 30 to 59: an ellipse 320 x 180 px across), over blue; then the
    canvas doubled to 1280x720 and the same project exported again (a circle of radius 180, an ellipse 640 x 360). A
    mask drawn for one picture or canvas and used for another shows the wrong shape, or the export fails."""
    edits.clear(d)
    d.set_project(width=W, height=H, fps=FPS)
    d.place_clip(d.import_media(t.media("mk-blue.png")), "v0", 0, 0, 2 * FPS)
    square = d.place_clip(d.import_media(t.media("mk-redsq.png")), v1, 0, 0, FPS)
    wide = d.place_clip(d.import_media(t.media("mk-red.png")), v1, FPS, 0, FPS)
    for c in (square, wide):
        d.set_mask(c, shape="ellipse", w=0.5, h=0.5)
    s.export("one-mask")
    d.set_project(width=2 * W, height=2 * H)
    s.export("one-mask-2x")
    d.set_project(width=W, height=H)

    def shape(name, k, red, blue):
        def look():
            f = s.pic(name, at(15) if k == 0 else at(45))
            cx, cy = f.w // 2, f.h // 2
            return [f.mean(cx + x, cy + y, 1) for x, y in red], [f.mean(cx + x, cy + y, 1) for x, y in blue]
        return look
    for name, k, red, blue, what in (
            ("one-mask", 0, ((70, 0), (0, 70)), ((140, 0), (0, 110)),
             "on the square picture a circle of radius 90: red 70 px right of and below the middle, blue 140 px right "
             "and 110 px below"),
            ("one-mask", 1, ((140, 0), (0, 60)), ((200, 0), (0, 110)),
             "on the picture that fills the canvas, in the same export, an ellipse 320 x 180 px of its own: red 140 px "
             "right of the middle and 60 px below it, blue 200 px right and 110 px below"),
            ("one-mask-2x", 0, ((140, 0), (0, 140)), ((220, 0), (0, 220)),
             "after the canvas is doubled (set_project 1280x720), the project exports again, and on the square picture "
             "the circle is twice as large (radius 180): red 140 px right and below, blue 220 px right and below"),
            ("one-mask-2x", 1, ((280, 0), (0, 150)), ((340, 0), (0, 220)),
             "...and on the picture that fills the canvas the ellipse is twice as large (640 x 360): red 280 px right "
             "and 150 px below, blue 340 px right and 220 px below")):
        t.measure(f"the same ellipse (w, h 0.5) on two pictures of different sizes: {what}", shape(name, k, red, blue),
                  lambda v: all(near(c, RED, 12) for c in v[0]) and all(near(c, BLUE, 12) for c in v[1]),
                  "red, then blue, +- 12 a channel")
