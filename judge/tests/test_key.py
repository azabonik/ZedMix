"""Keys, measured on exports: a colour key with its colour found by the editor (`auto`) on a grey screen with white,
black and red boxes; a key after a colour grade; a pillarboxed picture whose bars stay transparent after its key; a
green screen keyed with `auto` and its spill pulled down by despill; a black background keyed by brightness (`lumakey
auto`); and the colour the editor finds for a key (detect_key_colour). Port of packages/core/scripts/smoke-key.ts
(judge/PORTING.md has the map of its sections).

Every picture is a fixture of make.sh (key-*.mp4: BT.601 limited range with all four colour tags), over a flat blue
clip on the track below, so a keyed (transparent) place shows that blue. The test samples the export where the original
sampled its own: the mean colour of a 24x24 block (read as the export says: BT.709 limited range), with the original's
tolerances (40 levels a channel; 60 for the red box, whose edges the chroma subsampling softens; 30 for the spill box).
The colour `auto` resolves to is read from get_state and must be the one detect_key_colour answers, within 1 level of
the screen's grey (a flat grey decodes exactly); the export then shows that the key removed exactly that screen.
Whether a chroma key on that grey also removes the white and black boxes is not specified (PROTOCOL.md, "Effects"), so
the original's check that it does stays with that script (judge/PORTING.md, key 1). Last, a keyed noisy clip exports
the same frames twice: a check of its own, since the original's section 5 (the same frames whatever the filter thread
count) needs a thread count the judge cannot choose.

Every check is recorded on every path (a check whose input is missing fails with the reason), so CHECKS is exact.
"""
import observe

PORT_BOUND = True
TIMEOUT = 900
CHECKS = 29
EXTRA_MEDIA = ("key-grey.mp4", "key-blue-p.mp4", "key-blue-l.mp4", "key-green.mp4", "key-black.mp4", "key-noisy.mkv")

BLUE, WHITE, BLACK, RED = (0, 0, 255), (255, 255, 255), (0, 0, 0), (255, 0, 0)
FPS = 30
# The flat grey screen is 0x808080 coded as BT.601 limited range (Y 126, U and V 128), which decodes to 128 exactly; a
# key colour found 2 levels off would still key the screen, so only get_state's colour shows it (judge/PORTING.md, key 1).
GREY_TOL = 1


class Exports:
    """The test's exports and the frames read from them (read as BT.709 limited range, as the export is written)."""

    def __init__(self, t, d):
        self.t, self.d, self.out, self.pics = t, d, {}, {}

    def export(self, name, lossless=False):
        path = self.t.path("out", f"{name}.mp4")
        try:
            job = self.d.export(path, lossless=lossless)
            self.out[name] = (path, None if job.get("status") == "done" else f"export {job}")
        except Exception as e:  # noqa: BLE001 (a refused export fails the checks on it, with the reason)
            self.out[name] = (path, f"export failed: {e}")
        return path

    def pic(self, name, t):
        path, failed = self.out.get(name, (None, f"no export {name}"))
        if failed:
            raise observe.Unmeasurable(failed)
        if (name, t) not in self.pics:
            self.pics[(name, t)] = observe.Picture(path, t, observe.read_as("bt709", "tv"))
        return self.pics[(name, t)]

    def sample(self, name, t, x, y):
        """The mean colour of the 24x24 block centred on (x, y) of the export's frame at t s (the original's)."""
        return tuple(round(v) for v in self.pic(name, t).box(x - 12, y - 12, 24, 24))


def near(c, want, tol):
    return c is not None and all(abs(a - b) <= tol for a, b in zip(c, want))


def fmt(c):
    return "(" + ",".join(str(int(v)) for v in c) + ")" if c else str(c)


def channels(hexval):
    v = observe.hex_colour(hexval)
    return None if v is None else ((v >> 16) & 255, (v >> 8) & 255, v & 255)


def key_effect(d, clip, kind):
    """The clip's effect `kind` as get_state reports it (or None)."""
    for tr in d.get_state().get("tracks", []):
        for c in tr.get("clips", []):
            if c.get("id") == clip:
                return next((e for e in c.get("effects", []) if e.get("effect") == kind), None)
    return None


def clear(d):
    for tr in d.get_state().get("tracks", []):
        for c in tr.get("clips", []):
            d.remove_clip(c["id"])


def layered(t, d, w, h, below, over, track):
    """A fresh timeline on a w x h canvas: `below` on v0 and `over` on `track` above it, both whole. -> over's clip id"""
    clear(d)
    d.set_project(width=w, height=h, fps=FPS)
    d.place_clip(d.import_media(t.media(below)), "v0", 0, 0)
    return d.place_clip(d.import_media(t.media(over)), track, 0, 0)


def run(t):
    d = t.driver()
    x = Exports(t, d)
    m = t.measure
    v1 = d.add_track("video")

    def px(name, at, cx, cy, want, label, tol=40):
        m(f"{label}: {fmt(want)} +-{tol}", lambda: x.sample(name, at, cx, cy), lambda c: near(c, want, tol),
          f"{fmt(want)} +- {tol} a channel")

    # ---- 1. a grey screen keyed with the colour the editor finds (1080x1920)
    over = layered(t, d, 1080, 1920, "key-blue-p.mp4", "key-grey.mp4", v1)
    det = d.detect_key_colour(over)
    t.check(f"detect_key_colour finds the flat grey screen: 0x808080 (each channel within {GREY_TOL})",
            near(channels(det.get("color")), (128, 128, 128), GREY_TOL), det)
    t.check("...with a confidence of 0.95 or more (a flat screen)",
            isinstance(det.get("confidence"), (int, float)) and det["confidence"] >= 0.95, det)
    ck = d.apply_effect(over, "colorkey", color="auto")
    fx = key_effect(d, over, "colorkey")
    found = channels((fx or {}).get("color"))
    t.check(f"colorkey with colour auto keeps the colour it found, the screen's: get_state shows 0x808080 (each "
            f"channel within {GREY_TOL}), the colour detect_key_colour answered, not auto",
            near(found, (128, 128, 128), GREY_TOL) and found == channels(det.get("color")), fx)
    x.export("colorkey")
    px("colorkey", 1, 540, 1650, BLUE, "the grey background is keyed: the blue below shows")
    px("colorkey", 1, 540, 800, BLUE, "the grey between the boxes is keyed: blue")
    px("colorkey", 1, 250, 450, WHITE, "the white box is kept")
    px("colorkey", 1, 830, 450, BLACK, "the black box is kept")
    px("colorkey", 1, 250, 1150, RED, "the red box is kept", 60)
    px("colorkey", 1, 705, 1150, BLACK, "the black outline of the target is kept")
    px("colorkey", 1, 830, 1150, WHITE, "the white middle of the target is kept")
    # A colour grade ahead of the key: it still keys.
    d.apply_effect(over, "colorkey", color="0x808080", effect_id=ck)
    d.apply_colour(over, saturation=1.3)
    x.export("graded-key")
    px("graded-key", 1, 540, 1650, BLUE, "a graded clip (saturation 1.3): the grey still keys to blue")
    px("graded-key", 1, 250, 450, WHITE, "a graded clip: the white box is kept")
    px("graded-key", 1, 250, 1150, RED, "a graded clip: the red box is kept", 60)

    # ---- 2. the same picture pillarboxed on a 1280x720 canvas: its transparent bars stay transparent after the key
    over = layered(t, d, 1280, 720, "key-blue-l.mp4", "key-grey.mp4", v1)
    d.apply_effect(over, "colorkey", color="0x808080")
    x.export("pillarbox")
    # 1080x1920 is fitted as 405x720 in the middle: the bars are x < 437 and x > 842
    px("pillarbox", 1, 150, 360, BLUE, "the left pillarbox bar stays transparent after the key (blue)")
    px("pillarbox", 1, 1130, 360, BLUE, "the right pillarbox bar stays transparent after the key (blue)")
    px("pillarbox", 1, 640, 620, BLUE, "the keyed grey inside the picture shows blue")
    px("pillarbox", 1, 437 + round(250 * 0.375), round(450 * 0.375), WHITE, "the white box is kept, scaled", 50)

    # ---- 3 and 4. a green screen (chromakey auto, then despill) and a black background (lumakey auto)
    clear(d)
    d.set_project(width=1280, height=720, fps=FPS)
    d.place_clip(d.import_media(t.media("key-blue-l.mp4")), "v0", 0, 0)
    g = d.place_clip(d.import_media(t.media("key-green.mp4")), v1, 0, 0)
    lk = d.place_clip(d.import_media(t.media("key-black.mp4")), v1, 2 * FPS, 0)
    gk = d.apply_effect(g, "chromakey", color="auto")
    gfx = key_effect(d, g, "chromakey")
    gc = channels((gfx or {}).get("color"))
    t.check("chromakey auto finds the screen's green: get_state shows red and blue 3 or less, green 0xFC or more",
            gc is not None and gc[0] <= 3 and gc[1] >= 0xFC and gc[2] <= 3, gfx)
    d.apply_effect(lk, "lumakey", color="auto")
    lfx = key_effect(d, lk, "lumakey")
    thr = ((lfx or {}).get("params") or {}).get("threshold")
    t.check("lumakey auto sets a black threshold (get_state: 0 to 0.1)",
            isinstance(thr, (int, float)) and 0 <= thr < 0.1, lfx)
    x.export("keys")
    px("keys", 1, 640, 600, BLUE, "chromakey auto: the green screen shows the blue below")
    px("keys", 1, 320, 320, RED, "chromakey auto: the red subject is kept", 60)
    spill = m("chromakey auto: the spill box is kept, still green-tinted (no despill yet): (180,220,180) +-30",
              lambda: x.sample("keys", 1, 920, 320), lambda c: near(c, (180, 220, 180), 30), "(180,220,180) +- 30")
    px("keys", 3, 200, 600, BLUE, "lumakey auto: the black background shows the blue below")
    px("keys", 3, 640, 340, WHITE, "lumakey auto: the white subject is kept")
    d.apply_effect(g, "chromakey", color=(gfx or {}).get("color") or "0x00FF00", params={"despill": 1}, effect_id=gk)
    x.export("despill")
    ds = m("despill 1 pulls the spill box's green down by more than 25, its red within 20 of before",
           lambda: (x.sample("despill", 1, 920, 320), spill),
           lambda v: v[1] is not None and v[0][1] < v[1][1] - 25 and abs(v[0][0] - v[1][0]) < 20,
           "green < before - 25, |red - before| < 20")
    m("the despilled box is no longer green-dominant", lambda: x.sample("despill", 1, 920, 320),
      lambda c: c[1] <= max(c[0], c[2]) + 15, "green <= max(red, blue) + 15")
    px("despill", 1, 640, 600, BLUE, "with despill on, the green screen is still keyed")
    px("despill", 1, 320, 320, RED, "with despill on, the red subject is still kept", 60)
    del ds

    # ---- 5. a keyed clip exports the same frames each time. Not the original's section 5 (the same frames whatever
    # the filter thread count): the judge cannot choose the editor's thread count, so that stays v0.2.0-only.
    clear(d)
    d.set_project(width=320, height=240, fps=FPS)
    noisy = d.place_clip(d.import_media(t.media("key-noisy.mkv")), "v0", 0, 0)
    d.apply_effect(noisy, "chromakey", color="0x00FF00", params={"despill": 0.5})
    x.export("noisy-a", lossless=True)
    x.export("noisy-b", lossless=True)

    def same():
        a, b = (x.out[n] for n in ("noisy-a", "noisy-b"))
        for _, failed in (a, b):
            if failed:
                raise observe.Unmeasurable(failed)
        fa = observe.pixels(a[0], 0, "null", "yuv420p", frames=6)
        fb = observe.pixels(b[0], 0, "null", "yuv420p", frames=6)
        return len(fa), len(fb), sum(1 for p, q in zip(fa, fb) if p != q)
    m("a keyed noisy clip (chromakey with despill 0.5) exports the same frames twice (lossless; every sample of 6 "
      "frames)", same, lambda v: v[0] == v[1] == 320 * 240 * 3 // 2 * 6 and v[2] == 0,
      "6 whole frames each, no sample different")
