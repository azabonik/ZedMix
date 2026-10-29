"""Audio effects on a clip's sound, as the user sees and hears them: the editor clamps a value out of range, rounds a
switch and refuses an unknown param or effect; every effect exports with its clip's sound starting when it did, no
later (no delay added), lasting the clip's length and stopping at its end (an echo's or a reverb's tail does not run
past it); each one also exports at every param's lowest and highest value; a bypassed effect is not heard; a new effect
takes its place in the signal chain, reorder, bypass, remove and undo work, each one step; on a picture whose sound is
carried by a linked sound clip the effect goes on that clip, also through either half of a split pair; an adjustment
layer is refused; a bleep still mutes its window and its beep is not processed by the clip's effects; the preview has
the clip's effects. Port of the registry, "every effect", engine, bleeps and preview sections of
packages/core/scripts/smoke-voice.ts (judge/PORTING.md has the map; its sound-shaping sections are tests/test_voice.py,
its channel layout and speed sections tests/test_audio_layouts.py).

Media: onset.mkv (silence for 1 s, then 440 Hz at -12 dB to 4 s), voice.mkv (a voice-like sound, fixtures/make.sh),
bleep.mp4 (a staircase tone that says its source moment, as in test_bleeps). The canvas is 160x90 at 30 fps.

What is heard is measured on the exports' sound (observe.samples): the onset (the first sample at a quarter of the
clip's loudest, 15 % for robot, whose buzz starts softer), the level near the clip's end and in the gap after it, the
delay of the voice against the dry voice (the peak of their cross-correlation at 8 kHz over 1 s of speech, within
+-25 ms), and a pure tone's frequency (observe.dominant) and amplitude (observe.tone_amp). The bounds are the original's:
the onset within 25 ms of the dry one, the delay at most 6 ms (not measured on underwater, whose wobble moves it). An
effect that changes nothing passes the onset and length checks, as in the original, so each effect is also held to
get_state (it is on its clip, with the values sent), and test_voice measures what the effects do.

Every check is recorded on every path (a check whose input is missing fails with the reason), so CHECKS is exact.
"""
import driver as drv
import edits as E
import observe

PORT_BOUND = True
EXTRA_MEDIA = ("onset.mkv", "voice.mkv", "bleep.mp4")
TIMEOUT = 1500
FPS = 30
# Every audio effect (PROTOCOL.md, "Audio effects") with its params' lowest and highest values.
EFFECTS = {
    "enhance_voice": {"strength": (0, 1), "denoise": (0, 1), "normalize": (0, 1), "floor": (-90, -20)},
    "noise_reduction": {"amount": (0, 1), "floor": (-90, -20), "heavy": (0, 1)},
    "highpass": {"frequency": (20, 500)},
    "lowpass": {"frequency": (1000, 20000)},
    "de_esser": {"amount": (0, 1), "frequency": (0, 1)},
    "gate": {"threshold": (-80, -10), "reduction": (0, 60), "attack": (0.1, 100), "release": (10, 2000)},
    "declick": {"threshold": (2, 10)},
    "eq_presence": {"gain": (-12, 12), "frequency": (2000, 8000)},
    "eq_warmth": {"gain": (-12, 12), "frequency": (100, 400)},
    "eq_custom": {"low": (-12, 12), "mid": (-12, 12), "high": (-12, 12)},
    "bass_boost": {"gain": (0, 18), "frequency": (40, 250)},
    "compressor": {"threshold": (-60, 0), "ratio": (1, 20), "attack": (0.1, 200), "release": (10, 2000),
                   "makeup": (0, 24)},
    "limiter": {"ceiling": (-12, 0), "drive": (0, 24), "release": (1, 1000)},
    "normalize": {"target": (-30, -10), "even": (0, 1)},
    "pitch": {"semitones": (-12, 12)},
    "chipmunk": {"semitones": (3, 12)},
    "deep": {"semitones": (-12, -2)},
    "robot": {"tone": (0, 2)},
    "echo": {"delay": (50, 1000), "decay": (0.05, 0.9)},
    "reverb": {"room": (0, 1), "mix": (0, 1)},
    "telephone": {"grit": (0, 1)},
    "megaphone": {"grit": (0, 1)},
    "underwater": {"muffle": (200, 1500), "wobble": (0, 1)},
}
# They change the waveform's timing, so no delay is measured on them: the pitch shifters and robot (the original's
# list) and underwater, whose wobble is a delay that moves by design (v0.2.0 measures +5.8 ms against the original's
# 6 ms bound: no room for another wobble; PORTING.md, "batch 4" margins).
RETIMES = {"pitch", "chipmunk", "deep", "robot", "underwater"}
SLOT = 4.5           # each clip of onset.mkv (4 s) and the 0.5 s gap after it
VSLOT = 4.0          # each clip of voice.mkv's first phrase (3.5 s) and the gap after it
# Under a bleep the clip's pitched sound must be at most this (it plays at 0.25: 18 dB down). A pitch shifter smears
# its input over tens of milliseconds, so the steps on either side of the window leak into it: v0.2.0 shows 0.002 and
# 0.016 (PORTING.md, "batch 4" margins).
MUTED_PITCHED = 0.03
CHECKS = 4 + 1 + 3 * len(EFFECTS) + (len(EFFECTS) - len(RETIMES)) + len(EFFECTS) + 11 + 8 + 4


def export(t, d, name, rate=observe.RATE):
    """The export's sound at `rate` Hz, or why there is none (a str)."""
    out = t.path("out", f"{name}.mp4")
    try:
        job = d.export(out)
    except drv.JudgeError as e:
        return f"the export was refused: {e}"
    if job.get("status") != "done":
        return f"the export ended {job.get('status')}: {job.get('error')}"
    try:
        return observe.samples(out, rate)
    except observe.Unmeasurable as e:
        return f"unmeasurable: {e}"


def fx_of(st, cid):
    return [(f.get("effect"), f.get("params"), f.get("enabled")) for f in (E.clip(st, cid) or {}).get("audio_effects")
            or []]


def names(st, cid):
    return ",".join(f.get("effect") for f in (E.clip(st, cid) or {}).get("audio_effects") or [])


def run(t):
    d = t.driver()
    d.set_project(width=160, height=90, fps=FPS)
    onset = d.import_media(t.media("onset.mkv"))
    voice = d.import_media(t.media("voice.mkv"))
    bleep = d.import_media(t.media("bleep.mp4"))
    registry(t, d, onset)
    every(t, d, onset, voice)
    extremes(t, d, onset)
    engine(t, d, onset)
    bleeps(t, d, bleep, onset)


# ---------------------------------------------------------------- what the editor does with the values sent
def registry(t, d, onset):
    c = d.place_clip(onset, "v0", 0, 0)
    d.apply_audio_effect(c, "eq_presence", params={"gain": 40})
    got = fx_of(d.get_state(), c)
    t.check("a value out of range is clamped (eq_presence gain 40 -> 12)", len(got) == 1
            and (got[0][1] or {}).get("gain") == 12, E.short(got))
    ok, why = E.refused_unchanged(d, lambda: d.apply_audio_effect(c, "echo", params={"feedback": 0.5}))
    t.check("a param the effect does not have is refused (echo feedback), nothing changed", ok, why)
    ok, why = E.refused_unchanged(d, lambda: d.apply_audio_effect(c, "autotune"), (drv.ProductError, drv.BadRequest))
    t.check("an effect the editor does not have is refused (autotune), nothing changed", ok, why)
    d.apply_audio_effect(c, "enhance_voice", params={"denoise": 0.3})
    ev = next((f for f in fx_of(d.get_state(), c) if f[0] == "enhance_voice"), None)
    t.check("a switch param is rounded to 0 or 1 (enhance_voice denoise 0.3 -> 0)",
            ev is not None and (ev[1] or {}).get("denoise") == 0, E.short(ev))
    E.clear(d)


# ---------------------------------------------------------------- every effect: runs, no delay, keeps the length
def every(t, d, onset, voice):
    clips = {}
    for i, name in enumerate([None] + list(EFFECTS)):
        c = d.place_clip(onset, "v0", round(i * SLOT * FPS), 0)
        if name:
            d.apply_audio_effect(c, name)
        clips[name] = (c, i * SLOT)
    st = d.get_state()
    missing = [n for n in EFFECTS if [f[0] for f in fx_of(st, clips[n][0])] != [n]]
    t.check("get_state lists each effect on its own clip (and none on the dry one)", not missing
            and fx_of(st, clips[None][0]) == [], f"missing or other: {missing}" if missing else "all 23")
    snd = export(t, d, "every")
    dry_on = None
    if not isinstance(snd, str):
        dry = snd[int(0 * observe.RATE):int(4 * observe.RATE)]
        dry_on = observe.onset(dry)
    for name in EFFECTS:
        c, s = clips[name]
        if isinstance(snd, str) or dry_on is None:
            why = snd if isinstance(snd, str) else "the dry clip is silent"
            for chk in ("starts when the dry tone does", "lasts the clip's length", "stops at the clip's end"):
                t.check(f"{name}: {chk}", False, why)
            continue
        part = snd[int(s * observe.RATE):int((s + 4) * observe.RATE)]
        on = observe.onset(part, 0.15 if name == "robot" else 0.25)
        t.check(f"{name}: starts when the dry tone does", on is not None and abs(on - dry_on) <= 0.025,
                f"onset {'none' if on is None else f'{(on - dry_on) * 1000:+.1f} ms'} from the dry {dry_on:.3f} s "
                f"(within 25 ms)")
        end = observe.rms(snd, s + 3.7, s + 3.95)
        t.check(f"{name}: lasts the clip's length", end > 0.01, f"level in its last 0.3 s {end:.4f} (over 0.01)")
        gap = observe.rms(snd, s + 4.05, s + 4.45)
        t.check(f"{name}: stops at the clip's end", gap < 0.003, f"level in the gap after it {gap:.4f} (under 0.003)")
    E.clear(d)

    # The voice, against the dry voice: an effect that keeps the waveform's timing adds no delay.
    kept = [n for n in EFFECTS if n not in RETIMES]
    vclips = {}
    for i, name in enumerate([None] + kept):
        c = d.place_clip(voice, "v0", round(i * VSLOT * FPS), FPS, round(4.5 * FPS))
        if name:
            d.apply_audio_effect(c, name)
        vclips[name] = i * VSLOT
    snd = export(t, d, "every-voice", 8000)
    for name in kept:
        s = vclips[name]
        if isinstance(snd, str):
            t.check(f"{name}: adds no delay to the voice", False, snd)
            continue
        # the dry clip's moment 0.5..1.5 s (the source's 1.5..2.5 s) against the same moment of this clip
        dry = snd[0:int(4 * 8000)]
        mine = snd[int(s * 8000):int((s + 4) * 8000)]
        lag = observe.lag(dry, mine, 0.5, 1.5)
        t.check(f"{name}: adds no delay to the voice", abs(lag) <= 0.006, f"delay {lag * 1000:+.1f} ms (at most 6)")
    E.clear(d)


def extremes(t, d, onset):
    """Each effect with every param at its lowest, then its highest value: two clips, one export each."""
    for name, params in EFFECTS.items():
        lo = {k: v[0] for k, v in params.items()}
        hi = {k: v[1] for k, v in params.items()}
        if name in ("noise_reduction", "enhance_voice"):
            lo["floor"], hi["floor"] = -90, -25   # a quiet and a loud noise floor
        a = d.place_clip(onset, "v0", 0, 15, 75)            # 0.5..2.5 s of the source: the tone from 1 s
        b = d.place_clip(onset, "v0", 60, 15, 75)
        d.apply_audio_effect(a, name, params=lo)
        d.apply_audio_effect(b, name, params=hi)
        st = d.get_state()
        kept = [fx_of(st, a), fx_of(st, b)]
        out = t.path("out", f"extreme-{name}.mp4")
        why = None
        if [[(n, {k: p.get(k) for k in params}) for n, p, _ in fx] for fx in kept] != [[(name, lo)], [(name, hi)]]:
            why = f"get_state shows {E.short(kept, 300)}, not the values sent (each in its range)"
        try:
            job = d.export(out)
            if job.get("status") != "done":
                why = why or f"the export ended {job.get('status')}: {job.get('error')}"
        except drv.JudgeError as e:
            why = why or f"the export was refused: {e}"
        if why is None:
            try:
                s = observe.samples(out)
                n = len(s) / observe.RATE
                bad = sum(1 for v in s if v != v)
                why = (None if abs(n - 4.0) <= 0.1 and bad == 0
                       else f"{n:.2f} s of sound (4 s), {bad} samples not numbers")
            except observe.Unmeasurable as e:
                why = f"unmeasurable: {e}"
        t.check(f"{name} at its params' lowest and highest values: get_state keeps them, and the timeline's sound "
                f"exports", why is None,
                why or f"{E.short(lo, 150)} / {E.short(hi, 150)}")
        E.clear(d)


# ---------------------------------------------------------------- the chain, linked sound, split pairs, undo
def engine(t, d, onset):
    c = d.place_clip(onset, "v0", 0, 0)
    st0 = d.get_state()
    r1 = d.apply_audio_effect(c, "echo", params={"delay": 5000})
    r2 = d.apply_audio_effect(c, "noise_reduction")
    r3 = d.enhance_voice(c, strength=0.5)
    st3 = d.get_state()
    got = fx_of(st3, c)
    t.check("echo delay 5000 is clamped to 1000 and kept on the clip", any(f[0] == "echo"
                                                                         and (f[1] or {}).get("delay") == 1000
                                                                         for f in got), E.short(got))
    t.check("new effects take their place in the chain: enhance, then cleanup, then the voice changer",
            names(st3, c) == "enhance_voice,noise_reduction,echo", names(st3, c))
    d.undo()
    u = names(d.get_state(), c)
    d.redo()
    t.check("each effect added is one undo step", u == "noise_reduction,echo" and d.get_state() == st3, u)
    d.enhance_voice(c, normalize=False)
    ev = next((f for f in fx_of(d.get_state(), c) if f[0] == "enhance_voice"), (None, {}, None))
    t.check("enhance_voice again changes the clip's one in place, keeping what was not sent",
            names(d.get_state(), c) == "enhance_voice,noise_reduction,echo" and (ev[1] or {}).get("strength") == 0.5
            and (ev[1] or {}).get("normalize") == 0 and (ev[1] or {}).get("denoise") == 1, E.short(ev))
    d.reorder_audio_effect(c, r1["effect"], 0)
    t.check("reorder_audio_effect moves echo first", names(d.get_state(), c) == "echo,enhance_voice,noise_reduction",
            names(d.get_state(), c))
    d.apply_audio_effect(c, "echo", effect_id=r1["effect"], enabled=False)
    e1 = fx_of(d.get_state(), c)[0]
    t.check("enabled false alone bypasses the effect and keeps its params", e1[2] is False
            and (e1[1] or {}).get("delay") == 1000, E.short(e1))
    st = d.get_state()
    d.remove_audio_effect(c, r2["effect"])
    t.check("remove_audio_effect removes only that effect", names(d.get_state(), c) == "echo,enhance_voice",
            names(d.get_state(), c))
    d.undo()
    t.check("undo brings the removed effect back", d.get_state() == st, names(d.get_state(), c))
    for _ in range(6):
        d.undo()
    t.check("undo all the way gives the clip no audio effect", d.get_state() == st0, names(d.get_state(), c))
    ok, why = E.refused_unchanged(d, lambda: d.remove_audio_effect(c, "no-such-effect"))
    t.check("removing an effect the clip does not have is refused, nothing changed", ok, why)
    adj = d.add_adjustment_layer(0, 30, track=d.add_track("video"))
    ok, why = E.refused_unchanged(d, lambda: d.apply_audio_effect(adj, "echo"))
    t.check("an adjustment layer has no sound: an audio effect on it is refused, nothing changed", ok, why)
    E.clear(d)

    # A picture whose sound is carried by a linked sound clip (the picture's own at volume 0).
    a0 = d.add_track("audio")
    v = d.place_clip(onset, "v0", 0, 0)
    a = d.place_clip(onset, a0, 0, 0)
    d.link_clips([v, a])
    d.set_volume(v, 0)
    r = d.apply_audio_effect(v, "pitch", params={"semitones": 12})
    st = d.get_state()
    t.check("on a picture whose linked clip carries the sound, the effect goes on that clip", r.get("clip") == a
            and names(st, a) == "pitch" and names(st, v) == "", f"answered {r}; picture {names(st, v) or 'none'}, "
                                                                f"sound clip {names(st, a) or 'none'}")
    snd = export(t, d, "linked")
    hz = None if isinstance(snd, str) else observe.dominant(snd, 1.5, 3.5, 700, 1100)
    t.check("the linked sound clip exports pitched +12 (440 -> 880 Hz)", hz is not None and abs(hz - 880) < 6,
            snd if isinstance(snd, str) else f"{hz} Hz")
    d.remove_audio_effect(v, r["effect"])
    t.check("removing it through the picture finds it on the sound clip", names(d.get_state(), a) == "",
            names(d.get_state(), a))

    tel = d.apply_audio_effect(v, "telephone")
    left, right = d.split_clip(v, 60)
    st = d.get_state()
    halves = sorted(E.clips(st, a0), key=lambda x: x["start_frame"])
    if len(halves) != 2:
        for name in ("a split pair: both sound halves keep the effect",
                     "removing it through the right picture half removes the right sound half's copy only",
                     "an effect added through the right picture half lands on the right sound half",
                     "enhance_voice through each picture half goes to its own sound half",
                     "the halves keep their own effects"):
            t.check(name, False, f"the split left {len(halves)} sound clips on {a0}")
        return
    al, ar = halves[0]["id"], halves[1]["id"]
    t.check("a split pair: both sound halves keep the effect", tel.get("clip") == a and names(st, al) == "telephone"
            and names(st, ar) == "telephone", f"{names(st, al)} | {names(st, ar)}")
    d.remove_audio_effect(right, tel["effect"])
    st = d.get_state()
    t.check("removing it through the right picture half removes the right sound half's copy only",
            names(st, ar) == "" and names(st, al) == "telephone", f"{names(st, al)} | {names(st, ar) or 'none'}")
    rr = d.apply_audio_effect(right, "echo")
    t.check("an effect added through the right picture half lands on the right sound half", rr.get("clip") == ar,
            f"answered {rr}")
    er, el = d.enhance_voice(right), d.enhance_voice(left)
    t.check("enhance_voice through each picture half goes to its own sound half", er.get("clip") == ar
            and el.get("clip") == al, f"{er} / {el}")
    st = d.get_state()
    t.check("the halves keep their own effects", names(st, al) == "enhance_voice,telephone"
            and names(st, ar) == "enhance_voice,echo", f"{names(st, al)} | {names(st, ar)}")
    E.clear(d)
    d.remove_track(a0)


# ---------------------------------------------------------------- bleeps with an effect; a bypassed one; the preview
def bleeps(t, d, bleep, onset):
    c = d.place_clip(bleep, "v0", 0, 0)
    d.add_bleep(c, start=0.94, end=1.48)
    d.add_bleep(c, start=2.94, end=3.38)
    fx = d.apply_audio_effect(c, "pitch", params={"semitones": 12})
    off = d.apply_audio_effect(c, "pitch", params={"semitones": -5}, enabled=False)
    snd = export(t, d, "bleeped")
    if isinstance(snd, str):
        t.check("under the bleeps the pitched sound is muted, the beep plays unprocessed at 1 kHz", False, snd)
        t.check("elsewhere the sound is pitched +12 (each step heard an octave up); the bypassed -5 is not heard",
                False, snd)
    else:
        vals = []
        for a, b in ((0.94, 1.48), (2.94, 3.38)):
            vals.append((max(observe.tone_amp(snd, a + 0.05, b - 0.05, 2 * (300 + 30 * int(2 * x)))
                             for x in (a, b)),
                         observe.tone_amp(snd, a + 0.05, b - 0.05, 1000),
                         observe.tone_amp(snd, a + 0.05, b - 0.05, 2000)))
        t.check("under the bleeps the pitched sound is muted, the beep plays unprocessed at 1 kHz",
                all(p < MUTED_PITCHED and k > 0.1 and k2 < 0.01 for p, k, k2 in vals),
                "; ".join(f"pitched source {p:.4f} (under {MUTED_PITCHED}), 1 kHz {k:.3f} (over 0.1), "
                          f"2 kHz {k2:.4f}" for p, k, k2 in vals))
        want = [2 * (300 + 30 * int(2 * a)) for a in (1.6, 2.1, 4.1)]
        hz = [observe.dominant(snd, a, a + 0.3, w * 0.9, w * 1.1) for a, w in zip((1.6, 2.1, 4.1), want)]
        t.check("elsewhere the sound is pitched +12 (each step heard an octave up); the bypassed -5 is not heard",
                all(h is not None and abs(h - w) < w * 0.01 for h, w in zip(hz, want)),
                f"{hz} Hz for {want}")
    del fx, off
    E.clear(d)
    # The preview of onset.mkv's tone pitched +12 and then changed to -12 (a sound no export shows: 220 Hz).
    c = d.place_clip(onset, "v0", 0, 0)
    fx = d.apply_audio_effect(c, "pitch", params={"semitones": 12})
    d.apply_audio_effect(c, "pitch", params={"semitones": -12}, effect_id=fx["effect"])
    before = E.snapshot(t)
    try:
        path = d.render_preview().get("path")
        why = E.new_file(t, before, path)
    except drv.JudgeError as e:
        path, why = None, str(e)
    t.check("render_preview makes a new file of its own", why is None, why or str(path))
    try:
        pv = observe.samples(path) if why is None else why
    except observe.Unmeasurable as e:
        pv = f"unmeasurable: {e}"
    hz = None if isinstance(pv, str) else observe.dominant(pv, 1.5, 3.5, 150, 600)
    t.check("the preview has the clip's effect as changed (440 Hz pitched -12: 220 Hz)",
            hz is not None and abs(hz - 220) <= 220 * 0.015, pv if isinstance(pv, str) else f"{hz} Hz (220 +- 1.5 %)")
    E.clear(d)
