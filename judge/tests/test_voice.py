"""What the audio effects do to a voice, measured by the judge on the export: noise reduction lowers the noise between
phrases and keeps the speech, highpass removes a 40 Hz rumble and keeps 1 kHz, the presence EQ lifts 4 kHz and leaves
500 Hz, bass boost lifts the lows, the de-esser tames the "s" bursts, the compressor narrows loud against quiet, the
limiter holds its ceiling and adds level, normalize reaches its loudness target, pitch shifts by its semitones without
changing the length (+12, -12, +4 and deep -5), at speed 2 a pitch shift is kept and an EQ stays where it was, and
enhance_voice lowers the noise, evens the level, does not clip and lands at -16 LUFS at every strength. Port of the
cleanup, tone, dynamics, voice changer and enhance_voice sections of packages/core/scripts/smoke-voice.ts, and of the
export half of section 1 of packages/core/scripts/smoke-voicefx.ts (pitch +12, -12 and +4 on a 440 Hz tone: the
frequency and the level); judge/PORTING.md has the map.

Media: voice.mkv (a voice-like sound: phrases at 0, +12 and -12 dB over a -50 dB pink noise floor, with "s" bursts;
fixtures/make.sh), rumble.mkv (40 Hz and 1 kHz), noise.mkv (pink noise), onset.mkv (silence, then 440 Hz from 1 s).
The canvas is 160x90 at 30 fps. Each timeline holds the dry clip and one clip per effect, each clip followed by a gap,
and is exported once; normalize and enhance_voice, whose loudness is measured on the whole file, are exported one clip
each. Every export shows a sound no other export of the test shows.

The judge measures: levels as RMS over windows of the decoded sound (observe.samples), band power as the sum of tone
amplitudes across the band (observe.band_db), a tone's frequency as the peak of a windowed DFT (observe.dominant), and
loudness and true peak with its own EBU R128 reading (observe.loudness_peak). The bounds are the original's, except
where PORTING.md ("batch 4" margins) records a measured reason.

Every check is recorded on every path (a check whose input is missing fails with the reason), so CHECKS is exact.
"""
import math

import driver as drv
import edits as E
import observe

PORT_BOUND = True
EXTRA_MEDIA = ("voice.mkv", "rumble.mkv", "noise.mkv", "onset.mkv")
TIMEOUT = 1200
FPS = 30
NORMAL, LOUD, QUIET = (1.0, 4.5), (6.0, 8.0), (9.5, 11.5)   # voice.mkv's phrases (s)
GAPS = [(0.2, 0.8), (4.75, 5.75), (8.25, 9.25)]            # between them: only the noise floor
S_TIMES = [2.05, 3.05, 4.05]                                 # its "s" bursts, 80 ms each
# A pitch-shifted tone's level against the dry tone's. The original holds only its live preview to 2 dB; the export's
# shifter on FFmpeg 4.4 plays +12 semitones 10.7 dB down (v0.2.0 and this tree; 0.0 dB with 9.0.2-17), so the export
# is held to being heard at about its level, not muted or doubled (PORTING.md, "batch 4" margins).
PITCH_LEVEL = 12
# The limiter's ceiling, read in the export: the codec lifts a few of the limited peaks over it (v0.2.0's single
# highest sample reads -5.1 to -5.2 dBFS for a -6 dB ceiling, a lookahead limiter of FFmpeg's -4.8), but almost none
# of the samples. v0.2.0 has 0 to 3 of its 576000 samples over -5.5 dBFS, those limiters 0 to 2; a limiter that holds
# -4.5 dB instead has 1700 to 2000. The single highest sample is not held: it depends on the codec (the same limiter
# coded as Opus peaks at -2.2 dBFS with 15 samples over -5.5 dBFS), and the count alone tells the mutants apart
# (PORTING.md, "batch 4" margins).
LIMIT_OVER = 10 ** (-5.5 / 20)
CHECKS = 7 + 4 + 6 + 2 + 4 * 3


def place_all(d, asset, effects, length, gap=0.5, speeds=None):
    """Clips of `asset` one after the other with a gap after each: {name: start s} (None: the dry clip)."""
    out = {}
    for i, (name, fx) in enumerate(effects):
        c = d.place_clip(asset, "v0", round(i * (length + gap) * FPS), 0)
        for kind, params in fx:
            d.apply_audio_effect(c, kind, params=params)
        if speeds and name in speeds:
            d.set_speed(c, speeds[name], ripple="none")
        out[name] = i * (length + gap)
    return out


def export(t, d, name, rate=observe.RATE):
    """(path, samples) of an export, or (None, why)."""
    out = t.path("out", f"{name}.mp4")
    try:
        job = d.export(out)
    except drv.JudgeError as e:
        return None, f"the export was refused: {e}"
    if job.get("status") != "done":
        return None, f"the export ended {job.get('status')}: {job.get('error')}"
    try:
        return out, observe.samples(out, rate)
    except observe.Unmeasurable as e:
        return None, f"unmeasurable: {e}"


def lvl(s, at, a, b):
    return observe.db(observe.rms(s, at + a, at + b))


def floor_db(s, at):
    return max(lvl(s, at, a, b) for a, b in GAPS)


def spread(s, at):
    return lvl(s, at, LOUD[0] + 0.2, LOUD[1] - 0.2) - lvl(s, at, QUIET[0] + 0.2, QUIET[1] - 0.2)


def speech(s, at):
    return lvl(s, at, NORMAL[0] + 0.2, NORMAL[1] - 0.2)


def run(t):
    d = t.driver()
    d.set_project(width=160, height=90, fps=FPS)
    voice = d.import_media(t.media("voice.mkv"))
    rumble = d.import_media(t.media("rumble.mkv"))
    noise = d.import_media(t.media("noise.mkv"))
    tone = d.import_media(t.media("onset.mkv"))
    dry = voices(t, d, voice)
    shaping(t, d, rumble, noise)
    pitches(t, d, tone)
    loudness(t, d, voice, dry)


# ---------------------------------------------------------------- the voice: cleanup and dynamics
def voices(t, d, voice):
    at = place_all(d, voice, [(None, []), ("nr", [("noise_reduction", None)]),
                              ("ds", [("de_esser", {"amount": 0.5})]),
                              ("comp", [("compressor", {"threshold": -30, "ratio": 6, "makeup": 6})]),
                              ("lim", [("limiter", {"ceiling": -6, "drive": 6})])], 12)
    path, s = export(t, d, "voices")
    names = ["noise_reduction lowers the noise between phrases by 10 dB or more",
             "noise_reduction keeps the speech level (within 1.5 dB)",
             "noise_reduction keeps quiet speech (12 dB over the noise; it loses at most 3 dB)",
             "the dry voice does not clip (peak under -1 dBFS)",
             "de_esser tames the s bursts by 3 dB or more (5-12 kHz)",
             "the compressor narrows loud against quiet by 6 dB or more",
             "the limiter holds its -6 dB ceiling in the export (at most 0.01 % of its samples over -5.5 dBFS) and "
             "adds 3 dB or more to the speech (drive 6)"]
    if path is None:
        for n in names:
            t.check(n, False, s)
        E.clear(d)
        return None
    x0 = at[None]
    f0, fn = floor_db(s, x0), floor_db(s, at["nr"])
    t.check(names[0], f0 - fn >= 10, f"{f0:.1f} -> {fn:.1f} dB")
    dsp = speech(s, at["nr"]) - speech(s, x0)
    t.check(names[1], abs(dsp) <= 1.5, f"{dsp:+.1f} dB")
    q = lvl(s, at["nr"], QUIET[0] + 0.2, QUIET[1] - 0.2) - lvl(s, x0, QUIET[0] + 0.2, QUIET[1] - 0.2)
    t.check(names[2], q >= -3, f"{q:+.1f} dB")
    pk = observe.db(observe.peak(s, x0, x0 + 12))
    t.check(names[3], pk < -1, f"peak {pk:.1f} dBFS, floor {f0:.1f} dB, loud - quiet {spread(s, x0):.1f} dB")
    sd = max(observe.band_db(s, x0 + a, x0 + a + 0.08, 5000, 12000, step=100) for a in S_TIMES)
    sx = max(observe.band_db(s, at["ds"] + a, at["ds"] + a + 0.08, 5000, 12000, step=100) for a in S_TIMES)
    t.check(names[4], sd - sx >= 3, f"{sd - sx:.1f} dB")
    sp0, sp1 = spread(s, x0), spread(s, at["comp"])
    t.check(names[5], sp0 - sp1 >= 6, f"{sp0:.1f} -> {sp1:.1f} dB")
    lp = observe.db(observe.peak(s, at["lim"], at["lim"] + 12))
    seg = s[int(at["lim"] * observe.RATE):int((at["lim"] + 12) * observe.RATE)]
    over = sum(1 for v in seg if abs(v) > LIMIT_OVER)
    gain = speech(s, at["lim"]) - speech(s, x0)
    t.check(names[6], len(seg) > 0 and over <= len(seg) / 10000 and gain >= 3,
            f"{over} of {len(seg)} samples over -5.5 dBFS (at most {len(seg) // 10000}), peak {lp:.1f} dBFS, "
            f"speech {gain:+.1f} dB")
    E.clear(d)
    return {"floor": f0, "spread": spread(s, x0), "speech": speech(s, x0)}


# ---------------------------------------------------------------- rumble and noise: highpass, EQ, bass, speed 2
def shaping(t, d, rumble, noise):
    at = place_all(d, rumble, [(None, []), ("hp", [("highpass", {"frequency": 80})])], 4)
    path, s = export(t, d, "rumble", 16000)
    if path is None:
        t.check("highpass 80 Hz cuts the 40 Hz rumble by 20 dB or more and keeps 1 kHz (within 0.5 dB)", False, s)
    else:
        amp = (lambda at, f: observe.db(observe.tone_amp(s, at + 0.5, at + 3.5, f, 16000)))
        r40 = amp(at["hp"], 40) - amp(at[None], 40)
        r1k = amp(at["hp"], 1000) - amp(at[None], 1000)
        t.check("highpass 80 Hz cuts the 40 Hz rumble by 20 dB or more and keeps 1 kHz (within 0.5 dB)",
                r40 <= -20 and abs(r1k) <= 0.5, f"40 Hz {r40:+.1f} dB, 1 kHz {r1k:+.1f} dB")
    E.clear(d)
    at = place_all(d, noise, [(None, []), ("pres", [("eq_presence", {"gain": 6, "frequency": 4000})]),
                              ("bass", [("bass_boost", {"gain": 6, "frequency": 100})]),
                              ("fast", [("eq_presence", {"gain": 6, "frequency": 4000})])], 4, speeds={"fast": 2})
    path, s = export(t, d, "noise", 16000)
    names = ["eq_presence +6 dB at 4 kHz lifts the 4 kHz band by 4.5 dB or more and leaves 500 Hz (within 0.5 dB)",
             "bass_boost +6 dB lifts 40-70 Hz by 4.5 dB or more",
             "at speed 2 the presence EQ stays at 4 kHz (its tilt within 1.5 dB of the 1x clip's)"]
    if path is None:
        for n in names:
            t.check(n, False, s)
    else:
        band = (lambda at, a, b, lo, hi: observe.band_db(s, at + a, at + b, lo, hi, 16000, 25))
        b4 = band(at["pres"], 0.5, 3.5, 3700, 4300) - band(at[None], 0.5, 3.5, 3700, 4300)
        b5 = band(at["pres"], 0.5, 3.5, 400, 600) - band(at[None], 0.5, 3.5, 400, 600)
        t.check(names[0], b4 >= 4.5 and abs(b5) <= 0.5, f"4 kHz {b4:+.1f} dB, 500 Hz {b5:+.1f} dB")
        b6 = band(at["bass"], 0.5, 3.5, 40, 70) - band(at[None], 0.5, 3.5, 40, 70)
        t.check(names[1], b6 >= 4.5, f"{b6:+.1f} dB")
        tilt_fast = band(at["fast"], 0.3, 1.7, 3700, 4300) - band(at["fast"], 0.3, 1.7, 1700, 2300)
        tilt = band(at["pres"], 0.5, 3.5, 3700, 4300) - band(at["pres"], 0.5, 3.5, 1700, 2300)
        t.check(names[2], abs(tilt_fast - tilt) <= 1.5, f"tilt {tilt_fast:.1f} at 2x, {tilt:.1f} at 1x")
    E.clear(d)


# ---------------------------------------------------------------- a 440 Hz tone: pitch, deep, speed 2
def pitches(t, d, tone):
    cases = [(None, [], 440), ("+12", [("pitch", {"semitones": 12})], 880),
             ("-12", [("pitch", {"semitones": -12})], 220),
             ("+4", [("pitch", {"semitones": 4})], 440 * 2 ** (4 / 12)),
             ("deep -5", [("deep", {"semitones": -5})], 440 * 2 ** (-5 / 12)),
             ("+12 at speed 2", [("pitch", {"semitones": 12})], 880)]
    at = place_all(d, tone, [(n, fx) for n, fx, _ in cases], 4, speeds={"+12 at speed 2": 2})
    st = d.get_state()
    path, s = export(t, d, "pitches")
    names = [f"pitch {n}: the 440 Hz tone is heard at {w:.1f} Hz (within 1 %), for its length, at a level within "
             f"{PITCH_LEVEL} dB of the dry tone's" for n, fx, w in cases[1:5]]
    names += ["pitch +12 at speed 2: still 880 Hz, and the clip lasts half as long",
              "the dry clip is 440 Hz"]
    if path is None:
        for n in names:
            t.check(n, False, s)
        E.clear(d)
        return
    x0 = at[None]
    dry_lvl = observe.db(observe.rms(s, x0 + 1.2, x0 + 3.8))
    for n, (name, fx, want) in zip(names, cases[1:5]):
        x = at[name]
        hz = observe.dominant(s, x + 1.2, x + 3.8, want * 0.8, want * 1.2)
        lv = observe.db(observe.rms(s, x + 1.2, x + 3.8)) - dry_lvl
        end = observe.rms(s, x + 3.7, x + 3.95)
        t.check(n, hz is not None and abs(hz - want) <= want * 0.01 and abs(lv) <= PITCH_LEVEL and end > 0.01,
                f"{hz} Hz, level {lv:+.1f} dB, level in its last 0.3 s {end:.3f}")
    fast = next((c for tr in st["tracks"] for c in tr["clips"] if c.get("speed") == 2), None)
    x = at["+12 at speed 2"]
    hz = observe.dominant(s, x + 0.6, x + 1.9, 700, 1100)
    tail = observe.rms(s, x + 2.05, x + 2.4)
    t.check(names[4], hz is not None and abs(hz - 880) <= 8.8 and fast is not None
            and fast.get("length_frames") == 60 and tail < 0.003,
            f"{hz} Hz; {(fast or {}).get('length_frames')} frames (60); level after 2 s {tail:.4f}")
    hz = observe.dominant(s, x0 + 1.2, x0 + 3.8, 350, 550)
    t.check(names[5], hz is not None and abs(hz - 440) <= 3, f"{hz} Hz")
    E.clear(d)


# ---------------------------------------------------------------- loudness: normalize, enhance_voice
def loudness(t, d, voice, dry):
    for target in (-16, -23):
        c = d.place_clip(voice, "v0", 0, 0)
        d.apply_audio_effect(c, "normalize", params={"target": target})
        path, s = export(t, d, f"normalize{-target}")
        try:
            li = observe.loudness_peak(path)[0] if path else s
        except observe.Unmeasurable as e:
            li = str(e)
        t.check(f"normalize to {target} LUFS: the export measures {target} LUFS (within 1)",
                not isinstance(li, str) and abs(li - target) <= 1, f"{li} LUFS")
        E.clear(d)
    for strength in (0.4, 0.7, 1):
        c = d.place_clip(voice, "v0", 0, 0)
        d.enhance_voice(c, strength=strength)
        path, s = export(t, d, f"enhance{strength}")
        names = [f"enhance_voice {strength}: the speech stands 6 dB or more further above the noise",
                 f"enhance_voice {strength}: evens loud against quiet by 8 dB or more",
                 f"enhance_voice {strength}: does not clip (peak under -0.5 dBFS, true peak under -0.5 dBTP)",
                 f"enhance_voice {strength}: -16 LUFS (within 1)"]
        if path is None or dry is None:
            for n in names:
                t.check(n, False, s if path is None else "the dry voice was not measured")
            E.clear(d)
            continue
        try:
            li, tp = observe.loudness_peak(path)
        except observe.Unmeasurable as e:
            li, tp = math.nan, math.nan
            del e
        gain = (speech(s, 0) - floor_db(s, 0)) - (dry["speech"] - dry["floor"])
        t.check(names[0], gain >= 6, f"speech - floor {gain:+.1f} dB against the dry voice's")
        t.check(names[1], dry["spread"] - spread(s, 0) >= 8, f"{dry['spread']:.1f} -> {spread(s, 0):.1f} dB")
        pk = observe.db(observe.peak(s))
        t.check(names[2], pk < -0.5 and tp < -0.5, f"peak {pk:.1f} dBFS, true peak {tp} dBTP")
        t.check(names[3], abs(li + 16) <= 1, f"{li} LUFS")
        E.clear(d)
