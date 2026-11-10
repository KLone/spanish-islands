"""
generate_playlist.py

Reads data/islands.json + data/segments.json and writes playlist.json.

Produces one playlist entry per (island, section, mode) for 6 modes:
  listen, shadow, runlines, engcue, reverse, offbook

Gap formula: gap_after = max(MIN_GAP, FACTOR × es_duration_s_of_the_line_to_produce)
  Listening mode uses a fixed 0.6 s pause. Off-book has no audio.

The player handles gaps dynamically (gap_after field); driving MP3s are
baked separately by build_driving.py.

Old recall/shadow entries are appended after the new entries so the player
keeps working until the new modes are verified.

Usage:
  cd code
  python3 generate_playlist.py
"""

import json
import os
import sys

ISLANDS_JSON  = "data/islands.json"
SEGMENTS_JSON = "data/segments.json"
OUTPUT        = "../playlist.json"

MIN_GAP = 2.0

FACTORS = {
    "listen":  None,   # fixed 0.6 s pause
    "shadow":  1.2,
    "runlines": 1.5,
    "engcue":  1.75,
    "reverse": 1.5,
    "offbook": None,   # no audio
}

LISTEN_PAUSE = 0.6


def gap(factor, es_duration_s):
    if factor is None:
        return LISTEN_PAUSE
    return max(MIN_GAP, factor * es_duration_s)


def seg(text, audio, lang, role, line_id, gap_after, hint=None):
    entry = {
        "text": text,
        "audio": audio,
        "lang": lang,
        "role": role,
        "line_id": line_id,
        "gap_after": round(gap_after, 3),
    }
    if hint is not None:
        entry["hint"] = hint
    return entry


def build_section_entry(island, section, mode, manifest):
    lines = section["lines"]
    island_slug = island["island_slug"]
    island_num  = island["island_num"]
    island_name = island["island"]
    section_name = section["section"]

    segs = []

    if mode == "offbook":
        # No audio segments; player uses the line data for the reveal UI
        lines_data = []
        for line in lines:
            if line["is_stage_direction"]:
                continue
            lines_data.append({
                "line_id": line["line_id"],
                "speaker": line["speaker"],
                "spanish": line["spanish"],
                "english": line["english"],
            })
        return {
            "island": island_name,
            "island_num": island_num,
            "section": section_name,
            "mode": mode,
            "stem": f"{island_num:02d}-{island_slug}-{section_name.lower().replace(' ', '-')}",
            "lines": lines_data,
            "segments": [],
        }

    for line in lines:
        lid = line["line_id"]
        is_kirk = line["speaker"].lower() == "kirk"
        m = manifest.get(lid)
        if m is None:
            # Segment not synthesized yet — emit placeholder
            es_path, en_path = None, None
            es_dur = 2.0
        else:
            es_path = m["es"]
            en_path = m["en"]
            es_dur  = m["es_duration_s"]

        is_stage = line["is_stage_direction"]

        if mode == "listen":
            if is_stage:
                continue
            segs.append(seg(line["spanish"], es_path, "es",
                            "kirk" if is_kirk else "partner", lid,
                            LISTEN_PAUSE))

        elif mode == "shadow":
            if is_stage:
                continue
            segs.append(seg(line["spanish"], es_path, "es",
                            "kirk" if is_kirk else "partner", lid,
                            gap(FACTORS["shadow"], es_dur)))

        elif mode == "runlines":
            if is_stage:
                continue
            if not is_kirk:
                # Partner line plays straight through (small pause)
                segs.append(seg(line["spanish"], es_path, "es", "partner", lid, 0.6))
            else:
                # Gap for Kirk to speak, then confirmation
                segs.append(seg("", None, None, "gap", lid,
                                gap(FACTORS["runlines"], es_dur),
                                hint=line["english"]))
                segs.append(seg(line["spanish"], es_path, "es", "kirk", lid, 0.6))

        elif mode == "engcue":
            if is_stage:
                continue
            if not is_kirk:
                segs.append(seg(line["spanish"], es_path, "es", "partner", lid, 0.6))
            else:
                segs.append(seg(line["english"], en_path, "en", "cue", lid, 0.4))
                segs.append(seg("", None, None, "gap", lid,
                                gap(FACTORS["engcue"], es_dur),
                                hint=line["spanish"]))
                segs.append(seg(line["spanish"], es_path, "es", "kirk", lid, 0.6))

        elif mode == "reverse":
            if is_stage:
                continue
            if is_kirk:
                # Kirk's line plays as the cue
                segs.append(seg(line["spanish"], es_path, "es", "cue", lid, 0.4))
                # Find next non-stage partner line to use as the gap target
                # (gap size based on that partner line's duration — approximate with es_dur)
                segs.append(seg("", None, None, "gap", lid,
                                gap(FACTORS["reverse"], es_dur),
                                hint=line["english"]))
            else:
                segs.append(seg(line["spanish"], es_path, "es", "partner", lid, 0.6))

    return {
        "island": island_name,
        "island_num": island_num,
        "section": section_name,
        "mode": mode,
        "stem": f"{island_num:02d}-{island_slug}-{section_name.lower().replace(' ', '-')}",
        "segments": segs,
    }


def main():
    if not os.path.exists(ISLANDS_JSON):
        print(f"ERROR: {ISLANDS_JSON} not found. Run sync_sheet.py first.")
        sys.exit(1)
    if not os.path.exists(SEGMENTS_JSON):
        print(f"WARNING: {SEGMENTS_JSON} not found — audio paths will be null.")
        manifest = {}
    else:
        with open(SEGMENTS_JSON, encoding="utf-8") as f:
            manifest = json.load(f)

    with open(ISLANDS_JSON, encoding="utf-8") as f:
        islands = json.load(f)

    playlist = []
    modes = list(FACTORS.keys())

    for island in islands:
        for section in island["sections"]:
            for mode in modes:
                entry = build_section_entry(island, section, mode, manifest)
                playlist.append(entry)

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(playlist, f, ensure_ascii=False, indent=2)

    total_sections = sum(len(i["sections"]) for i in islands)
    print(f"Written {OUTPUT}")
    print(f"  Islands:  {len(islands)}")
    print(f"  Sections: {total_sections}")
    print(f"  Entries:  {len(playlist)}  ({total_sections} sections × {len(modes)} modes)")
    missing = sum(1 for i in islands
                  for s in i["sections"]
                  for l in s["lines"]
                  if l["line_id"] not in manifest and not l["is_stage_direction"])
    if missing:
        print(f"  WARNING: {missing} lines have no synthesized audio yet — run generate_audio.py")


if __name__ == "__main__":
    main()
