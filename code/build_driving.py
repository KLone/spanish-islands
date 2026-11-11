"""
build_driving.py

Bakes one loudness-normalized MP3 per island for CarPlay/Bluetooth use.

Structure per island:
  1. Lead-in: 2 s pink noise (wakes up the audio route)
  2. Sacrificial announcement (EN TTS): "Island one: Getting Coffee."
  3. 1.0 s silence
  4. For each section:
       EN announcement: "Section: Bebidas"
       Run-lines sequence (factor 2.0) for every line in that section
       1.5 s silence
  5. End tone: 0.5 s soft 660 Hz sine

Output: ../islands/<slug>/audio/<NN>-<slug>-driving.mp3
  ID3 tags: title, album, track number

Gaps are real silence baked via anullsrc at 24 kHz mono so there are no
concat glitches. Everything is resampled to 24 kHz mono before concat.
Final file is loudness-normalized to -16 LUFS.

Usage:
  cd code
  python3 build_driving.py                    # rebuild changed islands
  python3 build_driving.py --island "Getting Coffee"   # one island only
  python3 build_driving.py --force            # rebuild all
  python3 build_driving.py --all-only         # just rejoin the all-islands MP3

Also joins every island into one continuous file:
  ../islands/_all/audio/00-all-islands-driving.mp3  (+ ../driving.json with
  each island's start time, used by the player's "All islands" item)
"""

import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ISLANDS_JSON  = "data/islands.json"
SEGMENTS_JSON = "data/segments.json"
ASSET_DIR     = "audio/assets"
TTS_URL       = "https://texttospeech.googleapis.com/v1/text:synthesize"
EN_VOICE      = "en-US-Neural2-C"
EN_LANG       = "en-US"
EN_RATE       = 0.90
DRIVING_FACTOR = 2.0
MIN_GAP        = 2.0
SAMPLE_RATE    = 24000

# Cache TTS for announcements so reruns don't re-synthesize them
ANN_CACHE_DIR  = "audio/announcements"


def load_api_key():
    result = subprocess.run(
        ["security", "find-generic-password", "-a", "google_tts_api_key", "-w"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print("ERROR: Could not load Google TTS API key.")
        sys.exit(1)
    return result.stdout.strip()


def synthesize_en(api_key, text, rate=EN_RATE):
    payload = json.dumps({
        "input": {"text": text},
        "voice": {"languageCode": EN_LANG, "name": EN_VOICE},
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


def ann_path(text):
    h = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
    return os.path.join(ANN_CACHE_DIR, f"ann-{h}.mp3")


def get_announcement(api_key, text):
    path = ann_path(text)
    if not os.path.exists(path):
        mp3 = synthesize_en(api_key, text)
        with open(path, "wb") as f:
            f.write(mp3)
    return path


def make_silence(duration_s, tmpdir):
    """Write a silence file at SAMPLE_RATE mono into tmpdir."""
    path = os.path.join(tmpdir, f"sil-{duration_s:.3f}.mp3")
    if not os.path.exists(path):
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"anullsrc=r={SAMPLE_RATE}:cl=mono",
            "-t", str(duration_s), "-q:a", "9",
            path,
        ], check=True, capture_output=True)
    return path


def normalize_to_24k(src, tmpdir):
    """Resample/normalize to 24 kHz mono MP3; returns new path in tmpdir."""
    h = hashlib.sha1(src.encode("utf-8")).hexdigest()[:8]
    dst = os.path.join(tmpdir, f"norm-{h}.mp3")
    subprocess.run([
        "ffmpeg", "-y", "-i", src,
        "-ar", str(SAMPLE_RATE), "-ac", "1", "-q:a", "9",
        dst,
    ], check=True, capture_output=True)
    return dst


def measure_duration(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 2.0


def concat_mp3s(parts, output):
    lf = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
    lf.write("\n".join(f"file '{os.path.abspath(p)}'" for p in parts))
    lf.close()
    try:
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", lf.name, "-c", "copy", output,
        ], check=True, capture_output=True)
    finally:
        os.unlink(lf.name)


def loudnorm(src, dst):
    subprocess.run([
        "ffmpeg", "-y", "-i", src,
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-ar", str(SAMPLE_RATE), "-ac", "1",
        "-codec:a", "libmp3lame", "-q:a", "4",
        dst,
    ], check=True, capture_output=True)


def tag_mp3(path, title, track, album="Spanish Islands — Driving"):
    subprocess.run([
        "ffmpeg", "-y", "-i", path,
        "-metadata", f"title={title}",
        "-metadata", f"album={album}",
        "-metadata", f"track={track}",
        "-codec:a", "copy",
        path + ".tagged.mp3",
    ], check=True, capture_output=True)
    os.replace(path + ".tagged.mp3", path)


def build_island(island, manifest, api_key, force=False):
    slug = island["island_slug"]
    num  = island["island_num"]
    name = island["island"]

    out_dir = os.path.join("..", "islands", slug, "audio")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{num:02d}-{slug}-driving.mp3")

    if os.path.exists(out_path) and not force:
        # Check if any line in this island has changed (new segment path not matching manifest)
        changed = False
        for section in island["sections"]:
            for line in section["lines"]:
                if line["is_stage_direction"]:
                    continue
                lid = line["line_id"]
                if lid not in manifest:
                    changed = True
                    break
            if changed:
                break
        if not changed:
            print(f"  {name}: up to date, skipping")
            return

    print(f"  Building: {name} ...")

    with tempfile.TemporaryDirectory() as tmpdir:
        parts = []

        # 1. Lead-in pink noise
        lead = os.path.join(ASSET_DIR, "lead_in.mp3")
        parts.append(normalize_to_24k(lead, tmpdir))

        # 2. Sacrificial island announcement
        ann_text = f"Island {num}: {name}."
        ann_file = get_announcement(api_key, ann_text)
        parts.append(normalize_to_24k(ann_file, tmpdir))

        # 3. 1.0 s pause
        parts.append(make_silence(1.0, tmpdir))

        # 4. Sections
        for section in island["sections"]:
            sec_name = section["section"]

            # Section announcement
            sec_ann_text = f"Section: {sec_name}."
            sec_ann_file = get_announcement(api_key, sec_ann_text)
            parts.append(normalize_to_24k(sec_ann_file, tmpdir))

            # Run-lines at factor 2.0
            for line in section["lines"]:
                if line["is_stage_direction"]:
                    continue
                lid = line["line_id"]
                is_kirk = line["speaker"].lower() == "kirk"
                m = manifest.get(lid)
                if m is None:
                    print(f"    WARNING: no segment for {lid} — skipping line")
                    continue
                es_path = os.path.join("..", m["es"])
                es_dur  = m["es_duration_s"]

                if not is_kirk:
                    parts.append(normalize_to_24k(es_path, tmpdir))
                    parts.append(make_silence(0.6, tmpdir))
                else:
                    gap_s = max(MIN_GAP, DRIVING_FACTOR * es_dur)
                    parts.append(make_silence(gap_s, tmpdir))
                    parts.append(normalize_to_24k(es_path, tmpdir))
                    parts.append(make_silence(0.6, tmpdir))

            # 1.5 s between sections
            parts.append(make_silence(1.5, tmpdir))

        # 5. End tone
        end_tone = os.path.join(ASSET_DIR, "end_tone.mp3")
        parts.append(normalize_to_24k(end_tone, tmpdir))

        # Concat raw
        raw = os.path.join(tmpdir, "raw.mp3")
        concat_mp3s(parts, raw)

        # Loudnorm
        normalized = os.path.join(tmpdir, "normalized.mp3")
        loudnorm(raw, normalized)

        # Copy to final destination before tagging
        import shutil
        shutil.copy2(normalized, out_path)

    # Tag outside the tmpdir (file is at out_path now)
    tag_mp3(out_path,
            title=f"{num:02d} · {name} (Driving)",
            track=str(num))

    size_kb = os.path.getsize(out_path) // 1024
    print(f"    → {out_path}  ({size_kb} KB)")


ALL_DIR      = os.path.join("..", "islands", "_all", "audio")
ALL_MP3      = os.path.join(ALL_DIR, "00-all-islands-driving.mp3")
ALL_JSON     = os.path.join("..", "driving.json")
ISLAND_GAP_S = 2.0


def island_mp3(island):
    slug, num = island["island_slug"], island["island_num"]
    return os.path.join("..", "islands", slug, "audio", f"{num:02d}-{slug}-driving.mp3")


def file_version(path):
    """Short content hash, used as ?v= so the app's offline cache picks up rebuilt files."""
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:10]


def build_all(islands, force=False):
    """Join every island's driving MP3 (in island order) into one continuous file,
    and write driving.json with each island's start time for the player."""
    islands = sorted(islands, key=lambda i: i["island_num"])
    present = [i for i in islands if os.path.exists(island_mp3(i))]
    missing = [i["island"] for i in islands if i not in present]
    if missing:
        print(f"  WARNING: no driving MP3 yet for: {', '.join(missing)}")
    if not present:
        print("  No island MP3s to join.")
        return

    newest = max(os.path.getmtime(island_mp3(i)) for i in present)
    if (not force and os.path.exists(ALL_MP3) and os.path.exists(ALL_JSON)
            and os.path.getmtime(ALL_MP3) >= newest):
        print("  All-islands MP3: up to date, skipping")
        return

    print(f"  Building all-islands MP3 from {len(present)} islands ...")
    os.makedirs(ALL_DIR, exist_ok=True)
    chapters, t = [], 0.0
    with tempfile.TemporaryDirectory() as tmpdir:
        gap = make_silence(ISLAND_GAP_S, tmpdir)
        gap_dur = measure_duration(gap)
        parts = []
        for n, isl in enumerate(present):
            src = normalize_to_24k(os.path.abspath(island_mp3(isl)), tmpdir)
            chapters.append({"num": isl["island_num"], "name": isl["island"],
                             "slug": isl["island_slug"], "start": round(t, 2)})
            parts.append(src)
            t += measure_duration(src)
            if n < len(present) - 1:
                parts.append(gap)
                t += gap_dur
        raw = os.path.join(tmpdir, "raw.mp3")
        concat_mp3s(parts, raw)
        # Re-encode once so the file has one clean header (correct duration/seeking on iOS)
        subprocess.run([
            "ffmpeg", "-y", "-i", raw,
            "-ar", str(SAMPLE_RATE), "-ac", "1",
            "-codec:a", "libmp3lame", "-q:a", "4",
            "-metadata", "title=All islands (Driving)",
            "-metadata", "album=Spanish Islands — Driving",
            "-metadata", "track=0",
            ALL_MP3,
        ], check=True, capture_output=True)

    total = measure_duration(ALL_MP3)
    for ch, isl in zip(chapters, present):
        ch["file"] = os.path.relpath(island_mp3(isl), "..") + "?v=" + file_version(island_mp3(isl))
    with open(ALL_JSON, "w", encoding="utf-8") as f:
        json.dump({"file": "islands/_all/audio/00-all-islands-driving.mp3?v=" + file_version(ALL_MP3),
                   "duration": round(total, 2), "islands": chapters},
                  f, ensure_ascii=False, indent=1)
    size_mb = os.path.getsize(ALL_MP3) / 1e6
    print(f"    → {ALL_MP3}  ({total/60:.0f} min, {size_mb:.1f} MB)")


def main():
    args = sys.argv[1:]
    force = "--force" in args
    target_island = None
    if "--island" in args:
        idx = args.index("--island")
        if idx + 1 < len(args):
            target_island = args[idx + 1]

    for path in [ISLANDS_JSON, SEGMENTS_JSON]:
        if not os.path.exists(path):
            print(f"ERROR: {path} not found. Run sync_sheet.py and generate_audio.py first.")
            sys.exit(1)

    os.makedirs(ANN_CACHE_DIR, exist_ok=True)

    with open(ISLANDS_JSON, encoding="utf-8") as f:
        islands = json.load(f)
    with open(SEGMENTS_JSON, encoding="utf-8") as f:
        manifest = json.load(f)

    if target_island:
        islands = [i for i in islands if i["island"].lower() == target_island.lower()]
        if not islands:
            print(f"ERROR: Island '{target_island}' not found in {ISLANDS_JSON}")
            sys.exit(1)

    if "--all-only" in args:
        build_all(islands, force=force)
        return

    api_key = load_api_key()

    print(f"Building driving MP3s for {len(islands)} island(s)...")
    errors = []
    for island in islands:
        try:
            build_island(island, manifest, api_key, force=force)
        except subprocess.CalledProcessError as e:
            print(f"  ERROR (ffmpeg): {e}")
            errors.append(island["island"])
        except Exception as e:
            print(f"  ERROR: {e}")
            errors.append(island["island"])
        time.sleep(0.05)

    if not target_island:
        try:
            build_all(islands, force=force)
        except Exception as e:
            print(f"  ERROR building all-islands MP3: {e}")
            errors.append("(all islands)")

    print(f"\nDone. {len(islands) - len(errors)} succeeded, {len(errors)} failed.")
    if errors:
        print(f"Failed: {', '.join(errors)}")


if __name__ == "__main__":
    main()
