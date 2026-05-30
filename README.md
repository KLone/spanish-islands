# Spanish Islands Player

A PWA for drilling and shadowing Spanish language islands — personalized Q&A sentence sets built around real conversation topics.

**Player URL:** https://klone.github.io/spanish-islands/player.html

---

## Using on iPhone

1. Open the URL above in Safari
2. Tap the Share button → **Add to Home Screen**
3. On first open (with WiFi), all audio is downloaded and cached
4. After that, the app works fully offline — on a plane, no WiFi needed

---

## Modes

- **Recall** — English Q → pause → Spanish Q → English sentence → pause → Spanish sentence (repeat per sentence). Use this while actively drilling.
- **Shadow** — Spanish Q → pause → Spanish sentences. Use this once an island is memorized, for maintenance and fluency.

---

## Running locally

Serve from the `spanish/` directory:

```bash
cd language-learning/spanish
python3 -m http.server 8765
```

Then open `http://localhost:8765/player.html` in a browser.  
On iPhone over WiFi, use your Mac's local IP instead of `localhost`.

---

## Adding a new island

1. Add cards to `code/sentences.json` following the existing format:

```json
{
  "island_num": 2,
  "island_slug": "family",
  "card_type": "core",
  "card_num": 1,
  "q_en": "...",
  "q_es": "...",
  "a_en": "...",
  "a_es": "..."
}
```

2. Run from `code/`:

```bash
cd code
python3 generate_audio.py --all
python3 generate_playlist.py
python3 generate_text.py
```

3. Push to GitHub:

```bash
cd ..
git add .
git commit -m "Add family island"
git push
```

4. Open the player on your phone with WiFi — new content syncs automatically.

---

## Directory structure

```
spanish/
  player.html          # PWA player
  playlist.json        # Generated — all cards and audio paths
  manifest.json        # PWA manifest
  sw.js                # Service worker (offline caching)
  icon.svg             # Home screen icon
  code/
    sentences.json     # Source content — edit this to add islands
    generate_audio.py  # Generates MP3 segments and final recall/shadow files
    generate_playlist.py  # Generates playlist.json for the player
    generate_text.py   # Generates plain text reference files
    audio/
      segments/        # Individual TTS segments (used by player)
  islands/
    work/
      audio/           # Combined recall + shadow MP3s per card
      text/            # Plain text reference
    family/            # Added when family island is complete
    ...
```
