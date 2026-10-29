"""Colour space: every source is read the way players read it, and every export is BT.709 limited range with all
four colour tags, so the export shows the source's true colours everywhere. Port of
packages/core/scripts/smoke-colorspace.ts (judge/PORTING.md has the map of its sections): the reading rules and the
editor's colour bookkeeping are internals; what a user sees of them is judged here, on the files the editor writes.

The sources are make.sh's cs-* fixtures: an 8 x 4 grid of 32 flat patches (full and 75 % bars, skin, sky, darks,
greys) coded from exact RGB with a known matrix and range, and tagged with exactly the tags named (or none), so the
true colour of every patch is known; each also shows, in a band of sixteen stripes over the grid's top left corner
(above the patches' middles), its own number (NUMBER: no two sources share one) and each frame's index (0 to 17; 0 in
a still) (band(), marks()). The judge reads an export as BT.709 limited range (read_as: an explicit reading, not its
own FFmpeg's guess) and checks its tags apart (ffprobe); a patch is the mean of the 6 x 6 block at its middle (the
original's reading), and a source read the wrong way is off by 30 to 40 levels on the saturated patches, so the
original's limits (4 levels on an export, 6 on a rendered frame, 3 on a still, 8 on a JPEG thumbnail) tell them apart
(the judge's limit on the still where it plays, inverted, is 3 too).

Every file the editor is asked to make (an export, a rendered frame, a reversed or slowed copy, a still, a thumbnail)
must show what only that request on that clip's own source at that moment makes (README.md, threat model): its
source's number and the frames asked for, in the band, at the canvas's size; the cases that would look the same by
design (two plain lossless clips, the two renders, the two graphics renderers, the OTIO clip and section 1's export
of its media) each play another span or order. So no earlier export, render, copy or still, no file of the judge's and
no copy of one (with bytes added or not) passes for it.

- Exports (sections 1 and 3): untagged HD (BT.709), BT.709-tagged HD, BT.601-tagged HD, untagged HD VP9 (BT.601),
  BT.601-tagged SD on its own canvas and pillarboxed on an HD one, full range BT.709, an RGB still (PNG), a JPEG
  still (BT.601 full range); and the reading rules' other cases: untagged SD (BT.601), BT.709-tagged SD (the tag wins
  over the size), HD with only its matrix tagged, full range with no matrix (BT.601 full, as a JPEG), and an untagged
  SD clip shown turned a quarter (its 480 coded lines make it SD, whatever way it is shown; the only canvas of its
  size, 480x848, and its band is not read on the turned picture).
- Lossless (3b): a plain clip at the canvas's size exports its own 4:2:0 samples (also with effects that change
  nothing, and with a chroma key that is switched off: first seen to key, then bypassed), each played from a frame of
  its own (LL_FROM); a crop with an odd offset or size cuts the picture where it says; a clip zoomed 1.5 times (a
  fixed scale) is enlarged with smooth colour (against the source enlarged in RGB by the judge).
- Copies (3c): a reversed and a slowed (blended frames) copy of a BT.601 source, of untagged VP9 and of an FFV1 clip
  with alpha export with the source's colours. The copy must be a new file of the editor's, by the judge's own look
  (new_file: every file listed with its device, inode and bytes before the action; the copy at its real path, not
  the judge's own, not the same bytes as any file listed before, gone since or not, or as the source, and not the
  same file as one of the judge's own files, moved since or not, or as a file still at its path), and its frames
  and the export's must be what the operation makes on this source, by the band: this source's number in every
  frame, and its 18 frames backwards (17 first), or at half speed with blended frames between them (36 frames).
- Motion graphics (3d): a graphic that draws flat colours exports with them where it draws them (built-in renderer;
  the graphics add-on when the judge has one, with the colours in another order).
- An OTIO file from another editor, which says nothing about its media's colours, opens and exports with the true
  colours, and with the span of its media it names (frames 6 to 17): a check of its own. The original's section 4 (a
  project saved before the editor recorded each file's colour description) stays v0.2.0-only: an OTIO import reads
  the media again, so it never meets such a project, and only the editor's own project format can hold one.
- render_frame at frame 9, and after a preview render at frame 15 (5); a freeze frame's still of a clip with an
  invert (its own file, a new one as for the copies, showing the frame held, 6, of cs-hd, by the band, with or
  without the clip's invert; and where it plays, where it must show that frame inverted, as the clip's look makes
  it and the asset's own frame does not), made while a picture on the track above covers the timeline (the still is
  the clip's own frame, so a render of the composite that leaves the cover visible does not pass for it); a
  thumbnail at 0.4 s, frame 12, which no earlier file shows (a new file too, showing that frame or the one next to
  it, of cs-hd, in its true colours although the clip is inverted, also made under the cover); and the colour found
  for a key (6: within 1 level of the screen's border as the judge reads it); a JPEG is a still (2). What this
  cannot rule out (README.md, "What it does not defend against"): a still rebuilt from other operations of the
  editor, such as a thumbnail of the asset placed with the clip's effects copied onto it, or a render_frame made
  with the tracks above hidden (that one reads 4 levels off where it plays, against the limit of 3, where the real
  still reads 2: a margin of 1 level each way).

Every check is recorded on every path (a check whose input is missing fails with the reason), so CHECKS is exact.
"""
import json
import os

import driver as drv
import edits
import observe

PORT_BOUND = True
TIMEOUT = 1800
CHECKS = 59
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

    def error(self, name, at=0.3, rect=None, chain=AS_709, want=None):
        """(the largest error of any patch against the true colours (or `want`), the worst patch), the export read
        with `chain`."""
        cells = observe.Picture(self.path(name), at, chain).cells(8, 4, rect)
        return worst(cells, want or PATCH)


def worst(cells, want=PATCH):
    err = [max(abs(g - w) for g, w in zip(c, p)) for c, p in zip(cells, want)]
    k = max(range(len(err)), key=err.__getitem__)
    return round(err[k], 1), f"patch {k} {tuple(round(v) for v in cells[k])} for {want[k]}"


def snapshot(t):
    """Every regular file in the test's folder just before an action (edits.files: the judge's own files included),
    as the judge sees it: {path: (device, inode, sha256)}. Taken before each action, so a file that is moved or
    deleted after it is still known by its identity and its bytes."""
    files = list(edits.files(t))
    seen = t.look(files=files, stat=files)
    return {p: ((seen["stat"].get(p) or {}).get("dev"), (seen["stat"].get(p) or {}).get("ino"), seen["files"].get(p))
            for p in files}


def new_file(t, before, path, sources=()):
    """Why `path` (a file the editor reports it made: a copy, a still, a thumbnail) is not a new file of the editor's,
    or None when it is. `before` is snapshot(t) taken just before the action. The judge's own look decides, never the
    path's spelling: the file, made real (links and "/./" resolved), must be a regular file in the test's folder now,
    outside the judge's own folders (out/, in/), not at a path listed before, and not the same bytes (sha256) as any
    file listed before, still there or not, or as the media `sources` it was made from; nor the same file (device and
    inode) as one of the judge's own files listed before (out/, in/; still there or moved since), as the sources, or
    as any other file listed before that is still at its path (a hard link). So a link, a hard link, a moved file of
    the judge's or a copy of a file that was already there is not a new file. (An inode of a file the editor deleted
    since may be given to the new file, so a gone file of the editor's own counts by its bytes only. That the file
    holds what the action makes is judged on its pictures.)"""
    if not isinstance(path, str) or not path:
        return f"no file named ({path!r})"
    real = os.path.realpath(path)
    scratch = os.path.realpath(t.scratch)
    if not real.startswith(scratch + os.sep):
        return f"{path} is not in the test's folder"
    mine = [os.path.join(scratch, m) + os.sep for m in ("out", "in")]
    for m in mine:
        if real.startswith(m):
            return f"{path} is in the judge's own folder {os.path.basename(m.rstrip(os.sep))}/"
    if real in {os.path.realpath(p) for p in before}:
        return f"{path} was there before the action"
    seen = t.look(files=[real], stat=[real])
    st, digest = seen["stat"].get(real), seen["files"].get(real)
    if not st or st.get("type") != "file" or digest is None:
        return f"{path} is not a regular file the judge can read in the test's folder"
    ident = (st.get("dev"), st.get("ino"))
    known = {p: (dev, ino, sha, any(os.path.realpath(p).startswith(m) for m in mine))
             for p, (dev, ino, sha) in before.items()}
    for src in sources:
        info = os.stat(src)
        known[src] = (info.st_dev, info.st_ino, observe.sha256(src), True)
    for p, (dev, ino, sha, strict) in known.items():
        if sha is not None and sha == digest:
            return f"{path} holds the same bytes as {p}, which was there before the action"
    same = [p for p, (dev, ino, sha, strict) in known.items() if dev is not None and (dev, ino) == ident]
    still = t.look(stat=[p for p in same if not known[p][3]])["stat"] if same else {}
    for p in same:
        if known[p][3] or (dev_ino(still.get(p)) == ident):
            return f"{path} is the same file (device and inode) as {p}, which was there before the action"
    return None


def dev_ino(st):
    return (st.get("dev"), st.get("ino")) if st else None


# ---------------------------------------------------------------- the band: the file's number and the frame's index
# (make.sh: the cs-* pictures). The band over the picture's top left corner (x < W/2, y < H/16) is read scaled to BAND
# (area average), and each of its sixteen stripes as the mean grey of its middle half: over BRIGHT a set bit, under
# DARK a clear one, between them a stripe that is neither (a blend of two frames whose bit differs reads about 125:
# grey 30 and 220 in equal parts). Stripes 0 to 7 are the frame's index, 8 to 15 the source's own number (NUMBER).
BAND, BRIGHT, DARK = (512, 32), 160, 90
NUMBER = {"cs-hd.mp4": 1, "cs-709.mp4": 2, "cs-601.mp4": 3, "cs-sd601.mp4": 4, "cs-sd.mp4": 5, "cs-sd709.mp4": 6,
          "cs-full709.mp4": 7, "cs-fullnm.mp4": 8, "cs-partial.mp4": 9, "cs-vp9.webm": 10, "cs-cut601.mkv": 11,
          "cs-rotsd.mp4": 12, "cs-grid.png": 13, "cs-grid.jpg": 14, "cs-testsrc.mp4": 15}


def band(path, formats=observe.MEDIA, rect=None):
    """The band of every decoded frame of the video (or picture) at `path`, over the picture at `rect` (x, y, w, h;
    the whole frame by default): [[the grey of stripes 0 to 15]]."""
    w, h = BAND
    x, y, rw, rh = rect or (0, 0, None, None)
    crop = (f"crop=w=iw/2:h=ih/16:x=0:y=0" if rect is None else f"crop=w={rw // 2}:h={rh // 16}:x={x}:y={y}")
    raw = observe.pixels(path, 0, f"{crop},scale={w}:{h}:flags=area", "gray", 1000, formats)
    sw, out = w // 16, []
    for k in range(len(raw) // (w * h)):
        f = raw[k * w * h:(k + 1) * w * h]
        ys, row = range(h // 4, 3 * h // 4), []
        for b in range(16):
            xs = range(b * sw + sw // 4, b * sw + 3 * sw // 4)
            row.append(round(sum(f[y * w + x] for y in ys for x in xs) / (len(xs) * len(ys))))
        out.append(row)
    return out


def bits(stripes):
    """The number that eight stripes show, or None when a stripe is neither set nor clear (a blended frame)."""
    if any(DARK <= v <= BRIGHT for v in stripes):
        return None
    return sum(1 << b for b, v in enumerate(stripes) if v > BRIGHT)


def marks(path, formats=observe.MEDIA, rect=None):
    """[(the frame's index or None, the source's number or None)] of every frame at `path`."""
    return [(bits(s[:8]), bits(s[8:])) for s in band(path, formats, rect)]


def fmts(media):
    """The demuxers a source may be read with: a JPEG or PNG still as a picture."""
    return observe.STILL if media.endswith(STILLS) else observe.MEDIA


def indexes(path, formats=observe.MEDIA, rect=None):
    return [i for i, _ in marks(path, formats, rect)]


def sources(path, formats=observe.MEDIA, rect=None):
    """The source numbers its frames show (a set: one number when every frame comes from one source)."""
    return {n for _, n in marks(path, formats, rect)}


def picture_error(path, want=None):
    """worst() of a picture the editor wrote (a still, a thumbnail), read as its format is read: a PNG as its RGB, a
    JPEG as BT.601 full range; against the true colours, or `want`. -> (error, worst patch, codec)"""
    codec = (observe.video_stream(path, observe.STILL) or {}).get("codec_name")
    chain = {"mjpeg": observe.read_as("bt601", "pc"), "png": "null"}.get(codec)
    if chain is None:
        raise observe.Unmeasurable(f"{os.path.basename(path)} is {codec}, not a JPEG or PNG picture")
    return worst(observe.Picture(path, 0, chain, observe.STILL).cells(8, 4), want or PATCH) + (codec,)


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
def own_frames(path, media, frames, canvas, rect=None, first=0):
    """Whether the export at `path` is this source's own picture, whole and in turn: the canvas's size, every frame
    showing the source's number (NUMBER) in its band, and its frame indexes `first`, first + 1, ... for `frames`
    frames (a still: index 0 in each of `frames` frames; one more frame at the end at most). So an export of another
    source, of another canvas or of another span of this one does not pass for it. -> (ok, what the judge read)"""
    w, h, _ = observe.size(path)
    m = marks(path, observe.MEDIA, rect)
    seq, nums = [i for i, _ in m], {n for _, n in m}
    want = [0] * frames if media.endswith(STILLS) else list(range(first, first + frames))
    ok = ((w, h) == canvas and nums == {NUMBER[media]} and seq[:frames] == want
          and len(seq) in (frames, frames + 1) and (len(seq) == frames or seq[-1] == want[-1]))
    return ok, f"{w}x{h}, source number {sorted(nums, key=str)}, frames {shown(seq)}"


EXPORT_FROM = 2  # the first frame of each video source that section 1's exports play


def exports(t, d, o):
    for label, media, w, h, rect in SOURCES:
        fresh(d, w, h)
        # A video plays from its frame EXPORT_FROM (a still for SECS frames): the source file itself, or a copy of
        # it, is not this export (a BT.709-tagged source already looks as its export must).
        if media.endswith(STILLS):
            place(t, d, media)
        else:
            d.place_clip(d.import_media(t.media(media)), "v0", 0, EXPORT_FROM)
        name = o.export(media + f"-{w}x{h}")
        t.measure(f"{label}: the export is tagged BT.709 limited range, all four tags",
                  lambda name=name: observe.colour_tags(o.path(name)), lambda v: v == TAGGED_709, f"{TAGGED_709}")
        if rect == "turned":
            # The band is not read on the turned picture: this canvas (480x848) is the only one of its size here.
            def fn(name=name, w=w, h=h):
                size = observe.size(o.path(name))[:2]
                frames = observe.decode(o.path(name))["video_frames"]
                return turned_error(o.path(name), 0.3) + ((size == (w, h) and frames == SECS - EXPORT_FROM,
                                                           f"{size[0]}x{size[1]}, {frames} frames"),)
            what = f"at the canvas's size ({w}x{h}), {SECS - EXPORT_FROM} frames (from its frame {EXPORT_FROM})"
        else:
            def fn(name=name, rect=rect, media=media, w=w, h=h):
                n, first = (SECS, 0) if media.endswith(STILLS) else (SECS - EXPORT_FROM, EXPORT_FROM)
                return o.error(name, 0.3, rect) + (own_frames(o.path(name), media, n, (w, h), rect, first),)
            what = (f"this source's own frames (its number, {NUMBER[media]}, and in the band its frames from "
                    f"{EXPORT_FROM} in turn, a still's for {SECS} frames; at the canvas's size, {w}x{h})")
        t.measure(f"{label}: the export shows {what}, and its patches are within 4 levels of the true colours, read "
                  f"as tagged", fn, lambda v: v[0] <= 4 and v[2][0], "<= 4, its own frames; the detail names the "
                  "worst patch, then what the band shows")


# ---------------------------------------------------------------- 3b: lossless planes, crops
def planes(path, at=0):
    """The Y, U and V planes of the frame at `at` s (the first one at or after it) as yuv420p bytes."""
    return observe.pixels(path, at, "null", "yuv420p")


def frame_at(k):
    """A time that seeks to frame k of a 30 fps file (a quarter frame before it, between frames after rounding)."""
    return max(0.0, (k - 0.25) / FPS)


# Each lossless export plays its clip from a frame of its own (LL_FROM), so no two of them must show the same frames
# (two of the plain cases change nothing by design): an export of another case is not one of this one. cs-testsrc's
# band shows its number (15) and the frame (make.sh); its 12 frames also differ from each other (testsrc moves).
LL_FROM = {"cs-testsrc.mp4-False": 1, "cs-gridll.mp4-False": 4, "cs-testsrc.mp4-invert": 3,
           "cs-testsrc.mp4-keyoff": 5, "crop-3": 0, "crop-2": 7, "crop-1001": 0, "zoom": 0}
LL_FRAMES = 12  # cs-testsrc's and cs-gridll's frames (0.4 s)


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
        start = LL_FROM[f"{media}-{fx}"]
        clip = d.place_clip(d.import_media(t.media(media)), "v0", 0, start)
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

        def same(name=name, media=media, on=on, effects=effects, start=start):
            a, b = planes(t.media(media), frame_at(start)), planes(o.path(name))
            if len(a) != len(b):
                raise observe.Unmeasurable(f"{len(a)} samples in the source's frame {start}, {len(b)} in the export's")
            got = (observe.plane_diff(a, b, 0, y_size), observe.plane_diff(a, b, y_size, len(a)))
            if media == "cs-testsrc.mp4":
                m = marks(o.path(name))
                seq = [i for i, _ in m]
                own = (seq[:LL_FRAMES - start] == list(range(start, LL_FRAMES)) and len(seq) <= LL_FRAMES - start + 1
                       and {n for _, n in m} == {NUMBER[media]})
            else:  # the grid has no band (and every frame alike): its own length, from its frame `start`
                seq = None
                own = (observe.size(o.path(name))[:2] == (W, H)
                       and observe.decode(o.path(name))["video_frames"] == LL_FRAMES - start)
            got += ({"its own frames (the band: the source's number and its frames from " + str(start) + ")": own,
                     "frames": shown(seq) if seq is not None else "no band"},)
            if on is None:
                return got
            k = planes(o.path(on))
            keyed = observe.plane_diff(a, k, 0, y_size) if len(k) == len(a) else None
            km = marks(o.path(on))  # the key leaves the grey band alone: the keyed export's own frames too
            k_own = ([i for i, _ in km][:LL_FRAMES - start] == list(range(start, LL_FRAMES))
                     and {n for _, n in km} == {NUMBER[media]})
            bypassed = (isinstance(effects, list) and len(effects) == 1 and effects[0].get("effect") == "chromakey"
                        and effects[0].get("enabled") is False)
            return got + ({"the key switched on, Y against the source": keyed, "its own frames": k_own,
                           "get_state's effects": effects,
                           "ok": bool(keyed and keyed["mean"] >= KEY_ON_MEAN and bypassed and k_own)},)

        def within(v, limit=limit):
            own = next(iter(v[2].values()))
            return all(s["p99"] <= limit["p99"] and s["mean"] <= limit["mean"] and s.get("max", 0) <= limit.get(
                "max", 255) for s in v[:2]) and own and (len(v) == 3 or v[3]["ok"])
        t.measure(f"{label}: a plain clip at the canvas's size exports its own samples (lossless, played from frame "
                  f"{start}; Y, then U and V, against the source's there; and the band shows the source's number and "
                  f"its frames from {start} in turn)" + (
                      f" (the key, on, first changed the export: Y mean difference {KEY_ON_MEAN} or more; then "
                      f"get_state shows it kept and switched off; the keyed export shows the source's own frames from {start} "
                      f"too)" if fx == "keyoff" else ""), same, within,
                  f"each plane {limit}")
    # Crops with an odd offset or size, on a 640x360 canvas: the export against the source read whole, cut exactly
    # where the crop says (in RGB) and fitted to the canvas, each played from a frame of its own (LL_FROM). The first
    # needs no scaling, so its reference is the source's own pixels; the others are scaled a little to fit, and the
    # judge does not know the editor's resampling filter, so each is held to the closest of the references made with
    # five common ones.
    cw, ch = 640, 360
    for (x, y, w, h), at in (((3, 5, 640, 360), None), ((2, 4, 639, 359), None), ((1001, 3, 500, 281), (780, 3))):
        fresh(d, cw, ch)
        start = LL_FROM[f"crop-{x}"]
        clip = d.place_clip(d.import_media(t.media("cs-testsrc.mp4")), "v0", 0, start)
        d.crop_clip(clip, x, y, w, h)
        name = o.export(f"crop-{x}-{w}", lossless=True)
        cx, cy = at or (x, y)
        scalers = ("lanczos",) if (w, h) == (cw, ch) else CROP_SCALERS

        def cut(name=name, cx=cx, cy=cy, w=w, h=h, scalers=scalers, start=start):
            got = planes(o.path(name))
            best = None
            for fl in scalers:
                ref = observe.pixels(t.media("cs-testsrc.mp4"), frame_at(start), (
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
                  + f", played from frame {start}: the export shows the source's own pixels there (lossless; against "
                  "the source's frame cut exactly in RGB" + (")" if len(scalers) == 1 else
                                                              " and fitted, the closest of five resampling filters)"),
                  cut, lambda v: v[0]["p99"] <= 1 and v[0]["mean"] <= CROP_Y_MEAN and v[1]["p99"] <= 1
                  and v[1]["mean"] <= CROP_UV_MEAN, f"Y and U/V p99 <= 1, Y mean <= {CROP_Y_MEAN}, U/V mean <= "
                  f"{CROP_UV_MEAN}")


    # A fixed zoom (set_transform scale 1.5, about the middle): the export against the source read in RGB, enlarged
    # 1.5 times with each of five common resampling filters and its middle cut out, the closest of them. A zoomed
    # clip's colour must be read smoothly (interpolated) before it is enlarged: read sample by sample, as a clip at its
    # own size may be, its colour edges come out coarse and blocky (ZOOM_* below). (An animated scale stays
    # v0.2.0-only: judge/PORTING.md, colorspace 1.)
    fresh(d, W, H)
    clip = place(t, d, "cs-testsrc.mp4")
    d.set_transform(clip, scale=1.5)
    name = o.export("zoom-1.5", lossless=True)

    def zoomed(name=name):
        got = planes(o.path(name))
        best = None
        for fl in CROP_SCALERS:
            ref = observe.pixels(t.media("cs-testsrc.mp4"), 0, (
                f"{AS_709},scale=1920:1080:flags={fl}+accurate_rnd+full_chroma_int,crop=1280:720:320:180,"
                f"scale=out_color_matrix=bt709:out_range=tv:flags=accurate_rnd+full_chroma_int"), "yuv420p")
            if len(ref) != len(got):
                raise observe.Unmeasurable(f"{len(got)} samples in the export's first frame, want {len(ref)}")
            v = (observe.plane_diff(ref, got, 0, y_size), observe.plane_diff(ref, got, y_size, len(ref)), fl)
            if best is None or (v[1]["p99"], v[1]["mean"], v[0]["p99"]) < (best[1]["p99"], best[1]["mean"],
                                                                           best[0]["p99"]):
                best = v
        return best
    t.measure(f"testsrc zoomed 1.5 times (set_transform scale 1.5): the export is the source enlarged about its middle "
              f"with smooth colour (lossless; against the source enlarged in RGB, the closest of five resampling "
              f"filters: Y p99 <= {ZOOM_Y_P99}, U/V p99 under {ZOOM_UV_P99})", zoomed,
              lambda v: v[0]["p99"] <= ZOOM_Y_P99 and v[1]["p99"] < ZOOM_UV_P99,
              f"Y p99 <= {ZOOM_Y_P99}, U/V p99 < {ZOOM_UV_P99}")


# The zoom (3b; judge/PORTING.md, colorspace 1): v0.2.0's and this tree's exports read Y p99 0 and U/V p99 1 (mean
# 0.015) against the closest reference (lanczos) with FFmpeg 4.4 and 9.0.2-17; the same zoom with its colour read
# sample by sample (a blocky reading made by the judge in a probe) reads U/V p99 11 to 12 (mean 0.65 to 0.69), Y 2 to 5.
ZOOM_Y_P99, ZOOM_UV_P99 = 2, 4
# A chroma plane cut half a sample off (a crop made on the 4:2:0 picture itself) reads U/V p99 27 and 12 on the first
# two crops (mean 0.73 and 0.39), and U/V mean 0.09 to 0.11 on the third; the right cut reads p99 0 and mean 0.004 to
# 0.014 on v0.2.0's exports (judge/PORTING.md, colorspace 3b).
CROP_UV_MEAN = 0.05
# The crops' Y mean against their reference: v0.2.0 and this tree read 0.0 with FFmpeg 4.4 and 9.0.2-17 (testsrc's
# frames differ from each other by 0.4 on average, and the band's stripes by more).
CROP_Y_MEAN = 0.2
# The key that is switched on and then off (3b): a chroma key on pure green, which keys out testsrc's green bars (the
# canvas shows black there), so the export with it on differs from the source by KEY_ON_MEAN or more on average in Y
# (v0.2.0: 21.6 with FFmpeg 4.4, 22.3 with 9.0.2-17).
KEY_GREEN, KEY_ON_MEAN = "0x00FF00", 10
CROP_SCALERS = ("lanczos", "bicubic", "spline", "bilinear", "area")


# ---------------------------------------------------------------- 3c: reversed and slowed copies
def shown(seq):
    """A list of frame indexes as text ("~" for a blended frame)."""
    return ",".join("~" if i is None else str(i) for i in seq)


def reversed_ok(seq):
    """Whether the frames run backwards through the source: its last frame (17) first, then each one before it to
    frame 0 (one more frame at the end at most, frame 0 again)."""
    want = list(range(SECS - 1, -1, -1))
    return seq[:SECS] == want and (len(seq) == SECS or (len(seq) == SECS + 1 and seq[-1] == 0))


def slowed_ok(seq):
    """Whether the frames are the source's at half speed with blended frames between them: 36 frames (one more at
    most), the first is frame 0, every source frame shows in turn (each clean frame the same as the one before or the
    next), and between two clean frames that differ comes a blend of them (a frame that is neither): at least
    SLOW_BLENDS blends, and no clean frame shown more than twice in a row."""
    if not 2 * SECS <= len(seq) <= 2 * SECS + 1 or seq[0] != 0:
        return False
    clean = [i for i in seq if i is not None]
    if clean != sorted(clean) or sorted(set(clean)) != list(range(SECS)):
        return False
    runs, k = [], 0
    while k < len(seq):
        j = k
        while j + 1 < len(seq) and seq[j + 1] == seq[k]:
            j += 1
        runs.append(j - k + 1)
        k = j + 1
    return sum(1 for i in seq if i is None) >= SLOW_BLENDS and max(runs) <= 2


BANDED = tuple(m for m in NUMBER if m != "cs-rotsd.mp4")  # the band of cs-rotsd is turned with its picture
# The least number of blended frames in a slowed copy of the 18 frames: v0.2.0's copies and exports have 13 or 14 (it
# shows some middle frames twice instead), with FFmpeg 4.4 and 9.0.2-17; a copy that repeats each frame has none.
SLOW_BLENDS = 8


def copies(t, d, o):
    # Control: the judge reads each source's own frames as 0 to 17 in turn (so a copy's frames are judged against a
    # known reference).
    t.measure("control: the band of each banded source reads its own number and its frames 0 to 17 in turn (the "
              "judge's reading of make.sh's cs-* videos; a still, index 0), and no two sources show the same number",
              lambda: {m: (shown(indexes(t.media(m), fmts(m))), sorted(sources(t.media(m), fmts(m)), key=str))
                       for m in BANDED},
              lambda v: all(x == (shown([0] if m.endswith(STILLS) else range(LL_FRAMES if m == "cs-testsrc.mp4" else
                                                                             SECS)), [NUMBER[m]])
                            for m, x in v.items()) and len(set(NUMBER.values())) == len(NUMBER),
              "for each: 0,1,...,17 (cs-testsrc 0 to 11, a still 0) and its own number (NUMBER)")
    for label, media in (("untagged HD VP9", "cs-vp9.webm"), ("BT.601-tagged HD", "cs-601.mp4"),
                         ("a BT.601-tagged HD clip with alpha (FFV1)", "cs-cut601.mkv")):
        for bake in ("reverse", "slow"):
            fresh(d, 1280, 720)
            clip = place(t, d, media)
            before = d.get_state()
            files = snapshot(t)
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
            # The clip plays as many frames as the copy holds at 1x: the source's 18 reversed, or 36 (0.5x) slowed.
            frames = SECS if bake == "reverse" else 2 * SECS
            made = what
            if made is None:
                made = (None if c is not None and c.get("asset") in new else
                        f"the clip {c} plays no asset that is new in the State") or new_file(t, files, path,
                                                                                          (t.media(media),))
            if made is None and (c or {}).get("length_frames") != frames:
                made = f"the clip is {(c or {}).get('length_frames')} frames long (want {frames})"
            name = o.export(f"{bake}-{media}")
            at = 0.3 if bake == "reverse" else 0.6
            how = "reversed" if bake == "reverse" else "slowed to 0.5x with blended frames"
            t.measure(f"{label}, {how}: the clip plays the editor's new copy (a new file in the editor's folders, the "
                      f"clip {frames} frames long), and the export shows this source's frames (its number, "
                      f"{NUMBER[media]}, in every frame's band, {frames} frames) in the true colours (within 4)",
                      lambda name=name, at=at, made=made, media=media, frames=frames: (
                          made or True, o.error(name, at),
                          sorted(sources(o.path(name)), key=str) == [NUMBER[media]]
                          and len(indexes(o.path(name))) in (frames, frames + 1)),
                      lambda v: v[0] is True and v[1][0] <= 4 and v[2], "a new copy; patches within 4; its frames")
            ok = reversed_ok if bake == "reverse" else slowed_ok

            def run_of(name=name, made=made, path=path, media=media):
                if made:
                    raise observe.Unmeasurable(f"no copy of the editor's to read: {made}")
                a, b = marks(path), marks(o.path(name))
                ia, ib = [i for i, _ in a], [i for i, _ in b]
                na, nb = {n for _, n in a}, {n for _, n in b}
                return {"copy": shown(ia), "export": shown(ib), "source numbers": [sorted(na, key=str),
                                                                                   sorted(nb, key=str)],
                        "ok": ok(ia) and ok(ib) and na == nb == {NUMBER[media]}}
            t.measure(f"{label}, {how}: the copy's frames and the export's are this source's own (its number, "
                      f"{NUMBER[media]}, in every frame's band) "
                      + ("backwards: its last frame (17) first, down to frame 0" if bake == "reverse" else
                         f"at half speed with blends between them: frames 0 to 17 in turn, each shown twice at most, "
                         f"and at least {SLOW_BLENDS} frames that blend two of them")
                      + " (the band, read by the judge; ~ is a blend)", run_of, lambda v: v["ok"],
                      "the frame indexes of the copy, then of the export, and the source numbers they show")


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
    # 5. render_frame, then after a preview render (render_frame may be served from it), each at a moment of its own
    # (frames 9 and 15 of cs-hd, by the band), so neither frame can stand in for the other
    fresh(d, 1280, 720)
    clip = place(t, d, "cs-hd.mp4")
    asset = (edits.clip(d.get_state(), clip) or {}).get("asset")
    o.render("frame", FRAME_AT[0] / FPS)

    def rendered_at(name, k):
        def fn():
            return o.error(name, 0, chain="null") + (marks(o.path(name))[:1],)
        return fn
    shows = (lambda k: (lambda v: v[0] <= 6 and v[2] == [(k, NUMBER["cs-hd.mp4"])]))
    t.measure(f"render_frame of untagged HD at frame {FRAME_AT[0]}: that frame of the source (the band: its frame "
              f"index and the source's number), its patches within 6 levels of the true colours",
              rendered_at("frame", FRAME_AT[0]), shows(FRAME_AT[0]), f"<= 6; the band ({FRAME_AT[0]}, 1)")
    try:
        d.render_preview()
    except drv.JudgeError as e:
        o.out["frame-preview"] = (None, f"render_preview failed: {e}")
    else:
        o.render("frame-preview", FRAME_AT[1] / FPS)
    t.measure(f"...and after a preview render, at frame {FRAME_AT[1]}: that frame, within 6",
              rendered_at("frame-preview", FRAME_AT[1]), shows(FRAME_AT[1]), f"<= 6; the band ({FRAME_AT[1]}, 1)")
    # 6. a freeze frame's still: its own file (a new picture in the editor's folders, read as its format is read, as
    # the original read it) and where it plays (render_frame at its middle); each shows the frame held (frame 6 of
    # cs-hd, by the band), not another of the clip's or another source's. The clip has a look of its own, an invert,
    # and the still plays with it (PROTOCOL: "with the clip's look"): where it plays it shows the inverted frame (255
    # minus each patch, and the band's stripes inverted: INVERTED), which the asset's own frame (a thumbnail) does not.
    # The still's own file may hold the frame with the look or without it (the editor may keep the look on the still
    # clip: v0.2.0 and this tree do), so it is judged against both and must show one of them. While the freeze is
    # made, a picture on the track above (cs-green, the whole canvas) covers the whole timeline: the still is the
    # clip's own frame, so a frame of the composite (render_frame) that leaves the cover visible does not pass for it;
    # the cover is taken away before the still is rendered where it plays. Where it plays the limit is 3: v0.2.0 and
    # this tree read 2 there (FFmpeg 4.4 and 9.0.2-17), and a render_frame of the held moment with the tracks above
    # hidden, put in the still's place, reads 4 (README.md, "What it does not defend against": a 1-level margin).
    cover_track = d.add_track("video")
    green_asset = d.import_media(t.media("cs-green.mp4"))
    cover_clip(d, green_asset, cover_track)
    try:
        d.apply_effect(clip, "invert")
        look_why = None
    except drv.JudgeError as e:
        look_why = f"the invert was not added to the clip: {e}"
    before = d.get_state()
    files = snapshot(t)
    d.freeze_frame(clip, HELD_FRAME, 15)
    after = d.get_state()
    new = edits.new_assets(before, after)
    still = next((c for c in edits.clips(after, "v0") if c.get("asset") in new), None)
    still_path = next((a.get("path") for a in after.get("assets", []) if still and a.get("id") == still["asset"]),
                      None)
    still_why = (f"no still in the State: v0 {edits.clips(after, 'v0')}" if still is None else
                 new_file(t, files, still_path, (t.media("cs-hd.mp4"),)))
    uncover(d, cover_track)
    if still_why is None and look_why is None:
        # rendered on a canvas of half the size (STILL_CANVAS), so the still's own file (the source's size) does
        # not pass for the frame where it plays
        d.set_project(width=STILL_CANVAS[0], height=STILL_CANVAS[1], fps=FPS)
        o.render("still", (still["start_frame"] + 7.5) / FPS)
        d.set_project(width=1280, height=720, fps=FPS)
    else:
        o.out["still"] = (None, look_why or f"the still's file is not a new file of the editor's: {still_why}")
    held = [(HELD_FRAME, NUMBER["cs-hd.mp4"])]
    held_inverted = [inverted_mark(m) for m in held]

    def still_file():
        if still_why:
            raise observe.Unmeasurable(f"the still's file is not a new file of the editor's: {still_why}")
        band_seen = marks(still_path, observe.STILL)
        plain, with_look = picture_error(still_path), picture_error(still_path, INVERTED)
        return ((plain + (band_seen, "the frame without the clip's look")) if band_seen == held else
                (with_look + (band_seen, "the frame with the clip's look (inverted)")) if band_seen == held_inverted
                else (min(plain[0], with_look[0]), plain[1], plain[2], band_seen, "neither"))
    t.measure(f"a freeze frame of untagged HD at frame {HELD_FRAME} of a clip with an invert, made while a picture on "
              f"the track above covers the timeline: its still's own file (a new picture in the editor's folders, "
              f"read as its format is read) shows that frame of the clip alone (the band: frame {HELD_FRAME} of "
              f"source 1), as the source shows it or with the clip's invert, within 3 of those colours",
              still_file, lambda v: v[0] <= 3 and v[3] in (held, held_inverted),
              f"<= 3; the band {held} (or {held_inverted}, inverted)")
    t.measure(f"...and where it plays (render_frame at its middle, the cover taken away, the canvas set to "
              f"{STILL_CANVAS[0]}x{STILL_CANVAS[1]}): frame {HELD_FRAME} at that size with the clip's invert (the "
              f"band inverted: {held_inverted}; 255 minus each true colour), within 3",
              lambda: o.error("still", 0, chain="null", want=INVERTED) + (marks(o.path("still")),
                                                                          observe.size(o.path("still"))[:2]),
              lambda v: v[0] <= 3 and v[2] == held_inverted and v[3] == STILL_CANVAS,
              f"<= 3; the band {held_inverted}; {STILL_CANVAS[0]}x{STILL_CANVAS[1]}")

    # 6. a thumbnail: read as its format is read (a JPEG as BT.601 full range); it shows the frame at its time, a
    # moment that no earlier file or render shows (frame 12 of cs-hd: the still holds 6, the renders show 9, 15 and
    # 6), made while the cover is on the track above again over the whole timeline, so a frame of the composite does
    # not pass for it; it is the asset's own frame, so it shows the true colours although the clip that plays the
    # asset is inverted
    def thumb():
        cover_clip(d, green_asset, cover_track)
        mine = snapshot(t)
        try:
            path = d.thumbnail(asset, THUMB_AT)
        except drv.JudgeError as e:
            raise observe.Unmeasurable(f"thumbnail failed: {e}")
        finally:
            uncover(d, cover_track)
        why = new_file(t, mine, path, (t.media("cs-hd.mp4"),))
        if why:
            raise observe.Unmeasurable(f"the thumbnail is not a new file of the editor's: {why}")
        return picture_error(path) + (marks(path, observe.STILL),)
    t.measure(f"a thumbnail of untagged HD at {THUMB_AT} s, made while a picture on the track above covers the "
              f"timeline (a new picture in the editor's folders), read as its format is read: the frame there of the "
              f"asset alone (the band: frame {THUMB_FRAMES[1]} of source 1, or the frame next to it), within 8 levels "
              f"of the true colours", thumb,
              lambda v: v[0] <= 8 and v[3] in [[(f, NUMBER["cs-hd.mp4"])] for f in THUMB_FRAMES],
              f"<= 8; the band reads one of {THUMB_FRAMES}, source 1")
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


# The freeze frame's held frame, the moments of the two rendered frames, and the thumbnail's time and the frames it
# may show: the frame at 0.4 s is frame 12 (v0.2.0's thumbnail shows it), and the frame before or after it is allowed
# (a still of "the asset at 0.4 s"). No earlier file shows frames 11 to 13 of cs-hd as a picture: the still holds 6,
# the renders show 9, 15 and the still (6).
HELD_FRAME, FRAME_AT, THUMB_AT, THUMB_FRAMES = 6, (9, 15), 0.4, (11, 12, 13)
STILL_CANVAS = (640, 360)  # the canvas the still is rendered on where it plays
INVERTED = [tuple(255 - v for v in p) for p in PATCH]  # the true colours through the clip's invert


def inverted_mark(mark):
    """The band of a frame through an invert: each stripe flipped, so both numbers read as 255 minus themselves."""
    return tuple(None if v is None else 255 - v for v in mark)


def cover_clip(d, asset, track):
    """Places cs-green (0.4 s) end to end on `track` over the whole timeline (its first 60 frames, more than any
    timeline of this part): a picture over everything below. -> the clips"""
    return [d.place_clip(asset, track, k * 12, 0) for k in range(5)]


def uncover(d, track):
    """Removes every clip of `track` (as get_state lists them: an edit may have split or moved the cover)."""
    for tr in d.get_state().get("tracks", []):
        if tr.get("track") == track:
            for c in tr.get("clips", []):
                d.remove_clip(c["id"])


# ---------------------------------------------------------------- 3d: motion graphics
GRAPHIC_COLOURS = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255), (128, 128, 128), (224, 172, 105),
                   (100, 150, 220), (40, 20, 10)]
# Each renderer draws the colours in an order of its own (ORDER), so the export of one does not pass for the other's.
ORDER = {"builtin": [0, 1, 2, 3, 4, 5, 6, 7], "addon": [2, 3, 0, 4, 1, 7, 5, 6]}
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
"""


def graphic(renderer):
    """(the graphic's code, its colours in the order it draws them) for `renderer`."""
    colours = [GRAPHIC_COLOURS[k] for k in ORDER[renderer]]
    return GRAPHIC % json.dumps(["#%02x%02x%02x" % c for c in colours]), colours


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


# Which of GRAPHIC_COLOURS each renderer is held to: the built-in renderer all 8; the graphics add-on red, green,
# blue, white and grey (the colours a wrong matrix moves by 20 or more where the right one keeps them), since its own
# render already shifts the mid tones (judge/PORTING.md, colorspace 3d).
HELD = {"builtin": range(8), "addon": range(5)}


def graphics(t, d, o):
    for renderer in ("builtin", "addon"):
        if renderer == "builtin":
            name = ("a motion graphic that draws 8 flat colours (the built-in renderer), as its own clip: the export "
                    "shows its colours where it draws them (within 4)")
        else:
            name = ("a motion graphic that draws flat colours (the graphics add-on; in another order than the built-in "
                    "renderer's), as its own clip: the export shows its red, green, blue, white and grey where it draws "
                    "them (within 4; the detail also has its other colours)")
        if renderer == "addon" and t.graphics_addon is None:
            t.not_applicable(name, t.graphics_addon_why)
            continue
        fresh(d, 1280, 720)
        try:
            d.set_graphics_renderer(renderer)
            r, said = rendered(lambda: d.add_graphic(code=graphic(renderer)[0], duration_s=0.2))
        except drv.JudgeError as e:
            r, said = None, f"the renderer could not be chosen: {e}"
        if r is None:
            o.out[f"graphic-{renderer}"] = (None, f"the graphic did not render: {said}")
        else:
            o.export(f"graphic-{renderer}")
        def colours(renderer=renderer):
            cells = observe.Picture(o.path(f"graphic-{renderer}"), 0.1, AS_709).cells(4, 2, half=6)
            drawn = graphic(renderer)[1]
            held = [k for k, c in enumerate(drawn) if GRAPHIC_COLOURS.index(c) in HELD[renderer]]
            return worst([cells[k] for k in held], [drawn[k] for k in held]) + (
                [tuple(round(v) for v in c) for c in cells],)
        t.measure(name, colours, lambda v: v[0] <= 4, "<= 4")


# ---------------------------------------------------------------- an OTIO file that says nothing about colour (not
# the original's section 4, which stays v0.2.0-only: judge/PORTING.md)
OTIO_FROM = 6  # the OTIO clip's first frame of its media: its export is not the one of section 1 (frames 0 to 17)


def foreign_otio(t, d, o):
    media = t.media("cs-601.mp4")
    rt = (lambda v: {"OTIO_SCHEMA": "RationalTime.1", "rate": FPS, "value": v})
    doc = {"OTIO_SCHEMA": "Timeline.1", "name": "from another editor", "global_start_time": None,
           "tracks": {"OTIO_SCHEMA": "Stack.1", "name": "tracks", "children": [
               {"OTIO_SCHEMA": "Track.1", "name": "V1", "kind": "Video", "children": [
                   {"OTIO_SCHEMA": "Clip.2", "name": "cs-601.mp4",
                    "source_range": {"OTIO_SCHEMA": "TimeRange.1", "start_time": rt(OTIO_FROM),
                                     "duration": rt(SECS - OTIO_FROM)},
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
    n = SECS - OTIO_FROM
    t.measure(f"an OTIO file from another editor (it says nothing of its media's colours) opens with its BT.601-tagged "
              f"HD clip (frames {OTIO_FROM} to {SECS - 1} of it), and the export shows those frames of that source (the "
              f"band) in the true colours (within 4)",
              lambda: (placed == [(n, media)] or what or f"the State's v0: {placed}", o.error(name, 0.2),
                       own_frames(o.path(name), "cs-601.mp4", n, (1280, 720), first=OTIO_FROM)),
              lambda v: v[0] is True and v[1][0] <= 4 and v[2][0],
              f"one clip of {n} frames of the media; patches within 4; its frames {OTIO_FROM} to {SECS - 1}")
