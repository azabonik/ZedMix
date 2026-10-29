"""Colour space: every source is read the way players read it, and every export is BT.709 limited range with all
four colour tags, so the export shows the source's true colours everywhere. Port of
packages/core/scripts/smoke-colorspace.ts (judge/PORTING.md has the map of its sections): the reading rules and the
editor's colour bookkeeping are internals; what a user sees of them is judged here, on the files the editor writes.

The sources are make.sh's cs-* fixtures: an 8 x 4 grid of 32 flat patches (full and 75 % bars, skin, sky, darks,
greys) coded from exact RGB with a known matrix and range, and tagged with exactly the tags named (or none), so the
true colour of every patch is known. The judge reads an export as BT.709 limited range (read_as: an explicit reading,
not its own FFmpeg's guess) and checks its tags apart (ffprobe); a patch is the mean of the 6 x 6 block at its middle
(the original's reading), and a source read the wrong way is off by 30 to 40 levels on the saturated patches, so the
original's limits (4 levels on an export, 6 on a rendered frame, 3 on a still, 8 on a JPEG thumbnail) tell them apart.

- Exports (sections 1 and 3): untagged HD (BT.709), BT.709-tagged HD, BT.601-tagged HD, untagged HD VP9 (BT.601),
  BT.601-tagged SD on its own canvas and pillarboxed on an HD one, full range BT.709, an RGB still (PNG), a JPEG
  still (BT.601 full range); and the reading rules' other cases: untagged SD (BT.601), BT.709-tagged SD (the tag wins
  over the size), HD with only its matrix tagged, full range with no matrix (BT.601 full, as a JPEG), and an untagged
  SD clip shown turned a quarter (its 480 coded lines make it SD, whatever way it is shown).
- Lossless (3b): a plain clip at the canvas's size exports its own 4:2:0 samples (also with effects that change
  nothing, and with a chroma key that is switched off: first seen to key, then bypassed); a crop with an odd offset or
  size cuts the picture where it says.
- Copies (3c): a reversed and a slowed (blended frames) copy of a BT.601 source, of untagged VP9 and of an FFV1 clip
  with alpha export with the source's colours. The copy must be a new file of the editor's, by the judge's own look
  (new_file: listed before the action, its real path, not the judge's own, not the bytes of a file already there or
  of the source), with the frames the clip plays (18 reversed, 36 slowed).
- Motion graphics (3d): a graphic that draws flat colours exports with them (built-in renderer; the graphics add-on
  when the judge has one).
- An OTIO file from another editor, which says nothing about its media's colours, opens and exports with the true
  colours: a check of its own. The original's section 4 (a project saved before the editor recorded each file's colour
  description) stays v0.2.0-only: an OTIO import reads the media again, so it never meets such a project, and only the
  editor's own project format can hold one.
- render_frame, before and after a preview render (5); a freeze frame's still (its own file, a new one as for the
  copies, and where it plays), a thumbnail (a new file too) and the colour found for a key (6: within 1 level of the
  screen's border as the judge reads it); a JPEG is a still (2).

Every check is recorded on every path (a check whose input is missing fails with the reason), so CHECKS is exact.
"""
import json
import os

import driver as drv
import edits
import observe

PORT_BOUND = True
TIMEOUT = 1800
CHECKS = 51
EXTRA_MEDIA = ("cs-hd.mp4", "cs-709.mp4", "cs-601.mp4", "cs-sd601.mp4", "cs-sd.mp4", "cs-sd709.mp4", "cs-full709.mp4",
               "cs-fullnm.mp4", "cs-partial.mp4", "cs-vp9.webm", "cs-rotsd.mp4", "cs-grid.png", "cs-grid.jpg",
               "cs-cut601.mkv", "cs-testsrc.mp4", "cs-gridll.mp4", "cs-green.mp4")

FPS = 30
PATCH = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (0, 255, 255), (255, 0, 255), (255, 255, 0), (255, 255, 255),
         (0, 0, 0), (191, 0, 0), (0, 191, 0), (0, 0, 191), (0, 191, 191), (191, 0, 191), (191, 191, 0),
         (191, 191, 191), (128, 128, 128), (224, 172, 105), (141, 85, 36), (100, 150, 220), (60, 120, 40),
         (255, 128, 0), (128, 0, 200), (0, 128, 128), (255, 105, 180), (40, 20, 10), (10, 30, 60), (16, 16, 16),
         (32, 32, 32), (64, 64, 64), (200, 40, 30), (192, 192, 192), (235, 235, 235)]
AS_709 = observe.read_as("bt709", "tv")
TAGGED_709 = {"range": "tv", "matrix": "bt709", "transfer": "bt709", "primaries": "bt709"}

# (label, media, canvas width, height, where the picture lands: None (the whole canvas), (x, y, w, h), or "turned")
SOURCES = [
    ("untagged HD (read as BT.709)", "cs-hd.mp4", 1280, 720, None),
    ("BT.709-tagged HD", "cs-709.mp4", 1280, 720, None),
    ("BT.601-tagged HD", "cs-601.mp4", 1280, 720, None),
    ("untagged HD VP9 (read as BT.601)", "cs-vp9.webm", 1280, 720, None),
    ("BT.601-tagged SD on its own canvas", "cs-sd601.mp4", 720, 480, None),
    ("BT.601-tagged SD pillarboxed on an HD canvas", "cs-sd601.mp4", 1280, 720, (100, 0, 1080, 720)),
    ("full range BT.709", "cs-full709.mp4", 1280, 720, None),
    ("an RGB still (PNG)", "cs-grid.png", 1280, 720, None),
    ("a JPEG still (BT.601 full range)", "cs-grid.jpg", 1280, 720, None),
    ("untagged SD (read as BT.601)", "cs-sd.mp4", 720, 480, None),
    ("BT.709-tagged SD (the matrix tag wins over the size)", "cs-sd709.mp4", 720, 480, None),
    ("HD with only its matrix tagged, BT.601", "cs-partial.mp4", 1280, 720, None),
    ("full range with no matrix tag (read as BT.601 full range, as a JPEG)", "cs-fullnm.mp4", 1280, 720, None),
    ("untagged SD shown turned a quarter (480 coded lines: BT.601)", "cs-rotsd.mp4", 480, 848, "turned"),
]
STILLS = (".png", ".jpg")
SECS = 18  # frames of each source (0.6 s); a still is placed for as long


class Outs:
    """The test's exports and rendered frames, and their patches."""

    def __init__(self, t, d):
        self.t, self.d, self.out = t, d, {}

    def export(self, name, lossless=False):
        path = self.t.path("out", f"{name}.mp4")
        try:
            job = self.d.export(path, lossless=lossless)
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
        path, failed = self.out.get(name, (None, f"no output {name}"))
        if failed:
            raise observe.Unmeasurable(failed)
        return path

    def error(self, name, at=0.3, rect=None, chain=AS_709):
        """(the largest error of any patch against the true colours, the worst patch), the export read with `chain`."""
        cells = observe.Picture(self.path(name), at, chain).cells(8, 4, rect)
        return worst(cells)


def worst(cells, want=PATCH):
    err = [max(abs(g - w) for g, w in zip(c, p)) for c, p in zip(cells, want)]
    k = max(range(len(err)), key=err.__getitem__)
    return round(err[k], 1), f"patch {k} {tuple(round(v) for v in cells[k])} for {want[k]}"


def new_file(t, before, path, sources=()):
    """Why `path` (a file the editor reports it made: a copy, a still, a thumbnail) is not a new file of the editor's,
    or None when it is. `before` is edits.files(t) listed just before the action, the judge's own files included. The
    judge's own look decides, never the path's spelling: the file, made real (links and "/./" resolved), must be a
    regular file in the test's folder now (edits.files), outside the judge's own folders (out/, in/), not among the
    files listed before, and not the same bytes as any of them (sha256 of each one of the same size) or as the media
    `sources` it was made from, so a link, a hard link or a copy of a file that was already there is not a new
    file."""
    if not isinstance(path, str) or not path:
        return f"no file named ({path!r})"
    real = os.path.realpath(path)
    scratch = os.path.realpath(t.scratch)
    if not real.startswith(scratch + os.sep):
        return f"{path} is not in the test's folder"
    for mine in ("out", "in"):
        if real.startswith(os.path.join(scratch, mine) + os.sep):
            return f"{path} is in the judge's own folder {mine}/"
    was = {os.path.realpath(p): s for p, s in before.items()}
    if real in was:
        return f"{path} was there before the action"
    now = {os.path.realpath(p): s for p, s in edits.files(t).items()}
    if real not in now:
        return f"{path} is not a regular file in the test's folder"
    same = [p for p, s in was.items() if s == now[real]]
    hashes = t.look(files=[real] + same)["files"]
    if hashes.get(real) is None:
        return f"{path} cannot be read"
    dup = [p for p in same if hashes.get(p) == hashes[real]]
    dup += [p for p in sources if observe.sha256(p) == hashes[real]]
    if dup:
        return f"{path} holds the same bytes as {dup[0]}, which was there before the action"
    return None


def picture_error(path):
    """worst() of a picture the editor wrote (a still, a thumbnail), read as its format is read: a PNG as its RGB, a
    JPEG as BT.601 full range. -> (error, worst patch, codec)"""
    codec = (observe.video_stream(path, observe.STILL) or {}).get("codec_name")
    chain = {"mjpeg": observe.read_as("bt601", "pc"), "png": "null"}.get(codec)
    if chain is None:
        raise observe.Unmeasurable(f"{os.path.basename(path)} is {codec}, not a JPEG or PNG picture")
    return worst(observe.Picture(path, 0, chain, observe.STILL).cells(8, 4)) + (codec,)


def frame_count(path):
    """The number of frames the judge decodes from the video at `path` (up to 1000)."""
    vs = observe.video_stream(path) or {}
    w, h = vs.get("width"), vs.get("height")
    if not w or not h:
        raise observe.Unmeasurable(f"{os.path.basename(path)} has no picture size")
    return len(observe.pixels(path, 0, "null", "gray", frames=1000)) // (w * h)


def turned_error(path, at):
    """The patches of an export of cs-rotsd.mp4 (an 848x480 grid shown turned a quarter, on a 480x848 canvas), read
    for each way the picture can have been turned (clockwise, counter-clockwise; and not turned, fitted): the reading
    is what the check is about, not the direction. -> (the smallest largest error, how it was read)"""
    f = observe.Picture(path, at, AS_709)
    centres = [((c * 2 + 1) * 848 // 16, (r * 2 + 1) * 480 // 8) for r in range(4) for c in range(8)]
    ways = {"turned clockwise": lambda x, y: (479 - y, x), "turned counter-clockwise": lambda x, y: (y, 847 - x),
            "not turned, fitted": lambda x, y: (x * 480 / 848, 288 + y * 272 / 480)}
    best = None
    for how, mapping in ways.items():
        cells = [f.box(round(mapping(x, y)[0]) - 3, round(mapping(x, y)[1]) - 3, 6, 6) for x, y in centres]
        e = worst(cells)
        if best is None or e[0] < best[0]:
            best = (e[0], f"{how}: {e[1]}")
    return best


def run(t):
    d = t.driver(graphics_addon=True)
    o = Outs(t, d)
    exports(t, d, o)
    lossless(t, d, o)
    copies(t, d, o)
    stills_and_frames(t, d, o)
    graphics(t, d, o)
    foreign_otio(t, d, o)


def fresh(d, w, h):
    edits.clear(d)
    d.set_project(width=w, height=h, fps=FPS)


def place(t, d, media, start=0):
    """Places `media` whole (a still for SECS frames) at `start` on v0. -> clip id"""
    out = SECS if media.endswith(STILLS) else None
    return d.place_clip(d.import_media(t.media(media)), "v0", start, 0, out)


# ---------------------------------------------------------------- sections 1 and 3: exports
def exports(t, d, o):
    for label, media, w, h, rect in SOURCES:
        fresh(d, w, h)
        place(t, d, media)
        name = o.export(media + f"-{w}x{h}")
        t.measure(f"{label}: the export is tagged BT.709 limited range, all four tags",
                  lambda name=name: observe.colour_tags(o.path(name)), lambda v: v == TAGGED_709, f"{TAGGED_709}")
        if rect == "turned":
            fn = (lambda name=name: turned_error(o.path(name), 0.3))
        else:
            fn = (lambda name=name, rect=rect: o.error(name, 0.3, rect))
        t.measure(f"{label}: the export's patches are within 4 levels of the true colours, read as tagged", fn,
                  lambda v: v[0] <= 4, "<= 4; the detail names the worst patch")


# ---------------------------------------------------------------- 3b: lossless planes, crops
def planes(path):
    return observe.pixels(path, 0, "null", "yuv420p")


def lossless(t, d, o):
    W, H = 1280, 720
    y_size = W * H
    for label, media, limit, fx in (
            ("testsrc (hard colour edges at odd places)", "cs-testsrc.mp4", {"p99": 2, "mean": 0.2}, False),
            ("the patch grid (edges on the 2 x 2 grid)", "cs-gridll.mp4", {"p99": 0, "mean": 0.01, "max": 2}, False),
            ("testsrc with effects that change nothing (invert twice)", "cs-testsrc.mp4", {"p99": 2, "mean": 0.2},
             "invert"),
            ("testsrc with a switched-off chroma key", "cs-testsrc.mp4", {"p99": 2, "mean": 0.2}, "keyoff")):
        fresh(d, W, H)
        clip = place(t, d, media)
        on = None
        if fx == "invert":
            d.apply_effect(clip, "invert")
            d.apply_effect(clip, "invert")
        elif fx == "keyoff":
            # The key is switched on first and exported (it must change the picture: testsrc's green bars keyed out),
            # then switched off (bypassed, kept): the judge sees the key work before it sees it bypassed.
            eid = d.apply_effect(clip, "chromakey", color=KEY_GREEN)
            on = o.export("keyon", lossless=True)
            d.apply_effect(clip, "chromakey", effect_id=eid, enabled=False)
        name = o.export(f"plain-{media}-{fx}", lossless=True)
        effects = (edits.clip(d.get_state(), clip) or {}).get("effects")

        def same(name=name, media=media, on=on, effects=effects):
            a, b = planes(t.media(media)), planes(o.path(name))
            if len(a) != len(b):
                raise observe.Unmeasurable(f"{len(a)} samples in the source's first frame, {len(b)} in the export's")
            got = (observe.plane_diff(a, b, 0, y_size), observe.plane_diff(a, b, y_size, len(a)))
            if on is None:
                return got
            k = planes(o.path(on))
            keyed = observe.plane_diff(a, k, 0, y_size) if len(k) == len(a) else None
            bypassed = (isinstance(effects, list) and len(effects) == 1 and effects[0].get("effect") == "chromakey"
                        and effects[0].get("enabled") is False)
            return got + ({"the key switched on, Y against the source": keyed, "get_state's effects": effects,
                           "ok": bool(keyed and keyed["mean"] >= KEY_ON_MEAN and bypassed)},)

        def within(v, limit=limit):
            return all(s["p99"] <= limit["p99"] and s["mean"] <= limit["mean"] and s.get("max", 0) <= limit.get(
                "max", 255) for s in v[:2]) and (len(v) == 2 or v[2]["ok"])
        t.measure(f"{label}: a plain clip at the canvas's size exports its own samples (lossless; Y, then U and V, "
                  f"against the source's)" + (
                      f" (the key, on, first changed the export: Y mean difference {KEY_ON_MEAN} or more; then "
                      f"get_state shows it kept and switched off)" if fx == "keyoff" else ""), same, within,
                  f"each plane {limit}")
    # Crops with an odd offset or size, on a 640x360 canvas: the export against the source read whole, cut exactly
    # where the crop says (in RGB) and fitted to the canvas. The first needs no scaling, so its reference is the
    # source's own pixels; the others are scaled a little to fit, and the judge does not know the editor's resampling
    # filter, so each is held to the closest of the references made with five common ones.
    cw, ch = 640, 360
    for (x, y, w, h), at in (((3, 5, 640, 360), None), ((2, 4, 639, 359), None), ((1001, 3, 500, 281), (780, 3))):
        fresh(d, cw, ch)
        clip = place(t, d, "cs-testsrc.mp4")
        d.crop_clip(clip, x, y, w, h)
        name = o.export(f"crop-{x}-{w}", lossless=True)
        cx, cy = at or (x, y)
        scalers = ("lanczos",) if (w, h) == (cw, ch) else CROP_SCALERS

        def cut(name=name, cx=cx, cy=cy, w=w, h=h, scalers=scalers):
            got = planes(o.path(name))
            best = None
            for fl in scalers:
                ref = observe.pixels(t.media("cs-testsrc.mp4"), 0, (
                    f"{AS_709},crop={w}:{h}:{cx}:{cy}:exact=1,scale={cw}:{ch}:force_original_aspect_ratio=decrease:"
                    f"flags={fl}+accurate_rnd+full_chroma_int,pad={cw}:{ch}:(ow-iw)/2:(oh-ih)/2:color=black,"
                    f"scale=out_color_matrix=bt709:out_range=tv:flags=accurate_rnd+full_chroma_int"), "yuv420p")
                if len(ref) != len(got):
                    raise observe.Unmeasurable(f"{len(got)} samples in the export's first frame, want {len(ref)}")
                v = (observe.plane_diff(ref, got, 0, cw * ch), observe.plane_diff(ref, got, cw * ch, len(ref)), fl)
                if best is None or (v[1]["p99"], v[1]["mean"], v[0]["p99"]) < (best[1]["p99"], best[1]["mean"],
                                                                               best[0]["p99"]):
                    best = v
            return best
        t.measure(f"a crop of {w}x{h} at {x},{y}" + (f" (it runs off the right edge: moved in to {cx})" if at else "")
                  + ": the export shows the source's own pixels there (lossless; against the source cut exactly in "
                  "RGB" + (")" if len(scalers) == 1 else " and fitted, the closest of five resampling filters)"), cut,
                  lambda v: v[0]["p99"] <= 1 and v[1]["p99"] <= 1 and v[1]["mean"] <= CROP_UV_MEAN,
                  f"Y and U/V p99 <= 1, U/V mean <= {CROP_UV_MEAN}")


# A chroma plane cut half a sample off (a crop made on the 4:2:0 picture itself) reads U/V p99 27 and 12 on the first
# two crops (mean 0.73 and 0.39), and U/V mean 0.09 to 0.11 on the third; the right cut reads p99 0 and mean 0.004 to
# 0.014 on v0.2.0's exports (judge/PORTING.md, colorspace 3b).
CROP_UV_MEAN = 0.05
# The key that is switched on and then off (3b): a chroma key on pure green, which keys out testsrc's green bars (the
# canvas shows black there), so the export with it on differs from the source by KEY_ON_MEAN or more on average in Y
# (v0.2.0: 21.6 with FFmpeg 4.4, 22.3 with 9.0.2-17).
KEY_GREEN, KEY_ON_MEAN = "0x00FF00", 10
CROP_SCALERS = ("lanczos", "bicubic", "spline", "bilinear", "area")


# ---------------------------------------------------------------- 3c: reversed and slowed copies
def copies(t, d, o):
    for label, media in (("untagged HD VP9", "cs-vp9.webm"), ("BT.601-tagged HD", "cs-601.mp4"),
                         ("a BT.601-tagged HD clip with alpha (FFV1)", "cs-cut601.mkv")):
        for bake in ("reverse", "slow"):
            fresh(d, 1280, 720)
            clip = place(t, d, media)
            before = d.get_state()
            files = edits.files(t)
            what = None
            try:
                if bake == "reverse":
                    d.reverse_clip(clip)
                else:
                    d.set_speed(clip, 0.5)
                    d.smooth_slow_motion(clip, "blend")
            except drv.JudgeError as e:
                what = f"the {bake} failed: {e}"
            after = d.get_state()
            c = edits.clip(after, clip) or next(iter(edits.clips(after, "v0")), None)
            new = edits.new_assets(before, after)
            path = next((a.get("path") for a in after.get("assets", []) if c and a.get("id") == c.get("asset")), None)
            # The copy holds as many frames as the clip plays at 1x: the source's 18 reversed, or 36 (0.5x) slowed.
            frames = SECS if bake == "reverse" else 2 * SECS
            made = what
            if made is None:
                made = (None if c is not None and c.get("asset") in new else
                        f"the clip {c} plays no asset that is new in the State") or new_file(t, files, path,
                                                                                          (t.media(media),))
            if made is None:
                try:  # the judge's own look: a video of the right length
                    n = frame_count(path)
                    made = (None if frames <= n <= frames + 1 and (c or {}).get("length_frames") == frames else
                            f"the copy holds {n} frames and the clip is {(c or {}).get('length_frames')} frames long "
                            f"(want {frames} each, the copy one more at most)")
                except observe.Unmeasurable as e:
                    made = f"the copy {path} cannot be read: {e}"
            name = o.export(f"{bake}-{media}")
            at = 0.3 if bake == "reverse" else 0.6
            t.measure(f"{label}, {'reversed' if bake == 'reverse' else 'slowed to 0.5x with blended frames'}: the clip "
                      f"plays the editor's new copy (a new video file in the editor's folders, {frames} frames), and "
                      f"the export shows the true colours (within 4)",
                      lambda name=name, at=at, made=made: (made or True, o.error(name, at)),
                      lambda v: v[0] is True and v[1][0] <= 4, "a new copy; patches within 4")


# ---------------------------------------------------------------- 2, 5, 6: stills, rendered frames, thumbnails, keys
def stills_and_frames(t, d, o):
    # 2. a JPEG is a still: placed whole, as long as a PNG placed whole
    fresh(d, 1280, 720)
    jpg = d.place_clip(d.import_media(t.media("cs-grid.jpg")), "v0", 0, 0)
    png = d.place_clip(d.import_media(t.media("cs-grid.png")), "v0", 600, 0)
    st = d.get_state()
    lens = [(edits.clip(st, c) or {}).get("length_frames") for c in (jpg, png)]
    t.check("a JPEG file is a still: placed whole, it lasts as long as a PNG placed whole (the editor's still length, "
            "over 1 s)", lens[0] == lens[1] and isinstance(lens[0], int) and lens[0] > FPS, f"JPEG, PNG: {lens}")
    # 5. render_frame, then after a preview render (render_frame may be served from it)
    fresh(d, 1280, 720)
    clip = place(t, d, "cs-hd.mp4")
    asset = (edits.clip(d.get_state(), clip) or {}).get("asset")
    o.render("frame", 0.3)
    t.measure("render_frame of untagged HD: its patches within 6 levels of the true colours",
              lambda: o.error("frame", 0, chain="null"), lambda v: v[0] <= 6, "<= 6")
    try:
        d.render_preview()
    except drv.JudgeError as e:
        o.out["frame-preview"] = (None, f"render_preview failed: {e}")
    else:
        o.render("frame-preview", 0.3)
    t.measure("...and after a preview render: within 6", lambda: o.error("frame-preview", 0, chain="null"),
              lambda v: v[0] <= 6, "<= 6")
    # 6. a freeze frame's still: its own file (a new picture in the editor's folders, read as its format is read, as
    # the original read it) and where it plays (render_frame at its middle)
    before = d.get_state()
    files = edits.files(t)
    d.freeze_frame(clip, 6, 15)
    after = d.get_state()
    new = edits.new_assets(before, after)
    still = next((c for c in edits.clips(after, "v0") if c.get("asset") in new), None)
    still_path = next((a.get("path") for a in after.get("assets", []) if still and a.get("id") == still["asset"]),
                      None)
    still_why = (f"no still in the State: v0 {edits.clips(after, 'v0')}" if still is None else
                 new_file(t, files, still_path, (t.media("cs-hd.mp4"),)))
    if still_why is None:
        o.render("still", (still["start_frame"] + 7.5) / FPS)
    else:
        o.out["still"] = (None, f"the still's file is not a new file of the editor's: {still_why}")

    def still_file():
        if still_why:
            raise observe.Unmeasurable(f"the still's file is not a new file of the editor's: {still_why}")
        return picture_error(still_path)
    t.measure("a freeze frame of untagged HD: its still's own file (a new picture in the editor's folders, read as its "
              "format is read) shows the true colours (within 3)", still_file, lambda v: v[0] <= 3, "<= 3")
    t.measure("...and where it plays (render_frame at its middle): within 4",
              lambda: o.error("still", 0, chain="null"), lambda v: v[0] <= 4, "<= 4")

    # 6. a thumbnail: read as its format is read (a JPEG as BT.601 full range)
    def thumb():
        mine = edits.files(t)
        try:
            path = d.thumbnail(asset, 0.2)
        except drv.JudgeError as e:
            raise observe.Unmeasurable(f"thumbnail failed: {e}")
        why = new_file(t, mine, path)
        if why:
            raise observe.Unmeasurable(f"the thumbnail is not a new file of the editor's: {why}")
        return picture_error(path)
    t.measure("a thumbnail of untagged HD (a new picture in the editor's folders), read as its format is read: within "
              "8 levels of the true colours", thumb, lambda v: v[0] <= 8, "<= 8")
    # 6. the colour found for a key on an untagged HD green screen: the screen's colour as the judge reads it (its
    # border, read as BT.709 limited range as the export reads an untagged HD file; 0x1EC83D, the 0x1EC83C it was made
    # from after its coding), within 1, and within the original's 3 of 0x1EC83C
    fresh(d, 1280, 720)
    green = place(t, d, "cs-green.mp4")

    def key():
        pic = observe.Picture(t.media("cs-green.mp4"), 0, AS_709)
        border = [pic.box(x, y, 32, 32) for x, y in ((0, 0), (1248, 0), (0, 688), (1248, 688))]
        screen = tuple(round(sum(b[i] for b in border) / len(border)) for i in range(3))
        try:
            got = d.detect_key_colour(green)
        except drv.JudgeError as e:
            raise observe.Unmeasurable(f"detect_key_colour failed: {e}")
        v = observe.hex_colour(got.get("color"))
        if v is None:
            raise observe.Unmeasurable(f"no hex colour in {got}")
        rgb = ((v >> 16) & 255, (v >> 8) & 255, v & 255)
        return (max(abs(a - b) for a, b in zip(rgb, screen)), max(abs(a - b) for a, b in zip(rgb, (30, 200, 60))),
                "#%02x%02x%02x" % screen, got)
    t.measure("detect_key_colour on an untagged HD green screen finds its colour: within 1 of the screen's border as "
              "the judge reads it, and within 3 of the 0x1EC83C it was made from (read as BT.601 it would be "
              "0x2CE341, 27 off in green)", key, lambda v: v[0] <= 1 and v[1] <= 3,
              "<= 1 of the border, <= 3 of 0x1EC83C")


# ---------------------------------------------------------------- 3d: motion graphics
GRAPHIC_COLOURS = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255), (128, 128, 128), (224, 172, 105),
                   (100, 150, 220), (40, 20, 10)]
GRAPHIC = """import React from "react";
import { AbsoluteFill } from "remotion";
const COLOURS = %s;
export default function Patches() {
  return (
    <AbsoluteFill style={{ display: "flex", flexDirection: "row", flexWrap: "wrap", background: "#000000" }}>
      {COLOURS.map((c, i) => <div key={i} style={{ width: "25%%", height: "50%%", background: c }} />)}
    </AbsoluteFill>
  );
}
""" % json.dumps(["#%02x%02x%02x" % c for c in GRAPHIC_COLOURS])


def rendered(fn):
    """(result or None, what happened) of a render that must succeed, tried twice (as test_graphics_addon_missing:
    v0.2.0 picks a free port for the renderer's server and binds it later, and another process can take it)."""
    said = []
    for _ in range(2):
        try:
            return fn(), "; ".join(said)
        except (drv.ProductError, drv.BadRequest) as e:
            said.append(f"refused: {e.message[:200]}")
    return None, "; ".join(said)


# How many of GRAPHIC_COLOURS each renderer is held to: the built-in renderer all 8; the graphics add-on the first 5
# (red, green, blue, white, grey: the colours a wrong matrix moves by 20 or more where the right one keeps them),
# since its own render already shifts the mid tones (judge/PORTING.md, colorspace 3d).
HELD = {"builtin": 8, "addon": 5}


def graphics(t, d, o):
    for renderer in ("builtin", "addon"):
        if renderer == "builtin":
            name = ("a motion graphic that draws 8 flat colours (the built-in renderer), as its own clip: the export "
                    "shows its colours (within 4)")
        else:
            name = ("a motion graphic that draws flat colours (the graphics add-on), as its own clip: the export shows "
                    "its red, green, blue, white and grey (within 4; the detail also has its other colours)")
        if renderer == "addon" and t.graphics_addon is None:
            t.not_applicable(name, t.graphics_addon_why)
            continue
        fresh(d, 1280, 720)
        try:
            d.set_graphics_renderer(renderer)
            r, said = rendered(lambda: d.add_graphic(code=GRAPHIC, duration_s=0.2))
        except drv.JudgeError as e:
            r, said = None, f"the renderer could not be chosen: {e}"
        if r is None:
            o.out[f"graphic-{renderer}"] = (None, f"the graphic did not render: {said}")
        else:
            o.export(f"graphic-{renderer}")
        def colours(renderer=renderer):
            cells = observe.Picture(o.path(f"graphic-{renderer}"), 0.1, AS_709).cells(4, 2, half=6)
            n = HELD[renderer]
            return worst(cells[:n], GRAPHIC_COLOURS[:n]) + ([tuple(round(v) for v in c) for c in cells],)
        t.measure(name, colours, lambda v: v[0] <= 4, "<= 4")


# ---------------------------------------------------------------- an OTIO file that says nothing about colour (not
# the original's section 4, which stays v0.2.0-only: judge/PORTING.md)
def foreign_otio(t, d, o):
    media = t.media("cs-601.mp4")
    rt = (lambda v: {"OTIO_SCHEMA": "RationalTime.1", "rate": FPS, "value": v})
    doc = {"OTIO_SCHEMA": "Timeline.1", "name": "from another editor", "global_start_time": None,
           "tracks": {"OTIO_SCHEMA": "Stack.1", "name": "tracks", "children": [
               {"OTIO_SCHEMA": "Track.1", "name": "V1", "kind": "Video", "children": [
                   {"OTIO_SCHEMA": "Clip.2", "name": "cs-601.mp4",
                    "source_range": {"OTIO_SCHEMA": "TimeRange.1", "start_time": rt(0), "duration": rt(SECS)},
                    "media_references": {"DEFAULT_MEDIA": {
                        "OTIO_SCHEMA": "ExternalReference.1", "target_url": "file://" + media,
                        "available_range": {"OTIO_SCHEMA": "TimeRange.1", "start_time": rt(0),
                                            "duration": rt(SECS)}}},
                    "active_media_reference_key": "DEFAULT_MEDIA"}]}]}}
    path = t.path("in", "foreign.otio")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)
    what = None
    try:
        d.import_otio(path)
        d.set_project(width=1280, height=720, fps=FPS)
    except drv.JudgeError as e:
        what = f"the import failed: {e}"
    st = d.get_state()
    v0 = edits.clips(st, "v0")
    paths = {a.get("id"): a.get("path") for a in st.get("assets", [])}
    placed = [(c.get("length_frames"), paths.get(c.get("asset"))) for c in v0]
    name = o.export("foreign-otio")
    t.measure("an OTIO file from another editor (it says nothing of its media's colours) opens with its BT.601-tagged "
              "HD clip, and the export shows the true colours (within 4)",
              lambda: (placed == [(SECS, media)] or what or f"the State's v0: {placed}", o.error(name)),
              lambda v: v[0] is True and v[1][0] <= 4, f"one clip of {SECS} frames of the media; patches within 4")
