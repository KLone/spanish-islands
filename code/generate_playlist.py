"""
generate_playlist.py

Reads sentences.json and generates playlist.json for the island player.
Each card produces two entries (recall + shadow) with ordered segments:
  { text, audio, lang, role }

Recall sequence per card:
  EN question → ES question → EN sent 1 → ES sent 1 → EN sent 2 → ES sent 2 → ...

Shadow sequence per card:
  ES question → ES sent 1 → ES sent 2 → ...

Audio paths are relative to the spanish/ directory (one level up from code/).

Usage:
  python3 generate_playlist.py
"""

import json
import os
import re

INPUT_FILE  = "sentences.json"
OUTPUT_FILE = "../playlist.json"
TMP_DIR     = "code/audio/segments"   # relative to spanish/ (where player is served from)


def split_sentences(text):
    parts = re.split(r'(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÜÑA-Z])', text)
    return [p.strip() for p in parts if p.strip()]


def seg(text, audio, lang, role):
    return {"text": text, "audio": audio, "lang": lang, "role": role}


def tmp(filename):
    return f"{TMP_DIR}/{filename}"


def main():
    with open(INPUT_FILE, encoding="utf-8") as f:
        cards = json.load(f)

    playlist = []

    for card in cards:
        num = card["island_num"]
        slug = card["island_slug"]
        ctype = card["card_type"]
        cnum = card["card_num"]
        stem = f"island-{num:02d}-{slug}-{ctype}-{cnum}"

        en_sents = split_sentences(card["a_en"])
        es_sents = split_sentences(card["a_es"])

        label = f"{ctype.title()} {cnum}"
        island_name = slug.replace("-", " ").title()

        # ── Recall ──────────────────────────────────────────────────────────
        recall_segs = [
            seg(card["q_en"], tmp(f"{stem}-q-en.mp3"), "en", "question"),
            seg(card["q_es"], tmp(f"{stem}-q-es.mp3"), "es", "question"),
        ]
        for i, (en_s, es_s) in enumerate(zip(en_sents, es_sents), 1):
            recall_segs.append(seg(en_s, tmp(f"{stem}-a-en-s{i:02d}.mp3"), "en", "answer"))
            recall_segs.append(seg(es_s, tmp(f"{stem}-a-es-s{i:02d}.mp3"), "es", "answer"))

        playlist.append({
            "island": island_name,
            "card": label,
            "mode": "recall",
            "stem": stem,
            "segments": recall_segs,
        })

        # ── Shadow ──────────────────────────────────────────────────────────
        shadow_segs = [
            seg(card["q_es"], tmp(f"{stem}-q-es.mp3"), "es", "question"),
        ]
        for i, es_s in enumerate(es_sents, 1):
            shadow_segs.append(seg(es_s, tmp(f"{stem}-a-es-s{i:02d}.mp3"), "es", "answer"))

        playlist.append({
            "island": island_name,
            "card": label,
            "mode": "shadow",
            "stem": stem,
            "segments": shadow_segs,
        })

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(playlist, f, ensure_ascii=False, indent=2)

    card_count = len(cards)
    print(f"Written {len(playlist)} entries ({card_count} cards × 2 modes) to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
