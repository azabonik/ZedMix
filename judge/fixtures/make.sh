#!/usr/bin/env bash
# The judge's media, made from FFmpeg's lavfi sources (test patterns and tones, nobody's footage). Nothing is
# downloaded. Usage: make.sh <outdir> [<optional fixture> ...]   env: FFMPEG / FFPROBE (default: the ffmpeg / ffprobe
# on PATH). It always makes the base set below; an optional fixture (the edit tests' media, further below) is made only
# when it is named: run.py names those that the run's tests list in EXTRA_MEDIA, so a run that needs none of them (the
# runner's self-test) does not spend the time. A name that is not an optional fixture fails (exit 2).
# The base set. The four clips use the recipes of the repository's CI media (scripts/ci/make-media.sh):
#   a.mp4     testsrc2 1280x720 30 fps 6 s + sine 440 Hz   H.264 High yuv420p + AAC-LC mono 44.1 kHz
#   b.mp4     testsrc  1280x720 30 fps 6 s + sine 660 Hz   same codecs
#   c640.mp4  testsrc2  640x480 30 fps 5 s + sine 440 Hz   same codecs
#   m.mp3     sine 330 Hz 20 s                              MP3 mono 44.1 kHz 64 kb/s
# one for the measurement self-check:
#   gap.m4a   440 Hz tone, digital silence from 2.0 to 3.5 s, 5.5 s in all   AAC-LC mono 44.1 kHz
# and a very small video that a test puts in a data: URI (a few kB):
#   tiny.mp4  testsrc 32x32 10 fps 1 s, no audio                             H.264 yuv420p
# a colour look-up table that swaps red and blue (test_v020_otio_compat):
#   look.cube  LUT_3D_SIZE 2
# and the effects test's pictures (test_effects), 30 fps, 2 s unless said, no audio, H.264 yuv420p (crf 18):
#   fx-white.mp4     white 320x180                   fx-bars.mp4      testsrc2 240x180 (4:3, letterboxed in 16:9)
#   fx-base.mp4      0xE020E0 320x180, 20 s (under it)                fx-base2.mp4     0x20C840, the same
#   fx-gray64.mp4    0x404040 320x180
#   fx-gray128.mp4   0x808080 320x180                fx-gray128p.mp4  0x808080 180x320 (portrait)
#   fx-pair.mp4      0x806060 | 0xC04040, each 160x180
#   fx-redblue.mp4   0xE02020 | 0x2020E0             fx-blue.mp4      0x2060C0 320x180
#   fx-holdgb.mp4    0xE09020 | 0xE02090 (the same colour with green and blue swapped), each 160x180
#   fx-box.mp4       a white 60x50 box at (130, 65) on black 320x180
#   fx-gridline.mp4  a white line at y 30..33 on black 320x180
#   fx-mover.mp4     a white 40x40 box at y 70, x = 20 + 100 t, on black 320x180
#   fx-ramp.mp4      a grey ramp, 0 at the left to 255 at the right, 320x180, 1 s
#   fx-greensq.mp4   a 0x606060 60x60 square at y 60, x = 100 + 30 t, on 0x00FF00 320x180, 1 s
# The optional fixtures: the edit tests' media (test_cuts, test_speed_*, test_locks, test_freeze, test_reverse_slowmo),
# whose every frame shows its own index: nine vertical stripes of 20 pixels, stripe b bright (luma 220) when bit b of the
# frame's index is set, dark (30) when not (observe.frame_indexes); their sound is a chirp,
# 0.25 sin(2 pi (200 t + 100 t^2)), whose frequency 200 + 200 t Hz says the source moment (observe.chirp_time):
#   idx.mp4      stripes 180x90 30 fps 16 s + the chirp 16 s            H.264 crf 12 (GOP 15) + AAC-LC mono 48 kHz 192 kb/s
#   idx2997.mp4  stripes 180x90 30000/1001 fps 16 s on a 1/30000 timebase, no audio
#   skew.mp4     stripes 180x90 30 fps 3.0 s + the chirp 3.5 s (the sound outlasts the picture)
#   cutout.mkv   stripes 180x90 30 fps 2 s, the top half transparent     FFV1 yuva420p, no audio
#   move.mp4     testsrc2 320x180 30 fps 3 s + sine 440 Hz               H.264 crf 12 + AAC-LC mono 48 kHz
#   tone300.m4a  sine 300 Hz 10 s                                        AAC-LC mono 48 kHz
#   chirp.m4a    the chirp alone, 16 s: another recording of idx.mp4's   AAC-LC mono 48 kHz 192 kb/s
#                moments (a microphone's, say)
# and a long one, for the edit tests' bakes that must still run while the test changes the timeline or cancels them
# (test_locks, test_reverse_slowmo: reversing 10 s of it takes about 4 s on v0.2.0):
#   long.mp4     testsrc2 1920x1080 30 fps 20 s + sine 440 Hz            the base clips' codecs
# The compositing test's pictures (test_masks), exact RGB stills (PNG), 640x360 unless said:
#   mk-bands.png   eight vertical bands, 80 wide: E62828 28C83C 283CDC F0DC3C 808080 141414 FAFAFA C878B4
#   mk-greys.png   six horizontal bands, 60 high: 000000 282828 646464 A0A0A0 D2D2D2 FFFFFF
#   mk-blue.png    0000FF                 mk-red.png    FF0000              mk-white.png   FFFFFF
#   mk-grey64.png  404040                 mk-redsq.png  FF0000, 480x480 (a square picture)
#   mk-greenbox.png  00FF00 with an FF0000 box at x 200..439, y 100..259
#   mk-disc.mkv    an FF0000 disc of radius 120 at (320, 180) on transparency, 1 s   FFV1 yuva420p
# The key test's pictures (test_key), 30 fps, H.264 yuv420p (crf 18), BT.601 limited range with all four colour tags:
#   key-grey.mp4   808080 1080x1920 2 s; white boxes at (100, 300) and (730, 1050) (200x200), black at (680, 300)
#                  and (680, 1000) (300x300; the second around the white one), red at (100, 1000); 300x300 unless said
#   key-blue-p.mp4 0000FF 1080x1920 2 s     key-blue-l.mp4  0000FF 1280x720 4 s
#   key-green.mp4  00FF00 1280x720 2 s; FF0000 box at (200, 200) and B4DCB4 (a green spill) at (800, 200), 240x240
#   key-black.mp4  000000 1280x720 2 s; a white 280x280 box at (500, 200)
#   key-noisy.mkv  30C040 320x240 0.2 s with strong noise (temporal and uniform)                   FFV1 yuv444p
# The colour test's sources (test_colorspace): the 8 x 4 grid of 32 flat patches (cs_patches below: full and 75 %
# bars, skin, sky, darks, greys), each patch W/8 x H/4, coded from exact RGB with the matrix and range named and
# tagged with the tags named and no others (setparams on the frames and the encoder's options, so any FFmpeg writes
# the same tags), 0.6 s at 30 fps; H.264 crf 4 unless said. Each video's frames also show their own index (0 to 17) in
# a band over the grid's top left corner (x < W/4, y < H/16; the patches' middles are below it): eight stripes of W/32,
# stripe b grey 220 when bit b of the index is set and grey 30 when not, so a reversed, slowed or held frame is told
# from its neighbours; the stills (cs-grid.png, .jpg), the lossless clips (cs-testsrc, cs-gridll) and cs-green have no band:
#   cs-hd.mp4      1280x720 BT.709 limited, untagged        cs-709.mp4    1280x720 BT.709 limited, all four tags
#   cs-601.mp4     1280x720 BT.601 limited, all four tags    cs-sd601.mp4  720x480 BT.601 limited, all four tags
#   cs-sd.mp4      720x480 BT.601 limited, untagged          cs-sd709.mp4  720x480 BT.709 limited, all four tags
#   cs-full709.mp4 1280x720 BT.709 full range, all four tags
#   cs-fullnm.mp4  1280x720 BT.601 full range, only the range tagged (full)
#   cs-partial.mp4 1280x720 BT.601 limited, only the matrix tagged (smpte170m)
#   cs-vp9.webm    1280x720 BT.601 limited, untagged         VP9 lossless
#   cs-rotsd.mp4   848x480 BT.601 limited, untagged, shown turned a quarter (a portrait 480x848)
#   cs-grid.png    1280x720, RGB                            cs-grid.jpg   the same as a JPEG (quality 1)
#   cs-cut601.mkv  1280x720 BT.601 limited, all four tags, with an opaque alpha plane   FFV1 yuva420p
#   cs-testsrc.mp4 testsrc 1280x720 0.4 s BT.709 limited, all four tags   H.264 lossless (qp 0)
#   cs-gridll.mp4  the grid 1280x720 0.4 s BT.709 limited, all four tags   H.264 lossless (qp 0)
#   cs-green.mp4   1280x720 0.4 s, 1EC83C with a C83C32 rectangle in its middle 40 %, BT.709 limited, untagged
# The tones are at amplitude 1/8 (peak about -18 dBFS). The frame rate is the source's (rate=30), never -r.
# Then checks each file it made with ffprobe (codecs, size, rate, frame count, channels) and prints what it made.
set -euo pipefail
OUT="${1:?usage: make.sh <outdir> [<optional fixture> ...]}"; FF="${FFMPEG:-ffmpeg}"; FP="${FFPROBE:-ffprobe}"
shift
MK=" mk-bands.png mk-greys.png mk-blue.png mk-red.png mk-white.png mk-grey64.png mk-redsq.png mk-greenbox.png mk-disc.mkv "
KEY=" key-grey.mp4 key-blue-p.mp4 key-blue-l.mp4 key-green.mp4 key-black.mp4 key-noisy.mkv "
CS=" cs-hd.mp4 cs-709.mp4 cs-601.mp4 cs-sd601.mp4 cs-sd.mp4 cs-sd709.mp4 cs-full709.mp4 cs-fullnm.mp4 cs-partial.mp4"
CS="$CS cs-vp9.webm cs-rotsd.mp4 cs-grid.png cs-grid.jpg cs-cut601.mkv cs-testsrc.mp4 cs-gridll.mp4 cs-green.mp4 "
OPTIONAL=" idx.mp4 idx2997.mp4 skew.mp4 cutout.mkv move.mp4 tone300.m4a chirp.m4a long.mp4$MK${KEY# }${CS# }"
WANT=" "
for n in "$@"; do
  case "$OPTIONAL" in
    *" $n "*) WANT="$WANT$n " ;;
    *) echo "make.sh: '$n' is not an optional fixture (they are:$OPTIONAL)" >&2; exit 2 ;;
  esac
done
# want <file>: whether the optional fixture <file> was named
want() { case "$WANT" in *" $1 "*) return 0 ;; *) return 1 ;; esac; }
mkdir -p "$OUT"
"$FF" -version | sed -n 1p

# clip <file> <video source> <size> <seconds> <tone Hz>
clip() {
  "$FF" -nostdin -hide_banner -loglevel error -y \
    -f lavfi -i "$2=size=$3:rate=30:duration=$4" \
    -f lavfi -i "sine=frequency=$5:sample_rate=44100:duration=$4" \
    -map 0:v -map 1:a -c:v libx264 -preset medium -crf 23 -profile:v high -pix_fmt yuv420p \
    -c:a aac -ac 1 -ar 44100 "$OUT/$1"
}
clip a.mp4 testsrc2 1280x720 6 440
clip b.mp4 testsrc 1280x720 6 660
clip c640.mp4 testsrc2 640x480 5 440
if want long.mp4; then clip long.mp4 testsrc2 1920x1080 20 440; fi
"$FF" -nostdin -hide_banner -loglevel error -y -f lavfi -i "sine=frequency=330:sample_rate=44100:duration=20" \
  -c:a libmp3lame -b:a 64k -ac 1 -ar 44100 "$OUT/m.mp3"
"$FF" -nostdin -hide_banner -loglevel error -y \
  -f lavfi -i "aevalsrc=exprs='if(between(t\,2\,3.5)\,0\,0.125*sin(2*PI*440*t))':sample_rate=44100:duration=5.5" \
  -c:a aac -ac 1 -ar 44100 "$OUT/gap.m4a"

"$FF" -nostdin -hide_banner -loglevel error -y -f lavfi -i "testsrc=size=32x32:rate=10:duration=1" \
  -c:v libx264 -preset medium -crf 30 -pix_fmt yuv420p -movflags +faststart "$OUT/tiny.mp4"

printf 'LUT_3D_SIZE 2\n0 0 0\n0 0 1\n0 1 0\n0 1 1\n1 0 0\n1 0 1\n1 1 0\n1 1 1\n' > "$OUT/look.cube"

# still <file> <lavfi graph> [<seconds>]: a picture with no audio
still() {
  "$FF" -nostdin -hide_banner -loglevel error -y -f lavfi -i "$2" -t "${3:-2}" \
    -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p "$OUT/$1"
}
still fx-white.mp4 "color=c=white:s=320x180:r=30"
still fx-bars.mp4 "testsrc2=s=240x180:r=30"
still fx-base.mp4 "color=c=0xE020E0:s=320x180:r=30" 20
still fx-base2.mp4 "color=c=0x20C840:s=320x180:r=30" 20
still fx-gray64.mp4 "color=c=0x404040:s=320x180:r=30"
still fx-gray128.mp4 "color=c=0x808080:s=320x180:r=30"
still fx-gray128p.mp4 "color=c=0x808080:s=180x320:r=30"
still fx-pair.mp4 "color=c=0x806060:s=160x180:r=30[l];color=c=0xC04040:s=160x180:r=30[r];[l][r]hstack"
still fx-redblue.mp4 "color=c=0xE02020:s=160x180:r=30[l];color=c=0x2020E0:s=160x180:r=30[r];[l][r]hstack"
still fx-holdgb.mp4 "color=c=0xE09020:s=160x180:r=30[l];color=c=0xE02090:s=160x180:r=30[r];[l][r]hstack"
still fx-blue.mp4 "color=c=0x2060C0:s=320x180:r=30"
still fx-box.mp4 "color=c=black:s=320x180:r=30,drawbox=x=130:y=65:w=60:h=50:color=white:t=fill"
still fx-gridline.mp4 "color=c=black:s=320x180:r=30,drawbox=x=0:y=30:w=320:h=4:color=white:t=fill"
still fx-mover.mp4 "color=c=black:s=320x180:r=30[b];color=c=white:s=40x40:r=30[w];[b][w]overlay=x='20+t*100':y=70:eval=frame"
still fx-ramp.mp4 "color=c=gray:s=320x180:r=30,format=gray,geq=lum='X/320*255'" 1
still fx-greensq.mp4 "color=c=0x00FF00:s=320x180:r=30[b];color=c=0x606060:s=60x60:r=30[q];[b][q]overlay=x='100+t*30':y=60:eval=frame" 1

# The optional fixtures: the edit tests' frame-index pictures and chirp (see the top).
STRIPES="geq=lum='if(gt(mod(floor(N/pow(2\,floor(X*9/W)))\,2)\,0)\,220\,30)':cb=128:cr=128"
CHIRP="aevalsrc=exprs='0.25*sin(2*PI*(200*t+100*t*t))':sample_rate=48000"
X264="-c:v libx264 -preset medium -crf 12 -pix_fmt yuv420p -g 15"
if want idx.mp4; then
  # shellcheck disable=SC2086
  "$FF" -nostdin -hide_banner -loglevel error -y -f lavfi -i "color=c=gray:s=180x90:r=30:d=16,format=yuv420p,$STRIPES" \
    -f lavfi -i "$CHIRP:duration=16" -map 0:v -map 1:a $X264 -c:a aac -b:a 192k -ac 1 -ar 48000 "$OUT/idx.mp4"
fi
if want idx2997.mp4; then
  # shellcheck disable=SC2086
  "$FF" -nostdin -hide_banner -loglevel error -y \
    -f lavfi -i "color=c=gray:s=180x90:r=30000/1001:d=16,format=yuv420p,$STRIPES" $X264 -video_track_timescale 30000 \
    "$OUT/idx2997.mp4"
fi
if want skew.mp4; then
  # shellcheck disable=SC2086
  "$FF" -nostdin -hide_banner -loglevel error -y -f lavfi -i "color=c=gray:s=180x90:r=30:d=3,format=yuv420p,$STRIPES" \
    -f lavfi -i "$CHIRP:duration=3.5" -map 0:v -map 1:a $X264 -c:a aac -b:a 192k -ac 1 -ar 48000 "$OUT/skew.mp4"
fi
if want cutout.mkv; then
  "$FF" -nostdin -hide_banner -loglevel error -y \
    -f lavfi -i "color=c=gray:s=180x90:r=30:d=2,format=yuva420p,$STRIPES:a='if(lt(Y\,H/2)\,0\,255)'" \
    -c:v ffv1 -pix_fmt yuva420p "$OUT/cutout.mkv"
fi
if want move.mp4; then
  # shellcheck disable=SC2086
  "$FF" -nostdin -hide_banner -loglevel error -y -f lavfi -i "testsrc2=size=320x180:rate=30:duration=3" \
    -f lavfi -i "sine=frequency=440:sample_rate=48000:duration=3" -map 0:v -map 1:a $X264 \
    -c:a aac -b:a 128k -ac 1 -ar 48000 "$OUT/move.mp4"
fi
if want tone300.m4a; then
  "$FF" -nostdin -hide_banner -loglevel error -y -f lavfi -i "sine=frequency=300:sample_rate=48000:duration=10" \
    -c:a aac -b:a 128k -ac 1 -ar 48000 "$OUT/tone300.m4a"
fi
if want chirp.m4a; then
  "$FF" -nostdin -hide_banner -loglevel error -y -f lavfi -i "$CHIRP:duration=16" -c:a aac -b:a 192k -ac 1 -ar 48000 \
    "$OUT/chirp.m4a"
fi

# ---- test_masks: exact RGB stills (a PNG keeps the colours as given) and an alpha clip
# png <file> <lavfi graph>: one rgb24 frame of the graph as a PNG
png() { "$FF" -nostdin -hide_banner -loglevel error -y -filter_complex "$2,format=rgb24" -frames:v 1 "$OUT/$1"; }
# stack <h|v> <w> <h> <colour>...: the colours as flat pieces of w x h side by side (h) or one above the other (v)
stack() {
  local dir="$1" w="$2" h="$3" g="" i=0 c labels=""
  shift 3
  for c in "$@"; do g="${g}color=c=0x$c:s=${w}x${h}:r=30,format=rgb24[s$i];"; labels="$labels[s$i]"; i=$((i + 1)); done
  printf '%s%s%sstack=inputs=%d' "$g" "$labels" "$dir" "$i"
}
if want mk-bands.png; then png mk-bands.png "$(stack h 80 360 E62828 28C83C 283CDC F0DC3C 808080 141414 FAFAFA C878B4)"; fi
if want mk-greys.png; then png mk-greys.png "$(stack v 640 60 000000 282828 646464 A0A0A0 D2D2D2 FFFFFF)"; fi
if want mk-blue.png; then png mk-blue.png "color=c=0x0000FF:s=640x360"; fi
if want mk-red.png; then png mk-red.png "color=c=0xFF0000:s=640x360"; fi
if want mk-white.png; then png mk-white.png "color=c=0xFFFFFF:s=640x360"; fi
if want mk-grey64.png; then png mk-grey64.png "color=c=0x404040:s=640x360"; fi
if want mk-redsq.png; then png mk-redsq.png "color=c=0xFF0000:s=480x480"; fi
# boxed <w> <h> <colour> <box colour> <x> <y> <box w> <box h>: a lavfi graph of a flat picture with a flat box, rgb24
# (rows above the box, then colour | box | colour, then rows below it)
boxed() {
  local w="$1" h="$2" c="0x$3" b="0x$4" x="$5" y="$6" bw="$7" bh="$8" s="r=30,format=rgb24"
  printf '%s' "color=c=$c:s=${w}x$y:$s[t];color=c=$c:s=${x}x$bh:$s[a];color=c=$b:s=${bw}x$bh:$s[b];" \
    "color=c=$c:s=$((w - x - bw))x$bh:$s[c];[a][b][c]hstack=inputs=3[m];color=c=$c:s=${w}x$((h - y - bh)):$s[u];" \
    "[t][m][u]vstack=inputs=3"
}
if want mk-greenbox.png; then png mk-greenbox.png "$(boxed 640 360 00FF00 FF0000 200 100 240 160)"; fi
if want mk-disc.mkv; then
  "$FF" -nostdin -hide_banner -loglevel error -y -f lavfi \
    -i "color=c=red:s=640x360:r=30:d=1,format=rgba,geq=r='255':g='0':b='0':a='if(lte(hypot(X-320\,Y-180)\,120)\,255\,0)'" \
    -c:v ffv1 -pix_fmt yuva420p "$OUT/mk-disc.mkv"
fi

# ---- test_key: H.264 pictures drawn in BT.601 (lavfi's colours and boxes) and tagged so, all four tags
TAG601="setparams=colorspace=smpte170m:color_primaries=smpte170m:color_trc=smpte170m:range=tv"
OPT601="-colorspace smpte170m -color_primaries smpte170m -color_trc smpte170m -color_range tv"
# keyclip <file> <colour> <w> <h> <seconds> [<drawbox x:y:w:h:colour> ...]
keyclip() {
  local f="$1" c="$2" w="$3" h="$4" d="$5" vf="" b
  shift 5
  for b in "$@"; do IFS=: read -r bx by bw bh bc <<< "$b"; vf="$vf,drawbox=x=$bx:y=$by:w=$bw:h=$bh:c=$bc:t=fill"; done
  # shellcheck disable=SC2086
  "$FF" -nostdin -hide_banner -loglevel error -y -f lavfi -i "color=c=$c:s=${w}x$h:r=30:d=$d,format=yuv420p$vf,$TAG601" \
    -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p $OPT601 "$OUT/$f"
}
if want key-grey.mp4; then
  keyclip key-grey.mp4 0x808080 1080 1920 2 100:300:300:300:white 680:300:300:300:black 100:1000:300:300:red \
    680:1000:300:300:black 730:1050:200:200:white
fi
if want key-blue-p.mp4; then keyclip key-blue-p.mp4 blue 1080 1920 2; fi
if want key-blue-l.mp4; then keyclip key-blue-l.mp4 blue 1280 720 4; fi
if want key-green.mp4; then keyclip key-green.mp4 0x00FF00 1280 720 2 200:200:240:240:red 800:200:240:240:0xB4DCB4; fi
if want key-black.mp4; then keyclip key-black.mp4 black 1280 720 2 500:200:280:280:white; fi
if want key-noisy.mkv; then
  "$FF" -nostdin -hide_banner -loglevel error -y -f lavfi \
    -i "color=0x30C040:s=320x240:r=30:d=0.2,format=yuv444p,noise=alls=60:allf=u+t" -c:v ffv1 "$OUT/key-noisy.mkv"
fi

# ---- test_colorspace: the patch grid, coded with a known matrix and range, tagged with exactly the tags named
CS_PATCHES="FF0000 00FF00 0000FF 00FFFF FF00FF FFFF00 FFFFFF 000000 BF0000 00BF00 0000BF 00BFBF BF00BF BFBF00 BFBFBF \
808080 E0AC69 8D5524 6496DC 3C7828 FF8000 8000C8 008080 FF69B4 28140A 0A1E3C 101010 202020 404040 C8281E C0C0C0 EBEBEB"
# grid <w> <h> <seconds>: a lavfi graph of the 8 x 4 patch grid, rgb24
grid() {
  local w="$1" h="$2" d="$3" g="" rows="" i=0 r c
  read -r -a P <<< "$CS_PATCHES"
  for r in 0 1 2 3; do
    local row=""
    for c in 0 1 2 3 4 5 6 7; do
      g="${g}color=c=0x${P[$i]}:s=$((w / 8))x$((h / 4)):r=30:d=$d,format=rgb24[p$i];"; row="$row[p$i]"; i=$((i + 1))
    done
    g="$g${row}hstack=inputs=8[r$r];"; rows="$rows[r$r]"
  done
  printf '%s%svstack=inputs=4' "$g" "$rows"
}
# tags <space> <primaries> <transfer> <range>: the setparams step and the encoder options for exactly these tags
# ("-": not tagged)
tagstep() { printf 'setparams=colorspace=%s:color_primaries=%s:color_trc=%s:range=%s' \
  "${1/#-/unknown}" "${2/#-/unknown}" "${3/#-/unknown}" "${4/#-/unknown}"; }
tagopts() {
  local o=""
  [ "$1" = - ] || o="$o -colorspace $1"; [ "$2" = - ] || o="$o -color_primaries $2"
  [ "$3" = - ] || o="$o -color_trc $3"; [ "$4" = - ] || o="$o -color_range $4"
  printf '%s' "$o"
}
# The frame's index over the grid's top left corner (x < W/4, y < H/16, above the middles of the top row's patches):
# eight stripes, stripe b grey 220 when bit b of the frame's index is set, grey 30 when not (in RGB, before the coding)
CS_BIT="if(lt(Y\\,H/16)*lt(X\\,W/4)\\,if(mod(floor(N/pow(2\\,floor(X*32/W)))\\,2)\\,220\\,30)"
CS_BAND="format=gbrp,geq=r='$CS_BIT\\,r(X\\,Y))':g='$CS_BIT\\,g(X\\,Y))':b='$CS_BIT\\,b(X\\,Y))',format=rgb24"
# patches <file> <w> <h> <matrix> <range> <codec> <space> <primaries> <transfer> <range tag>
patches() {
  local f="$1" w="$2" h="$3" m="$4" rg="$5" codec="$6" pix=yuv420p enc
  case "$codec" in
    h264) enc="-c:v libx264 -preset medium -crf 4" ;;
    vp9) enc="-c:v libvpx-vp9 -lossless 1 -deadline realtime -cpu-used 8" ;;
    ffv1) enc="-c:v ffv1"; pix=yuva420p ;;
  esac
  # shellcheck disable=SC2046,SC2086
  "$FF" -nostdin -hide_banner -loglevel error -y -filter_complex "$(grid "$w" "$h" 0.6),$CS_BAND,scale=out_color_matrix=$m:out_range=$rg:flags=lanczos+accurate_rnd+full_chroma_int,format=$pix,$(tagstep "$7" "$8" "$9" "${10}")" \
    $enc -pix_fmt $pix $(tagopts "$7" "$8" "$9" "${10}") "$OUT/$f"
}
if want cs-hd.mp4; then patches cs-hd.mp4 1280 720 bt709 tv h264 - - - -; fi
if want cs-709.mp4; then patches cs-709.mp4 1280 720 bt709 tv h264 bt709 bt709 bt709 tv; fi
if want cs-601.mp4; then patches cs-601.mp4 1280 720 bt601 tv h264 smpte170m smpte170m smpte170m tv; fi
if want cs-sd601.mp4; then patches cs-sd601.mp4 720 480 bt601 tv h264 smpte170m smpte170m smpte170m tv; fi
if want cs-sd.mp4; then patches cs-sd.mp4 720 480 bt601 tv h264 - - - -; fi
if want cs-sd709.mp4; then patches cs-sd709.mp4 720 480 bt709 tv h264 bt709 bt709 bt709 tv; fi
if want cs-full709.mp4; then patches cs-full709.mp4 1280 720 bt709 pc h264 bt709 bt709 bt709 pc; fi
if want cs-fullnm.mp4; then patches cs-fullnm.mp4 1280 720 bt601 pc h264 - - - pc; fi
if want cs-partial.mp4; then patches cs-partial.mp4 1280 720 bt601 tv h264 smpte170m - - -; fi
if want cs-vp9.webm; then patches cs-vp9.webm 1280 720 bt601 tv vp9 - - - -; fi
if want cs-cut601.mkv; then patches cs-cut601.mkv 1280 720 bt601 tv ffv1 smpte170m smpte170m smpte170m tv; fi
if want cs-rotsd.mp4; then
  patches cs-rotsd-flat.mp4 848 480 bt601 tv h264 - - - -
  # a quarter turn for display: FFmpeg 6 and later take it as an input option, earlier ones as the rotate tag (each
  # gives the display matrix that ffprobe reports as rotation 90; grep reads all of the help, so no pipe is cut short)
  if "$FF" -hide_banner -h full 2>/dev/null | grep -- '-display_rotation' > /dev/null; then
    "$FF" -nostdin -hide_banner -loglevel error -y -display_rotation:v:0 90 -i "$OUT/cs-rotsd-flat.mp4" -c copy \
      "$OUT/cs-rotsd.mp4"
  else
    "$FF" -nostdin -hide_banner -loglevel error -y -i "$OUT/cs-rotsd-flat.mp4" -c copy -metadata:s:v:0 rotate=90 \
      "$OUT/cs-rotsd.mp4"
  fi
  rm -f "$OUT/cs-rotsd-flat.mp4"
fi
if want cs-grid.png || want cs-grid.jpg; then
  "$FF" -nostdin -hide_banner -loglevel error -y -filter_complex "$(grid 1280 720 0.04)" -frames:v 1 "$OUT/cs-grid.png"
fi
if want cs-grid.jpg; then
  "$FF" -nostdin -hide_banner -loglevel error -y -i "$OUT/cs-grid.png" -q:v 1 "$OUT/cs-grid.jpg"
  want cs-grid.png || rm -f "$OUT/cs-grid.png"
fi
LL709="-c:v libx264 -preset medium -qp 0 -pix_fmt yuv420p -colorspace bt709 -color_primaries bt709 -color_trc bt709 -color_range tv"
SCALE709="scale=out_color_matrix=bt709:out_range=tv:flags=lanczos+accurate_rnd+full_chroma_int,format=yuv420p,$(tagstep bt709 bt709 bt709 tv)"
if want cs-testsrc.mp4; then
  # shellcheck disable=SC2086
  "$FF" -nostdin -hide_banner -loglevel error -y -f lavfi -i "testsrc=size=1280x720:rate=30:duration=0.4" \
    -vf "$SCALE709" $LL709 "$OUT/cs-testsrc.mp4"
fi
if want cs-gridll.mp4; then
  # shellcheck disable=SC2086
  "$FF" -nostdin -hide_banner -loglevel error -y -filter_complex "$(grid 1280 720 0.4),$SCALE709" $LL709 \
    "$OUT/cs-gridll.mp4"
fi
if want cs-green.mp4; then
  # the rectangle covers x 385..895 and y 217..503: inside 30 % to 70 % of the width and height
  "$FF" -nostdin -hide_banner -loglevel error -y -filter_complex "$(boxed 1280 720 1EC83C C83C32 385 217 511 287),scale=out_color_matrix=bt709:out_range=tv:flags=lanczos+accurate_rnd+full_chroma_int,format=yuv420p,$(tagstep - - - -)" \
    -t 0.4 -c:v libx264 -preset medium -crf 4 -pix_fmt yuv420p "$OUT/cs-green.mp4"
fi

# probe <file> <stream> <entries>: the stream's values, comma-separated, in ffprobe's order.
probe() { "$FP" -v error -select_streams "$2" -show_entries "stream=$3" -of csv=p=0 "$OUT/$1"; }
# expect <file> <stream> <entries> <values>
expect() {
  local got
  got="$(probe "$1" "$2" "$3")"
  got="${got%,}"  # newer ffprobe prints a stream's side data (a rotation) as one more, empty, field
  [ "$got" = "$4" ] || { echo "make.sh: $1 $2 is '$got', expected '$4' ($3)" >&2; exit 1; }
}
clips="a.mp4:1280:720:180 b.mp4:1280:720:180 c640.mp4:640:480:150"
if want long.mp4; then clips="$clips long.mp4:1920:1080:600"; fi
for f in $clips; do
  IFS=: read -r n w h frames <<< "$f"
  expect "$n" v:0 codec_name,profile,width,height,pix_fmt,r_frame_rate,nb_frames "h264,High,$w,$h,yuv420p,30/1,$frames"
  expect "$n" a:0 codec_name,profile,sample_rate,channels aac,LC,44100,1
done
expect m.mp3 a:0 codec_name,sample_rate,channels,bit_rate mp3,44100,1,64000
expect gap.m4a a:0 codec_name,profile,sample_rate,channels aac,LC,44100,1
expect tiny.mp4 v:0 codec_name,width,height,pix_fmt,r_frame_rate,nb_frames h264,32,32,yuv420p,10/1,10
for f in fx-white fx-gray64 fx-gray128 fx-pair fx-redblue fx-holdgb fx-blue fx-box fx-gridline fx-mover; do
  expect "$f.mp4" v:0 codec_name,width,height,pix_fmt,r_frame_rate,nb_frames h264,320,180,yuv420p,30/1,60
done
for f in fx-base fx-base2; do
  expect "$f.mp4" v:0 codec_name,width,height,pix_fmt,r_frame_rate,nb_frames h264,320,180,yuv420p,30/1,600
done
expect fx-bars.mp4 v:0 codec_name,width,height,pix_fmt,r_frame_rate,nb_frames h264,240,180,yuv420p,30/1,60
expect fx-gray128p.mp4 v:0 codec_name,width,height,pix_fmt,r_frame_rate,nb_frames h264,180,320,yuv420p,30/1,60
for f in fx-ramp fx-greensq; do
  expect "$f.mp4" v:0 codec_name,width,height,pix_fmt,r_frame_rate,nb_frames h264,320,180,yuv420p,30/1,30
done
for f in fx-white fx-bars fx-ramp; do
  [ -z "$(probe "$f.mp4" a "codec_type")" ] || { echo "make.sh: $f.mp4 has an audio stream" >&2; exit 1; }
done
[ "$(sed -n 1p "$OUT/look.cube")" = "LUT_3D_SIZE 2" ] || { echo "make.sh: look.cube is not a LUT" >&2; exit 1; }
if want idx.mp4; then
  expect idx.mp4 v:0 codec_name,width,height,pix_fmt,r_frame_rate,nb_frames h264,180,90,yuv420p,30/1,480
  expect idx.mp4 a:0 codec_name,profile,sample_rate,channels aac,LC,48000,1
fi
if want idx2997.mp4; then
  expect idx2997.mp4 v:0 codec_name,width,height,pix_fmt,r_frame_rate,time_base,nb_frames \
    h264,180,90,yuv420p,30000/1001,1/30000,480
  [ -z "$(probe idx2997.mp4 a "codec_type")" ] || { echo "make.sh: idx2997.mp4 has an audio stream" >&2; exit 1; }
fi
if want skew.mp4; then
  expect skew.mp4 v:0 codec_name,width,height,r_frame_rate,nb_frames h264,180,90,30/1,90
  expect skew.mp4 a:0 codec_name,sample_rate,channels,duration aac,48000,1,3.500000
fi
if want cutout.mkv; then
  expect cutout.mkv v:0 codec_name,width,height,pix_fmt,r_frame_rate ffv1,180,90,yuva420p,30/1
fi
if want move.mp4; then
  expect move.mp4 v:0 codec_name,width,height,pix_fmt,r_frame_rate,nb_frames h264,320,180,yuv420p,30/1,90
  expect move.mp4 a:0 codec_name,sample_rate,channels aac,48000,1
fi
if want tone300.m4a; then expect tone300.m4a a:0 codec_name,sample_rate,channels aac,48000,1; fi
if want chirp.m4a; then
  expect chirp.m4a a:0 codec_name,profile,sample_rate,channels aac,LC,48000,1
  [ -z "$(probe chirp.m4a v "codec_type")" ] || { echo "make.sh: chirp.m4a has a video stream" >&2; exit 1; }
fi
# test_masks' stills: exact RGB, and the alpha clip
for f in mk-bands mk-greys mk-blue mk-red mk-white mk-grey64 mk-greenbox; do
  if want "$f.png"; then expect "$f.png" v:0 codec_name,width,height,pix_fmt png,640,360,rgb24; fi
done
if want mk-redsq.png; then expect mk-redsq.png v:0 codec_name,width,height,pix_fmt png,480,480,rgb24; fi
if want mk-disc.mkv; then expect mk-disc.mkv v:0 codec_name,width,height,pix_fmt,r_frame_rate ffv1,640,360,yuva420p,30/1; fi
# test_key's pictures: BT.601 limited with all four tags (ffprobe prints them in its order: range, matrix, transfer,
# primaries, before the rate)
T601="tv,smpte170m,smpte170m,smpte170m"
for f in key-grey:1080:1920:60 key-blue-p:1080:1920:60 key-blue-l:1280:720:120 key-green:1280:720:60 \
         key-black:1280:720:60; do
  IFS=: read -r n w h frames <<< "$f"
  if want "$n.mp4"; then
    expect "$n.mp4" v:0 codec_name,width,height,pix_fmt,r_frame_rate,nb_frames,color_range,color_space,color_transfer,color_primaries \
      "h264,$w,$h,yuv420p,$T601,30/1,$frames"
  fi
done
if want key-noisy.mkv; then expect key-noisy.mkv v:0 codec_name,width,height,pix_fmt ffv1,320,240,yuv444p; fi
# test_colorspace's sources: each with exactly its tags (range, matrix, transfer, primaries; "unknown": none)
U="unknown,unknown,unknown"
for f in "cs-hd.mp4:h264,1280,720,yuv420p:unknown,$U" "cs-709.mp4:h264,1280,720,yuv420p:tv,bt709,bt709,bt709" \
         "cs-601.mp4:h264,1280,720,yuv420p:$T601" "cs-sd601.mp4:h264,720,480,yuv420p:$T601" \
         "cs-sd.mp4:h264,720,480,yuv420p:unknown,$U" "cs-sd709.mp4:h264,720,480,yuv420p:tv,bt709,bt709,bt709" \
         "cs-full709.mp4:h264,1280,720,yuvj420p:pc,bt709,bt709,bt709" "cs-fullnm.mp4:h264,1280,720,yuvj420p:pc,$U" \
         "cs-partial.mp4:h264,1280,720,yuv420p:tv,smpte170m,unknown,unknown" \
         "cs-vp9.webm:vp9,1280,720,yuv420p:tv,$U" "cs-rotsd.mp4:h264,848,480,yuv420p:unknown,$U" \
         "cs-cut601.mkv:ffv1,1280,720,yuva420p:$T601" "cs-testsrc.mp4:h264,1280,720,yuv420p:tv,bt709,bt709,bt709" \
         "cs-gridll.mp4:h264,1280,720,yuv420p:tv,bt709,bt709,bt709" "cs-green.mp4:h264,1280,720,yuv420p:unknown,$U"; do
  IFS=: read -r n v t <<< "$f"
  if want "$n"; then
    expect "$n" v:0 codec_name,width,height,pix_fmt,r_frame_rate,color_range,color_space,color_transfer,color_primaries \
      "$v,$t,30/1"
  fi
done
if want cs-rotsd.mp4; then
  "$FP" -v error -select_streams v:0 -show_streams -of json "$OUT/cs-rotsd.mp4" | grep '"rotation": 90' > /dev/null \
    || { echo "make.sh: cs-rotsd.mp4 is not shown turned a quarter (rotation 90)" >&2; exit 1; }
fi
if want cs-grid.png; then expect cs-grid.png v:0 codec_name,width,height,pix_fmt png,1280,720,rgb24; fi
if want cs-grid.jpg; then expect cs-grid.jpg v:0 codec_name,width,height,color_range mjpeg,1280,720,pc; fi
for f in a.mp4 b.mp4 c640.mp4 m.mp3 gap.m4a tiny.mp4$WANT; do
  printf '%-9s %s s, %s bytes\n' "$f" "$("$FP" -v error -show_entries format=duration -of csv=p=0 "$OUT/$f")" "$(stat -c %s "$OUT/$f")"
done
