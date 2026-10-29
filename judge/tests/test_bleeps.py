"""Bleeps belong to their clip and follow it through every edit, heard in the export: under a bleep the clip's own
sound is muted and the bleep's sound plays; a bleep moves with its clip, a head trim shifts it, a trim past its word
hides it and a trim back shows it again, a split leaves each half its own bleep, at speed 2 the beep is still 1 kHz and
lasts its window halved, an audio slip moves it; set_bleep nudges, refuses an empty window, keeps the shortest window
and the asset's end; add_bleep takes source or timeline seconds and refuses a moment outside the clip, a quack plays its
natural length; remove_bleep and remove_bleeps, each one undo step; clear_effects keeps the bleeps; a muted track
silences its bleeps too; bleeps survive save and load; every built-in sound is heard, peaks at half of full scale or
more and does not clip; the preview mixes the bleeps; a bleep with `mute` false leaves the clip's own sound playing
under its beep, and set back to true it mutes it again; bleep_words with no transcript bleeps nothing. Port of
packages/core/scripts/smoke-bleep.ts (judge/PORTING.md has the map of its sections: the profanity matcher and the
transcript-driven sections stay with v0.2.0).

Media: bleep.mp4 (320x180 30 fps, 8 s), whose sound is a staircase tone that says its source moment: 300 + 30 k Hz for
k = floor(2 t), amplitude 0.25 (fixtures/make.sh). So the judge knows which source moment plays at each moment of an
export from the State alone (a clip at start S with source in point I, speed k and sound slip O plays source moment
I + (t - S - O) k at timeline moment t), and checks that this clip's own sound plays there. The canvas is 320x180 at
30 fps.

What is heard is measured on the export's sound decoded at 16 kHz (observe.samples): the amplitude of a pure tone over
a window (observe.tone_amp). In a window that a bleep covers (less 30 ms at each end for the source's mute ramps, 50 ms
for the beep's), the source's step tones must be under 0.008 (the source plays at 0.25: 30 dB down) and the beep's
1 kHz over 0.1 (the original's bounds; the beep plays at 0.8); in a window it does not cover, every step tone of the
source must be over 0.1 and 1 kHz under 0.005. A window is measured in the pieces that each step of the source covers
(a piece under 60 ms, or within 15 ms of a step, is left out). Every export shows a set of bleeps, a placement or a
level that no earlier file of the test shows, so a file handed in for another cannot pass (PORTING.md, "batch 4").

Every check is recorded on every path (a check whose input is missing fails with the reason), so CHECKS is exact.
"""
import math

import driver as drv
import edits as E
import observe

PORT_BOUND = True
EXTRA_MEDIA = ("bleep.mp4",)
TIMEOUT = 900
FPS = 30
RATE = 16000
CHECKS = 62
B1 = (0.94, 1.48)    # the original's two padded word windows, in source seconds
B2 = (2.94, 3.38)
W3 = (3.74, 4.18)    # the bleep with mute false: a window (across the 4 s step) and a volume, 0.5, no other export has
SOUNDS = ["beep", "quack", "squeak", "boing", "honk"]
LOUD, MUTED = 0.1, 0.008      # the source's step tones: heard / muted (it plays at 0.25)
BEEP, NO_BEEP = 0.1, 0.005    # the beep's 1 kHz: heard / not heard
# Each built-in sound peaks at more than half of full scale (the original's bound on the sound itself), so at the
# default volume 0.8 its bleep peaks over 0.4 in the export, where the source is muted (v0.2.0: 0.64 to 0.71; a sound
# played at a fifth of its level: 0.14).
SOUND_PEAK = 0.4


def step(src_t):
    """The frequency (Hz) of bleep.mp4's sound at source moment `src_t` s."""
    return 300 + 30 * math.floor(2 * src_t + 1e-9)


class Clip:
    """The map from a timeline moment to the source moment a clip plays there: start S, in point I (s), speed k,
    sound slip O (s)."""

    def __init__(self, start=0.0, src_in=0.0, speed=1.0, slip=0.0):
        self.start, self.src_in, self.speed, self.slip = start, src_in, speed, slip

    def src(self, t):
        return self.src_in + (t - self.start - self.slip) * self.speed

    def tl(self, src_t):
        return self.start + self.slip + (src_t - self.src_in) / self.speed

    def window(self, w):
        """A source window as timeline seconds."""
        return (self.tl(w[0]), self.tl(w[1]))


def pieces(m, a, b):
    """The parts of timeline window [a, b) that each step of the source covers (from map `m`): [(a, b, Hz)], less 15 ms
    at each step, and none under 60 ms."""
    out, t = [], a
    while t < b - 1e-9:
        s = m.src(t)
        nxt = (math.floor(2 * s + 1e-9) + 1) / 2
        end = min(b, m.tl(nxt))
        lo, hi = t + (0.015 if t > a else 0), end - (0.015 if end < b else 0)
        if hi - lo >= 0.06:
            out.append((lo, hi, step(s)))
        t = end
    return out


def source_amps(snd, m, a, b):
    """[(a, b, Hz, amplitude)]: the source's step tone heard in each piece of [a, b)."""
    return [(lo, hi, f, observe.tone_amp(snd, lo, hi, f, RATE)) for lo, hi, f in pieces(m, a, b)]


def bleeped(snd, m, wins, m_src=0.03, m_beep=0.05, beep=True):
    """(ok, detail): in each timeline window the source is muted and (beep) the 1 kHz beep plays."""
    if isinstance(snd, str):
        return False, snd
    ok, notes = True, []
    for a, b in wins:
        amps = source_amps(snd, m, a + m_src, b - m_src)
        k = observe.tone_amp(snd, a + m_beep, b - m_beep, 1000, RATE)
        src = max((x[3] for x in amps), default=None)
        good = src is not None and src < MUTED and (not beep or k > BEEP)
        ok = ok and good
        notes.append(f"[{a:.2f},{b:.2f}] source {'none measured' if src is None else f'{src:.4f}'}"
                     + (f", 1 kHz {k:.3f}" if beep else "") + ("" if good else " <-"))
    return ok, "; ".join(notes) + f" (source muted under {MUTED}" + (f", beep over {BEEP})" if beep else ")")


def clean(snd, m, wins):
    """(ok, detail): in each timeline window the source's own steps play and no beep."""
    if isinstance(snd, str):
        return False, snd
    ok, notes = True, []
    for a, b in wins:
        amps = source_amps(snd, m, a, b)
        k = observe.tone_amp(snd, a, b, 1000, RATE)
        low = min((x[3] for x in amps), default=None)
        good = low is not None and low > LOUD and k < NO_BEEP
        ok = ok and good
        notes.append(f"[{a:.2f},{b:.2f}] source {'none measured' if low is None else f'{low:.3f}'} "
                     f"({'/'.join(str(x[2]) for x in amps)} Hz), 1 kHz {k:.4f}" + ("" if good else " <-"))
    return ok, "; ".join(notes) + f" (source over {LOUD}, 1 kHz under {NO_BEEP})"


def export(t, d, name):
    """The export's sound at 16 kHz, or why there is none (a str)."""
    out = t.path("out", f"{name}.mp4")
    try:
        job = d.export(out)
    except drv.JudgeError as e:
        return f"the export was refused: {e}"
    if job.get("status") != "done":
        return f"the export ended {job.get('status')}: {job.get('error')}"
    try:
        return observe.samples(out, RATE)
    except observe.Unmeasurable as e:
        return f"unmeasurable: {e}"


def bleeps_of(st, cid):
    c = E.clip(st, cid)
    return (c or {}).get("bleeps") or []


def window_is(b, w, tol=1e-3):
    return b is not None and abs(b.get("start", -9) - w[0]) <= tol and abs(b.get("end", -9) - w[1]) <= tol


def short_bleeps(bs):
    return ", ".join(f"{b.get('id')}[{b.get('start')},{b.get('end')}] {b.get('sound')}" for b in bs) or "none"


def run(t):
    d = t.driver()
    d.set_project(width=320, height=180, fps=FPS)
    asset = d.import_media(t.media("bleep.mp4"))
    A = d.place_clip(asset, "v0", 0, 0)
    m0 = Clip()
    sounds(t, d, A, m0)
    words(t, d, asset)
    b1, b2 = basics(t, d, A, m0)
    unmuted(t, d, A, m0)
    follow(t, d, A, b1, b2)
    adjust(t, d, A, b1, b2, m0)
    adding(t, d, A, m0)
    clearing(t, d, A, b2, m0)
    tracks(t, d, asset, A, m0)


# ---------------------------------------------------------------- every built-in sound; no transcript, no bleeps
def sounds(t, d, A, m0):
    wins = [(0.6 + k, 1.0 + k) for k in range(len(SOUNDS))]
    for (a, b), s in zip(wins, SOUNDS):
        d.add_bleep(A, start=a, end=b, sound=s)
    snd = export(t, d, "sounds")
    for (a, b), s in zip(wins, SOUNDS):
        name = f"the {s} sound is heard in its bleep, over the muted source, peaking at half of full scale or more"
        if isinstance(snd, str):
            t.check(name, False, snd)
            continue
        f = step(a)
        src = observe.tone_amp(snd, a + 0.03, b - 0.03, f, RATE)
        res = observe.residual_rms(snd, a + 0.05, b - 0.05, [f], RATE)
        pk = observe.peak(snd, a + 0.03, b - 0.03, RATE)
        t.check(name, res > 0.03 and src < 0.02 and pk > SOUND_PEAK,
                f"[{a},{b}]: what is heard besides the source {res:.3f} (over 0.03), the source's {f} Hz {src:.4f} "
                f"(under 0.02: a sound may have some energy there itself), the peak {pk:.3f} (over {SOUND_PEAK}: "
                f"half of full scale at the default volume 0.8)")
    top = "no sound" if isinstance(snd, str) else observe.peak(snd)
    t.check("no built-in sound clips (the export's peak stays under full scale)",
            not isinstance(snd, str) and top < 0.99, f"peak {top if isinstance(top, str) else round(top, 3)}")
    d.remove_bleeps([A])
    t.check("remove_bleeps on the clip leaves it no bleep", bleeps_of(d.get_state(), A) == [],
            short_bleeps(bleeps_of(d.get_state(), A)))


def words(t, d, asset):
    """bleep_words needs the editor's word-level transcript. The judge's media holds no speech and the editor has no
    speech model in a test (PROTOCOL.md rule 4), so it must bleep nothing: refuse with nothing changed, or find no
    word."""
    tr = d.get_transcript(asset)
    for name, kw in (("a dry run", {"dry_run": True}), ("a real run", {})):
        st = d.get_state()
        try:
            hits = d.bleep_words(**kw).get("hits")
        except (drv.ProductError, drv.BadRequest):
            hits = None
        if hits is None:
            same = d.get_state() == st
            ok, why = E.refused_unchanged(d, lambda: d.bleep_words(**kw))
            t.check(f"bleep_words ({name}) on media with no transcript bleeps nothing: refused, nothing changed",
                    ok and same, f"transcript {E.short(tr, 120)}; {why}" + ("" if same else "; the State changed"))
        else:
            st2 = d.get_state()
            t.check(f"bleep_words ({name}) on media with no transcript bleeps nothing: refused, nothing changed",
                    hits == [] and st2 == st, f"transcript {E.short(tr, 120)}; it answered {E.short(hits, 200)}"
                    + ("" if st2 == st else "; the State changed"))


# ---------------------------------------------------------------- two bleeps, an export, the preview
def basics(t, d, A, m0):
    st0 = d.get_state()
    b1 = d.add_bleep(A, start=B1[0], end=B1[1])["bleep"]
    st1 = d.get_state()
    b2 = d.add_bleep(A, start=B2[0], end=B2[1])["bleep"]
    st2 = d.get_state()
    bs = bleeps_of(st2, A)
    by = {b.get("id"): b for b in bs}
    t.check("add_bleep puts each window on the clip in source seconds, sound beep",
            len(bs) == 2 and window_is(by.get(b1), B1) and window_is(by.get(b2), B2)
            and all(b.get("sound") == "beep" for b in bs), short_bleeps(bs))
    d.undo()
    u = d.get_state()
    d.redo()
    r = d.get_state()
    t.check("add_bleep is one undo step (undo takes back only the second bleep, redo brings it back)",
            u == st1 and r == st2 and st0 != st1, f"after undo {short_bleeps(bleeps_of(u, A))}; "
                                                  f"after redo {short_bleeps(bleeps_of(r, A))}")
    snd = export(t, d, "base")
    base = snd
    ok, why = bleeped(snd, m0, [B1, B2])
    t.check("export: under each bleep the source is muted and the 1 kHz beep plays", ok, why)
    ok, why = clean(snd, m0, [(0.2, 0.8), (1.7, 2.8), (3.6, 7.5)])
    t.check("export: elsewhere the clip's own sound plays, with no beep", ok, why)

    # The preview, made after the first bleep was turned down to 0.4 (a level no export shows).
    d.set_bleep(A, b1, volume=0.4)
    before = E.snapshot(t)
    try:
        path = d.render_preview().get("path")
    except drv.JudgeError as e:
        path, err = None, str(e)
    else:
        err = None
    why = err or E.new_file(t, before, path)
    t.check("render_preview makes a new file of its own (the preview)", why is None, why or str(path))
    try:
        pv = observe.samples(path, RATE) if why is None else why
    except observe.Unmeasurable as e:
        pv = f"unmeasurable: {e}"
    if isinstance(pv, str) or isinstance(base, str):
        t.check("the preview mixes the bleeps: the first at its new level, the second as in the export", False,
                pv if isinstance(pv, str) else base)
    else:
        k1 = [observe.tone_amp(x, B1[0] + 0.07, B1[1] - 0.07, 1000, RATE) for x in (pv, base)]
        k2 = [observe.tone_amp(x, B2[0] + 0.07, B2[1] - 0.07, 1000, RATE) for x in (pv, base)]
        ok1, ok2 = bleeped(pv, m0, [B1, B2], 0.04, 0.07)
        r1, r2 = k1[0] / max(k1[1], 1e-9), k2[0] / max(k2[1], 1e-9)
        t.check("the preview mixes the bleeps: the first at its new level, the second as in the export",
                ok1 and 0.3 <= r1 <= 0.7 and 0.8 <= r2 <= 1.25,
                f"{ok2}; the first beep at {r1:.2f} of the export's (0.3..0.7: 0.4 for 0.8), the second at "
                f"{r2:.2f} (0.8..1.25)")
    d.undo()
    t.check("set_bleep is one undo step (undo gives the State before it)", d.get_state() == st2,
            short_bleeps(bleeps_of(d.get_state(), A)))
    return b1, b2


# ---------------------------------------------------------------- mute false: the clip's sound plays under the bleep
def unmuted(t, d, A, m0):
    """A bleep with `mute` false, at volume 0.5 (the source at 0.25 and the beep at 0.5 stay under full scale): the
    clip's own sound keeps playing under its beep; set_bleep `mute` true mutes it again. Two undos take both back."""
    st = d.get_state()

    def mine(bid):
        return next((x for x in bleeps_of(d.get_state(), A) if x.get("id") == bid), None)

    b3 = d.add_bleep(A, start=W3[0], end=W3[1], volume=0.5, mute=False)["bleep"]
    b = mine(b3)
    t.check("add_bleep with mute false and volume 0.5: the State shows the bleep with mute false",
            b is not None and b.get("mute") is False and b.get("volume") == 0.5 and window_is(b, W3),
            f"{short_bleeps([b] if b else [])}: mute {(b or {}).get('mute')!r}, volume {(b or {}).get('volume')!r}")
    snd = export(t, d, "unmuted")
    name = ("export: under the bleep with mute false the clip's own sound keeps playing and the beep plays over it "
            "(the bleeps with mute true still mute it)")
    if isinstance(snd, str):
        t.check(name, False, snd)
    else:
        amps = source_amps(snd, m0, W3[0] + 0.03, W3[1] - 0.03)
        k = observe.tone_amp(snd, W3[0] + 0.05, W3[1] - 0.05, 1000, RATE)
        low = min((x[3] for x in amps), default=None)
        ok, why = bleeped(snd, m0, [B1, B2])
        t.check(name, low is not None and low > LOUD and k > BEEP and ok,
                f"[{W3[0]},{W3[1]}] source {'none measured' if low is None else f'{low:.3f}'} "
                f"({'/'.join(str(x[2]) for x in amps)} Hz; over {LOUD}), 1 kHz {k:.3f} (over {BEEP}); {why}")
    d.set_bleep(A, b3, mute=True)
    b = mine(b3)
    snd = export(t, d, "remuted")
    ok, why = bleeped(snd, m0, [W3])
    t.check("set_bleep mute true: the State shows it, and the export mutes the clip's sound under the bleep again",
            (b or {}).get("mute") is True and ok, f"mute {(b or {}).get('mute')!r}; {why}")
    d.undo()
    d.undo()
    t.check("two undos take back set_bleep and add_bleep (the State before them)", d.get_state() == st,
            short_bleeps(bleeps_of(d.get_state(), A)))


# ---------------------------------------------------------------- the bleeps follow the clip
def follow(t, d, A, b1, b2):
    st = d.get_state()
    d.move_clip(A, 30)
    m = Clip(start=1.0)
    snd = export(t, d, "moved")
    ok, why = bleeped(snd, m, [m.window(B1), m.window(B2)])
    t.check("moved +1 s: the bleeps play 1 s later", ok, why)
    ok, why = clean(snd, m, [(1.2, 1.8), (2.7, 3.8), (4.6, 8.5)])
    t.check("moved +1 s: the old windows and the rest play the clip's sound", ok, why)
    d.undo()

    d.trim_clip(A, in_frame=15)
    m = Clip(src_in=0.5)
    snd = export(t, d, "trimmed")
    ok, why = bleeped(snd, m, [m.window(B1), m.window(B2)])
    t.check("head trimmed 0.5 s: the bleeps play 0.5 s earlier, with their words", ok, why)
    ok, why = clean(snd, m, [(0.05, 0.4), (1.2, 2.3)])
    t.check("head trimmed 0.5 s: around them the clip's sound plays", ok, why)

    d.trim_clip(A, in_frame=48)  # 1.6 s: past the first window's end
    bs = bleeps_of(d.get_state(), A)
    t.check("trimmed past the first window: the clip keeps both bleeps (source time)",
            sorted(b.get("id") for b in bs) == sorted([b1, b2]), short_bleeps(bs))
    m = Clip(src_in=1.6)
    snd = export(t, d, "past-first")
    ok, why = bleeped(snd, m, [m.window(B2)])
    t.check("trimmed past the first window: the second bleep plays where its word now is", ok, why)
    ok, why = clean(snd, m, [(0.05, 1.2)])
    t.check("trimmed past the first window: the first is not heard", ok, why)

    d.trim_clip(A, in_frame=6)   # 0.2 s: the first window is back in view
    m = Clip(src_in=0.2)
    snd = export(t, d, "trimmed-back")
    ok, why = bleeped(snd, m, [m.window(B1), m.window(B2)])
    t.check("trimmed back to 0.2 s: the first bleep is heard again", ok, why)
    d.trim_clip(A, in_frame=0)

    before = d.get_state()
    left, right = d.split_clip(A, 66)  # 2.2 s, between the windows
    st2 = d.get_state()

    def own(cid):
        c = E.clip(st2, cid) or {}
        lo, hi = (c.get("in_frame") or 0) / FPS, (c.get("out_frame") or 0) / FPS
        return [b for b in c.get("bleeps") or [] if b.get("end", 0) > lo and b.get("start", 0) < hi]

    ids = [[b.get("id") for b in (E.clip(st2, c) or {}).get("bleeps") or []] for c in (left, right)]
    lo_b, hi_b = own(left), own(right)
    t.check("split between the windows: each half has its own bleep in its range, ids unique in each half",
            len(lo_b) == 1 and window_is(lo_b[0], B1) and len(hi_b) == 1 and window_is(hi_b[0], B2)
            and all(len(set(x)) == len(x) for x in ids),
            f"left {short_bleeps(lo_b)}; right {short_bleeps(hi_b)}; ids {ids}")
    d.move_clip(right, 81)   # the right half 0.5 s later: a placement no other export shows
    m_l, m_r = Clip(), Clip(start=81 / FPS, src_in=2.2)
    snd = export(t, d, "split")
    ok1, why1 = bleeped(snd, m_l, [B1])
    ok2, why2 = bleeped(snd, m_r, [m_r.window(B2)])
    t.check("split, the right half moved +0.5 s: each half plays its own bleep", ok1 and ok2, f"{why1}; {why2}")
    ok1, why1 = clean(snd, m_l, [(0.2, 0.8), (1.7, 2.15)])
    ok2, why2 = clean(snd, m_r, [(2.8, 3.35), (4.1, 6.0)])
    t.check("split, the right half moved: the rest of each half plays its sound", ok1 and ok2, f"{why1}; {why2}")
    d.undo()
    d.undo()
    t.check("undo of the move and the split gives back the one clip with both bleeps", d.get_state() == before,
            short_bleeps(bleeps_of(d.get_state(), A)))

    d.set_speed(A, 2)
    m = Clip(speed=2)
    w1, w2 = m.window(B1), m.window(B2)
    snd = export(t, d, "speed2")
    ok, why = bleeped(snd, m, [w1, w2], 0.03, 0.04)
    t.check("speed 2: the bleeps play over their words, at half the time", ok, why)
    if isinstance(snd, str):
        t.check("speed 2: the beep is still 1 kHz (not 2 kHz or 500 Hz)", False, snd)
        t.check("speed 2: the beep ends with its window", False, snd)
    else:
        vals = [(observe.tone_amp(snd, a + 0.04, b - 0.04, 1000, RATE),
                 observe.tone_amp(snd, a + 0.04, b - 0.04, 2000, RATE),
                 observe.tone_amp(snd, a + 0.04, b - 0.04, 500, RATE)) for a, b in (w1, w2)]
        t.check("speed 2: the beep is still 1 kHz (not 2 kHz or 500 Hz)",
                all(k1 > BEEP and k2 < 0.01 and k5 < 0.01 for k1, k2, k5 in vals),
                "; ".join(f"1 kHz {a:.3f}, 2 kHz {b:.4f}, 500 Hz {c:.4f}" for a, b, c in vals))
        tail = observe.tone_amp(snd, w1[1] + 0.03, w1[1] + 0.2, 1000, RATE)
        t.check("speed 2: the beep ends with its window", tail < NO_BEEP, f"1 kHz after it {tail:.4f}")
    ok, why = clean(snd, m, [(0.05, 0.4), (0.8, 1.4), (1.8, 3.9)])
    t.check("speed 2: elsewhere the clip's sound plays at twice the pace, its pitch kept", ok, why)
    d.undo()

    d.set_audio_offset(A, 15)
    m = Clip(slip=0.5)
    snd = export(t, d, "slipped")
    ok, why = bleeped(snd, m, [m.window(B1), m.window(B2)])
    t.check("sound slipped +0.5 s (an L-cut): the bleeps move with the sound", ok, why)
    ok, why = clean(snd, m, [(0.6, 1.35), (2.05, 3.35)])
    t.check("sound slipped: the clip's sound plays 0.5 s late around them", ok, why)
    d.undo()
    t.check("after these edits and their undos the clip has its two bleeps as made",
            d.get_state() == st, short_bleeps(bleeps_of(d.get_state(), A)))


# ---------------------------------------------------------------- set_bleep
def adjust(t, d, A, b1, b2, m0):
    st = d.get_state()
    n1 = (B1[0] + 0.3, B1[1] + 0.3)
    d.set_bleep(A, b1, start=n1[0], end=n1[1])
    got = {b.get("id"): b for b in bleeps_of(d.get_state(), A)}
    t.check("set_bleep moves the first window +0.3 s (source seconds)", window_is(got.get(b1), n1)
            and window_is(got.get(b2), B2), short_bleeps(got.values()))
    snd = export(t, d, "nudged")
    ok, why = bleeped(snd, m0, [n1, B2])
    t.check("nudged: the first bleep plays 0.3 s later", ok, why)
    ok, why = clean(snd, m0, [(0.97, 1.2)])
    t.check("nudged: where it began the clip's sound plays again", ok, why)
    ok, why = E.refused_unchanged(d, lambda: d.set_bleep(A, b1, start=2, end=1))
    t.check("set_bleep refuses a window that ends before it starts, and changes nothing", ok, why)
    d.set_bleep(A, b1, start=1.0, end=1.01)
    b = next((x for x in bleeps_of(d.get_state(), A) if x.get("id") == b1), {})
    t.check("set_bleep keeps a window of at least 0.04 s", b.get("end", 0) - b.get("start", 0) >= 0.04 - 1e-6
            and b.get("start", 0) >= 1.0 - 0.04 - 1e-6, short_bleeps([b]))
    d.set_bleep(A, b1, start=5.8, end=9)
    b = next((x for x in bleeps_of(d.get_state(), A) if x.get("id") == b1), {})
    t.check("set_bleep keeps a window inside the asset (it ends at the 8 s asset's end, not at 9 s)",
            7.95 <= b.get("end", 0) <= 8.05 and abs(b.get("start", 0) - 5.8) <= 1e-3, short_bleeps([b]))
    d.undo()
    d.undo()
    d.undo()
    t.check("three undos give back the first window as made", d.get_state() == st,
            short_bleeps(bleeps_of(d.get_state(), A)))


# ---------------------------------------------------------------- add_bleep, remove_bleep, remove_bleeps
def adding(t, d, A, m0):
    manual = d.add_bleep(A, at_seconds=5.0, duration=0.4)["bleep"]
    got = {b.get("id"): b for b in bleeps_of(d.get_state(), A)}
    t.check("add_bleep at timeline seconds 5.0 for 0.4 s: the window 5.0..5.4 s of the source (the clip starts at 0)",
            len(got) == 3 and window_is(got.get(manual), (5.0, 5.4)), short_bleeps(got.values()))
    quack = d.add_bleep(A, start=4.5, end=4.6, sound="quack")["bleep"]
    got = {b.get("id"): b for b in bleeps_of(d.get_state(), A)}
    t.check("add_bleep with the quack sound", (got.get(quack) or {}).get("sound") == "quack"
            and window_is(got.get(quack), (4.5, 4.6)), short_bleeps(got.values()))
    ok, why = E.refused_unchanged(d, lambda: d.add_bleep(A, at_seconds=9.0))
    t.check("add_bleep at a moment outside the clip (9 s of an 8 s clip) is refused and changes nothing", ok, why)
    snd = export(t, d, "added")
    ok, why = bleeped(snd, m0, [(5.0, 5.4)])
    t.check("the bleep added at 5.0 s plays there", ok, why)
    if isinstance(snd, str):
        t.check("the quack plays its natural length past its 0.1 s window, over the source again", False, snd)
    else:
        src = observe.tone_amp(snd, 4.62, 4.95, step(4.7), RATE)
        res = observe.residual_rms(snd, 4.62, 4.78, [step(4.7)], RATE)
        t.check("the quack plays its natural length past its 0.1 s window, over the source again",
                res > 0.03 and src > LOUD, f"heard besides the source in 4.62..4.78 s {res:.3f} (over 0.03), the "
                                           f"source after the window {src:.3f} (over {LOUD})")
    d.remove_bleep(A, manual)
    got = {b.get("id"): b for b in bleeps_of(d.get_state(), A)}
    t.check("remove_bleep removes only that bleep", manual not in got and len(got) == 3, short_bleeps(got.values()))
    snd = export(t, d, "removed-one")
    ok1, why1 = clean(snd, m0, [(5.05, 5.35)])
    ok2, why2 = bleeped(snd, m0, [B1, B2])
    t.check("after remove_bleep its window plays the clip's sound, the others are still bleeped", ok1 and ok2,
            f"{why1}; {why2}")
    d.remove_bleep(A, quack)
    st = d.get_state()
    d.remove_bleeps()
    t.check("remove_bleeps removes every bleep", all(not (c.get("bleeps") or [])
                                                    for tr in d.get_state()["tracks"] for c in tr["clips"]),
            short_bleeps(bleeps_of(d.get_state(), A)))
    snd = export(t, d, "no-bleeps")
    ok, why = clean(snd, m0, [(0.9, 1.5), (2.9, 3.4)])
    t.check("after remove_bleeps the windows play the clip's sound", ok, why)
    d.undo()
    t.check("undo of remove_bleeps brings the bleeps back (one step)", d.get_state() == st,
            short_bleeps(bleeps_of(d.get_state(), A)))


# ---------------------------------------------------------------- clear_effects keeps the bleeps
def clearing(t, d, A, b2, m0):
    d.set_bleep(A, b2, sound="quack")
    d.set_speed(A, 2)
    d.clear_effects(A)
    c = E.clip(d.get_state(), A) or {}
    by = {b.get("id"): b for b in c.get("bleeps") or []}
    t.check("clear_effects takes the speed off and keeps the bleeps", c.get("speed") == 1 and len(by) == 2
            and (by.get(b2) or {}).get("sound") == "quack", f"speed {c.get('speed')}; {short_bleeps(by.values())}")
    snd = export(t, d, "cleared")
    ok1, why1 = bleeped(snd, m0, [B1])
    ok2, why2 = bleeped(snd, m0, [B2], beep=False)
    if isinstance(snd, str):
        res = 0.0
    else:
        res = observe.residual_rms(snd, B2[0] + 0.05, B2[1] - 0.05, [step(B2[0]), step(B2[1])], RATE)
    t.check("after clear_effects: the beep plays under the first, the quack under the second", ok1 and ok2
            and res > 0.03, f"{why1}; {why2}; heard under the second {res:.3f} (over 0.03)")


# ---------------------------------------------------------------- a sound clip's bleeps, a muted track, save and load
def tracks(t, d, asset, A, m0):
    d.remove_bleeps([A])
    d.set_volume(A, 0)            # the picture is silent: the sound clip on a0 carries the sound
    a0 = d.add_track("audio")
    Aa = d.place_clip(asset, a0, 0, 0)
    d.add_bleep(Aa, start=B1[0], end=B1[1])
    snd = export(t, d, "sound-clip")
    ok1, why1 = bleeped(snd, m0, [B1])
    ok2, why2 = clean(snd, m0, [(2.9, 3.4), (0.2, 0.8)])
    t.check("a bleep on the sound clip: heard there, the picture's silent clip adds nothing", ok1 and ok2,
            f"{why1}; {why2}")
    d.set_track(a0, muted=True)
    snd = export(t, d, "muted")
    if isinstance(snd, str):
        t.check("a muted track silences its bleeps too", False, snd)
    else:
        k = observe.tone_amp(snd, B1[0] + 0.05, B1[1] - 0.05, 1000, RATE)
        r = observe.rms(snd, 0, 7.9, RATE)
        t.check("a muted track silences its bleeps too", k < NO_BEEP and r < 0.003,
                f"1 kHz under the bleep {k:.4f} (under {NO_BEEP}), the whole export's level {r:.4f} (under 0.003)")
    d.set_track(a0, muted=False)
    d.add_bleep(Aa, start=6.0, end=6.5)
    before = bleeps_of(d.get_state(), Aa)
    p = t.path("out", "bleeps.project")
    d.save_project(p)
    d.load_project(p)
    st = d.get_state()
    t.check("bleeps survive save and load (ids, windows, sounds)", bleeps_of(st, Aa) == before and len(before) == 2,
            f"before {short_bleeps(before)}; after {short_bleeps(bleeps_of(st, Aa))}")
    snd = export(t, d, "reopened")
    ok1, why1 = bleeped(snd, m0, [B1, (6.0, 6.5)])
    ok2, why2 = clean(snd, m0, [(2.9, 3.4)])
    t.check("the reopened project's export plays its bleeps", ok1 and ok2, f"{why1}; {why2}")
