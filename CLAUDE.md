# Spanish Islands Player — Claude Code Context

## What this project is

A PWA (Progressive Web App) deployed to GitHub Pages for drilling Mexican Spanish via
scenario-based dialogue islands. Kirk's target is DELE B1 by end of 2026.

Repo: https://github.com/KLone/spanish-islands  
Deployed: https://klone.github.io/spanish-islands/player.html

---

## Two-Layer Content Architecture

### Layer 1 — Dialogue Islands (primary content)
Scenario dialogues: getting coffee, ordering at a restaurant, going to the bank, etc.
- **Source of truth**: Google Sheet `Islands` tab, sheet ID `1tF1nY0rZuojjOMGBlouzPOvHx9J7Yl2iV4-Pe6OFMf0`, gid 101
- **Local data**: `code/data/islands.json` (built by `sync_sheet.py`)
- **Audio segments**: `code/audio/segments/seg-<sha1>.mp3` (cached by text+voice+rate hash)
- **Per-island driving MP3s**: `islands/<slug>/audio/<NN>-<slug>-driving.mp3`
- **All-islands continuous MP3**: `islands/_all/audio/00-all-islands-driving.mp3`
- **Driving manifest**: `driving.json` (island names, start times, durations — read by player)

Currently 23 islands (20 is "Giving advice to a friend", 21 "Reacting to family news", 22 "Regrets and what-ifs", 23 "Weighing a decision" were added in Nov 2026).

### Layer 2 — Q&A Interview Cards (secondary content)
Classic language-island interview Q&A: Work (6 cards), Daily Routine (6 cards).
- **Source**: `code/sentences.json`
- **Playlist**: `playlist.json` (built by `generate_playlist.py`)
- These feed the Recall, Shadow, Listen, Engcue, Reverse, Offbook modes

---

## Player Modes

| Mode button | Color | Content source | Description |
|---|---|---|---|
| Run Lines | green | dialogue islands | Play ES line → pause → play EN line, card by card |
| Eng Cue | yellow | dialogue islands | Show EN line → speak → tap Reveal → ES plays |
| Reverse | purple | dialogue islands | Play ES → user speaks EN → reveal EN |
| Offbook | teal | dialogue islands | No text, just audio — full immersion |
| Listen | orange | Q&A cards | ES question → ES answer, auto-advance, loops |
| Shadow | blue | Q&A cards | Continuous ES audio, loop |
| Driving | red | driving MP3s | CarPlay/Bluetooth — per-island or all-islands continuous |

The island dropdown (`#island-sel`) filters all modes to one island or "All islands".

---

## Full Content Pipeline

**When the Google Sheet is updated, run these in order from `code/`:**

```bash
cd /Users/Kirk/kirk-projects/language-learning/spanish/code

# 1. Convert sheet data to islands.json
#    Sheet is NOT publicly shared — use the Google Sheets MCP connector to
#    download the 'Islands' tab, save as data/islands.csv, then:
python3 sync_sheet.py --region MX

# 2. Generate TTS audio for new/changed lines (skips cached segments)
python3 generate_audio.py

# 3. Rebuild driving MP3s and driving.json (skips unchanged islands)
python3 build_driving.py

# 4. Rebuild playlist.json (for Q&A card modes, from sentences.json)
python3 generate_playlist.py
```

**To force-rebuild all driving MP3s:**
```bash
python3 build_driving.py --force
```

**To regenerate Q&A cards audio (island 1 or 2):**
```bash
python3 generate_audio.py --all   # re-checks everything
```

**After any content change, commit and push:**
```bash
cd /Users/Kirk/kirk-projects/language-learning/spanish
git add -A
git commit -m "..."
git push origin main
```

---

## Google Sheet → Local CSV (MCP Connector)

The sheet is not publicly link-shared, so `sync_sheet.py --fetch` won't work.
Instead, use the Google Sheets MCP connector:

```
mcp__d14900c1__get_values(
  spreadsheetId="1tF1nY0rZuojjOMGBlouzPOvHx9J7Yl2iV4-Pe6OFMf0",
  range="Islands!A1:J1334"
)
```

Then convert the returned `values` array to CSV and write to `code/data/islands.csv`,
then run `sync_sheet.py --region MX` (no `--fetch` flag).

---

## Service Worker Cache Busting

**Every time `player.html` or `sw.js` changes, the phone won't update until the SW
cache version is bumped.** The current cache name is in `sw.js`:

```js
const SHELL_CACHE = 'island-shell-v11';
```

Increment `v11` → `v12` etc. on every push that changes player behavior.
After pushing, the phone picks up the update on next WiFi open (network-first strategy).

---

## TTS Voices

| Use | Voice | Lang | Rate |
|---|---|---|---|
| Kirk's Spanish lines | `es-US-Neural2-C` | `es-US` | 0.80 |
| Partner Spanish lines | `es-US-Neural2-B` | `es-US` | 0.80 |
| English lines | `en-US-Neural2-C` | `en-US` | 0.90 |

API key stored in macOS Keychain as `google_tts_api_key`.

---

## Key Files

```
spanish/
├── player.html          # PWA player (all modes, island dropdown)
├── sw.js                # Service worker (bump SHELL_CACHE version on changes)
├── playlist.json        # Q&A card playlist (generated)
├── driving.json         # Driving mode manifest (island start times, file refs)
├── manifest.json        # PWA manifest
├── icon.svg             # Home screen icon
├── islands/             # Per-island audio output
│   ├── _all/audio/00-all-islands-driving.mp3
│   └── <slug>/audio/<NN>-<slug>-driving.mp3
└── code/
    ├── sentences.json        # Q&A interview cards (Work, Daily Routine)
    ├── sync_sheet.py         # Sheet CSV → data/islands.json
    ├── generate_audio.py     # TTS segments for dialogue islands
    ├── build_driving.py      # Concat segments → per-island + all-islands MP3
    ├── generate_playlist.py  # sentences.json → playlist.json
    ├── data/
    │   ├── islands.csv       # Raw sheet download
    │   ├── islands.json      # Parsed island data
    │   └── segments.json     # {line_id: {es, en, durations}}
    └── audio/
        ├── segments/         # Cached TTS segment MP3s (sha1-named)
        └── assets/           # lead_in.mp3, end_tone.mp3, section_tick.mp3
```

---

## Sheet Format

Columns: Island | Section | Line | Speaker | Spanish | English | Region | Variant | Variant Region | Notes

- `Region` col: regional tag for the base Spanish (e.g. `PA` = Panama)
- `Variant` / `Variant Region`: alternate phrasing for a different region (e.g. `MX`)
- Run with `--region MX` to substitute MX variants where available
- `Notes` starting with `Stage direction:` → display-only, never spoken

---

## Norwegian Player (parallel project)

Same architecture, different language. Lives at:
`/Users/Kirk/kirk-projects/language-learning/norwegian/player/`
See `norwegian/CLAUDE.md` for its own context.
