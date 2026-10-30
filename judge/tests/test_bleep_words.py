"""bleep_words with the user's own words, on real speech, heard in the export: the editor transcribes a recording of
seven words with the speech recogniser the judge gives it (run.py --whisper: a pinned whisper.cpp and its tiny.en
model, judge/README.md "The speech recogniser"); a dry run reports the hits and changes nothing, its undo and redo
history included, the first one too (making a transcript is not an edit: a known bug of v0.2.0 and this line, held to
a rewrite, README.md "Known bugs"); the transcript holds the seven words, each in its place; a real run bleeps exactly
the words asked for, matched whole (no stem or prefix: "rive" does not bleep river, nor "apples" apple), with case and
punctuation ignored, each hit at its word in source seconds and its bleep around it; the export mutes those words and
plays the beep over them while every other word keeps its own sound; it is one undo step; a second run replaces the
first run's bleeps (whether it keeps bleeps added by hand is unspecified, and no check depends on it); after the runs'
undos one more undo still changes the State, so no step that changes nothing visible (a transcript's, made at any
moment) is left in the undo history; on a picture whose sound a linked clip carries, the bleeps go on the clip
that carries the sound. Port of the word-targeting sections of packages/core/scripts/smoke-bleep.ts (the
dry run, the real run and its undo, the re-run, the linked sound clip), with the user's own words only
(`use_default_list` false): the built-in list and `include_mild` stay v0.2.0-only, so no swearing enters the
repository (judge/PORTING.md has the map).

Media: speech.mkv (fixtures/speech: espeak-ng's voice, 16 kHz FLAC, committed and hashed by JUDGE.lock), whose words
are at LAYOUT (their voiced extents, from the judge's own level reading when it was made). The clip is placed at 1 s
of the timeline, so the hits' times (source seconds) differ from the timeline's.

What is heard is measured by how much of the source's own sound plays in each word's window of the export
(observe.own_sound: the export's projection on the source, at the lag that lines them up best, with the 1 kHz beep
fitted and taken out first): 1 where the word plays as it is, 0 where it is muted. A target word must read under
MUTED with the beep's 1 kHz over BEEP; every other word between HEARD_LO and HEARD_HI with no more 1 kHz than the
source has there (plus NO_BEEP). Each window is the word's voiced extent less 30 ms at each end (the mute's ramps).
Each export bleeps a set of words that no earlier export of the test bleeps, so a file handed in for another cannot
pass; a transcript or hits the adapter made up, without the editor's bleeps, fail on the export.

Without the recogniser every check is recorded as not applicable (run.py --strict fails them), never as passed, and
the editor is not started. Every check is recorded on every path (a check whose input is missing fails with the
reason), so CHECKS is exact.
"""
import re

import driver as drv
import edits as E
import observe

PORT_BOUND = True
EXTRA_MEDIA = ("speech.mkv",)
TIMEOUT = 900
FPS = 30
RATE = 16000
START = 1.0                  # the clip's start on the timeline (s)
LENGTH = 8.33                # the recording's length (s)
LAYOUT = [                   # fixtures/speech/layout.json: each word's voiced extent in the recording (s)
    ("apple", 0.60, 1.01), ("river", 1.61, 2.08), ("basket", 2.68, 3.26), ("orange", 3.86, 4.36),
    ("window", 4.96, 5.49), ("garden", 6.09, 6.60), ("pencil", 7.20, 7.73),
]
# The user's words: two targets in other cases and with punctuation, and four that only share a stem or a prefix with a
# word of the recording ("pen" begins "pencil", "gardens" is "garden" and more, "rive" begins "river", "apples" is
# "apple" and more): words match whole, case and punctuation ignored. River and apple are not targets, so an editor
# that matches stems or prefixes bleeps them (pen and gardens only reach words that are targets anyway).
WORDS = ["Garden", "PENCIL,", "pen", "gardens", "rive", "apples"]
TARGETS = {"garden", "pencil"}
RERUN = ["window."]          # the second run: one other word, with punctuation
LINKED = ["Pencil"]          # the linked sound clip's run: one word, a set no other export bleeps
# The transcript: each word's start no earlier than TR_EARLY s before its voiced extent and no later than TR_LATE s
# after it ends (so within the silence that follows it: the words are 0.6 s apart); its end after its start and no
# later than TR_LATE s after the next word's voiced extent ends (the recording's end for the last). The recogniser's
# word ends run into the silence after a word, and a word after one that ran on starts late (PORTING.md, the margins).
TR_EARLY, TR_LATE = 0.10, 0.25
# A hit: its start within HIT_START s of its word's voiced start; its end no earlier than HIT_END_EARLY s before the
# word's voiced end and no later than HIT_END_LATE s after the next word's voiced start (the recording's end for
# the last); its bleep around it, padded at most PAD s each side.
HIT_START, HIT_END_EARLY, HIT_END_LATE, PAD = 0.15, 0.15, 0.05, 0.25
MUTED, BEEP = 0.03, 0.1                  # a target word: the source's share under 0.03 (-30 dB), 1 kHz over 0.1
HEARD_LO, HEARD_HI, NO_BEEP = 0.8, 1.25, 0.005   # another word: its share 0.8..1.25, 1 kHz no more than its own + 0.005
EDGE = 0.03

NAMES = [
    "bleep_words dry run (the first: the editor transcribes the clip's sound): it reports the words asked for "
    "(garden and pencil, matched whole, case and punctuation ignored), each with no bleep, and the State is unchanged",
    "the first dry run leaves the undo and the redo history as they were (making a transcript is not an edit)",
    "a second dry run (the transcript made): the same hits, and it changes nothing (the State and the undo history)",
    "get_transcript: the recording's seven words in order (case and punctuation ignored), each in its place",
    "the dry run's hits are at their words: the transcript's times for them, in source seconds, near each word's "
    "voiced extent",
    "bleep_words: the same hits, each with a bleep on the clip around its word (beep, mute); no track or clip is added",
    "bleep_words is one undo step (undo gives the State before it, redo brings its bleeps back)",
    "export: under garden and pencil the speech is muted and the beep plays",
    "export: the other five words keep their own sound, with no beep",
    "a second bleep_words (window) replaces the first run's bleeps: one bleep, on window, none of the first run's",
    "export after the second run: window is muted and beeped; every other word, garden and pencil again, is heard",
    "the second run is one undo step (undo gives back the first run's bleeps), and undo again leaves no bleep",
    "no hidden step: after those undos, one more undo changes the State (no step that changes nothing visible, of the "
    "transcript, the dry runs or the runs, is left in the undo history), and redo gives it back",
    "export after both undos: every word keeps its own sound, with no beep",
    "on a silent picture whose sound a linked clip carries: the hit and its bleep go on the sound clip, none on the "
    "picture",
    "export of the linked sound clip: pencil is muted and beeped, every other word is heard",
]
CHECKS = len(NAMES)
# Bugs a release is known to have, per check (run.py T.check's known_bug; README.md "Known bugs"): for a listed
# release (--release) a failure is recorded as a KNOWN BUG with the reason, never as a pass, and does not fail the run;
# any other release (rewrite) must pass the check. Anthony's ruling of 2026-10-30: making a transcript is not an edit.
HIDDEN_STEP = ("the first dry run keeps its transcript as an undo step that changes nothing visible (ruling of "
               "2026-10-30)")
KNOWN_BUGS = {NAMES[1]: {"v0.2.0": HIDDEN_STEP, "zedmix": HIDDEN_STEP}}


def norm(text):
    """A word as the matching sees it: lower case, letters and digits only."""
    return re.sub(r"[^0-9a-z]", "", str(text).lower())


def place_of(word):
    """(start, end, the next word's start, the next word's end) of a word of LAYOUT; the recording's end after the
    last."""
    i = [w for w, _, _ in LAYOUT].index(word)
    nxt = LAYOUT[i + 1] if i + 1 < len(LAYOUT) else (None, LENGTH, LENGTH)
    return LAYOUT[i][1], LAYOUT[i][2], nxt[1], nxt[2]


def short_hits(hits):
    return ", ".join(f"{h.get('text')!r} [{h.get('start')},{h.get('end')}] clip {h.get('clip')} bleep {h.get('bleep')}"
                     for h in hits or []) or "none"


def short_bleeps(bs):
    return ", ".join(f"{b.get('id')} [{b.get('start')},{b.get('end')}] {b.get('sound')} mute {b.get('mute')}"
                     for b in bs or []) or "none"


def bleeps_of(st, cid):
    return (E.clip(st, cid) or {}).get("bleeps") or []


def without_bleeps(st):
    """The State's tracks with every clip's bleeps left out (what bleep_words must not change)."""
    return [{**tr, "clips": [{k: v for k, v in c.items() if k != "bleeps"} for c in tr.get("clips", [])]}
            for tr in st.get("tracks", [])]


def hits_ok(hits, clip, targets, bleep):
    """(ok, detail): `hits` are exactly one per target word (normalized text), each on `clip`, each with a bleep id
    (bleep True) or none (False)."""
    if not isinstance(hits, list) or not all(isinstance(h, dict) for h in hits):
        return False, f"no hits ({hits!r})"
    texts = sorted(norm(h.get("text")) for h in hits)
    ok = texts == sorted(targets) and all(h.get("clip") == clip for h in hits) and all(
        (isinstance(h.get("bleep"), str) and h.get("bleep")) if bleep else h.get("bleep") is None for h in hits)
    return ok, f"hits {short_hits(hits)}; want one each of {sorted(targets)} on clip {clip}, " + (
        "each with a bleep" if bleep else "with no bleep")


def at_words(hits, words):
    """(ok, detail): each hit's start and end are its transcript word's times, and are near its word's voiced extent
    (the bounds above)."""
    if not isinstance(words, list):
        return False, f"no transcript ({words!r})"
    by = {norm(w.get("text")): w for w in words if isinstance(w, dict)}
    ok, notes = bool(hits), []
    for h in hits or []:
        t = norm(h.get("text"))
        w = by.get(t)
        try:
            s, e = float(h.get("start")), float(h.get("end"))
        except (TypeError, ValueError):
            ok = False
            notes.append(f"{t}: start/end {h.get('start')!r}/{h.get('end')!r} <-")
            continue
        if t not in TARGETS or w is None:
            ok = False
            notes.append(f"{t}: not a target word in the transcript <-")
            continue
        a, b, na, _ = place_of(t)
        same = abs(s - float(w.get("start", -9))) <= 1e-3 and abs(e - float(w.get("end", -9))) <= 1e-3
        near = abs(s - a) <= HIT_START and b - HIT_END_EARLY <= e <= na + HIT_END_LATE
        ok = ok and same and near
        notes.append(f"{t} [{s:.3f},{e:.3f}] (transcript [{w.get('start')},{w.get('end')}], voiced [{a},{b}], next "
                     f"word at {na})" + ("" if same and near else " <-"))
    return ok, "; ".join(notes) + (f" (start within {HIT_START} s of the voiced start; end from {HIT_END_EARLY} s "
                                   f"before the voiced end to {HIT_END_LATE} s after the next word's start)")


def bleeps_around(st, clip, hits):
    """(ok, detail): the clip's bleeps are one per hit (its id), each around its hit (padded 0 to PAD s each side),
    sound beep, mute true."""
    bs = bleeps_of(st, clip)
    by = {b.get("id"): b for b in bs}
    ok = isinstance(hits, list) and len(bs) == len(hits) and len(hits) > 0
    for h in hits if isinstance(hits, list) else []:
        b = by.get(h.get("bleep"))
        try:
            pre, post = float(h["start"]) - float(b["start"]), float(b["end"]) - float(h["end"])
        except (TypeError, KeyError, ValueError):
            ok = False
            continue
        ok = ok and 0 <= pre <= PAD and 0 <= post <= PAD and b.get("sound") == "beep" and b.get("mute") is True
    return ok, f"bleeps {short_bleeps(bs)} (each around its hit, padded 0 to {PAD} s, beep, mute true)"


def export(t, d, name):
    """The export's sound at RATE, or why there is none (a str)."""
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


def heard(t, src, snd, muted):
    """((ok muted, detail), (ok heard, detail)): in the export `snd`, each word of `muted` reads muted and beeped,
    each other word heard with no beep (the bounds above)."""
    if isinstance(snd, str) or isinstance(src, str):
        why = snd if isinstance(snd, str) else src
        return (False, why), (False, why)
    wins = [(a + EDGE, b - EDGE) for _, a, b in LAYOUT]
    lag, gains = observe.own_sound(src, snd, START, LAYOUT[0][1] - 0.2, LAYOUT[-1][2] + 0.2, wins, rate=RATE,
                                   tones=[1000])
    ok_m, ok_h, nm, nh = True, True, [], []
    for (w, _, _), (a, b), g in zip(LAYOUT, wins, gains):
        k = observe.tone_amp(snd, a + START + lag, b + START + lag, 1000, RATE)
        own = observe.tone_amp(src, a, b, 1000, RATE)
        if w in muted:
            good = g is not None and abs(g) < MUTED and k > BEEP
            ok_m = ok_m and good
            nm.append(f"{w} share {g if g is None else round(g, 4)}, 1 kHz {k:.3f}" + ("" if good else " <-"))
        else:
            good = g is not None and HEARD_LO <= g <= HEARD_HI and k <= own + NO_BEEP
            ok_h = ok_h and good
            nh.append(f"{w} share {g if g is None else round(g, 3)}, 1 kHz {k:.4f} (its own {own:.4f})"
                      + ("" if good else " <-"))
    lagnote = f"; lag {lag * 1000:.1f} ms"
    return ((ok_m and bool(muted), "; ".join(nm) + f" (share under {MUTED}, 1 kHz over {BEEP}){lagnote}"),
            (ok_h, "; ".join(nh) + f" (share {HEARD_LO}..{HEARD_HI}, 1 kHz at most its own + {NO_BEEP}){lagnote}"))


def run(t):
    if t.whisper is None:
        for n in NAMES:
            t.not_applicable(n, t.whisper_why)
        return
    d = t.driver(whisper=True)
    d.set_project(width=320, height=180, fps=FPS)
    media = t.media("speech.mkv")
    try:
        src = observe.samples(media, RATE)
    except observe.Unmeasurable as e:
        src = f"the recording is unmeasurable: {e}"
    asset = d.import_media(media)
    A = d.place_clip(asset, "v0", int(START * FPS), 0)
    st0 = d.get_state()

    # ---------------------------------------------------------------- the dry runs, the transcript, the hits
    # The first transcribes; it is held to the State, and (its own check) to the undo and the redo history, with a
    # redo entry set up first (edits.unchanged): making a transcript is not an edit. v0.2.0 keeps the transcript with
    # an undo step that changes nothing in the State (KNOWN_BUGS); the State is then put back (the probe's marker) so
    # the checks after it judge the rest. The second dry run, with the transcript made, is held to both again.
    dry, st_ok, hist_ok, hist_why = E.unchanged(d, lambda: d.bleep_words(clips=[A], words=WORDS, use_default_list=False,
                                                                         dry_run=True))
    dhits = (dry or {}).get("hits") if isinstance(dry, dict) else f"no answer ({hist_why})"
    ok, hwhy = hits_ok(dhits, A, TARGETS, bleep=False)
    t.check(NAMES[0], ok and st_ok, hwhy + ("" if st_ok else "; the State changed (or it was refused)"))
    back = E.restore(d, st0)
    t.check(NAMES[1], hist_ok, hist_why + ("" if back else "; the State could not be put back afterwards"),
            known_bug=KNOWN_BUGS[NAMES[1]])
    key = (lambda hs: sorted((norm(h.get("text")), h.get("start"), h.get("end")) for h in hs)
           if isinstance(hs, list) and all(isinstance(h, dict) for h in hs) else hs)
    dry, st_ok, hist_ok, why = E.unchanged(d, lambda: d.bleep_words(clips=[A], words=WORDS, use_default_list=False,
                                                                    dry_run=True))
    hits0 = (dry or {}).get("hits") if isinstance(dry, dict) else None
    ok, hwhy = hits_ok(hits0, A, TARGETS, bleep=False)
    t.check(NAMES[2], ok and st_ok and hist_ok and key(hits0) == key(dhits), f"{hwhy}"
            + ("" if key(hits0) == key(dhits) else " (not the first dry run's)") + f"; {why}")
    E.restore(d, st0)

    words = d.get_transcript(asset)
    ok, notes = isinstance(words, list) and [norm(w.get("text")) for w in words if isinstance(w, dict)] == [
        w for w, _, _ in LAYOUT], []
    for i, w in enumerate(words if ok else []):
        a, b, _, nb = place_of(LAYOUT[i][0])
        try:
            s, e = float(w.get("start")), float(w.get("end"))
        except (TypeError, ValueError):
            ok = False
            continue
        good = a - TR_EARLY <= s <= b + TR_LATE and s < e <= nb + TR_LATE
        ok = ok and good
        notes.append(f"{w.get('text')!r} [{s},{e}] (voiced [{a},{b}])" + ("" if good else " <-"))
    t.check(NAMES[3], ok, ("; ".join(notes) if notes else f"transcript {E.short(words, 300)}")
            + f" (start from {TR_EARLY} s before the voiced start to {TR_LATE} s after its end; end no later than "
              f"{TR_LATE} s after the next word's voiced end)")
    ok, why = at_words(dhits, words)
    t.check(NAMES[4], ok, why)

    # ---------------------------------------------------------------- the real run, its undo, the export
    try:
        hits = d.bleep_words(clips=[A], words=WORDS, use_default_list=False).get("hits")
    except drv.JudgeError as e:
        hits = f"refused: {e}"
    st1 = d.get_state()
    ok1, why1 = hits_ok(hits, A, TARGETS, bleep=True)
    same = key(hits) == key(dhits)
    ok2, why2 = bleeps_around(st1, A, hits if ok1 else None)
    kept = without_bleeps(st1) == without_bleeps(st0)
    t.check(NAMES[5], ok1 and same and ok2 and kept, f"{why1}; " + ("the dry run's texts and times" if same else
                                                                    f"not the dry run's ({short_hits(dhits)})")
            + f"; {why2}" + ("" if kept else "; the tracks or clips changed besides the bleeps"))
    d.undo()
    u = d.get_state()
    d.redo()
    r = d.get_state()
    t.check(NAMES[6], u == st0 and r == st1 and st1 != st0,
            f"after undo {short_bleeps(bleeps_of(u, A))}; after redo {short_bleeps(bleeps_of(r, A))}")
    (okm, whym), (okh, whyh) = heard(t, src, export(t, d, "words"), TARGETS)
    t.check(NAMES[7], okm, whym)
    t.check(NAMES[8], okh, whyh)

    # ---------------------------------------------------------------- the second run replaces the first
    first = {h.get("bleep") for h in hits} if ok1 else set()
    try:
        hits2 = d.bleep_words(clips=[A], words=RERUN, use_default_list=False, sound="beep").get("hits")
    except drv.JudgeError as e:
        hits2 = f"refused: {e}"
    st2 = d.get_state()
    ok, why = hits_ok(hits2, A, {"window"}, bleep=True)
    bs = bleeps_of(st2, A)
    okb, whyb = bleeps_around(st2, A, hits2 if ok else None)
    t.check(NAMES[9], ok and okb and len(bs) == 1 and not first & {b.get("id") for b in bs},
            f"{why}; {whyb}; the first run's bleeps {sorted(first)}")
    (okm, whym), (okh, whyh) = heard(t, src, export(t, d, "rerun"), {"window"})
    t.check(NAMES[10], okm and okh, f"{whym}; {whyh}")
    d.undo()
    u1 = d.get_state()
    d.undo()
    u0 = d.get_state()
    t.check(NAMES[11], u1 == st1 and u0 == st0, f"after one undo {short_bleeps(bleeps_of(u1, A))}; after two "
                                                f"{short_bleeps(bleeps_of(u0, A))}")
    # The step before the first run is the user's last edit (the clip's placement, on v0.2.0): a step the editor kept
    # for a transcript (or anything else that changes nothing visible) would be undone here instead.
    d.undo()
    up = d.get_state()
    d.redo()
    ur = d.get_state()
    t.check(NAMES[12], up != st0 and ur == st0,
            ("" if up != st0 else "one more undo changed nothing (a step that changes nothing visible is left in the "
                                  "undo history); ")
            + ("" if ur == st0 else "redo did not give the State back; ")
            + f"clips after that undo: {[c.get('id') for tr in up.get('tracks', []) for c in tr.get('clips', [])]}")
    (_, _), (okh, whyh) = heard(t, src, export(t, d, "undone"), set())
    t.check(NAMES[13], okh, whyh)

    # ---------------------------------------------------------------- a linked sound clip carries the sound
    try:
        d.set_volume(A, 0)
        a0 = d.add_track("audio")
        Aa = d.place_clip(asset, a0, int(START * FPS), 0)
        d.link_clips([A, Aa])
    except drv.JudgeError as e:  # (the undos above took back more than they should have, for one)
        for n in NAMES[14:]:
            t.check(n, False, f"the linked sound clip could not be set up: {e}")
        return
    try:
        hits3 = d.bleep_words(clips=[A], words=LINKED, use_default_list=False).get("hits")
    except drv.JudgeError as e:
        hits3 = f"refused: {e}"
    st3 = d.get_state()
    ok, why = hits_ok(hits3, Aa, {"pencil"}, bleep=True)
    okb, whyb = bleeps_around(st3, Aa, hits3 if ok else None)
    t.check(NAMES[14], ok and okb and bleeps_of(st3, A) == [],
            f"{why}; on the sound clip: {whyb}; on the picture: {short_bleeps(bleeps_of(st3, A))}")
    (okm, whym), (okh, whyh) = heard(t, src, export(t, d, "linked"), {"pencil"})
    t.check(NAMES[15], okm and okh, f"{whym}; {whyh}")
