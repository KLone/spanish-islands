"""
generate_audio.py

Synthesizes audio segments for every line in data/islands.json.

Segment cache: audio/segments/seg-<sha1(text|voice|rate)[:12]>.mp3
  Renaming or reordering a line costs nothing; editing its text regenerates it.

Also generates small shared assets once:
  audio/assets/lead_in.mp3       — 2 s pink noise (CarPlay wake-up guard)
  audio/assets/end_tone.mp3      — 0.5 s soft 660 Hz sine
  audio/assets/section_tick.mp3  — 150 ms very soft tick

Outputs:
  data/segments.json  — {line_id: {es, en, es_duration_s, en_duration_s}}

Usage:
  cd code
  python3 generate_audio.py          # synthesize only missing segments
  python3 generate_audio.py --all    # re-check everything (still skips cached)
"""

import base64
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

# ── Config ────────────────────────────────────────────────────────────────────
ISLANDS_JSON  = "data/islands.json"
SEGMENTS_JSON = "data/segments.json"
SEG_DIR       = "audio/segments"
ASSET_DIR     = "audio/assets"
TTS_URL       = "https://texttospeech.googleapis.com/v1/text:synthesize"

ES_VOICE_KIRK    = "es-US-Neural2-C"   # Kirk's voice
ES_VOICE_PARTNER = "es-US-Neural2-B"   # Contrasting partner voice
EN_VOICE         = "en-US-Neural2-C"
ES_LANG          = "es-US"
EN_LANG          = "en-US"
ES_RATE          = 0.80
EN_RATE          = 0.90
# ─────────────────────────────────────────────────────────────────────────────


def load_api_key():
    result = subprocess.run(
        ["security", "find-generic-password", "-a", "google_tts_api_key", "-w"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print("ERROR: Could not load Google TTS API key from Keychain.")
        print("Store it with:")
        print("  security add-generic-password -a 'google_tts_api_key' -s 'google_tts' -w 'YOUR_KEY'")
        sys.exit(1)
    return result.stdout.strip()


def seg_path(text, voice, rate):
    key = f"{text}|{voice}|{rate}"
    h = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
    return os.path.join(SEG_DIR, f"seg-{h}.mp3")


def synthesize(api_key, text, lang, voice, rate):
    payload = json.dumps({
        "input": {"text": text},
        "voice": {"languageCode": lang, "name": voice},
        "audioConfig": {"audioEncoding": "MP3", "speakingRate": rate},
    }).encode("utf-8")
    url = f"{TTS_URL}?key={api_key}"
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        body = json.loads(resp.read())
    return base64.b64decode(body["audioContent"])


def fetch_if_missing(path, api_key, text, lang, voice, rate):
    """Return path; synthesize and cache if not present."""
    if not os.path.exists(path):
        mp3 = synthesize(api_key, text, lang, voice, rate)
        with open(path, "wb") as f:
            f.write(mp3)
    return path


def measure_duration(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True,
    )
    try:
        return round(float(result.stdout.strip()), 3)
    except ValueError:
        return 0.0


def make_lead_in():
    path = os.path.join(ASSET_DIR, "lead_in.mp3")
    if os.path.exists(path):
        return
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "anoisesrc=color=pink:amplitude=0.02:duration=2",
        "-af", "afade=t=in:st=0:d=0.3,afade=t=out:st=1.7:d=0.3",
        "-ar", "24000", "-ac", "1", "-q:a", "9",
        path,
    ], check=True, capture_output=True)
    print("  Generated lead_in.mp3")


def make_end_tone():
    path = os.path.join(ASSET_DIR, "end_tone.mp3")
    if os.path.exists(path):
        return
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "aevalsrc=0.08*sin(2*PI*660*t):s=24000:c=mono:d=0.5",
        "-af", "afade=t=in:st=0:d=0.05,afade=t=out:st=0.4:d=0.1",
        "-ar", "24000", "-ac", "1", "-q:a", "9",
        path,
    ], check=True, capture_output=True)
    print("  Generated end_tone.mp3")


def make_section_tick():
    path = os.path.join(ASSET_DIR, "section_tick.mp3")
    if os.path.exists(path):
        return
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "aevalsrc=0.03*sin(2*PI*1000*t):s=24000:c=mono:d=0.15",
        "-af", "afade=t=in:st=0:d=0.02,afade=t=out:st=0.12:d=0.03",
        "-ar", "24000", "-ac", "1", "-q:a", "9",
        path,
    ], check=True, capture_output=True)
    print("  Generated section_tick.mp3")


def main():
    os.makedirs(SEG_DIR, exist_ok=True)
    os.makedirs(ASSET_DIR, exist_ok=True)
    os.makedirs("data", exist_ok=True)

    if not os.path.exists(ISLANDS_JSON):
        print(f"ERROR: {ISLANDS_JSON} not found. Run sync_sheet.py first.")
        sys.exit(1)

    with open(ISLANDS_JSON, encoding="utf-8") as f:
        islands = json.load(f)

    # Load existing segments manifest
    if os.path.exists(SEGMENTS_JSON):
        with open(SEGMENTS_JSON, encoding="utf-8") as f:
            manifest = json.load(f)
    else:
        manifest = {}

    # Generate static assets
    print("Checking static assets...")
    make_lead_in()
    make_end_tone()
    make_section_tick()

    # Collect all lines
    all_lines = []
    for island in islands:
        for section in island["sections"]:
            for line in section["lines"]:
                all_lines.append((island, section, line))

    print(f"\nLines total: {len(all_lines)}")

    # Determine which lines need synthesis
    pending = []
    for island, section, line in all_lines:
        lid = line["line_id"]
        speaker = line["speaker"].lower()
        voice = ES_VOICE_KIRK if speaker == "kirk" else ES_VOICE_PARTNER
        es_path = seg_path(line["spanish"], voice, ES_RATE)
        en_path = seg_path(line["english"], EN_VOICE, EN_RATE)
        needs = (not os.path.exists(es_path)) or (not os.path.exists(en_path)) or (lid not in manifest)
        if needs:
            pending.append((line, voice, es_path, en_path))

    if not pending:
        print("All segments already cached.")
    else:
        print(f"Segments to synthesize: {len(pending) * 2}  ({len(pending)} lines × ES+EN)")

    api_key = None
    errors = []

    for i, (line, voice, es_path, en_path) in enumerate(pending, 1):
        lid = line["line_id"]
        print(f"  [{i}/{len(pending)}] {lid} ...", end=" ", flush=True)
        if api_key is None:
            api_key = load_api_key()
        try:
            fetch_if_missing(es_path, api_key, line["spanish"], ES_LANG, voice, ES_RATE)
            fetch_if_missing(en_path, api_key, line["english"], EN_LANG, EN_VOICE, EN_RATE)
            es_dur = measure_duration(es_path)
            en_dur = measure_duration(en_path)
            manifest[lid] = {
                "es": os.path.relpath(es_path, start=".."),
                "en": os.path.relpath(en_path, start=".."),
                "es_duration_s": es_dur,
                "en_duration_s": en_dur,
                "voice_es": voice,
            }
            print(f"✓  ({es_dur:.2f}s ES / {en_dur:.2f}s EN)")
        except subprocess.CalledProcessError as e:
            print(f"ERROR (ffmpeg/ffprobe): {e}")
            errors.append(lid)
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            print(f"ERROR HTTP {e.code}: {body[:120]}")
            errors.append(lid)
        except Exception as e:
            print(f"ERROR: {e}")
            errors.append(lid)
        time.sleep(0.1)

    # Update durations for already-cached lines not yet in manifest
    new_in_manifest = 0
    for island, section, line in all_lines:
        lid = line["line_id"]
        if lid in manifest:
            continue
        speaker = line["speaker"].lower()
        voice = ES_VOICE_KIRK if speaker == "kirk" else ES_VOICE_PARTNER
        es_path = seg_path(line["spanish"], voice, ES_RATE)
        en_path = seg_path(line["english"], EN_VOICE, EN_RATE)
        if os.path.exists(es_path) and os.path.exists(en_path):
            manifest[lid] = {
                "es": os.path.relpath(es_path, start=".."),
                "en": os.path.relpath(en_path, start=".."),
                "es_duration_s": measure_duration(es_path),
                "en_duration_s": measure_duration(en_path),
                "voice_es": voice,
            }
            new_in_manifest += 1

    with open(SEGMENTS_JSON, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    total_done = sum(1 for _, _, l in all_lines if l["line_id"] in manifest)
    print(f"\nManifest: {len(manifest)} entries  ({total_done}/{len(all_lines)} lines covered)")
    print(f"Written {SEGMENTS_JSON}")
    if errors:
        print(f"\nFailed ({len(errors)}): {', '.join(errors)}")
        print("Run again to retry.")


if __name__ == "__main__":
    main()
