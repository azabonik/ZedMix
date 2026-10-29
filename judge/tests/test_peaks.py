"""The waveform overview (the file surface's /peaks, PROTOCOL.md "File surface and network computers"): a request
without the interface's authentication is refused (401), a file the editor would not serve (a system file, a media file
next to an imported one that was never imported) is refused (403) without its path in the answer, a bucket count
outside 16..8192 or not a whole number is refused (400), a file with no sound is refused (422); the answer is
4 x buckets bytes of little-endian float32, readable by the editor's window from any origin, 1600 buckets when none is
asked for, and holds, for each bucket, the loudest |sample| of the file's first channel over that bucket's samples,
divided by the loudest bucket; a file rewritten in place with the same size gets the new file's levels; six files in
a row all get their own. Port of sections 1 to 5 of packages/core/scripts/smoke-peaks.ts (judge/PORTING.md has the map:
its cache files, its count of computations, its requests made at the same moment and its storage section stay with
v0.2.0).

Media (fixtures/make.sh): pk-rise.mkv, pk-fall.mkv and pk-six1.mkv to pk-six5.mkv, each 16 s of stereo PCM at
44.1 kHz (705600 samples, a count that 16, 800 and 1600 all divide, so every way of cutting the buckets into equal
parts gives the same buckets, and so does one at 48 kHz); channel 0 a tone whose level steps on whole seconds
(silence, then loud and quiet parts at moments of each file's own), channel 1 a steady 1 kHz tone at 0.9 (so levels
read from the wrong channel, or from both, are flat, or not silent where channel 0 is). The files have the same size
in bytes. tiny.mp4 has no sound. The test copies pk-rise.mkv to in/rise.mkv and imports the copy, so it can rewrite it
in place (with pk-fall.mkv's bytes), and copies pk-fall.mkv and pk-six1..5.mkv to in/fall0.mkv .. in/fall5.mkv: six
files each loud at a moment of its own, so an answer for one of them does not pass for another.

The judge's reference: channel 0 of the judge's own file decoded by the judge (observe.channel_samples, 44.1 kHz), n
samples in `buckets` buckets of n / buckets samples each, each bucket's loudest |sample|, divided by the loudest
bucket (at least 1e-6) and kept at most 1. The level served for bucket i must be within 0.03 of the reference at a
bucket no more than 1 + i // 200 from it: one bucket of slack, and 0.5 % of the moment for an editor that reads the
sound at another rate or cuts whole-sample buckets from a count that does not divide (on scratch 2.9 s files the
editor of this tree drew each step up to 1.27 % late, 19 buckets of 1600 at the last one; such a cut loses at most one
sample per bucket, under 0.5 % for buckets of 220 samples or more). So a level drawn a bucket off at a step passes,
while the overview shifted by two buckets or more near the start, or squeezed or stretched in time by more than about
0.6 %, puts a level by a step 0.2 or more off (PORTING.md, "batch 4" margins). The 0.03 absorbs another decoding
(16-bit samples / 32768); the wrong channel is off by 1.0, a mix of both by 0.66 or more.

Every check is recorded on every path (a check whose input is missing fails with the reason), so CHECKS is exact.
"""
import os
import shutil
import struct
import time

import observe

PORT_BOUND = True
EXTRA_MEDIA = ("pk-rise.mkv", "pk-fall.mkv", "pk-six1.mkv", "pk-six2.mkv", "pk-six3.mkv", "pk-six4.mkv",
               "pk-six5.mkv")
SIX = ("pk-fall.mkv", "pk-six1.mkv", "pk-six2.mkv", "pk-six3.mkv", "pk-six4.mkv", "pk-six5.mkv")
TIMEOUT = 600
TOL = 0.03
CHECKS = 6 + 6 + 2


def reference(path, buckets):
    """The judge's levels of channel 0 of `path` (see the module's text)."""
    ch = observe.channel_samples(path, 0, 44100)
    n = len(ch)
    size = max(1, n // buckets)
    out = []
    for i in range(buckets):
        out.append(max((abs(v) for v in ch[i * size:min(n, i * size + size)]), default=0.0))
    top = max(max(out), 1e-6)
    return [min(1.0, v / top) for v in out]


def floats(r):
    b = r.get("body") or b""
    if r.get("truncated") or len(b) % 4:
        return None
    return list(struct.unpack(f"<{len(b) // 4}f", b))


def diff(got, want):
    """The largest difference of a served level from the reference at a bucket no more than 1 + i // 200 from its own
    (the slack in time: see the module's text), or None when the counts differ."""
    if got is None or len(got) != len(want):
        return None
    n = len(want)
    return max(min(abs(g - want[j]) for j in range(max(0, i - 1 - i // 200), min(n, i + 2 + i // 200)))
               for i, g in enumerate(got))


def levels(d, path, buckets=None):
    q = {"path": path}
    if buckets is not None:
        q["buckets"] = str(buckets)
    return d.http_get("/peaks", q)


def run(t):
    d = t.driver()
    rise = t.path("in", "rise.mkv")
    shutil.copyfile(t.media("pk-rise.mkv"), rise)
    os.chmod(rise, 0o644)
    copies = []
    for i, m in enumerate(SIX):
        p = t.path("in", f"fall{i}.mkv")
        shutil.copyfile(t.media(m), p)
        os.chmod(p, 0o644)
        copies.append(p)
    d.import_media(rise)
    d.import_media(t.media("tiny.mp4"))
    for p in copies:
        d.import_media(p)

    # ---- access and validation
    r = d.http_get("/peaks", {"path": rise}, anonymous=True)
    t.check("without the interface's authentication: 401", r["status"] == 401, f"{r['status']}")
    r = levels(d, "/etc/passwd")
    t.check("a system file (/etc/passwd): 403", r["status"] == 403, f"{r['status']}")
    t.check("the refusal does not repeat the path", b"/etc/passwd" not in (r.get("body") or b""),
            (r.get("body") or b"")[:200].decode("utf-8", "replace"))
    r = levels(d, t.media("pk-fall.mkv"))
    t.check("a media file that was never imported: 403", r["status"] == 403, f"{r['status']}")
    bad = {b: levels(d, rise, b)["status"] for b in ("0", "15", "8193", "1.5", "abc", "", "1e3x")}
    t.check("a bucket count outside 16..8192 or not a whole number: 400 each",
            all(v == 400 for v in bad.values()), f"{bad}")
    r = levels(d, t.media("tiny.mp4"))
    t.check("a file with no sound: 422", r["status"] == 422, f"{r['status']}")

    # ---- the values
    r = levels(d, rise)
    h = {k.lower(): v for k, v in (r.get("headers") or {}).items()}
    t.check("no bucket count: 200, octet-stream, 1600 buckets (6400 bytes)",
            r["status"] == 200 and r.get("content_type", "").split(";")[0].strip() == "application/octet-stream"
            and r.get("body_length") == 6400, f"{r['status']}, {r.get('content_type')}, {r.get('body_length')} bytes")
    t.check("readable by the editor's window from any origin (Access-Control-Allow-Origin *)",
            h.get("access-control-allow-origin") == "*", f"{h.get('access-control-allow-origin')!r}")
    ref = reference(rise, 1600)
    got = floats(r)
    dv = diff(got, ref)
    t.check(f"each of the 1600 levels is channel 0's loudest sample in its bucket over the loudest bucket (within "
            f"{TOL})", dv is not None and dv <= TOL, f"largest difference {dv}")
    top = None if not got else max(range(len(got)), key=lambda i: got[i])
    t.check("it is channel 0's (silent for its first 2 s, loudest from 9 to 13 s), not channel 1's (steady)",
            got is not None and len(got) == 1600 and max(got[:190]) < 0.02 and 890 <= top < 1310,
            "no levels" if not got else f"loudest of the first 190 {max(got[:190]):.3f}, the loudest at bucket {top}")
    r16 = levels(d, rise, 16)
    dv = diff(floats(r16), reference(rise, 16))
    t.check("16 buckets (the fewest): 64 bytes, each level as the reference", r16["status"] == 200
            and r16.get("body_length") == 64 and dv is not None and dv <= TOL, f"{r16['status']}, "
                                                                              f"{r16.get('body_length')} bytes, "
                                                                              f"largest difference {dv}")
    r800 = levels(d, rise, 800)
    dv = diff(floats(r800), reference(rise, 800))
    t.check("800 buckets: each level as the reference", r800["status"] == 200 and dv is not None and dv <= TOL,
            f"{r800['status']}, largest difference {dv}")

    # ---- the same file rewritten in place, with the same size and a new time
    size = os.path.getsize(rise)
    with open(t.media("pk-fall.mkv"), "rb") as f:
        data = f.read()
    with open(rise, "r+b") as f:
        f.write(data)
        f.truncate()
    later = time.time() + 5
    os.utime(rise, (later, later))
    r = levels(d, rise)
    dv = diff(floats(r), reference(rise, 1600))
    t.check("the file rewritten in place (same size, a new time) gets the new file's levels",
            os.path.getsize(rise) == size and r["status"] == 200 and dv is not None and dv <= TOL,
            f"{size} -> {os.path.getsize(rise)} bytes; {r['status']}, largest difference {dv}")
    res = []
    for p in copies:
        x = levels(d, p)
        res.append((os.path.basename(p), x["status"], diff(floats(x), reference(p, 1600))))
    t.check("six files one after the other, each loud at a moment of its own: each gets its own levels",
            all(s == 200 and v is not None and v <= TOL for _, s, v in res), f"{res}")
