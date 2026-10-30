"""Makes the speech fixture (speech.mkv) and its layout (layout.json): a tool a person runs once, never a test.

    python3 -I -B judge/fixtures/speech/make_speech.py <out folder> [--gap S]

Each word of WORDS is spoken by espeak-ng on its own (written to a WAV file with -w, never played), resampled to
16 kHz mono by the ffmpeg on PATH, and cut to its voiced extent: the 10 ms frames whose root mean square (the judge's
own reading, observe.rms) is over 0.01 of full scale, from the first to the last. The words are then placed one after
the other, LEAD s of silence first, `--gap` s between them and TAIL s after the last, in one 16 kHz mono signal, coded
losslessly (FLAC in Matroska, metadata and encoder tags left out), so every FFmpeg decodes the same samples. The
layout (each word's text, start and end in seconds) is what the test holds as constants (tests/test_bleep_words.py).

The committed file was made with espeak-ng 1.50 (voice en-us, speed 150 words a minute: `espeak-ng -v en-us -s 150
-w <word>.wav <word>`), FFmpeg 4.4.2 (Ubuntu 22.04's), --gap 0.6 (the default). Making it again with other versions may give other
samples; the test is held to the committed file (JUDGE.lock hashes it), so it is not made at test time: a recogniser
can hear a new synthesis differently.
"""
import array
import json
import os
import subprocess
import sys
import wave

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import observe  # noqa: E402  (the judge's own reading of a sound's level)

WORDS = ["apple", "river", "basket", "orange", "window", "garden", "pencil"]
VOICE, SPEED = "en-us", "150"
RATE = 16000
LEAD, TAIL = 0.6, 0.6
FRAME, VOICED = 0.01, 0.01


def read16(path):
    with wave.open(path) as w:
        assert w.getnchannels() == 1 and w.getsampwidth() == 2 and w.getframerate() == RATE
        a = array.array("h", w.readframes(w.getnframes()))
    if sys.byteorder != "little":
        a.byteswap()
    return a


def voiced(a):
    """(first, last + 1) sample of the voiced frames of int16 samples `a`."""
    f = [v / 32768 for v in a]
    n = int(len(f) / (FRAME * RATE))
    on = [i for i in range(n) if observe.rms(f, i * FRAME, (i + 1) * FRAME, RATE) > VOICED]
    return int(round(on[0] * FRAME * RATE)), int(round((on[-1] + 1) * FRAME * RATE))


def main():
    out = sys.argv[1]
    gap = float(sys.argv[sys.argv.index("--gap") + 1]) if "--gap" in sys.argv else 0.6
    os.makedirs(out, exist_ok=True)
    total, layout = array.array("h", [0] * int(round(LEAD * RATE))), []
    for k, word in enumerate(WORDS):
        raw, w16 = os.path.join(out, f"{word}.wav"), os.path.join(out, f"{word}.16k.wav")
        subprocess.run(["espeak-ng", "-v", VOICE, "-s", SPEED, "-w", raw, word], check=True)
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", raw, "-ar", str(RATE), "-ac", "1",
                        "-c:a", "pcm_s16le", w16], check=True)
        a = read16(w16)
        i0, i1 = voiced(a)
        if k:
            total.extend([0] * int(round(gap * RATE)))
        start = len(total) / RATE
        total.extend(a[i0:i1])
        layout.append({"text": word, "start": round(start, 4), "end": round(len(total) / RATE, 4)})
        os.remove(raw)
        os.remove(w16)
    total.extend([0] * int(round(TAIL * RATE)))
    wav = os.path.join(out, "speech.wav")
    with wave.open(wav, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((total if sys.byteorder == "little" else array.array("h", total)).tobytes())
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", wav, "-map_metadata", "-1", "-fflags", "+bitexact",
                    "-c:a", "flac", "-flags", "+bitexact", os.path.join(out, "speech.mkv")], check=True)
    os.remove(wav)
    with open(os.path.join(out, "layout.json"), "w", encoding="utf-8") as f:
        json.dump({"rate": RATE, "seconds": round(len(total) / RATE, 4), "gap": gap, "words": layout}, f, indent=1)
        f.write("\n")
    print(json.dumps(layout), len(total) / RATE)


if __name__ == "__main__":
    main()
