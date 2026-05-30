"""
generate_audio.py

Generates MP3 audio for each Q&A card in sentences.json using Google Cloud TTS.
For each card, produces two files:

  Recall  (island-01-work-core-1-recall.mp3):
    EN question → pause → ES question → pause →
    EN answer sentence 1 → pause → ES answer sentence 1 → pause →
    EN answer sentence 2 → pause → ES answer sentence 2 → ...

  Shadow  (island-01-work-core-1-shadow.mp3):
    ES question → pause → ES answer (full)

Intermediate per-segment files are written to audio/tmp/ and reused.
Final files are assembled with ffmpeg.

Spanish voice: es-US-Neural2-C (Mexican Spanish neural)
English voice: en-US-Neural2-C

Resumable: skips final files that already exist.

Usage:
  python3 generate_audio.py           # process up to BATCH_SIZE cards
  python3 generate_audio.py --all     # process everything
"""

import json
import os
import re
import sys
import base64
import time
import tempfile
import urllib.request
import urllib.error
import subprocess

# ── Config ───────────────────────────────────────────────────────────────────
INPUT_FILE       = "sentences.json"
ISLANDS_DIR      = "../islands"
TMP_DIR          = "audio/tmp"
BATCH_SIZE       = 20
TTS_URL          = "https://texttospeech.googleapis.com/v1/text:synthesize"

ES_VOICE         = "es-US-Neural2-C"
ES_LANG          = "es-US"
EN_VOICE         = "en-US-Neural2-C"
EN_LANG          = "en-US"
ES_SPEAKING_RATE = 0.80
EN_SPEAKING_RATE = 0.90
PAUSE_SEC        = 5.0
# ─────────────────────────────────────────────────────────────────────────────


def load_api_key():
    result = subprocess.run(
        ["security", "find-generic-password", "-a", "google_tts_api_key", "-w"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print("ERROR: Could not load Google TTS API key from Keychain.")
        print("Store it with: security add-generic-password -a 'google_tts_api_key' -s 'google_tts' -w 'YOUR_KEY'")
        sys.exit(1)
    return result.stdout.strip()


def split_sentences(text):
    """Split text into individual sentences on period/!/? followed by a capital."""
    parts = re.split(r'(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÜÑA-Z])', text)
    return [p.strip() for p in parts if p.strip()]


def card_stem(card):
    return (
        f"island-{card['island_num']:02d}-{card['island_slug']}"
        f"-{card['card_type']}-{card['card_num']}"
    )


def island_audio_dir(card):
    path = os.path.join(ISLANDS_DIR, card["island_slug"], "audio")
    os.makedirs(path, exist_ok=True)
    return path


def final_paths(card):
    stem = card_stem(card)
    d = island_audio_dir(card)
    return {
        "recall": os.path.join(d, f"{stem}-recall.mp3"),
        "shadow": os.path.join(d, f"{stem}-shadow.mp3"),
    }


def card_is_done(card):
    return all(os.path.exists(p) for p in final_paths(card).values())


def synthesize(api_key, text, lang, voice, rate):
    payload = json.dumps({
        "input": {"text": text},
        "voice": {"languageCode": lang, "name": voice},
        "audioConfig": {
            "audioEncoding": "MP3",
            "speakingRate": rate,
        }
    }).encode("utf-8")

    url = f"{TTS_URL}?key={api_key}"
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req) as resp:
        body = json.loads(resp.read())
    return base64.b64decode(body["audioContent"])


def fetch_if_missing(path, api_key, text, lang, voice, rate):
    if not os.path.exists(path):
        mp3 = synthesize(api_key, text, lang, voice, rate)
        with open(path, "wb") as f:
            f.write(mp3)


def make_silence(pause_sec):
    """Generate a silence MP3 as a temp file, return its path."""
    sf = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    sf.close()
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"anullsrc=r=24000:cl=mono",
        "-t", str(pause_sec),
        "-q:a", "9", "-acodec", "libmp3lame",
        sf.name
    ], check=True, capture_output=True)
    return sf.name


def concat_files(parts, output):
    """Concatenate a list of MP3 paths into a single output file using ffmpeg."""
    lf = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
    lf.write("\n".join(f"file '{os.path.abspath(p)}'" for p in parts))
    lf.close()
    try:
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", lf.name, "-c", "copy", output
        ], check=True, capture_output=True)
    finally:
        os.unlink(lf.name)


def process_card(card, api_key):
    stem = card_stem(card)
    fp = final_paths(card)

    en_sents = split_sentences(card["a_en"])
    es_sents = split_sentences(card["a_es"])

    # Fetch question segments
    q_en_path = os.path.join(TMP_DIR, f"{stem}-q-en.mp3")
    q_es_path = os.path.join(TMP_DIR, f"{stem}-q-es.mp3")
    fetch_if_missing(q_en_path, api_key, card["q_en"], EN_LANG, EN_VOICE, EN_SPEAKING_RATE)
    fetch_if_missing(q_es_path, api_key, card["q_es"], ES_LANG, ES_VOICE, ES_SPEAKING_RATE)

    # Fetch answer sentence segments
    en_sent_paths, es_sent_paths = [], []
    for idx, (en_s, es_s) in enumerate(zip(en_sents, es_sents), 1):
        en_p = os.path.join(TMP_DIR, f"{stem}-a-en-s{idx:02d}.mp3")
        es_p = os.path.join(TMP_DIR, f"{stem}-a-es-s{idx:02d}.mp3")
        fetch_if_missing(en_p, api_key, en_s, EN_LANG, EN_VOICE, EN_SPEAKING_RATE)
        fetch_if_missing(es_p, api_key, es_s, ES_LANG, ES_VOICE, ES_SPEAKING_RATE)
        en_sent_paths.append(en_p)
        es_sent_paths.append(es_p)

    silence = make_silence(PAUSE_SEC)
    try:
        # Recall: EN Q → pause → ES Q → pause → (EN sent → pause → ES sent) × N
        if not os.path.exists(fp["recall"]):
            parts = [q_en_path, silence, q_es_path, silence]
            for en_p, es_p in zip(en_sent_paths, es_sent_paths):
                parts += [en_p, silence, es_p, silence]
            concat_files(parts, fp["recall"])

        # Shadow: ES Q → pause → ES sent 1 → pause → ES sent 2 → pause → ...
        if not os.path.exists(fp["shadow"]):
            parts = [q_es_path, silence]
            for es_p in es_sent_paths:
                parts += [es_p, silence]
            concat_files(parts, fp["shadow"])
    finally:
        os.unlink(silence)


def main():
    process_all = "--all" in sys.argv

    api_key = load_api_key()
    os.makedirs(TMP_DIR, exist_ok=True)

    with open(INPUT_FILE, encoding="utf-8") as f:
        cards = json.load(f)

    pending = [c for c in cards if not card_is_done(c)]
    total = len(cards)

    if not pending:
        print("All audio already generated.")
        return

    batch = pending if process_all else pending[:BATCH_SIZE]
    print(f"Cards done: {total - len(pending)}/{total}")
    print(f"Cards remaining: {len(pending)}")
    print(f"Processing this run: {len(batch)}")
    print()

    errors = []
    for i, card in enumerate(batch, 1):
        stem = card_stem(card)
        print(f"  [{i}/{len(batch)}] {stem} ...", end=" ", flush=True)
        try:
            process_card(card, api_key)
            print("✓")
        except subprocess.CalledProcessError as e:
            print(f"ERROR (ffmpeg): {e.stderr.decode()[:120]}")
            errors.append((stem, str(e)))
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            print(f"ERROR {e.code}: {body[:120]}")
            errors.append((stem, str(e)))
        except Exception as e:
            print(f"ERROR: {e}")
            errors.append((stem, str(e)))

        time.sleep(0.1)

    done = sum(1 for c in cards if card_is_done(c))
    print(f"\nDone. {len(batch) - len(errors)} succeeded, {len(errors)} failed.")
    if errors:
        print("Failed cards:")
        for stem, err in errors:
            print(f"  {stem}: {err}")
    print(f"Total complete: {done}/{total} cards.")
    if done < total:
        print(f"Run again to continue ({total - done} remaining).")


if __name__ == "__main__":
    main()
