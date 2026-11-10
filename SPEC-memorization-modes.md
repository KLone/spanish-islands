# Spec: Sheet-driven islands + memorization modes (incl. Driving)

Hand-off for Claude Code. Extends the existing pipeline in `code/` (`generate_audio.py`, `generate_playlist.py`) and `player.html`. Keep what works (Google TTS via Keychain key, ffmpeg concat, segment cache, PWA offline caching); change the source of truth and add modes.

---

## 1. Goal

Memorize every island the way actors learn lines: Kirk must be able to (a) say his line when he hears the other person's cue, (b) say the cue when he hears his line, and (c) perform a whole scene from memory. Practice happens mostly **while walking** (player on iPhone, earbuds) and **while driving** (CarPlay, one MP3 per island).

---

## 2. Source of truth: the Google Sheet

Sheet: **Language Islands** — `https://docs.google.com/spreadsheets/d/1tF1nY0rZuojjOMGBlouzPOvHx9J7Yl2iV4-Pe6OFMf0/edit`

`sentences.json` is replaced by the sheet. The old Q/A card format is retired.

### Tab `Islands` (gid `101`) — one row per spoken line

| Col | Name | Meaning |
|---|---|---|
| A | Island | Island name, e.g. `Getting Coffee`. Rows of one island are contiguous; sheet order = island order. |
| B | Section | Sub-island ("beat"), e.g. `1. Saludo`, `Core 1`. Unit of learning. |
| C | Line | Line number within the island (1..n). |
| D | Speaker | `Kirk` = the learner. Anyone else (Andrea, Mesero, Agente…) = partner. |
| E | Spanish | Text to synthesize. Primary version (Panama-first where regional). |
| F | English | Translation; used for English-cue mode and on-screen. |
| G | Region | Region of col E when it's region-specific (`PA`), else blank. |
| H | Variant | Full alternate Spanish line for another region, else blank. |
| I | Variant Region | Region of col H (`MX`). |
| J | Notes | Line notes. Values starting with `Stage direction:` are **not spoken**. Everything here is display-only. |

The sheet holds **content only**. Learning progress is tracked in the player (§6) and never written back to the sheet.

Tab `Notes` (gid `103`: Island, Type, Spanish, English, Explanation) and tab `Planned` are out of scope for audio. Optional later: Notes rows with Type=`Frame` as extra flashcards.

### Getting the data locally

New script `code/sync_sheet.py`:
- Default: read `data/islands.csv` (Kirk downloads the `Islands` tab via File → Download → CSV).
- Optional `--fetch`: download `https://docs.google.com/spreadsheets/d/<ID>/export?format=csv&gid=101` (works only if the sheet is link-shared; fail with a clear message otherwise).
- Output `data/islands.json`: list of islands → sections → lines, each line with a stable `line_id` = `{island_num:02d}-{island_slug}-{line:02d}` (island_num = order of first appearance; slug = kebab-case of col A).
- Validate: no empty Spanish/English, Speaker present, line numbers contiguous per island. Print a summary (islands, sections, lines, Kirk lines).
- `--region MX`: substitute col H for col E wherever col I == `MX` (produces a Mexico-flavored build). Default build uses col E.

---

## 3. Audio segments

- One clip per line per language: ES and EN. Partner lines and Kirk lines use **different Spanish voices** so it sounds like a conversation (e.g. keep `es-US-Neural2-C` for Kirk; pick a contrasting voice for partners — verify names with the TTS voices list). English voice as today.
- **Cache by content hash**, not by position: filename `seg-<sha1(text|voice|rate)[:12]>.mp3` in `code/audio/segments/`. Editing a line in the sheet therefore regenerates only that line; reordering costs nothing. Keep a manifest `line_id → {es, en, es_duration_s, en_duration_s}` in `data/segments.json` (measure durations with ffprobe).
- Speaking rates: keep current (ES 0.80, EN 0.90). Expose as config.
- Small non-spoken assets generated once with ffmpeg: `lead_in.mp3` (see Driving), `end_tone.mp3`, `section_tick.mp3` (very soft 150 ms tick, optional).

---

## 4. Modes

Gap length is computed per line: `gap = max(MIN_GAP, FACTOR × duration_of_the_line_Kirk_must_produce)`, where duration is the Spanish clip length. `MIN_GAP = 2.0 s`. Factors are config values.

| # | Mode | Sequence per line (within a section) | Factor |
|---|---|---|---|
| 1 | **Listen** | every line ES, in order, short fixed pause (0.6 s) | — |
| 2 | **Shadow** | line ES → gap (repeat it aloud) | 1.2 |
| 3 | **Run lines** (main drill) | partner line ES → *gap* → Kirk line ES (confirmation). Partner lines just play. If Kirk has two lines in a row, each gets its own gap. | 1.5 |
| 4 | **English cue** | Kirk line EN → *gap* → Kirk line ES. Partner lines play in ES for context. | 1.75 |
| 5 | **Reverse** | Kirk line ES → *gap* → partner line ES (learn the questions). | 1.5 |
| 6 | **Off book** | No audio. Screen shows section title + speaker names only; tap to reveal each line. | — |
| 7 | **Driving** | Baked MP3 per island — see §5. | 2.0 |

Section boundaries: short English announcement "Section two: Lo mejor" (TTS, EN voice) or the soft tick, configurable.

### Playlist output (`playlist.json`)

Extend the existing entry format rather than replacing it, so the player change is incremental:

```json
{
  "island": "Getting Coffee",
  "island_num": 1,
  "section": "Bebidas",
  "mode": "runlines",
  "stem": "01-getting-coffee-bebidas",
  "segments": [
    {"text": "¡Buenos días! ¿Qué le sirvo?", "audio": "code/audio/segments/seg-ab12….mp3",
     "lang": "es", "role": "partner", "line_id": "01-getting-coffee-01", "gap_after": 0.6},
    {"text": "", "audio": null, "lang": null, "role": "gap", "line_id": "01-getting-coffee-02", "gap_after": 3.4},
    {"text": "Buenos días. Me da un cold brew mediano, por favor.", "audio": "…", "lang": "es",
     "role": "kirk", "line_id": "01-getting-coffee-02", "gap_after": 0.8}
  ]
}
```

- `gap_after` = silence the player waits after the segment. A `role: "gap"` segment carries the line's English text in a `hint` field (shown only if Kirk taps "hint").
- Remove the old fixed `PAUSE_SEC` baking for these modes; the player handles gaps (lets Kirk tweak factors in-app without regenerating).
- Keep old `recall`/`shadow` entries working until the new modes are verified, then retire them.

---

## 5. Driving mode (CarPlay)

Problem: over Bluetooth/CarPlay the first 1–3 s of playback is clipped while the audio route wakes up. Within one continuously playing file, nothing is clipped (silent gaps are fine).

Output: **one MP3 per island**, baked with ffmpeg: `islands/<slug>/audio/<NN>-<slug>-driving.mp3`.

Structure:
1. **Lead-in:** 2.0 s pink noise at low level — `anoisesrc=color=pink:amplitude=0.02:duration=2` with a 0.3 s fade-in/out. Not digital silence (some stacks treat silence as "not playing" and don't wake).
2. **Sacrificial announcement (EN):** "Island one: Getting Coffee." If the lag eats part of it, nothing important is lost.
3. 1.0 s pause.
4. For each section: EN announcement "Section: Bebidas" → Run-lines sequence (mode 3) with factor **2.0** (attention is split while driving) → 1.5 s pause.
5. **End tone:** 0.5 s soft sine (e.g. 660 Hz, amplitude ≤ 0.1, faded) so Kirk knows the island ended.

Also:
- Gaps are real silence baked into the file (`anullsrc`), matching sample rate/channels of the TTS clips to avoid concat glitches (resample everything to a single format first, e.g. 24 kHz mono, then concat, then encode once).
- Loudness-normalize the final file (`loudnorm`, target ≈ −16 LUFS) so it's audible over road noise.
- ID3 tags: title = `NN · Island name (Driving)`, album = `Spanish Islands — Driving`, track = NN. CarPlay shows these.
- Make the driving MP3s available in the player (a "Driving" list that plays the baked file) **and** as plain files Kirk can AirDrop to the Music/Files app.

---

## 6. Player changes (`player.html`)

- Mode picker: Listen, Shadow, Run lines, English cue, Reverse, Off book, Driving. (Existing Recall/Shadow/Listen/Cue buttons can be remapped.)
- Pick island → pick section (or "whole island"). Plus a **Review mix** (see Progress tracking below).
- Honor `gap_after`; gap-factor slider (0.75×–2.5×) stored in localStorage.
- **Auto-rewind on resume:** when playback resumes after a pause > 2 s, seek back ~3 s (or restart the current segment) so Bluetooth wake-up lag doesn't clip it.
- **Media Session API**: set title/artist/artwork and play/pause/next/previous handlers so lock-screen, earbud and CarPlay controls work (next/previous = next/previous section).
- **Progress tracking, per section, stored only on the phone** (localStorage; no Google auth, nothing written to the sheet):
  - After a section finishes in Run lines, English cue or Reverse mode, show three large buttons usable while walking: **Again** (struggled), **OK**, **Solid**.
  - Store per section `{section_key, last_run, rating, interval_days, due_date}`. `section_key` = `{island_slug}/{section}`; if a section's lines change after a sheet re-sync, keep its history but reset it to Again.
  - Simple scheduling: Again → due tomorrow; OK → interval × 2 (start 2 days); Solid → interval × 3 (start 4 days); cap at 60 days. New sections are due immediately.
  - **Review mix** = all due sections across islands, overdue first, shuffled within the same day, capped by a "minutes" setting (default 15). Show counts on the home screen: due today / learning / solid / new.
  - **Export progress** button → downloads a CSV (`section_key, last_run, rating, interval_days, due_date`) for backup; **Import** restores it (e.g. new phone).
- Off-book view: shows section and speaker names; tap a line to reveal ES; long-press to reveal EN.
- Keep offline caching (service worker) — add new segment files and driving MP3s to the cache manifest; bump the cache version on each build.

---

## 7. Commands (target)

```bash
cd code
python3 sync_sheet.py            # data/islands.csv → data/islands.json
python3 generate_audio.py        # synthesize missing segments (hash cache)
python3 generate_playlist.py     # all modes → ../playlist.json
python3 build_driving.py         # baked driving MP3 per island
```
Each script is idempotent and only does work for changed lines.

---

## 8. Acceptance checks

- Changing one Spanish cell in the sheet → re-sync → exactly one new segment synthesized; its island's driving MP3 rebuilt; other islands untouched.
- Stage-direction notes never appear in audio.
- Run-lines gap for a Kirk line = 1.5 × its ES duration (≥ 2 s); driving = 2.0 ×.
- Driving MP3 over CarPlay: the island announcement may clip, the first Spanish line never does.
- Pausing at a red light and resuming replays the last ~3 s.
- Rating a section Again/OK/Solid changes when it appears in the Review mix; progress survives app restarts and a playlist rebuild; Export → Import round-trips.
- `--region MX` build uses `departamento`, `popotes`, `cheque de caja`, etc. where Variant Region = MX.
- Player works offline after first load.

---

## 9. Migration notes

- Work and Daily Routine already have audio from `sentences.json`; their wording has since changed in the sheet (role → solutions architect, tenure, several Daily Routine fixes). Regenerate both from the sheet; then retire `sentences.json` and `islands.txt` (keep in git history).
- Existing segment naming (`island-01-work-core-1-a-es-s01.mp3`) can stay on disk until the new playlist is verified, then be cleaned up.
- Sheet currently holds 18 islands, ~452 lines.
