# Judge adapter protocol, version 1

The judge drives an editor through an **adapter**: a separate process that turns the judge's product-level operations
into calls on one editor build. The judge (`judge/driver.py`) is the client. An adapter can be written in any
language; it needs stdin, stdout, JSON and the editor's own interfaces.

`judge/adapters/v020/adapter.py` is the adapter for v0.2.0's interfaces (its MCP tools over stdio, and the core's
HTTP routes where an operation needs them). A new editor ships its own adapter and runs the same tests with
`python3 -I judge/run.py --adapter "<command>"`.

## Transport

- The runner starts the adapter command once per test, with an empty scratch folder for that test. The adapter's
  current folder is that scratch folder, and its environment has `JUDGE_TEST_SCRATCH=<the scratch folder>` (the
  runner's sweep uses it to find processes left running, see rule 3). The adapter inherits no file descriptor other
  than stdin, stdout and stderr. `run.py --adapter` makes a word of the command that names an existing relative path
  absolute, so `--adapter "node adapters/new.mjs"` works from the folder you run it in.
- With `run.py --as-user <name>` (CI: `zjudge`) the adapter and everything it starts run as that user, with umask
  022 and an environment of exactly `PATH` (the runner's), `LANG`, `HOME` and `TMPDIR` (the scratch folder), `USER`,
  `LOGNAME`, `JUDGE_TEST_SCRATCH`, and `AIVE_FFMPEG` / `AIVE_FFPROBE` when the runner has them. The adapter's command,
  the build and the media must be readable by that user. The scratch folder belongs to the runner (mode 1777): the
  adapter can add files and folders there, but cannot rename or remove the judge's. The hostile inputs the judge
  writes (`observe.craft`) are writable by others, because the editor may save into a project it opened; the
  judge's other files there are not. Files the editor writes for the judge to read
  (exports, saved projects, frames) must be readable by others; its own private files need not be (the judge reads
  those through `t.look`, as that user).
- The judge sends `hello` first and fails the test when the result's `protocol` is not the judge's version (1).
- Requests go to the adapter's **stdin** and responses come from its **stdout**: one JSON object per line, UTF-8.
- The judge sends one request at a time and waits for its response before it sends the next.
- **stdout carries response lines only.** Logs go to stderr. The runner saves stderr as `adapter.stderr` in the test's
  scratch folder.
- When stdin closes, the adapter stops everything it started (as `stop` does) and exits within 30 s.

### Timeouts

The judge waits this long for each response before it fails the operation with `adapter_error` (`driver.py`):

| op | seconds |
|---|---|
| `hello` | 60 |
| `start` | 300 |
| `stop` | 120 |
| `export` | 1800 |
| `poke_agent_tools` | 1800 |
| every other operation | 600 |

After stdin closes, the judge waits 30 s for the adapter to exit, then kills it. The runner also ends the whole test
after its `TIMEOUT` (600 s unless the test sets another).

Request:

```json
{"id": 7, "op": "trim_clip", "args": {"clip": "c1", "in_frame": 30, "out_frame": 120}}
```

Response, success:

```json
{"id": 7, "ok": true, "result": {}}
```

Response, failure:

```json
{"id": 7, "ok": false, "error": {"code": "product_error", "message": "...", "product_code": "media_offline"}}
```

| `error.code` | Meaning |
|---|---|
| `unsupported` | The adapter does not implement this operation. A test that needs it fails. |
| `bad_request` | The arguments do not fit the operation (missing field, wrong type). |
| `product_error` | The editor answered the operation with an error or a refusal. `message` is the editor's text. `product_code` is its machine-readable code, when it gives one. |
| `adapter_error` | The adapter itself failed: the editor did not start, crashed or did not answer in time. |

A request with an unknown `op` gets `unsupported`. Unknown fields in `args` are ignored, so a later version of the
judge can add optional fields to an operation without breaking older adapters.

### Ports

Any result may carry `"ports": [int]`: TCP ports the editor started listening on during that operation (a server it
starts on first use, for example). A port opened during an operation that answered with an error goes in the next
result that succeeds (`stop`'s included), so it is reported once in every case. The judge adds them to the ports of
`start`, and the runner checks that every one is closed after `stop`.

## Rules for every adapter

1. **Everything stays in the scratch folder.** `start` receives `scratch`, an absolute path to an empty folder that
   the adapter owns until `stop`. The editor's home, settings and data folders, and its temporary files, all go
   inside it. On v0.2.0 that means `HOME`, `USERPROFILE`, `XDG_CONFIG_HOME`, `TMPDIR` and the data folder. The
   editor must never see the user's own settings or data.
2. **Free ports only.** Every port the editor listens on is picked free at start. Never use the editor's default
   port: the user's own editor may be running on it.
3. **Stop only your own processes.** `stop` ends every process the adapter started, by exact process id, and no
   other. After the test, the runner also ends (by exact process id) any process left whose environment has a value
   inside the scratch folder (`JUDGE_TEST_SCRATCH`, or the editor's sandbox folders), and fails the test's "nothing
   left running" check if it finds one. A process that removes those values from its environment is not found.
4. **No sound and no downloads.** Every Chromium or Electron launch passes `--mute-audio`. The adapter downloads
   nothing, and it **starts the editor so that the editor downloads nothing**, whatever operation a test sends
   (`poke_agent_tools` calls every agent tool): every model or helper program the editor would fetch on first use is
   either switched off or named by a setting that points at a file that does not exist, so the feature refuses
   instead of fetching. Never point such a setting at the user's own copy. On v0.2.0: `AIVE_CLIP_DISABLE=1`, and
   `AIVE_WHISPER_BIN` / `AIVE_WHISPER_MODEL` name files in the sandbox that are never made (as the FFmpeg matrix does).
   The graphics add-on is never installed through the editor (that downloads it): a test that needs it gets the
   judge's copy in `start`, headless shell included, so the editor never fetches a browser (see "Motion graphics").
   The same holds for speech recognition: a test that needs it gets the judge's recogniser in `start` (`whisper`: a
   whisper.cpp `whisper-cli` and its model, pinned and checked by the judge), and the adapter points the editor at
   those files instead of the missing ones, so the editor transcribes and fetches nothing (see "Sound"). Without
   `whisper` the settings name missing files, as above.
   The judge checks this rule: the runner traces the network calls of the adapter and everything it starts (strace)
   and fails the test's "nothing was downloaded" check on a TCP connect to another computer, a DNS lookup or a send to
   another computer, also when the network is down and the call failed (`judge/README.md`, "Write a test").
5. **No private shortcuts.** The adapter uses the interfaces a user or an AI client has (tools, HTTP routes, files the
   editor documents). It does not read or write the editor's internal state behind its back. One operation is the
   exception on purpose: `add_host_outside` plays an attacker who edits the editor's files (see "File surface
   and network computers").

## Identifiers, tracks and time

- Asset, clip and job ids are opaque strings that the adapter returns. The judge passes them back unchanged.
- Tracks are named from the bottom: `v0` is the base video track, `v1` composites over it, and so on. `a0`, `a1`, ...
  are the audio tracks. A new project has at least `v0`; `add_track` adds one. `place_clip` or `move_clip` on a track
  that does not exist answers `bad_request` and changes nothing.
- Timeline positions and source ranges are integer **frames** at the project's frame rate. `out_frame` is exclusive,
  so a clip with `in_frame` 30 and `out_frame` 120 is 90 frames long. `render_frame` takes **seconds**.
- Paths are absolute. A test may send, on purpose, a string that is not a local absolute path where an operation takes
  a path (`import_media`, `load_project`, `save_project`, `import_otio`, `export_otio`, `export`, `apply_lut`, the `font`
  of `add_text`): an http or data: URL, a network path such as `//host/share/a.mp4` or `\\host\share\a.mp4`, a
  relative path, or a path with a `..` segment. The adapter passes it to the editor unchanged and does not normalize
  it; the test checks what the editor does with it.

## Files the editor saves, and the hostile copies made from them

The judge makes its hostile inputs (a project or OTIO file with a URL, a network path, a `../` identifier, filter
text in a colour or a number) by text substitution in a file the editor itself saved with `save_project`, `save` or
`export_otio`: it needs no knowledge of the format. That works when the saved file holds the values the test gave
the editor as plain text or JSON values: media, LUT and font paths as given, the asset, clip and text identifiers
the adapter returned, text colours as given, and some numbers exactly once. A format that does not (one that stores
paths relative to the project, encodes the file, or renames identifiers) is allowed: the checks on an input that
cannot be made are then recorded as **not applicable**, each listed by name with the replacement counts, never as
failed and never as passed. `run.py --strict` turns them into failures. The adapter does not change saved files.

## Operations

An operation whose result is `{}` may return more fields; the judge ignores fields it does not know.

Every operation can answer the errors in the table under "Transport": `bad_request` for arguments of the wrong shape,
`product_error` when the editor refuses, `adapter_error` when the editor is not started or does not answer. Where an
operation has refusals of its own, its "Errors" line below names them; the tests check that a refusal happens and
what it leaves behind, never its message or code.

### Lifecycle

| op | args | result |
|---|---|---|
| `hello` | `{}` | `{"protocol": 1, "adapter": str, "ops": [str]}`: the operations this adapter implements. Works before `start`. |
| `start` | `{"build": str, "scratch": str, "graphics_addon"?: {"root": str, "browser": str}, "whisper"?: {"bin": str, "model": str}}` | `{"product": {"name": str, "version": str}, "ports": [int]}`: `build` is the editor checkout or build to run. `ports` lists every TCP port the editor listens on; the runner checks that they are closed after `stop`. `graphics_addon` (see "Motion graphics" below): the graphics add-on the judge gives this editor; left out, the editor has none. `whisper` (see "Sound" below): the speech recogniser the judge gives this editor, `bin` a whisper.cpp `whisper-cli` program and `model` its model file (absolute paths, read-only); the editor transcribes with them; left out, the editor has no speech recogniser (rule 4). Errors: `bad_request` for a `graphics_addon` or `whisper` of another shape; `adapter_error` when `whisper`'s `bin` is not a program or its `model` not a file. |
| `stop` | `{}` | `{}`: every process the adapter started has exited. |

### Media and timeline

| op | args | result |
|---|---|---|
| `import_media` | `{"path"}` | `{"asset": id}` |
| `place_clip` | `{"asset", "track"?, "start_frame", "in_frame", "out_frame"?}` | `{"clip": id}`: the source range `[in_frame, out_frame)` placed at `start_frame` on `track`. `track` left out means `v0`. `out_frame` left out (or null) means the end of the source. |
| `trim_clip` | `{"clip", "in_frame"?, "out_frame"?}` | `{}`: new source range. The clip's start position does not change. |
| `move_clip` | `{"clip", "start_frame", "track"?}` | `{}` |
| `split_clip` | `{"clip", "at_frame"}` | `{"clips": [left id, right id]}`: `at_frame` counts from the clip's start on the timeline. |
| `remove_clip` | `{"clip"}` | `{}` |
| `set_speed` | `{"clip", "speed", "ripple"?}` | `{}`: constant speed, 1 = normal. See "Speed and time" below for its range, `ripple` and its refusals. |
| `insert_clip` | `{"asset", "track"?, "start_frame", "in_frame"?, "out_frame"?}` | `{"clip": id}`: as `place_clip`, but first every clip of `track` that starts at or after `start_frame` moves right by the new clip's length, so nothing is overwritten. Errors: `product_error` when the track is locked. |
| `cut_range` | `{"clip", "start_frame", "end_frame"}` | `{}`: removes the clip's part `[start_frame, end_frame)`, counted in frames from the clip's start on the timeline; the rest of the clip and every later clip on its track close up (they move left by what was removed). On a clip that is slowed, ramped or at a constant speed other than 1x, 2x, 3x or 4x, each end of the cut moves to where its source frame starts playing; a piece left on either side keeps at least one frame, and a side too short to hold one source frame goes with the cut: no gap is ever left. Errors: `product_error` when the clip's track is locked. |
| `ripple_delete` | `{"ranges": [{"track", "start_frame", "end_frame"}]}` | `{}`: removes the timeline frames `[start_frame, end_frame)` of each listed track and closes each gap (the later clips on that track move left). The same range on several tracks removes the same frames from each; a range end inside a slowed or ramped clip moves as for `cut_range`, so a range shorter than one source frame can remove nothing. Errors: `bad_request` for a track that does not exist; `product_error` when a listed track is locked (nothing changes). |
| `set_track` | `{"track", "name"?, "locked"?, "muted"?, "hidden"?}` | `{}`: changes the track's settings as the user does; only the fields sent change. `name` is its label (the State's `name`; the track keeps its `track` name). `muted`: its sound is left out of the mix. `hidden`: its picture is left out of the composite. `locked`: its clips are protected: an edit that would add, remove, move, trim or change a clip on it, directly or by a ripple (an insert, a cut, a ripple delete, a freeze, a speed change, a reverse, the change of a linked clip), is refused and changes nothing, its undo history included; renaming, unlocking or removing the track and an fps change stay allowed, and so does a speed change or freeze with ripple `none` that leaves the track alone. Errors: `bad_request` for a track that does not exist, a flag that is not a boolean, or no field. |
| `remove_track` | `{"track"}` | `{}`: removes the track and its clips (a locked one too). The tracks above it of its kind take the names below (removing `v1` makes `v2` the new `v1`). Errors: `product_error` for the last video track. |
| `link_clips` | `{"clips": [id, id, ...]}` | `{}`: links the clips (a picture and its sound on another track, for example): they move and split and are removed together, and a speed change, a freeze or a reverse of one applies to the others that play the same moment (see "Speed and time"). Errors: `bad_request` for fewer than two clips. |
| `unlink_clip` | `{"clip"}` | `{}`: unlinks the clip and the rest of its link group. |
| `set_transition` | `{"clip", "kind", "frames"}` | `{}`: a transition of `frames` frames entering `clip` from the clip before it on its track: the clip and every later clip on the track move left by `frames`, so the two overlap by that much and cross there. `kind`: `dissolve` and `fade` are the ones the tests use. Errors: `product_error` for a track's first clip, and when the track is locked (the clip would move). |
| `set_markers` | `{"markers": [{"frame", "name"?}]}` | `{}`: replaces the timeline's markers (an empty list removes them). |
| `apply_effect` | `{"clip", "effect", "amount"?, "params"?, "color"?, "enabled"?, "effect_id"?}` | `{"effect": id or null}`: adds the effect `effect` (see "Effects" below) at the end of the clip's effects. With `effect_id` (an effect of this clip) it changes that effect in place instead: `amount`, `params` and `color` are replaced by what is sent, and `enabled` alone (false: bypassed, kept but not rendered; true: on again) changes nothing else. Values are passed on unchanged: the editor clamps a value outside its range (get_state then shows the clamped value) or refuses it. Errors: `bad_request` when `enabled` is not a boolean or a field has the wrong type; `product_error` when the editor refuses: an effect it does not have, a param the effect does not have, an amount or a colour for an effect that takes none, a colour it cannot read or the effect does not take, an `effect_id` the clip does not have, a clip on a locked track (`set_track`). |
| `remove_effect` | `{"clip", "effect"}` | `{}`: removes the effect (an id from `apply_effect`). Errors: `product_error` when the clip does not have it, or its track is locked. |
| `reorder_effect` | `{"clip", "effect", "to_index"}` | `{}`: moves the effect to position `to_index` of the clip's effects (0 is the first, rendered first); a position past the end puts it last. One undo step. Errors: `product_error` when the clip does not have it. |
| `add_track` | `{"kind": "video" \| "audio"}` | `{"track": name}`: a new track: a video track composites over every video track there is (it is the highest `v` name), an audio track is the next `a` name. Errors: `bad_request` for another kind. |
| `apply_colour` | `{"clip", "brightness"?, "contrast"?, "saturation"?, "gamma"?, "temperature"?, "tint"?, "hue"?}` | `{}`: a colour grade. Neutral values: brightness 0, contrast 1, saturation 1, gamma 1, temperature 0, tint 0, hue 0. Errors: `bad_request` when no colour field is given or a value is not a number; `product_error` when the clip does not exist or its track is locked (`set_track`). |
| `apply_lut` | `{"clip", "path"}` | `{}`: applies the colour look-up table (a `.cube` file) at `path` to the clip. Errors: `bad_request` when `clip` or `path` is missing or not a string; `product_error` when the clip does not exist, or the path is not a local file the editor may read: a URL or another protocol, a path on a network computer the user has not allowed (that computer then waits for the user, see `list_hosts`), or a file of the editor's own allowed list in any spelling; and when the clip's track is locked (`set_track`). |
| `add_text` | `{"clip", "text", "style": {}}` | `{"text": id}`: a text overlay on the clip, shown for the whole clip. `style` fields, all optional: `position` (a placement name such as `bottom`, `top`, `center`), `x`, `y` (0..1), `font` (a font name or a font file path), `font_size`, `color`, `outline_color`, `outline_width`, `shadow_color`, `shadow_x`, `shadow_y`, `box` (bool), `box_color`, `box_border`. A colour is a name (`yellow`), `#rrggbb`, `#rrggbbaa`, `0xRRGGBB` or `name@alpha` (`white@0.5`). The adapter passes every value on unchanged, also one of another type: tests send hostile values on purpose, and the editor accepts or refuses each. |
| `make_proxy` | `{"asset"}` | `{}`: makes the editor's lower-resolution working copy of the asset (in the editor's own folders). Errors: `bad_request` when `asset` is missing; `product_error` when the asset does not exist or its media is offline, for example while it waits for its network computer. |
| `thumbnail` | `{"asset", "time"}` | `{"path": str or null}`: makes a still image of the asset at `time` seconds (the asset's own frame, whatever the timeline composites over it), where the editor keeps such images; read as its image format is read (a JPEG as BT.601 full range), it shows the asset's colours. Errors: `bad_request` when `asset` is missing or `time` is not a number; `product_error` as for `make_proxy`. |
| `set_project` | `{"width"?, "height"?, "fps"?}` | `{}`: the output canvas: the size and frame rate of every export and rendered frame. See "The canvas" below. |
| `undo`, `redo` | `{}` | `{}` |
| `get_state` | `{}` | a **State** (below) |

State:

```json
{
  "canvas": {"width": 1280, "height": 720, "fps": 30},
  "length_frames": 90,
  "assets": [{"id": "...", "path": "/abs/a.mp4", "offline": false, "waiting_host": null}],
  "tracks": [
    {"track": "v0", "name": "V1", "locked": false, "muted": false, "hidden": false, "clips": [
      {"id": "...", "asset": "...", "start_frame": 0, "in_frame": 30, "out_frame": 120, "length_frames": 90,
       "speed": 1, "ramp": false, "transition": null, "graphics": [], "texts": [{"id": "...", "text": "Hello"}],
       "effects": [{"id": "...", "effect": "vignette", "enabled": true, "amount": 1.5}],
       "volume": 1, "audio_offset_frames": 0,
       "bleeps": [{"id": "...", "start": 0.94, "end": 1.48, "sound": "beep", "volume": 0.8, "mute": true}],
       "audio_effects": [{"id": "...", "effect": "pitch", "enabled": true, "params": {"semitones": 12}}]}
    ]}
  ],
  "markers": [{"frame": 30, "name": "early"}],
  "graphics": {"renderer": "builtin", "ready": true}
}
```

A track's `name` is its label (`set_track`), and `locked`, `muted` and `hidden` its settings. A clip's `ramp` says
whether it plays a speed ramp (`set_speed_ramp`; its `speed` is then 1), and its `transition` is the transition that
enters it (`{"kind", "frames"}`, see `set_transition`) or null. `markers` are the timeline's markers in frame order,
each with its `name` or null. A clip's `blend_mode` is its blend mode (`set_blend_mode`; `normal` when none was set),
its `mask` its shape mask (`set_mask`: `{"shape", "x", "y", "w", "h", "rotation", "feather", "roundness", "invert"}`,
the values as the editor keeps them, clamped) or null, and `adjustment` is true for an adjustment layer
(`add_adjustment_layer`; its `asset` is null). A clip's `volume` is its sound level (`set_volume`), its
`audio_offset_frames` how far its sound is slid against its picture (`set_audio_offset`), its `bleeps` its bleeps and
its `audio_effects` the effects on its sound in the order they run (see "Sound" below). An adapter whose State has no
such field leaves it out; the tests that need it then fail.

### The canvas

- Before any `set_project`, the canvas is the editor's default. v0.2.0 starts at 1920x1080, 30 fps, and while the
  canvas has never been set it takes the size of the first media imported or placed. Tests do not depend on the
  default: they call `set_project` before they import or place anything, and a canvas set that way does not change
  when media of another size is imported or placed.
- Changing `fps` keeps every placed clip at the same time in seconds: its `start_frame`, `in_frame` and `out_frame`
  are scaled by new fps / old fps. On v0.2.0, a clip at `start_frame` 60 with source frames 30-120 at 30 fps is at
  `start_frame` 120 with source frames 60-240 after `set_project(fps=60)`.
- Changing `width` or `height` does not move or change clips.

`length_frames` of a clip is its length on the timeline (after speed). `length_frames` of the State is the end of the
last clip. Tracks are listed from `v0` up, then `a0` up, with their clips in timeline order. An asset is `offline`
when the editor cannot use its file now: it is missing, or it waits for the user to allow its network computer.
`waiting_host` is that computer's name (lower case, as in `list_hosts`) while the asset waits for it, else null. An
adapter whose State has no such field leaves it out; the tests that need it then fail. A clip's `graphics` lists the
ids of the motion graphics shown over it (`add_graphic` with `clip`), and the State's `graphics` says which renderer
the user chose for motion graphics and whether it can render now (see "Motion graphics" below). A clip's `texts` are
its text overlays (`add_text`: their ids and texts), and its `effects` are its visual effects in the order they are
rendered: each one's id, its name (see "Effects"), whether it is on (`enabled` false: bypassed), and, when it has
them, its `amount`, its `params` (an object of numbers) and its `color`. A colour that is a hex colour is reported as
`0xRRGGBB` or `#rrggbb` (any case, red first): the tests read its value (observe.hex_colour) and compare it with the
colour they gave, so a colour given as `#e02020` must come back as that red in either spelling. An adapter whose editor
stores colours another way converts them to one of these (v0.2.0's adapter passes on the editor's own `0xRRGGBB`).
Values the editor clamped are shown clamped.

### Effects

The effects a clip can have (`apply_effect`), as the product names them, with their controls: the range of the
`amount` (a number) and of each param (`params`, numbers), and what they do. A value outside its range is clamped. The
tests use these names and ranges; another editor's adapter maps them to its own.

| effect | controls | what it does |
|---|---|---|
| `blur` | amount 0..100 (the blur radius, sigma in pixels) | Gaussian blur |
| `sharpen` | amount 0..5 | unsharp-mask sharpening |
| `detail` | amount 0..1 | contrast-adaptive sharpening |
| `denoise` | amount 0..30 | noise reduction over space and time |
| `sepia`, `grayscale`, `edges`, `invert` | none | a warm brown tone; no colour; an edge drawing; every colour inverted |
| `vignette` | amount 0..2.5 (1 the classic strength, 0 none) | darker corners |
| `posterize` | amount 2..32 (levels per channel) | flat colour levels |
| `pixelate` | amount 2..100 (block size factor) | mosaic blocks |
| `chromakey` | params similarity 0.01..1, blend 0..1, despill 0..1; `color` the key colour (`0xRRGGBB`, `#rrggbb`, or `auto`) | a green or blue screen made transparent. How it treats brightness is not specified: a key on a neutral grey may or may not also remove white and black (`colorkey` is the key that keeps them) |
| `colorkey` | params similarity 0.01..1, blend 0..1; `color` as chromakey | a flat colour made transparent: it compares the whole colour, brightness too, so a key on a grey keeps white and black |
| `lumakey` | params threshold 0..1, tolerance 0..1, softness 0..1; `color` only `auto` | black or white made transparent |
| `exposure` | amount -3..3 (stops), params black -1..1 (the black point; kept below the white point) | camera-style exposure |
| `vibrance` | amount -2..2 | saturation that lifts dull colours more than saturated ones |
| `colorhold` | params similarity 0.01..1, blend 0..1; `color` the colour kept (hex, not `auto`) | every other colour turned grey |
| `grain` | amount 0..100 | film grain, new on every frame |
| `glow` | amount 0..1, params radius 1..100 (pixels) | a bloom around bright areas |
| `rgbsplit` | amount 0..50 (pixels), params angle 0..360 (degrees, 0 horizontal) | red and blue pushed apart |
| `lens` | amount -1..1 (k1: positive barrel, negative pincushion), params k2 -1..1, fill 0..1 (1: zoomed so that no corner is left empty, the default; 0: the uncovered corners stay transparent) | a lens warp around the middle |
| `trails` | amount 0.8..0.99 (the decay per source frame) | a fading echo of what moves |

Only the keys (and `lens` with fill 0) make pixels transparent. A clip smaller than the canvas, or of another aspect,
is fitted in the middle, and the rest of the canvas is transparent: the tracks below show there, also under any
effect.

A key's `color` `auto` is resolved when the effect is added: the editor samples the clip's background (the border of
its frames) and keeps that colour, so get_state shows the colour it found, never `auto` (for `lumakey`, `auto` sets
`threshold` to the background's brightness instead).

| op | args | result |
|---|---|---|
| `detect_key_colour` | `{"clip"}` | `{"color": hex, "confidence": number}`: the colour `auto` would key on this clip (as `0xRRGGBB` or `#rrggbb`, red first) and the share 0..1 of the sampled border that has it (near 1: a flat screen). It reads the clip's source as an export does (its colour tags; see "Exports"), and changes nothing. Errors: `product_error` when the clip does not exist or has no picture. |

### Compositing

How a clip's picture is laid over the tracks below it, as the user sets it: its blend mode, its shape mask, its
transform (position, scale, rotation, opacity) and its animation (keyframes), its crop, and adjustment layers.

| op | args | result |
|---|---|---|
| `set_blend_mode` | `{"clip", "mode"}` | `{}`: how the clip's picture combines with the composite of the video tracks below it. Modes, by the W3C compositing names (a base colour b below, the layer's colour s, each 0..1): `normal` (plain layering, the default), `multiply`, `screen`, `overlay`, `darken`, `lighten`, `color-dodge`, `color-burn`, `hard-light`, `soft-light`, `difference`, `exclusion` as the W3C formulas, and `add` (min(1, b + a s), with a the layer's opacity). The result is mixed with the base by the layer's opacity and alpha (its keys, mask, letterbox), so only its visible part blends. Only the picture blends: the clip's own texts draw normally on top. Clips joined by a transition (`set_transition`) blend as one, so the mode is set on every clip of the run. One undo step. `mode` is passed on unchanged. Errors: `product_error` for a mode it does not have, an adjustment layer, a clip that does not exist, a locked track. |
| `set_mask` | `{"clip", "shape"?, "x"?, "y"?, "w"?, "h"?, "rotation"?, "feather"?, "roundness"?, "invert"?}` | `{}`: a shape mask in the clip's own picture (after its crop and fit; it moves, scales and turns with the clip's transform): only the part inside the shape shows (`invert` true: the part outside), the tracks below show elsewhere, and the clip's letterbox stays transparent either way. `shape`: `rect`, `ellipse`, `linear` (a half plane: the line through x, y at `rotation`; it keeps the side above the line at rotation 0), `mirror` (a band of height `h` through x, y at `rotation`), or `none` (removes the mask). `x`, `y`: the centre, as fractions of the picture's width and height (0.5, 0.5 by default; v0.2.0 keeps -0.5..1.5); `w`, `h`: the size as fractions of the picture's width and height (a new `rect` or `ellipse` is a centred square or circle half the picture's short side; v0.2.0 keeps 0.01..2); `rotation`: degrees clockwise (kept as the same angle in -180..180); `feather`: the width of the shape's soft edge, 0..1 of the picture's short side (0: crisp): across the edge the clip goes from 90 % shown to 10 % shown over `feather` times the short side, and the edge is centred on the shape's outline (v0.2.0's edge is a Gaussian; its exact profile between those points is not part of the protocol); `roundness`: a rect's corner radius 0..1; `invert`. Only the fields sent change; a value out of range is clamped. It multiplies the clip's alpha, so it combines with keys and alpha media. On an adjustment layer it limits where the layer's look applies (in canvas space). One undo step. Errors: `bad_request` when no field is given or one has the wrong type; `product_error` for a shape it does not have, a clip that does not exist, a locked track. |
| `set_transform` | `{"clip", "x"?, "y"?, "scale"?, "rotation"?, "opacity"?}` | `{}`: places the clip's picture after it is fitted to the canvas: `x`, `y` move it by fractions of the canvas's width and height (0: centred, + right and down), `scale` (1: fitted), `rotation` (degrees clockwise), `opacity` 0..1. Only the fields sent change. One undo step. Errors: `bad_request` when no field is given or one is not a number; `product_error` when the editor refuses (a clip that does not exist, a locked track). |
| `set_keyframes` | `{"clip", "property", "keyframes": [{"frame", "value", "ease"?}]}` | `{}`: animates one of the clip's `set_transform` fields over time. `property`: `x`, `y`, `scale`, `rotation` or `opacity`, with the same units. `frame` is a whole number counted from the clip's start (0: its first frame), `value` the field's value there, `ease` how the value moves into that keyframe from the one before: `linear` (the default), `hold` (a step), `ease`, `easeIn`, `easeOut`. The list replaces that property's keyframes (an empty list removes them). The tests use `linear` keyframes on the clip's first and last frames, and one `easeOut` keyframe whose motion is judged halfway through it. The clip's mask moves and scales with the animated picture, and the clip stays transparent where it was (outside its picture and its mask). One undo step. Errors: `bad_request` for another property, a `keyframes` that is not a list, a frame that is not a whole number of 0 or more, a value that is not a number, an ease of another name; `product_error` when the editor refuses (a clip that does not exist, a locked track). |
| `crop_clip` | `{"clip", "x", "y", "width", "height"}` | `{}`: crops the clip's picture to the rectangle of its source pixels with its top left corner at x, y (a rectangle that runs off the picture's right or bottom edge is moved in), which is then fitted to the canvas like a whole picture. One undo step. Errors: `bad_request` for a missing or non-number field; `product_error` when the editor refuses. |
| `add_adjustment_layer` | `{"track"?, "start_frame", "frames"}` | `{"clip": id}`: an adjustment layer: a clip with no media, `frames` long from `start_frame` on `track` (left out: the highest video track), whose colour, effects and mask apply to the composite of every video track below it while it plays. `apply_effect`, `apply_colour`, `set_mask`, `move_clip` and `remove_clip` work on it as on a clip; `set_blend_mode` is refused. Errors: `bad_request` for a track that does not exist or a field of the wrong type; `product_error` when the editor refuses. |

`clear_effects` removes a clip's blend mode, mask and transform too.

### Speed and time

A clip's speed, its speed ramp, a freeze, a reverse and smooth slow motion, as the user sees them. Positions and
lengths are frames, as everywhere; a ramp's points are in seconds of the source.

**Ripple.** When a clip's length changes (`set_speed`, `set_speed_ramp`, `clear_speed_ramp`, `clear_effects`,
`freeze_frame`), `ripple` says what moves from its old end:

- `track` (what the editor does when `ripple` is not sent): the later clips on its track, and on the tracks of the
  linked clips that change with it, move by its change in length (sped up, they pull in and leave no gap; slowed
  down, they move out and do not overlap; gaps and transition overlaps after it are kept). A later clip's own linked
  clips on other tracks (its sound, a recording linked to it) move with it, together with the clips after them. The
  other tracks (titles, music) and the markers stay.
- `all`: every other track's clips that start at or after the old end move too, and so do the markers there. A clip
  that straddles that point stays, and so does a clip that would break the edit by moving: one entering a clip that
  stays through a transition, one butted to it, one that would run into it, one linked to a clip that stays.
- `none`: nothing moves; the clip's length changes in place.

A ripple that would start a clip before frame 0, run a clip into another, break a transition or split a linked pair
is refused and changes nothing, and so is a speed-up that leaves the clip no longer than a transition into or out of
it. Clips linked to the clip that play the same moment (its sound on another track, another recording of the same
moment, a copy of the same footage showing the same frame at the same time) take the same speed or ramp (another
recording moved by its offset to the same moment); a linked clip of other footage (a cutaway), the other half of a
split pair and a freeze's still keep theirs. A linked sound's J-cut head or L-cut tail (its part before or after the
picture) changes length with it; one that would run into another clip or start before frame 0 is cut to fit, and one
that gets shorter leaves a short silence. Called on a linked sound, the change applies to its picture, which keeps
its start. One undo step undoes the change and its ripple.

| op | args | result |
|---|---|---|
| `set_speed` | `{"clip", "speed", "ripple"?}` | `{}`: constant speed 0.25..4 (1 = normal): the clip's length becomes its source range / speed, and the timeline ripples. Replaces a ramp. Errors: `bad_request` for a `ripple` of another name; `product_error` for a refused ripple and a locked track. |
| `set_speed_ramp` | `{"clip", "preset"?, "points"?, "audio"?, "ripple"?}` | `{}`: a speed that changes over the clip: a `preset` (below) spread over the clip's source range, or `points`, `[{"src": seconds of the source, "speed": 0.1..10}]`, linear between them and constant before the first and after the last. The clip's length becomes the time its source range takes at that speed, and the timeline ripples. `audio`: `stretch` (the sound follows the curve, its pitch kept) or `mute` (silent, and the linked sound too). With neither `preset` nor `points` only the audio of the ramp the clip has changes (nothing moves). Errors: as for `set_speed`, and a ramp on a pair whose sound plays at another constant speed than its picture (`smooth_slow_motion`). |
| `clear_speed_ramp` | `{"clip", "ripple"?}` | `{}`: removes the ramp: the clip and its linked sound play at 1x again, and the timeline ripples. Errors: as for `set_speed` (`bad_request` for a `ripple` of another name; `product_error` for a refused ripple and a locked track). |
| `clear_effects` | `{"clip", "ripple"?}` | `{}`: removes every effect of the clip (its speed and ramp, its visual effects, its colour and volume); a change of length ripples as above. Errors: as for `set_speed`; a clip on a locked track is refused whether or not its length would change. |
| `freeze_frame` | `{"clip", "at_frame", "frames", "ripple"?}` | `{"still": id or null}`: holds the frame the clip shows `at_frame` frames after its start (its speed, ramp and trim respected) for `frames` frames: the clip is split there and a still clip (that exact frame as a picture, with the clip's look and no sound: where it plays it shows the clip's own frame with its effects, mask and transform, not the composite of the tracks over it) goes between the halves. Whether the look is in the still's picture file or kept on the still clip (v0.2.0 keeps the clip's effects, mask and transform on the still clip, and its file holds the frame as the source shows it) is the editor's choice; the look must show once where the still plays; the held frame is also the right half's first. Ripple `track`: the clip's track and its linked clips' tracks move right by the still (a linked sound is split at the same point and is silent under the still); `all` as above; `none`: the still overwrites the clip from that frame for up to `frames` frames, never past its end, and nothing moves. `at_frame` 0 puts the still before the clip; at or past its end the last frame inside its source range is held. Freezing a linked sound clip freezes its picture. `still` is the adapter's word; the tests find the still in get_state. Errors: `product_error` for a sound clip with no linked picture, a freeze point inside the next clip's transition overlap, a refused ripple, a locked track. |
| `reverse_clip` | `{"clip", "audio"?, "linked"?, "wait"?}` | `{"job": id or null}`: plays the clip's source range backwards: the editor makes a reversed copy (every frame once, in reverse order; its sound reversed, or silent with `audio` `mute`) and the clip plays it at the same place and length. The linked clips that play the same moment are reversed with it (`linked` false: only this clip); a linked sound that started before the picture (a J-cut) then ends after it (an L-cut) and the other way round, which is refused when it would run into another clip. Called on a reversed clip, it plays the original forwards again (no new copy), with a trim made since mapped back. One undo step. `wait` false: it returns at once with the job that makes the copy (`jobs`, `cancel`; a canceled copy leaves no file and changes nothing, then or later); `job` is null when `wait` is true. Errors: `product_error` for those refusals and a locked track; a track locked, or a spot taken, while the copy is made ends the job with status `error`, the project unchanged, and it stays so once the track is unlocked or the spot is free again (no copy is placed or left later). |
| `smooth_slow_motion` | `{"clip", "mode"?, "wait"?}` | `{"job": id or null}`: for a clip slowed below 1x at a constant speed: the editor makes a copy with in-between frames (`mode` `blend`, the default: blended frames, the source's own frames in turn with frames between them that mix the two on either side; `flow`: motion-interpolated ones) and the clip plays it at 1x, at the same place and length, its sound slowed with its pitch kept. A linked sound of the same footage and span is moved onto the copy too; another linked clip keeps its speed and place, and a later speed change keeps the ratio between them. `wait` as for `reverse_clip`. Errors: `product_error` at 1x or faster, on a ramped clip, on a locked track. |

The presets of `set_speed_ramp`, by the product's names: `montage` (pulses: 1x, 3x, 0.5x, 3x, 0.5x, 1x), `hero` (3x,
with 0.3x for the middle tenth), `bullet` (real time, 0.15x through the middle, real time again), `jump_cut` (real
time with an 8x jump through the middle fifth), `flash_in` (from 8x down to real time by 30 %), `flash_out` (real time
until 70 %, then up to 8x at the end). Another editor's adapter maps them to its own.

### Output and jobs

| op | args | result |
|---|---|---|
| `export` | `{"path", "wait": true, "lossless"?: bool}` | a **Job**. With `wait` true, the call returns when the export has finished. With `wait` false, it returns at once with a running job. `lossless` true: the user's lossless quality (see "Exports"). See "Exports" below. |
| `jobs` | `{}` | `{"jobs": [Job]}`: the exports, and the copies `reverse_clip` and `smooth_slow_motion` make. |
| `cancel` | `{"job"}` | `{"canceled": bool}`: `canceled` true when the editor accepted the cancel of the running job. The answer may come before the job's work has stopped (v0.2.0 answers once its bake has stopped), so the judge does not take it as proof: from the answer on, the job ends `canceled` in `jobs` and never turns `done`, and a canceled copy (`reverse_clip`, `smooth_slow_motion`) never changes the project or leaves a file, also later. The tests look at the State and the editor's files at once and again after one and a half times as long as a full bake of the same media takes, and 2 s more (measured on a clean bake of another span of it). |
| `render_frame` | `{"time", "path"}` | `{"path"}`: one composited frame of the timeline at `time` seconds, written as a PNG at `path` (RGB: the colours an export shows there). A time past the end shows the last frame. |
| `render_preview` | `{}` | `{"path": str or null}`: renders the editor's preview of the whole timeline, where the editor keeps it (the user's playback); `render_frame` may then be served from it, and must show the same frames. `path` is the preview's file (a new file each time; readable by others, as an export is, and a format an export may have), or null when the editor does not say: its picture may be smaller than the canvas, and its sound is the timeline's mix, with the clips' bleeps and audio effects, as an export's. |

Job: `{"job": id or null, "status": "running" | "done" | "error" | "canceled", "path": str or null, "error": str or
null, "fraction": number or null}`.

#### Exports

- The path's extension names the container. `.mp4` is an MP4 file with H.264 video and AAC audio. The judge's tests
  use `.mp4` only. For an extension the editor cannot write, the adapter answers `product_error` (the editor refused)
  or `bad_request`.
- The video is the project canvas: its width, height and fps (not the size or rate of the media placed on it), with
  square pixels. It covers the timeline from frame 0 to the State's `length_frames`.
- There is an audio stream when any clip on the timeline has audio. It is stereo, whatever the sources' channel
  layouts (mono, stereo, quad, 5.1).
- Colour: the video is BT.709 at limited range, and all four of its colour tags (matrix, primaries, transfer, range)
  say so, so every player shows the same colours. Each source is read as players read it: by its colour tags (a
  matrix or a range tag alone counts), and where a tag is missing, an untagged HD picture (720 lines or more, counted
  in the coded picture, before any rotation) as BT.709, an SD one as BT.601, untagged VP9 as BT.601, full range with
  no matrix as BT.601 (as a JPEG), limited range unless tagged full; a picture with no matrix at all (a PNG) as RGB. So
  a source coded the way its tags (or, untagged, the rule) say exports with its true colours. The same holds for the
  copies the editor makes of a source (a reversed or slowed copy, a still) and for a motion graphic: each exports with
  the colours of what it was made from.
- `lossless` true: the user's lossless quality: the video is coded without loss from the editor's own composite
  (v0.2.0: H.264 at quality 0, in `yuv420p`), so the judge reads the compositing's own values, not codec noise. An
  editor that has no lossless export answers `product_error`, and the tests that need it fail.
- With `wait` true, `status` is the editor's own: `error` or `canceled` (with the editor's text in `error`) when the
  editor reports one, even when it left a file at the path; `done` only when the editor reports no error and the file
  is there.

### Sound

A clip's sound: its level, its slide against its picture, its bleeps and its audio effects. Times of bleeps are
**seconds of the clip's source** (the asset), so a bleep stays on its word whatever happens to the clip.

| op | args | result |
|---|---|---|
| `set_volume` | `{"clip", "volume"}` | `{}`: the clip's sound level, 1 unchanged, 0 silent. A picture at 0 whose linked sound clip plays the same footage leaves that clip to carry the sound (see `apply_audio_effect`). |
| `set_audio_offset` | `{"clip", "frames"}` | `{}`: slides the clip's sound against its picture by `frames` (positive: later, an L-cut; negative: earlier, a J-cut; 0: back in place). Its bleeps move with the sound. |
| `add_bleep` | `{"clip", "start"?, "end"?, "at_seconds"?, "duration"?, "sound"?, "volume"?, "mute"?}` | `{"bleep": id, "clip": id}`: one bleep: while it plays, the clip's own sound is muted (`mute`, true by default) and the bleep's sound plays (`sound`: `beep`, the default, a 1 kHz tone; `quack`, `squeak`, `boing`, `honk`; `volume` its level, 0.8 by default). Its window is `[start, end)` in source seconds, or `at_seconds` (a moment of the timeline) and `duration` (timeline seconds, 0.5 by default). A bleep belongs to its clip and follows it through every edit: a move, a trim (a window trimmed off is not heard; trimmed back, it is again), a split (each half keeps the bleeps of its own range), a speed change (the window plays faster or slower; the bleep's sound keeps its pitch and lasts the window), a sound slide, save and load. The beep lasts its window; the other sounds play their natural length (`quack` about 0.3 s) even past a shorter window. A muted track silences its bleeps too. `clear_effects` keeps the bleeps. One undo step. Errors: `product_error` for a window outside the clip (`at_seconds` past its end, for example). |
| `set_bleep` | `{"clip", "bleep", "start"?, "end"?, "sound"?, "volume"?, "mute"?}` | `{}`: changes one bleep (only the fields sent). A window shorter than 0.04 s is made 0.04 s; one that runs past the asset's end ends there. One undo step. Errors: `product_error` for `start` at or after `end`, a bleep the clip does not have. |
| `remove_bleep` | `{"clip", "bleep"}` | `{}`: removes one bleep; the clip's sound plays there again. One undo step. |
| `remove_bleeps` | `{"clips"?: [id]}` | `{}`: removes every bleep of the clips (every clip when `clips` is left out). One undo step. |
| `get_transcript` | `{"asset"}` | `{"words": [{"text", "start", "end"}] or null}`: the asset's word-level transcript (source seconds, each word as the recogniser wrote it, in the order spoken), or null when the editor has none. The editor makes one with its speech recogniser when an operation needs it (`bleep_words`, a dry run included); it may also make one earlier. Making a transcript is never an edit, whenever it is made: it adds no step to the undo history and keeps the redo history (v0.2.0's first `bleep_words` dry run breaks this: a known bug, see `bleep_words`). Without the judge's recogniser (`start`'s `whisper`, rule 4) it has none unless it can make one without a download. |
| `bleep_words` | `{"clips"?: [id], "words"?: [str], "use_default_list"?: bool, "include_mild"?: bool, "sound"?, "dry_run"?: bool}` | `{"hits": [{"clip", "bleep", "text", "start", "end"}]}`: bleeps every swear word of the clips' transcripts (a built-in list, `include_mild` adding mild words, `words` adding the user's own, `use_default_list` false using only those), each as a bleep on the clip that carries the asset's sound (a linked sound clip when the clip given is a silent picture), its window the word's padded a little; re-running replaces the bleeps the clips' previous `bleep_words` run made (whether it keeps bleeps added by hand with `add_bleep` is unspecified); `dry_run` true only reports the hits (`bleep` null) and changes nothing: not the State, nor the undo or the redo history, the dry run that makes a transcript included (making a transcript is not an edit; v0.2.0 adds an undo step there that changes nothing visible and drops the redo history, a known bug of that release and of this line: judge/README.md, "Known bugs"). A user's word matches a transcript word when the two are the same with case ignored and every character that is not a letter or a digit left out ("PENCIL," matches "pencil"); a word matches whole, never a part or a stem ("pen" does not match "pencil", nor "rive" "river", nor "apples" "apple"). A hit is one transcript word: `text` as the recogniser wrote it, `start` and `end` its times in the transcript (source seconds); `bleep` the bleep made for it, whose window holds the word's. The bleeps are `add_bleep`'s defaults but for `sound` (`beep` when left out). One undo step. Errors: `product_error` when a clip's asset has no transcript and none can be made (no speech recogniser: rule 4); nothing is changed then. |

#### Audio effects

The effects on a clip's sound (`apply_audio_effect`), by the product's names, with their params' ranges. They run in
the clip's source time, after the bleeps' mutes and before its speed: a speed change does not change an EQ's frequency
or a pitch shift (a voice pitched +12 stays pitched at 2x), and a bleep's sound is never processed by them. A value
outside a range is clamped (get_state shows the clamped value), a switch (0|1) is rounded to 0 or 1, a param the
effect does not have and an effect the editor does not have are refused. Each effect keeps the clip's sound starting
when it did (no delay added) and lasting the clip's length, and stops at its end (an echo's or a reverb's tail does
not run past it). Another editor's adapter maps the names to its own.

| effect | params (range) | what it does |
|---|---|---|
| `enhance_voice` | strength 0..1, denoise 0\|1, normalize 0\|1, floor -90..-20 (dBFS) | one-step voice polish: rumble cut, noise reduction, de-essing, EQ, gentle compression, -16 LUFS with a true peak at most -1.5 dBTP |
| `noise_reduction` | amount 0..1, floor -90..-20, heavy 0\|1 | steady noise taken down (the floor is measured from the clip when not given) |
| `highpass` | frequency 20..500 (Hz) | removes what is below (24 dB per octave) |
| `lowpass` | frequency 1000..20000 | removes what is above |
| `de_esser` | amount 0..1, frequency 0..1 | tames sibilance |
| `gate` | threshold -80..-10 (dB), reduction 0..60 (dB), attack 0.1..100, release 10..2000 (ms) | turns the sound down between phrases |
| `declick` | threshold 2..10 | removes clicks |
| `eq_presence` | gain -12..12 (dB), frequency 2000..8000 | a peak around 4 kHz |
| `eq_warmth` | gain -12..12, frequency 100..400 | a peak around 200 Hz |
| `eq_custom` | low, mid, high -12..12 | shelves at 100 Hz and 8 kHz, a peak at 1 kHz |
| `bass_boost` | gain 0..18, frequency 40..250 | a low shelf |
| `compressor` | threshold -60..0, ratio 1..20, attack 0.1..200, release 10..2000, makeup 0..24 | evens loud and quiet |
| `limiter` | ceiling -12..0 (dBFS), drive 0..24, release 1..1000 | no peak over the ceiling |
| `normalize` | target -30..-10 (LUFS), even 0..1 | the clip's integrated loudness to the target |
| `pitch` | semitones -12..12 | pitch shifted, speed and length kept |
| `chipmunk` | semitones 3..12 | pitch up, formants shifted |
| `deep` | semitones -12..-2 | pitch down, formants shifted |
| `robot` | tone 0..2 | a monotone metallic voice |
| `echo` | delay 50..1000 (ms), decay 0.05..0.9 | repeats |
| `reverb` | room 0..1, mix 0..1 | reflections |
| `telephone` | grit 0..1 | a phone's band |
| `megaphone` | grit 0..1 | a horn's band, driven |
| `underwater` | muffle 200..1500 (Hz), wobble 0..1 | muffled and wobbling |

| op | args | result |
|---|---|---|
| `apply_audio_effect` | `{"clip", "effect", "params"?: {name: number}, "enabled"?: bool, "effect_id"?}` | `{"effect": id or null, "clip": id or null}`: adds the effect to the clip's sound. A new effect takes its place in the chain by kind: `enhance_voice`, then cleanup (`noise_reduction` .. `declick`), tone (the EQs, `bass_boost`), dynamics (`compressor`, `limiter`, `normalize`), then the voice changers; `reorder_audio_effect` moves one. With `effect_id` it changes that effect in place (its params replaced by those sent), and `enabled` alone (false: bypassed, kept but not heard; true: on again) changes nothing else. On a picture whose sound a linked clip carries (the picture at volume 0, `set_volume`), the effect goes on that linked clip, also through either half of a split linked pair (each picture half reaches its own sound half); `clip` is the clip that has it. One undo step. Errors: `product_error` for an effect the editor does not have or a param the effect does not have, an adjustment layer (no sound), an `effect_id` the clip does not have. |
| `remove_audio_effect` | `{"clip", "effect"}` | `{}`: removes it (found on the clip or on the linked clip that carries its sound). One undo step. Errors: `product_error` when neither has it. |
| `reorder_audio_effect` | `{"clip", "effect", "to_index"}` | `{}`: moves it to position `to_index` (0: runs first; past the end: last). One undo step. |
| `enhance_voice` | `{"clip", "strength"?, "noise_reduction"?: bool, "normalize"?: bool}` | `{"effect": id or null, "clip": id or null}`: adds the clip's `enhance_voice` (strength 0.7 when not sent), or changes the one it has (only what is sent; `noise_reduction` false: no noise reduction, `normalize` false: the clip's own level, a limiter still keeps it from clipping). Goes on the linked clip that carries the sound, as `apply_audio_effect`. One undo step. |

### Projects and interchange

| op | args | result |
|---|---|---|
| `save_project` | `{"path"}` | `{}`: save as `path`. `path` becomes the project's current file. |
| `save` | `{}` | `{}`: the plain Save: writes the project to its current file, the one it was last saved as (`save_project`) or opened from (`load_project`). A project that has no current file is refused (`product_error`). A refused `load_project` or `import_otio` does not change the current file. |
| `load_project` | `{"path"}` | `{"notice": str or null}`: opens the project. `notice` is what the editor tells the user about it (offline media, for example). |
| `export_otio` | `{"path"}` | `{}`: the timeline as an OpenTimelineIO file. |
| `import_otio` | `{"path"}` | `{"missing": [str]}`: opens the OTIO file as the project. `missing` lists the media paths the editor could not find. |

### File surface and network computers

| op | args | result |
|---|---|---|
| `http_get` | `{"route", "query": {}, "anonymous"?: bool}` | `{"status": int, "content_type": str, "body_length": int, "body_sha256": str, "body_b64": str, "truncated": bool, "headers"?: {name: value}}`: `anonymous` true sends the request without the authentication the editor's interface adds (the tests check that it is refused). `headers` are the answer's headers, names in lower case. Errors: `bad_request` when `anonymous` is not a boolean. |
| `list_hosts` | `{}` | `{"approved": [host], "pending": [host], "outside": [host]}`: `approved` the computers the user allowed; `pending` those that offline media or a refused path names, waiting for the user; `outside` the entries of the editor's allowed list that it did not make itself (see `add_host_outside`): not used until the user keeps them. |
| `approve_host` | `{"host"}` | `{}`: allows media from network computer `host`, as the user does in the editor's window (Allow, or Keep for an entry listed outside). No agent tool may be able to do this. The editor stores the name in lower case; a name that cannot be a network computer is refused (`product_error`). |
| `revoke_host` | `{"host", "only_if_outside"?}` | `{"removed": bool}`: removes `host` from the allowed computers, as the user does in the editor's window. With `only_if_outside` true it removes the entry only while it is still listed outside (the Remove of a Keep question): an entry the user kept meanwhile stays, and `removed` is false. For a host that is not in the list, `removed` is the editor's own answer (v0.2.0 answers true); the tests do not depend on it. Errors: `bad_request` when `host` is missing or `only_if_outside` is not a boolean; `product_error` when the window refuses the name (one that cannot be a network computer); `adapter_error` when the window's interface cannot be reached (on v0.2.0 the web shell did not start or did not take its key). |
| `add_host_outside` | `{"host", "forged"?}` | `{"files": [path], "secrets": [str]}`: adds `host` to the editor's allowed list by editing the editor's files, not through its window: what another program or an agent with file access could do. With `forged` true the entry claims an approval it never had (for example a stamp made with a key that is not the editor's). The editor must treat it as `outside`. The result names the files that hold the allowed list and its secrets, and the secret texts (the key that stamps approvals), so a test can check that no answer of the editor holds them and that no agent operation changes the files. The adapter may create the secret when the editor has none yet, as an attacker could; call it before any approval. Errors: `bad_request` when `host` is missing or `forged` is not a boolean; `adapter_error` when the editor is not started or its files cannot be written. Never `product_error`: the editor is not asked. |
| `recheck_media` | `{}` | `{}`: the editor reads its list of allowed computers again and re-checks offline media. |

`http_get` requests the editor's file surface: the HTTP routes the editor's own interface uses to read media. The
adapter adds the authentication that the editor's interface uses. The judge tests what is served, not how a client
signs in. Routes, by their v0.2.0 names (another editor's adapter maps each one to its own route):

- `/file`: the bytes of the file named by `query.path`. Only files that the project uses or that the editor made may
  be served.
- `/frames`: decoded video frames of the file named by `query.path`: `from` (the first frame), `count`, `w`, `h` (the
  size of each frame) and `fps`. The same files as `/file` may be read.
- `/peaks`: the audio levels (a waveform overview) of the file named by `query.path`. The same files as `/file`.
  `query.buckets`: how many levels, a whole number 16..8192 (1600 when it is left out). The answer is `4 x buckets`
  bytes, `application/octet-stream`, with `Access-Control-Allow-Origin: *` (the editor's window reads it from any
  origin): one little-endian float32 per bucket, in time order. The file's first channel's samples (n of them) are cut
  into `buckets` buckets of floor(n / buckets) samples (the samples left over at the end are not used); each value is
  the loudest |sample| of its bucket divided by the loudest bucket's (at least 1e-6), at most 1. A file rewritten in
  place gets its new levels, also when it keeps its size. Refusals: 401 without the interface's authentication
  (`anonymous`), 403 for a file `/file` would not serve (the answer does not repeat its path), 400 for a bucket count
  outside 16..8192 or that is not a whole number written in decimal digits, 422 for a file with no sound.

`body_b64` holds at most the first 262144 bytes of the body (`truncated` says whether there was more).
`body_length` and `body_sha256` always describe the whole body.

`host` is a computer name as it appears in a network path (`nas` in `//nas/share/clip.mp4`), in lower case. The
judge's tests use names under the reserved `.invalid` domain, which never resolve.

### Motion graphics

A motion graphic is code an AI agent writes: a TSX module whose default export is a React component that uses
[Remotion](https://www.remotion.dev)'s API (`remotion`, and `react`). The editor renders it to video. Which renderer
does that is the user's setting, made in the editor's window, never by an agent:

- `builtin`: the editor's own renderer (v0.2.0: ZedMix's renderer, in the app's Electron; the default).
- `addon`: the **graphics add-on**, Remotion 4.0.481 itself and the Chrome headless shell it renders in. A user
  installs it from the editor's window, which downloads it. The judge never asks the editor to install it: `start`'s
  `graphics_addon` gives the editor the add-on's files, which the judge installed before the run (README, "The
  graphics add-on"): `root` is a folder whose `node_modules` holds Remotion 4.0.481's packages (`remotion`,
  `@remotion/bundler`, `@remotion/renderer`, `react`, `react-dom` and what they need, as
  `judge/fixtures/graphics-addon/package-lock.json` pins them), and `browser` is the Chrome for Testing headless shell
  that Remotion 4.0.481 tests with (149.0.7790.0, pinned in `judge/fixtures/graphics-addon/headless-shell.json`). The
  adapter starts the editor so that it uses these files as its installed add-on (v0.2.0: `AIVE_REMOTION_ADDON=<root>`
  and `AIVE_REMOTION_BROWSER=<browser>`, which a source checkout honours; another adapter may copy them where its
  editor keeps its add-on, inside the scratch folder). Without `graphics_addon` the editor has no add-on, as for a
  user who never installed it. The files are read-only; the editor must not need to write there.

| op | args | result |
|---|---|---|
| `set_graphics_renderer` | `{"renderer": "builtin" \| "addon"}` | `{}`: chooses the renderer, as the user does in the editor's window (v0.2.0: Help, Graphics add-on, Graphics renderer). Errors: `bad_request` for another value; `product_error` when the window refuses it; `adapter_error` when the window's interface cannot be reached (v0.2.0: the web shell, started on first use as for `approve_host`; its port comes back in `ports`). |
| `add_graphic` | `{"code"?: str, "template"?: str, "props"?: {}, "clip"?: id, "duration_s"?: number}` | `{"graphic": id or null, "clip": id, "asset": id or null}`: renders a motion graphic with the chosen renderer and adds it. Exactly one of `code` (the TSX module, sent unchanged: tests send hostile code on purpose) and `template` (a built-in graphic: `title`, a title card whose `props.title` is its text). `props` are the component's props. With `clip`, the graphic is shown over that clip for the clip's whole length, and `graphic` is its id (in the clip's `graphics` in the State). Without it, the graphic is a clip of its own, `duration_s` seconds long, added at the end of `v0`; `graphic` is then null. `clip` is the clip that shows it, and `asset` the project asset that holds the rendered graphic (null when the editor keeps it in no asset). That asset's file (its `path` in the State) must be readable by others, as an export is. Errors: `bad_request` when neither or both of `code` and `template` are given, or a field has the wrong type; `product_error` when the editor refuses or the render fails: the renderer cannot run, the add-on is missing on the `addon` setting, the code imports what a graphic may not, or the graphic loads media it may not. The tests check that a refusal happens and what it leaves behind (no graphic, no asset, no file, nothing contacted), never its message. |

The State's `graphics` is `{"renderer": "builtin" | "addon", "ready": bool}`: the user's choice, and whether
`add_graphic` can render with it now (false while the `addon` setting has no add-on, or the renderer cannot run on
this computer). An adapter whose editor has no renderer setting leaves it out, and answers `unsupported` for
`set_graphics_renderer`; the tests that need them then fail.

Every graphic is rendered muted (no sound reaches the speakers, and the rendered graphic has no audio stream), and the
renderer gives the graphic no network: the only computer its page may reach is this one at `127.0.0.1` or
`localhost` (the add-on's own server runs there), and no request may make the renderer open a network path or a file
the graphic names. The page keeps the browser's same-origin policy: it cannot read the answer of a server of another
origin (another port of `127.0.0.1` included) that gives it no cross-origin permission, and it cannot read a file of
this computer by its `file://` URL.

### The command-line installer

The editor's command-line installer (this tree: `npx zedmix`, v0.2.0: `npx` and its own package name; the v0.2.0 adapter runs the
`bin` program of the build's `packages/skill-installer` with node) installs the editor's AI skill (`add`) and moves what an earlier release left in a
user's AI-client configuration over to the current one (`migrate`). It works on the files of a home folder, so the
judge gives it a **world**: a folder in the test's scratch folder with a home folder, project folders and the files in
them, made by the adapter as the editor's user (with `run.py --as-user` the installer runs as that user, and must be
able to rewrite, rename and remove a user's own files there).

| op | args | result |
|---|---|---|
| `cli_world` | `{"root", "files": {path: entry}}` | `{}`: makes the folder `root` (absolute, inside the test's scratch folder, not there yet) and in it, for each relative `path` (`/`-separated plain names), the entry: `{"text": str}` a file with that text (UTF-8, exactly, line ends included), `{"link": target}` a symbolic link, or `{"dir": true}` a folder; each may have `"mode"` (permission bits, set after everything is made). Missing parent folders are made. Errors: `bad_request` when `root` is not inside the scratch folder or is there already, an entry's path is below a `link` entry (it would be made through the link), or an entry or path has another shape; nothing is made outside `root`. |
| `cli` | `{"args": [str], "cwd", "home", "appdata"?, "path"?: [folder], "input"?: str, "tty"?: bool}` | `{"exit": int, "output": str, "capped": bool}`: runs the installer with `args` in the folder `cwd`, with its home folder at `home` (`HOME`, `USERPROFILE`, and `XDG_CONFIG_HOME` at `<home>/.config`), `APPDATA` at `appdata` (default `<home>/AppData/Roaming`), its data folder and temporary files in the editor's sandbox, and `PATH` exactly the `path` folders (none: no program can be found). `input` goes to its stdin; with `tty` true it runs on a new terminal instead, and each line of `input` is typed once the installer has printed something and waits. `exit` is its exit code (-9 when it did not end within 120 s and was killed); `output` is what it printed (stdout and stderr, or what the terminal showed). The adapter keeps a long output only up to a limit of its own (the v0.2.0 adapter: 1 MiB): at that limit it ends the installer (`exit` -9) and `capped` is true, else `capped` is false. Once the installer has exited, the adapter reads what is left of its output for a short while (the v0.2.0 adapter: 2 s), then ends every process that still holds its output or its terminal (in its session or not), so `cli` returns even when the installer leaves a process behind. Every path is absolute and inside the test's scratch folder. Errors: `bad_request` for a path outside it or a field of another type; `adapter_error` when the installer cannot be found or started. |

The tests check the world's files after each run (through `t.look`), and the exit code; they never check what the
installer printed for its wording, only that a dry run names the files it would change or leave alone. Which release's
names the installer is graded against (the skill it installs, the configuration it migrates) is the runner's input,
`run.py --release`, never an adapter's answer.

### What an AI agent is offered

| op | args | result |
|---|---|---|
| `agent_tools` | `{}` | `{"tools": [{"name": str, "read_only": bool}], "instructions": str}`: every tool the editor offers an AI agent (on v0.2.0 its MCP tools), and the instructions it gives the agent. Errors: `adapter_error` when the editor is not started or does not list its tools. Never `product_error`. |
| `poke_agent_tools` | `{}` | `{"called": int, "refused": int}`: calls every agent tool once with empty arguments; answers and refusals are only counted. It may change the project (a tool that starts a new project, for example), so tests call it last. A tool that refuses, fails or does not answer within the adapter's limit for one tool (v0.2.0: 120 s) counts in `refused`, not as an error of the operation. No tool may download anything (rule 4). Errors: `adapter_error` when the editor is not started or does not list its tools. |
| `transcript` | `{}` | `{"texts": [str]}`: every text the editor answered through this adapter since `start`: tool results and errors, and the bodies of `http_get` and of the window's routes (images left out). Tests search it for secrets that must never reach an agent. Errors: none of its own; before `start` it answers an empty list. |

## Adding operations

A batch of judge tests that needs a new operation adds it to this file and to `driver.py`, and adds it to the
adapters. An existing operation's arguments and result keep their meaning. New optional arguments and new result
fields are allowed. An adapter that does not have a new operation yet answers `unsupported`, and the tests that need
it fail.
