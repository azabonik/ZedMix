"""The export finishes, with stereo sound, whatever the source's channel layout and speed: the telephone and megaphone
voices on a mono, stereo, quad and 5.1 source export stereo at a heard level, also after enhance_voice with a bleep;
a clip at speed 0.5 to 3, plain or with an effect and a bleep, exports within a deadline and lasts its source / speed.
Port of the channel layouts and speed section of packages/core/scripts/smoke-voice.ts (judge/PORTING.md has the map).

Media: lay-mono.mkv, lay-stereo.mkv, lay-quad.mkv, lay-51.mkv: 3 s of a 440 Hz tone at -12 dB in every channel of that
layout (fixtures/make.sh). The canvas is 160x90 at 30 fps. Each case is one clip on an empty timeline, exported in the
background (export with wait false) and canceled when it has not finished after its deadline (60 s for the layouts,
30 s for the speeds, the original's): a stalled export fails its check instead of hanging the test. Every export shows
a sound that no other export of the test shows: case i places its clip at 0.2 i s, so its sound starts there (silent,
under 0.003, from 0.15 s to 0.02 s before it; heard, over 0.01, from 0.05 s to 0.3 s after it: the noise reduction of
enhance_voice fades in over some 40 ms on FFmpeg 4.4) and lasts 3 s / speed (within 0.06 s) after it. Each case is also
held to get_state (the clip has the effects, the speed and the bleep sent), since a stereo export at a heard level does
not show that an effect ran.

Every check is recorded on every path (a check whose input is missing fails with the reason), so CHECKS is exact.
"""
import driver as drv
import edits as E
import observe

PORT_BOUND = True
EXTRA_MEDIA = ("lay-mono.mkv", "lay-stereo.mkv", "lay-quad.mkv", "lay-51.mkv")
TIMEOUT = 1500
FPS = 30
LAYOUTS = [("mono", "lay-mono.mkv", 1), ("stereo", "lay-stereo.mkv", 2), ("quad", "lay-quad.mkv", 4),
           ("5.1", "lay-51.mkv", 6)]
# (effect or None, speed, a bleep too): the original's cases, on the mono source
SPEEDS = [(None, 3, False), (None, 3, True), ("robot", 1.5, False), ("robot", 0.5, True), ("declick", 2, False),
          ("noise_reduction", 2, True), ("highpass", 3, False), ("echo", 3, False), ("megaphone", 1.5, False),
          ("enhance_voice", 2, True)]
CHECKS = len(LAYOUTS) * 3 + len(SPEEDS)


def export_within(t, d, name, deadline):
    """(path, None) of an export that finished within `deadline` s, or (None, why)."""
    out = t.path("out", f"{name}.mp4")
    try:
        job = d.export(out, wait=False)
    except drv.JudgeError as e:
        return None, f"the export was refused: {e}"
    jid = job.get("job")
    if job.get("status") == "running" and jid:
        job = E.wait_job(d, jid, deadline) or job
        if job.get("status") == "running":
            try:
                d.cancel(jid)
            except drv.JudgeError:
                pass
            return None, f"stalled: still running after {deadline} s (canceled)"
    if job.get("status") != "done":
        return None, f"the export ended {job.get('status')}: {job.get('error')}"
    return out, None


def case(t, d, i, asset, fx, speed, bleep, deadline):
    """One case: the clip at 0.2 i s (so each export starts its sound at a moment of its own), its effects `fx`, its
    speed and a bleep at 1 to 1.5 s of the source; the State must show them, and the export must finish in time,
    stereo, with the sound starting at the clip's start and lasting 3 s / speed, heard, and the beep in its window.
    -> (ok, detail)"""
    start = 0.2 * i
    c = d.place_clip(asset, "v0", round(start * FPS), 0)
    for kind in fx:
        if kind == "enhance_voice":
            d.enhance_voice(c)
        else:
            d.apply_audio_effect(c, kind)
    if bleep:
        d.add_bleep(c, start=1, end=1.5)
    if speed != 1:
        d.set_speed(c, speed)
    st = E.clip(d.get_state(), c) or {}
    got = ([f.get("effect") for f in st.get("audio_effects") or []], st.get("speed"), len(st.get("bleeps") or []))
    if got != (list(fx), speed, int(bleep)):
        E.clear(d)
        return False, f"get_state shows effects, speed, bleeps {got}, not {(list(fx), speed, int(bleep))}"
    out, why = export_within(t, d, f"case{i}", deadline)
    E.clear(d)
    if why:
        return False, why
    try:
        ch = observe.channels(out)
        s = observe.samples(out)
    except observe.Unmeasurable as e:
        return False, f"unmeasurable: {e}"
    n = len(s) / observe.RATE
    before = observe.rms(s, start - 0.15, start - 0.02) if start > 0.15 else 0.0
    after = observe.rms(s, start + 0.05, start + 0.3)
    end = start + 3 / speed
    lv = observe.db(observe.rms(s, start + 0.1, end - 0.1))
    k = observe.tone_amp(s, start + 1.05 / speed, start + 1.45 / speed, 1000) if bleep else None
    bad = []
    if ch != 2:
        bad.append(f"{ch} channels")
    if before >= 0.003 or after <= 0.01:
        bad.append(f"not silent before {start:.1f} s and heard after it: {before:.4f} before, {after:.4f} after")
    if abs(n - end) > 0.06:
        bad.append(f"{n:.2f} s of sound, not {end:.2f}")
    if lv <= -30:
        bad.append(f"level {lv:.1f} dBFS")
    if bleep and k <= 0.05:
        bad.append(f"1 kHz under the bleep {k:.3f}")
    detail = (f"{ch} channels, {before:.4f} before {start:.1f} s and {after:.3f} after it, {n:.2f} s, {lv:.1f} dBFS"
              + ("" if k is None else f", the beep {k:.3f}"))
    return not bad, "; ".join(bad) or detail


def run(t):
    d = t.driver()
    d.set_project(width=160, height=90, fps=FPS)
    media, i = {}, 0
    for label, f, n in LAYOUTS:
        media[label] = d.import_media(t.media(f))
        for kind in ("telephone", "megaphone"):
            ok, why = case(t, d, i, media[label], [kind], 1, False, 60)
            t.check(f"{label} ({n} channels) with {kind}: exports stereo at a heard level (over -30 dBFS), from "
                    f"the clip's start for its length", ok, why)
            i += 1
        ok, why = case(t, d, i, media[label], ["enhance_voice", "telephone"], 1, True, 60)
        t.check(f"{label} with enhance_voice, telephone and a bleep: exports stereo, the beep heard", ok, why)
        i += 1
    for kind, speed, bleep in SPEEDS:
        ok, why = case(t, d, i, media["mono"], [kind] if kind else [], speed, bleep, 30)
        name = f"{kind or 'no effect'}{' and a bleep' if bleep else ''} at speed {speed}"
        t.check(f"{name}: the export finishes and its sound lasts 3 s / {speed} (within 0.06 s)", ok, why)
        i += 1
