#!/usr/bin/env bash
# Installs the speech recogniser that the judge gives the editor (judge/README.md, "The speech recogniser"):
# whisper.cpp's whisper-cli, built from the commit that pin.json names with pin.json's cmake flags (a static binary,
# not tuned to this computer's processor: it needs SSE4.2, AVX, AVX2, FMA, F16C and BMI2, a Haswell or later x86-64),
# and the model pin.json names, from its Hugging Face revision URL (its size and sha256 checked before it is
# installed). Then it writes <dest>/manifest.json (the commit, the binary's and the model's sha256, the compiler and
# cmake versions) and makes <dest> read-only for everyone (the editor only reads it and runs the binary).
#
# The source is fetched by its commit hash (git fetch --depth 1 origin <commit>, then HEAD is checked against it),
# never by tag: a tag can move, and GitHub's tag archives are not byte-stable. It downloads (github.com and
# huggingface.co), so it runs before the judge, never in a test: judge.yml runs it as the runner's user into
# /srv/judge/whisper. --src takes a checkout already on disk (its HEAD must be the pinned commit and its tree clean),
# --model a copy of the model already on disk (checked the same way), --bin a whisper-cli that a person built from
# that checkout with pin.json's flags (a local install; nothing is built then, and the manifest says so; CI never
# passes it). CMAKE names the cmake to use (default: cmake on PATH), JOBS the build's parallel jobs (default: the
# processor count).
# Usage: install.sh <dest> [--src <checkout>] [--model <file>] [--bin <file>]   (<dest> must not exist yet)
#        needs: git (without --src), a C and C++ compiler and cmake 3.14 or newer (without --bin), curl (without
#        --model), readelf, sha256sum
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${1:?usage: install.sh <dest> [--src <checkout>] [--model <file>]}"
shift
SRC="" MODEL="" PREBUILT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --src) SRC="${2:?--src needs a folder}"; shift 2 ;;
    --model) MODEL="${2:?--model needs a file}"; shift 2 ;;
    --bin) PREBUILT="${2:?--bin needs a file}"; shift 2 ;;
    *) echo "install.sh: unknown argument $1" >&2; exit 2 ;;
  esac
done
if [ -e "$DEST" ]; then echo "install.sh: $DEST exists" >&2; exit 1; fi
pin() { python3 -I -c 'import json, sys
v = json.load(open(sys.argv[1]))
for k in sys.argv[2].split("."):
    v = v[k]
print("\n".join(v) if isinstance(v, list) else v)' "$HERE/pin.json" "$1"; }
REPO="$(pin repository)"; COMMIT="$(pin commit)"; TARGET="$(pin target)"
MFILE="$(pin model.file)"; MURL="$(pin model.url)"; MSIZE="$(pin model.size)"; MSHA="$(pin model.sha256)"
mapfile -t FLAGS < <(pin cmake_flags)
CMAKE="${CMAKE:-cmake}"
JOBS="${JOBS:-$(nproc)}"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
if [ -z "$SRC" ]; then
  SRC="$TMP/whisper.cpp"
  git init -q "$SRC"
  git -C "$SRC" remote add origin "$REPO"
  git -C "$SRC" fetch -q --depth 1 origin "$COMMIT"
  git -C "$SRC" -c advice.detachedHead=false checkout -q FETCH_HEAD
fi
head="$(git -C "$SRC" rev-parse HEAD)"
if [ "$head" != "$COMMIT" ]; then echo "install.sh: $SRC is at $head, not the pinned $COMMIT" >&2; exit 1; fi
if [ -n "$(git -C "$SRC" status --porcelain --untracked-files=all)" ]; then
  echo "install.sh: $SRC has changes or untracked files: build only the pinned commit as it is" >&2; exit 1
fi

if [ -z "$MODEL" ]; then
  MODEL="$TMP/$MFILE"
  curl -fsSL --retry 3 --max-time 900 -o "$MODEL" "$MURL"
fi
got_size="$(stat -c %s "$MODEL")"
if [ "$got_size" != "$MSIZE" ]; then echo "install.sh: the model is $got_size bytes, not $MSIZE" >&2; exit 1; fi
echo "$MSHA  $MODEL" | sha256sum -c --quiet - || { echo "install.sh: the model's sha256 is not the pinned one" >&2; exit 1; }

if [ -z "$PREBUILT" ]; then
  "$CMAKE" -S "$SRC" -B "$TMP/build" "${FLAGS[@]}" > "$TMP/configure.log" 2>&1 || { cat "$TMP/configure.log" >&2; exit 1; }
  "$CMAKE" --build "$TMP/build" --target "$TARGET" -j "$JOBS" > "$TMP/build.log" 2>&1 || { tail -50 "$TMP/build.log" >&2; exit 1; }
  BIN="$TMP/build/bin/$TARGET"
  CMAKE_V="$("$CMAKE" --version | head -1)"
  CXX="$(grep -m1 '^CMAKE_CXX_COMPILER:' "$TMP/build/CMakeCache.txt" | cut -d= -f2-)"
else
  BIN="$PREBUILT" CMAKE_V="not built by install.sh (--bin)" CXX=""
fi
test -x "$BIN"
# The build records its commit (whisper.cpp's build-info takes it from git): the judge looks for it in the binary.
grep -aqF "${COMMIT:0:7}" "$BIN" || { echo "install.sh: the built $TARGET does not name commit ${COMMIT:0:7}" >&2; exit 1; }
# Static: no program interpreter (a dynamic binary would load the runner's libraries, which differ between hosts).
if readelf -lW "$BIN" | grep -q 'INTERP'; then echo "install.sh: $BIN is not a static binary" >&2; exit 1; fi

mkdir -p "$DEST/bin" "$DEST/models"
cp "$BIN" "$DEST/bin/$TARGET"
cp "$MODEL" "$DEST/models/$MFILE"
python3 -I - "$DEST" "$COMMIT" "$TARGET" "$MFILE" "$CMAKE_V" "$CXX" <<'PY'
import hashlib, json, os, subprocess, sys
dest, commit, target, mfile, cmake, cxx = sys.argv[1:7]
def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()
cc = subprocess.run([cxx, "--version"], capture_output=True, text=True).stdout.splitlines()[:1] if cxx else ["unknown (--bin)"]
m = {"commit": commit, "bin": f"bin/{target}", "bin_sha256": sha(os.path.join(dest, "bin", target)),
     "model": f"models/{mfile}", "model_sha256": sha(os.path.join(dest, "models", mfile)),
     "compiler": cc[0] if cc else cxx, "cmake": cmake}
with open(os.path.join(dest, "manifest.json"), "w", encoding="utf-8") as f:
    json.dump(m, f, indent=1)
    f.write("\n")
PY
chmod -R a-w,a+rX "$DEST"
echo "install.sh: the speech recogniser is in $DEST (whisper.cpp ${COMMIT:0:7}, $MFILE)"
